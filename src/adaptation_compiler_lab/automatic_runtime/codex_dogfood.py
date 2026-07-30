"""Pinned Codex pickup and next-session delivery for the local dogfood runtime."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import ClassVar, Final, Protocol

from pydantic import Field, field_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    InteractionObservation,
    PreparedRuntimeActivation,
    RuntimeTargetDeliveryAcknowledgement,
)
from adaptation_compiler_lab.connectors.codex_app_server import (
    CodexAppServerProcess,
    CodexProtocolError,
    CodexSchemaSet,
    RpcClient,
    _integer,
    _object,
    _string,
)
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import (
    CodexAppServerPin,
    VerifiedCodexRuntime,
    verify_codex_runtime,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    FrozenModel,
    Identifier,
    Scope,
    Sha256Digest,
    SourceClass,
    TaskRecordRef,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text

DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT: Final = (
    Path(__file__).resolve().parents[1] / "connectors" / "schema_snapshots" / "codex" / "0.146.0"
)
_INTERACTIVE_SOURCE_KINDS: Final = ("appServer", "cli", "vscode")
_TERMINAL_THREAD_STATUSES: Final = frozenset({"idle", "notLoaded"})


def _resolved_runtime_path(value: str) -> Path:
    """Resolve a Codex-returned path across native and WSL Windows interop."""

    candidate_value = value
    windows_drive = re.fullmatch(
        r"(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)",
        value,
    )
    if os.name != "nt" and windows_drive is not None:
        drive = windows_drive.group("drive").lower()
        rest = windows_drive.group("rest").replace("\\", "/")
        candidate_value = f"/mnt/{drive}/{rest}"
    return Path(candidate_value).expanduser().resolve()


class CodexDogfoodRpc(RpcClient, Protocol):
    """Request plus notification surface needed for a fresh target session."""

    def next_notification(self, *, timeout_seconds: float | None = None) -> JsonObject:
        """Return one app-server notification."""


class CodexDogfoodSchemaSet(CodexSchemaSet):
    """Version-generated schemas used by the product integration."""

    _FILES: ClassVar[dict[str, str]] = {
        "initialize_params": "v1/InitializeParams.json",
        "initialize_response": "v1/InitializeResponse.json",
        "account_params": "v2/GetAccountParams.json",
        "account_response": "v2/GetAccountResponse.json",
        "thread_list_params": "v2/ThreadListParams.json",
        "thread_list_response": "v2/ThreadListResponse.json",
        "thread_read_params": "v2/ThreadReadParams.json",
        "thread_read_response": "v2/ThreadReadResponse.json",
        "thread_start_params": "v2/ThreadStartParams.json",
        "thread_start_response": "v2/ThreadStartResponse.json",
        "turn_start_params": "v2/TurnStartParams.json",
        "turn_start_response": "v2/TurnStartResponse.json",
        "item_completed": "v2/ItemCompletedNotification.json",
        "turn_completed": "v2/TurnCompletedNotification.json",
    }

    def __init__(self, root: Path = DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT) -> None:
        super().__init__(root)


class CodexThreadHead(FrozenModel):
    """Raw-ID-free append-only prefix marker for one persisted Codex thread."""

    thread_id_digest: Sha256Digest
    item_count: int = Field(ge=0)
    prefix_digest: Sha256Digest


class CodexDogfoodCursor(FrozenModel):
    """Portable cursor containing only source pins and hashed thread prefixes."""

    cursor_version: str = "1.0.0"
    source_version: str
    source_schema_digest: Sha256Digest
    thread_heads: tuple[CodexThreadHead, ...] = ()

    @field_validator("thread_heads")
    @classmethod
    def heads_are_sorted_unique(
        cls, value: tuple[CodexThreadHead, ...]
    ) -> tuple[CodexThreadHead, ...]:
        digests = tuple(item.thread_id_digest for item in value)
        if digests != tuple(sorted(set(digests))):
            raise ValueError("Codex cursor thread heads must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)

    @property
    def value(self) -> str:
        return canonical_json(self)


@dataclass(frozen=True, slots=True)
class CodexProjectScope:
    """Explicit local path allowlist mapped to one governed adaptation scope."""

    root: Path
    scope: Scope

    def __post_init__(self) -> None:
        resolved = self.root.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"Codex dogfood project root is unavailable: {resolved}")
        if not self.scope.project_ids:
            raise ValueError("Codex dogfood project mapping requires one project scope")
        object.__setattr__(self, "root", resolved)

    def contains(self, cwd: str) -> bool:
        candidate = _resolved_runtime_path(cwd)
        return candidate == self.root or candidate.is_relative_to(self.root)


@dataclass(frozen=True, slots=True)
class CodexLearningWorkItem:
    """One trusted user-message observation plus its deterministic source position."""

    observation: InteractionObservation
    processed_at: datetime


@dataclass(frozen=True, slots=True)
class CodexLearningBatch:
    """One bounded pickup page and the cursor to commit after acknowledgement."""

    items: tuple[CodexLearningWorkItem, ...]
    cursor: CodexDogfoodCursor


@dataclass(frozen=True, slots=True)
class CodexLaunchResult:
    """Transient final message plus the raw-free acknowledgement safe for the ledger."""

    acknowledgement: RuntimeTargetDeliveryAcknowledgement
    final_message: str | None


def require_chatgpt_account(
    rpc: RpcClient,
    *,
    schemas: CodexDogfoodSchemaSet,
) -> None:
    """Fail closed unless the exact current app-server account is ChatGPT subscription auth."""

    params: JsonObject = {"refreshToken": False}
    schemas.validate("account_params", params)
    response = rpc.request("account/read", params)
    schemas.validate("account_response", response)
    account = response.get("account")
    if not isinstance(account, dict) or account.get("type") != "chatgpt":
        raise CodexProtocolError(
            "Codex dogfood requires saved ChatGPT authentication; API-key auth is refused"
        )


def _thread_digest(thread_id: str) -> Sha256Digest:
    return canonical_digest({"thread_id": thread_id})


def _prefix_digest(items: list[tuple[str, JsonObject]], count: int) -> Sha256Digest:
    return canonical_digest({"items": items[:count]})


def _text_user_message(item: JsonObject) -> str | None:
    if item.get("type") != "userMessage":
        return None
    content = item.get("content")
    if not isinstance(content, list) or not content:
        return None
    fragments: list[str] = []
    for raw_fragment in content:
        fragment = _object(raw_fragment, field="user-message content")
        if fragment.get("type") != "text":
            return None
        text = _string(fragment.get("text"), field="user-message text").strip()
        if text:
            fragments.append(text)
    joined = "\n".join(fragments).strip()
    return joined or None


class CodexDogfoodInteractionSource:
    """Read only new interactive Codex user messages through the pinned app server."""

    def __init__(
        self,
        rpc: RpcClient,
        *,
        subject_id: Identifier,
        source_version: str,
        source_schema_digest: Sha256Digest,
        schemas: CodexDogfoodSchemaSet,
        projects: tuple[CodexProjectScope, ...],
        capture_after_epoch_seconds: int,
        clock: Callable[[], datetime] | None = None,
        maximum_threads: int = 250,
    ) -> None:
        if not projects:
            raise ValueError("Codex dogfood source requires an explicit project allowlist")
        if capture_after_epoch_seconds < 0:
            raise ValueError("Codex dogfood construction cutoff must not be negative")
        if not 1 <= maximum_threads <= 1_000:
            raise ValueError("Codex dogfood maximum threads must be between 1 and 1000")
        self._rpc = rpc
        self._subject_id = subject_id
        self._source_version = source_version
        self._source_schema_digest = source_schema_digest
        self._schemas = schemas
        self._projects = projects
        self._capture_after = capture_after_epoch_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._maximum_threads = maximum_threads

    @property
    def source_id(self) -> str:
        return "codex-dogfood-interactive"

    def empty_cursor(self) -> CodexDogfoodCursor:
        return CodexDogfoodCursor(
            source_version=self._source_version,
            source_schema_digest=self._source_schema_digest,
        )

    def parse_cursor(self, value: str | None) -> CodexDogfoodCursor:
        if value is None:
            return self.empty_cursor()
        try:
            cursor = CodexDogfoodCursor.model_validate_json(value, strict=True)
        except ValueError as error:
            raise CodexProtocolError("Codex dogfood cursor is invalid") from error
        if (
            cursor.source_version != self._source_version
            or cursor.source_schema_digest != self._source_schema_digest
        ):
            raise CodexProtocolError("Codex dogfood cursor belongs to another source pin")
        return cursor

    def poll(self, *, after_cursor: str | None, limit: int = 25) -> CodexLearningBatch:
        if not 1 <= limit <= 100:
            raise ValueError("Codex dogfood pickup limit must be between 1 and 100")
        require_chatgpt_account(self._rpc, schemas=self._schemas)
        prior_cursor = self.parse_cursor(after_cursor)
        heads = {item.thread_id_digest: item for item in prior_cursor.thread_heads}
        polled_at = self._clock()
        if polled_at.tzinfo is None or polled_at.utcoffset() is None:
            raise CodexProtocolError("Codex dogfood clock must be timezone-aware")
        summaries = self._list_threads()
        work: list[CodexLearningWorkItem] = []

        for summary in summaries:
            if len(work) >= limit:
                break
            thread_id = _string(summary.get("id"), field="thread id")
            created_at = _integer(summary.get("createdAt"), field="thread createdAt")
            if created_at < self._capture_after:
                continue
            status = _object(summary.get("status"), field="thread status")
            if (
                status.get("type") not in _TERMINAL_THREAD_STATUSES
                or summary.get("ephemeral") is not False
            ):
                continue
            cwd = _string(summary.get("cwd"), field="thread cwd")
            project = next(
                (candidate for candidate in self._projects if candidate.contains(cwd)),
                None,
            )
            if project is None:
                continue
            thread = self._read_thread(thread_id)
            flattened = self._flatten_terminal_items(thread)
            digest = _thread_digest(thread_id)
            prior = heads.get(digest)
            consumed = 0 if prior is None else prior.item_count
            if consumed > len(flattened):
                raise CodexProtocolError("Codex thread history shrank after checkpoint")
            if prior is not None and prior.prefix_digest != _prefix_digest(flattened, consumed):
                raise CodexProtocolError("Codex thread prefix changed after checkpoint")

            index = consumed
            while index < len(flattened):
                turn_id, item = flattened[index]
                text = _text_user_message(item)
                index += 1
                if text is None:
                    continue
                item_id = _string(item.get("id"), field="user-message item id")
                observation_id = (
                    "codex-observation-"
                    + str(
                        canonical_digest(
                            {
                                "item_id": item_id,
                                "thread_id": thread_id,
                                "turn_id": turn_id,
                            }
                        )
                    ).removeprefix("sha256:")[:32]
                )
                observation = InteractionObservation(
                    observation_id=observation_id,
                    subject_id=self._subject_id,
                    task_ref=TaskRecordRef(
                        record_id=thread_id,
                        record_version="1.0.0",
                    ),
                    turn_id=turn_id,
                    actor=ActorRef(actor_id=self._subject_id, kind=ActorKind.USER),
                    source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
                    text=text,
                    scope=project.scope,
                    observed_at=polled_at,
                    source_system="codex_app_server",
                    source_version=self._source_version,
                    source_schema_digest=self._source_schema_digest,
                )
                work.append(
                    CodexLearningWorkItem(
                        observation=observation,
                        processed_at=polled_at,
                    )
                )
                if len(work) >= limit:
                    break
            heads[digest] = CodexThreadHead(
                thread_id_digest=digest,
                item_count=index,
                prefix_digest=_prefix_digest(flattened, index),
            )

        if len(heads) > self._maximum_threads:
            raise CodexProtocolError("Codex dogfood cursor exceeded its bounded thread ceiling")
        cursor = CodexDogfoodCursor(
            source_version=self._source_version,
            source_schema_digest=self._source_schema_digest,
            thread_heads=tuple(sorted(heads.values(), key=lambda item: item.thread_id_digest)),
        )
        return CodexLearningBatch(items=tuple(work), cursor=cursor)

    def _list_threads(self) -> tuple[JsonObject, ...]:
        cursor: str | None = None
        result: list[JsonObject] = []
        while True:
            params: JsonObject = {
                "archived": False,
                "cursor": cursor,
                "limit": min(100, self._maximum_threads - len(result) + 1),
                "sortDirection": "asc",
                "sortKey": "updated_at",
                "sourceKinds": list(_INTERACTIVE_SOURCE_KINDS),
                "useStateDbOnly": True,
            }
            self._schemas.validate("thread_list_params", params)
            response = self._rpc.request("thread/list", params)
            self._schemas.validate("thread_list_response", response)
            data = response.get("data")
            if not isinstance(data, list):
                raise CodexProtocolError("Codex thread/list data must be an array")
            result.extend(_object(item, field="thread") for item in data)
            if len(result) > self._maximum_threads:
                raise CodexProtocolError("Codex dogfood source exceeded its thread ceiling")
            next_cursor = response.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise CodexProtocolError("Codex thread/list cursor must be non-empty or null")
            cursor = next_cursor
        return tuple(result)

    def _read_thread(self, thread_id: str) -> JsonObject:
        params: JsonObject = {"threadId": thread_id, "includeTurns": True}
        self._schemas.validate("thread_read_params", params)
        response = self._rpc.request("thread/read", params)
        self._schemas.validate("thread_read_response", response)
        thread = _object(response.get("thread"), field="thread")
        if _string(thread.get("id"), field="thread id") != thread_id:
            raise CodexProtocolError("Codex thread/read returned another thread")
        return thread

    @staticmethod
    def _flatten_terminal_items(thread: JsonObject) -> list[tuple[str, JsonObject]]:
        turns = thread.get("turns")
        if not isinstance(turns, list):
            raise CodexProtocolError("Codex thread turns must be an array")
        flattened: list[tuple[str, JsonObject]] = []
        for raw_turn in turns:
            turn = _object(raw_turn, field="turn")
            if turn.get("status") not in {"completed", "failed", "interrupted"}:
                raise CodexProtocolError("Codex pickup encountered a non-terminal turn")
            if turn.get("itemsView", "full") != "full":
                raise CodexProtocolError("Codex pickup requires full persisted turn items")
            turn_id = _string(turn.get("id"), field="turn id")
            items = turn.get("items")
            if not isinstance(items, list):
                raise CodexProtocolError("Codex turn items must be an array")
            flattened.extend((turn_id, _object(item, field="turn item")) for item in items)
        return flattened


class CodexDogfoodSessionLauncher:
    """Launch one fresh Codex thread with exactly one prepared adaptation projection."""

    def __init__(
        self,
        rpc: CodexDogfoodRpc,
        *,
        schemas: CodexDogfoodSchemaSet,
        model: str = "gpt-5.6-luna",
        reasoning_effort: str = "medium",
        turn_timeout_seconds: float = 600.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not model.strip() or not reasoning_effort.strip():
            raise ValueError("Codex launcher model and reasoning effort must not be empty")
        if not 1 <= turn_timeout_seconds <= 1_800:
            raise ValueError("Codex launcher timeout must be between 1 and 1800 seconds")
        self._rpc = rpc
        self._schemas = schemas
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._timeout = turn_timeout_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def launch(
        self,
        prepared: PreparedRuntimeActivation,
        *,
        workspace: Path,
        ephemeral: bool = False,
    ) -> CodexLaunchResult:
        """Start one bounded fresh thread and return only raw-free durable evidence."""

        root = workspace.expanduser().resolve()
        if not root.is_dir():
            raise CodexProtocolError("Codex target workspace is unavailable")
        thread_id: str | None = None
        turn_id: str | None = None
        try:
            require_chatgpt_account(self._rpc, schemas=self._schemas)
            thread_params: JsonObject = {
                "approvalPolicy": "never",
                "cwd": str(root),
                "dynamicTools": [],
                "environments": [],
                "ephemeral": ephemeral,
                "model": self._model,
                "personality": "none",
                "runtimeWorkspaceRoots": [str(root)],
                "sandbox": "workspace-write",
                "selectedCapabilityRoots": [],
                "threadSource": "adaptationCompilerLab",
            }
            self._schemas.validate("thread_start_params", thread_params)
            thread_response = self._rpc.request("thread/start", thread_params)
            self._schemas.validate("thread_start_response", thread_response)
            thread = _object(thread_response.get("thread"), field="started thread")
            thread_id = _string(thread.get("id"), field="started thread id")
            if thread_response.get("model") != self._model:
                raise CodexProtocolError("Codex substituted another target model")
            if thread_response.get("approvalPolicy") != "never":
                raise CodexProtocolError("Codex changed the target approval policy")
            if (
                _resolved_runtime_path(_string(thread_response.get("cwd"), field="started cwd"))
                != root
            ):
                raise CodexProtocolError("Codex changed the target working directory")
            runtime_roots = thread_response.get("runtimeWorkspaceRoots", [])
            if not isinstance(runtime_roots, list) or len(runtime_roots) != 1:
                raise CodexProtocolError("Codex changed the target runtime workspace roots")
            if (
                _resolved_runtime_path(_string(runtime_roots[0], field="runtime workspace root"))
                != root
            ):
                raise CodexProtocolError("Codex changed the target runtime workspace roots")
            sandbox = _object(thread_response.get("sandbox"), field="target sandbox")
            if (
                sandbox.get("type") != "workspaceWrite"
                or sandbox.get("networkAccess", False) is not False
            ):
                raise CodexProtocolError(
                    "Codex did not establish the required network-denied workspace sandbox"
                )
            writable_roots = sandbox.get("writableRoots", [])
            if not isinstance(writable_roots, list) or len(writable_roots) != 1:
                raise CodexProtocolError("Codex changed the sandbox writable roots")
            if (
                _resolved_runtime_path(_string(writable_roots[0], field="sandbox writable root"))
                != root
            ):
                raise CodexProtocolError("Codex changed the sandbox writable roots")
            instruction_sources = thread_response.get("instructionSources", [])
            if not isinstance(instruction_sources, list):
                raise CodexProtocolError("Codex instruction sources must be an array")
            for source in instruction_sources:
                path = _resolved_runtime_path(_string(source, field="instruction source"))
                if path != root and not path.is_relative_to(root):
                    raise CodexProtocolError(
                        "Codex loaded an instruction source outside the target workspace"
                    )

            turn_params: JsonObject = {
                "clientUserMessageId": prepared.activation.activation_id,
                "cwd": str(root),
                "effort": self._reasoning_effort,
                "input": [
                    {
                        "type": "text",
                        "text": prepared.task.delivered_task,
                        "text_elements": [],
                    }
                ],
                "model": self._model,
                "threadId": thread_id,
            }
            self._schemas.validate("turn_start_params", turn_params)
            turn_response = self._rpc.request("turn/start", turn_params)
            self._schemas.validate("turn_start_response", turn_response)
            turn = _object(turn_response.get("turn"), field="started turn")
            turn_id = _string(turn.get("id"), field="started turn id")
            final_messages: list[str] = []
            deadline = monotonic() + self._timeout
            terminal: JsonObject | None = None
            while terminal is None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise CodexProtocolError("Codex target turn timed out")
                notification = self._rpc.next_notification(timeout_seconds=min(remaining, 30.0))
                method = notification.get("method")
                params = _object(notification.get("params"), field="notification params")
                if method == "item/completed":
                    self._schemas.validate("item_completed", params)
                    if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
                        raise CodexProtocolError("Codex item notification crossed the target turn")
                    item = _object(params.get("item"), field="completed item")
                    if item.get("type") == "agentMessage":
                        final_messages.append(_string(item.get("text"), field="agent message"))
                elif method == "turn/completed":
                    self._schemas.validate("turn_completed", params)
                    if params.get("threadId") != thread_id:
                        raise CodexProtocolError("Codex completion crossed the target thread")
                    completed_turn = _object(params.get("turn"), field="completed turn")
                    if completed_turn.get("id") != turn_id:
                        raise CodexProtocolError("Codex completion crossed the target turn")
                    terminal = completed_turn
            status = terminal.get("status")
            if status != "completed":
                return self._failed(
                    prepared,
                    failure_class=f"turn_{status}",
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
            final_message = "\n".join(final_messages).strip()
            result_digest = canonical_digest(
                {
                    "final_message": final_message,
                    "status": status,
                }
            )
            acknowledgement = RuntimeTargetDeliveryAcknowledgement(
                acknowledgement_id=f"target-ack-{prepared.activation.activation_id}",
                activation_id=prepared.activation.activation_id,
                subject_id=prepared.activation.subject_id,
                target_family="codex",
                activation_digest=prepared.activation.content_digest,
                external_session_digest=sha256_text(thread_id),
                external_turn_digest=sha256_text(turn_id),
                result_digest=result_digest,
                status="completed",
                acknowledged_at=self._clock(),
            )
            return CodexLaunchResult(
                acknowledgement=acknowledgement,
                final_message=final_message,
            )
        except (CodexProtocolError, ValueError) as error:
            return self._failed(
                prepared,
                failure_class=type(error).__name__,
                thread_id=thread_id,
                turn_id=turn_id,
            )

    def _failed(
        self,
        prepared: PreparedRuntimeActivation,
        *,
        failure_class: str,
        thread_id: str | None,
        turn_id: str | None,
    ) -> CodexLaunchResult:
        acknowledgement = RuntimeTargetDeliveryAcknowledgement(
            acknowledgement_id=f"target-ack-{prepared.activation.activation_id}",
            activation_id=prepared.activation.activation_id,
            subject_id=prepared.activation.subject_id,
            target_family="codex",
            activation_digest=prepared.activation.content_digest,
            external_session_digest=(None if thread_id is None else sha256_text(thread_id)),
            external_turn_digest=None if turn_id is None else sha256_text(turn_id),
            status="failed",
            failure_class=failure_class,
            acknowledged_at=self._clock(),
        )
        return CodexLaunchResult(
            acknowledgement=acknowledgement,
            final_message=None,
        )


@contextmanager
def open_codex_dogfood(
    *,
    executable: Path,
    codex_home: Path,
    pin: CodexAppServerPin,
    schema_root: Path = DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT,
    windows_interop: bool = False,
) -> Iterator[tuple[VerifiedCodexRuntime, CodexDogfoodSchemaSet, CodexAppServerProcess]]:
    """Verify, authenticate, and expose one pinned local Codex app-server connection."""

    runtime = verify_codex_runtime(
        executable,
        pin,
        windows_interop=windows_interop,
    )
    schemas = CodexDogfoodSchemaSet(schema_root)
    with CodexAppServerProcess(
        runtime,
        codex_home=codex_home,
        schemas=schemas,
    ) as rpc:
        require_chatgpt_account(rpc, schemas=schemas)
        yield runtime, schemas, rpc
