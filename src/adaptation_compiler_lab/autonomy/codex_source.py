"""Prospective completed-chat pickup under an explicit source-authority policy.

The existing Codex source transport supplies conversations, not human attribution. No
role, client ID, thread origin, hook label, or text classifier can admit a producer.
Strict mode excludes unknown input. A separately opted-in owner-trusted conversation
policy admits conversation requests while preserving unknown human authorship.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import Field

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodInteractionSource,
    CodexDogfoodSchemaSet,
    _resolved_runtime_path,
    _text_user_message,
)
from adaptation_compiler_lab.autonomy.models import InputOrigin, LearningGrantV1, StyleEpisodeV1
from adaptation_compiler_lab.autonomy.origin_receipts import (
    AdmittedOriginProducerV1,
    OriginReceiptV1,
    attribute_verified_input,
)
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.autonomy.worker import CapturePage
from adaptation_compiler_lab.connectors.codex_app_server import CodexAppServerProcess, RpcClient
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

SOURCE_CLIENT = "codex-interactive"

if TYPE_CHECKING:
    from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService


class ChatCheckpointV1(FrozenModel):
    task_digest: Sha256Digest
    item_count: int = Field(ge=0)
    prefix_digest: Sha256Digest
    completed_at: datetime


class HabitSourceCursorV1(FrozenModel):
    cursor_version: Literal["1.0.0"] = "1.0.0"
    grant_digest: Sha256Digest
    source_binding: Sha256Digest
    next_page: str | None = None
    checkpoints: tuple[ChatCheckpointV1, ...] = Field(default=(), max_length=4096)


class StoredOriginEvidence:
    """Read owner-signed producer admissions; there is deliberately no auto-admit API.

    A production input producer must first pass native human/automated controls and
    owner onboarding. Recording its admission is separate from connecting this reader.
    Existing chat records and fixture self-assertions never create such an admission.
    """

    def __init__(self, store: AutonomyStore, *, client_version: str, binary_digest: str) -> None:
        self.store = store
        self.client_version = client_version
        self.binary_digest = binary_digest

    def producers(self, grant: LearningGrantV1) -> dict[str, AdmittedOriginProducerV1]:
        result: dict[str, AdmittedOriginProducerV1] = {}
        for event in self.store.events():
            value = event["payload"]
            if event["type"] == "origin_producer_revoked":
                result.pop(value["producer_id"], None)
            elif event["type"] == "origin_producer_admitted":
                if value.get("grant_digest") != grant.content_digest:
                    continue
                producer = AdmittedOriginProducerV1.model_validate_json(
                    json.dumps(value["producer"]), strict=True
                )
                if (
                    producer.source_client == SOURCE_CLIENT
                    and producer.client_version == self.client_version
                    and producer.client_binary_digest == self.binary_digest
                    and producer.human_fixture_passed
                    and producer.automated_fixture_passed
                    and set(producer.project_ids) <= set(grant.project_ids)
                    and producer.project_ids
                ):
                    result[producer.producer_id] = producer
        return result

    def receipt(self, task_id: str, message_id: str) -> OriginReceiptV1 | None:
        receipts = [
            OriginReceiptV1.model_validate_json(json.dumps(event["payload"]), strict=True)
            for event in self.store.events()
            if event["type"] == "input_origin_receipt"
            and event["payload"].get("task_id") == task_id
            and event["payload"].get("message_id") == message_id
        ]
        if len(receipts) > 1:
            raise AutonomyIntegrityError("input has multiple origin receipts")
        return receipts[0] if receipts else None

    def verify_episode(self, episode: StyleEpisodeV1, grant: LearningGrantV1 | None) -> bool:
        if grant is None:
            return False
        producers = self.producers(grant)
        proof = next(
            (
                event["payload"]
                for event in self.store.events()
                if event["type"] == "source_episode_proof"
                and canonical_digest(event["payload"]) == episode.provenance_digest
            ),
            None,
        )
        if proof is None or proof["grant_digest"] != grant.content_digest:
            return False
        if proof["episode_digest"] != canonical_digest(
            episode.model_dump(mode="json", exclude={"provenance_digest"})
        ):
            return False
        if (
            proof["client_version"] != self.client_version
            or proof["binary_digest"] != self.binary_digest
        ):
            return False
        if proof.get("input_policy") == "owner_authorized_conversations":
            return (
                grant.input_policy == "owner_authorized_conversations"
                and episode.origin is InputOrigin.AUTHORIZED_CHAT
            )
        if episode.origin is not InputOrigin.HUMAN:
            return False
        # Revoking a producer immediately invalidates its outstanding evidence.
        return bool(proof["producer_digests"]) and all(
            producer_id in producers and canonical_digest(producers[producer_id]) == digest
            for producer_id, digest in proof["producer_digests"].items()
        )


class CodexHabitSource:
    def __init__(
        self,
        rpc: RpcClient,
        *,
        schemas: CodexDogfoodSchemaSet,
        projects: Mapping[str, tuple[Path, ...]],
        grant: LearningGrantV1,
        evidence: StoredOriginEvidence,
        source_binding: str,
        clock: Callable[[], datetime],
        project_cutoffs: Mapping[str, datetime] | None = None,
    ) -> None:
        self.rpc = rpc
        self.schemas = schemas
        self.projects = {
            key: tuple(root.resolve() for root in roots) for key, roots in projects.items()
        }
        self.project_cutoffs = dict(project_cutoffs or {})
        self.grant = grant
        self.evidence = evidence
        self.binding = source_binding
        self.clock = clock

    def poll(self, cutoff: datetime, previous: str | None) -> CapturePage:
        now = self.clock()
        if cutoff != self.grant.issued_at or SOURCE_CLIENT not in self.grant.source_clients:
            raise AutonomyIntegrityError("source pickup is outside its learning grant")
        cursor = (
            HabitSourceCursorV1.model_validate_json(previous, strict=True)
            if previous is not None
            else HabitSourceCursorV1(
                grant_digest=self.grant.content_digest, source_binding=self.binding
            )
        )
        if (
            cursor.grant_digest != self.grant.content_digest
            or cursor.source_binding != self.binding
        ):
            raise AutonomyIntegrityError("chat cursor belongs to another grant or native source")
        heads = {
            value.task_digest: value
            for value in cursor.checkpoints
            if value.completed_at > now - timedelta(days=30)
        }
        producers = self.evidence.producers(self.grant)
        owner_trusted = self.grant.input_policy == "owner_authorized_conversations"
        if not producers and not owner_trusted:
            raise AutonomyIntegrityError("native human input producer is not admitted")
        params: JsonObject = {
            "archived": False,
            "cursor": cursor.next_page,
            "limit": 20,
            "sortDirection": "desc",
            "sortKey": "updated_at",
            "sourceKinds": ["cli", "vscode", "appServer"],
            "useStateDbOnly": True,
        }
        self.schemas.validate("thread_list_params", params)
        page = self.rpc.request("thread/list", params)
        self.schemas.validate("thread_list_response", page)
        episodes: list[StyleEpisodeV1] = []
        for summary in cast(list[JsonObject], page["data"]):
            assert isinstance(summary, dict)
            project = self._eligible_project(summary, cutoff, now)
            if project is None:
                continue
            task_id = str(summary["id"])
            task_digest = canonical_digest({"task": task_id})
            read_params: JsonObject = {"threadId": task_id, "includeTurns": True}
            self.schemas.validate("thread_read_params", read_params)
            response = self.rpc.request("thread/read", read_params)
            self.schemas.validate("thread_read_response", response)
            thread = response["thread"]
            assert isinstance(thread, dict)
            # The task can move, restart, or change while the metadata is being read.
            if str(thread["id"]) != task_id:
                raise AutonomyIntegrityError("source returned another completed chat")
            if self._eligible_project(thread, cutoff, now) != project:
                continue
            items = CodexDogfoodInteractionSource._flatten_terminal_items(thread)
            turns = cast(list[dict[str, Any]], thread["turns"])
            if not turns or turns[-1]["status"] != "completed":
                continue
            # A rename or other thread-metadata update is not a completion date.
            completed_value = turns[-1].get("completedAt")
            if not isinstance(completed_value, int) or isinstance(completed_value, bool):
                continue
            completed = datetime.fromtimestamp(completed_value, UTC)
            created = datetime.fromtimestamp(cast(int, thread["createdAt"]), UTC)
            if not cutoff <= created <= completed <= now - timedelta(minutes=15):
                continue
            if completed <= now - timedelta(days=30):
                continue
            prior = heads.get(task_digest)
            if prior is not None:
                if prior.item_count > len(items) or prior.prefix_digest != canonical_digest(
                    {"items": items[: prior.item_count]}
                ):
                    raise AutonomyIntegrityError("completed chat prefix changed after pickup")
                # One conversation is at most one supporting episode, even if resumed.
                continue
            receipts: list[OriginReceiptV1] = []
            text_parts: list[str] = []
            message_ids: list[str] = []
            successful_turns = {turn["id"] for turn in turns if turn["status"] == "completed"}
            for turn_id, item in items:
                text = _text_user_message(item)
                if text is None or turn_id not in successful_turns:
                    continue
                message_id = str(item["id"])
                if owner_trusted:
                    # This is a request in an opted-in conversation, not human proof.
                    # Assistant outputs, tool results and native memory are not read here.
                    text_parts.append(text)
                    message_ids.append(message_id)
                    continue
                receipt = self.evidence.receipt(task_id, message_id)
                origin = attribute_verified_input(
                    receipt=receipt,
                    producers=producers,
                    source_client=SOURCE_CLIENT,
                    client_version=self.evidence.client_version,
                    binary_digest=self.evidence.binary_digest,
                    project_id=project,
                    task_id=task_id,
                    message_id=message_id,
                    text=text,
                )
                if origin is not InputOrigin.HUMAN or receipt is None:
                    continue
                if not created <= receipt.observed_at < completed + timedelta(seconds=1):
                    continue
                receipts.append(receipt)
                text_parts.append(text)
                message_ids.append(message_id)
            if not text_parts:
                # Do not checkpoint unknown input: a delayed valid receipt may arrive.
                continue
            joined = "\n\n".join(text_parts)
            if len(joined) > 32_768:
                # Never truncate a message into an apparently different preference.
                continue
            episode = StyleEpisodeV1(
                episode_id="codex-chat-" + str(task_digest)[7:],
                source_task_id=task_id,
                observation_ids=tuple(message_ids),
                project_id=project,
                source_client=SOURCE_CLIENT,
                origin=InputOrigin.AUTHORIZED_CHAT if owner_trusted else InputOrigin.HUMAN,
                created_at=created,
                completed_at=completed,
                text=joined,
            )
            proof = {
                "grant_digest": self.grant.content_digest,
                "source_binding": self.binding,
                "client_version": self.evidence.client_version,
                "binary_digest": self.evidence.binary_digest,
                "episode_digest": canonical_digest(
                    episode.model_dump(mode="json", exclude={"provenance_digest"})
                ),
                "receipt_digests": [canonical_digest(receipt) for receipt in receipts],
                "producer_digests": {
                    key: canonical_digest(producers[key])
                    for key in sorted({receipt.producer_id for receipt in receipts})
                },
            }
            if owner_trusted:
                proof["input_policy"] = "owner_authorized_conversations"
                proof["source_snapshot_digest"] = canonical_digest(thread)
            digest = canonical_digest(proof)
            self.evidence.store.append(
                "source-proof-" + str(digest)[7:], "source_episode_proof", proof, at=now
            )
            episodes.append(episode.model_copy(update={"provenance_digest": digest}))
            heads[task_digest] = ChatCheckpointV1(
                task_digest=task_digest,
                item_count=len(items),
                prefix_digest=canonical_digest({"items": items}),
                completed_at=completed,
            )
        next_cursor = HabitSourceCursorV1(
            grant_digest=self.grant.content_digest,
            source_binding=self.binding,
            next_page=cast(str | None, page["nextCursor"]),
            checkpoints=tuple(heads[key] for key in sorted(heads)),
        )
        if cursor.next_page is not None and next_cursor.next_page == cursor.next_page:
            raise AutonomyIntegrityError("native completed-chat cursor did not advance")
        return CapturePage(cursor=canonical_json(next_cursor), episodes=tuple(episodes))

    def _eligible_project(
        self, thread: Mapping[str, Any], cutoff: datetime, now: datetime
    ) -> str | None:
        if (
            thread["ephemeral"] is not False
            or thread["status"]["type"] not in {"idle", "notLoaded"}
            or thread["cliVersion"] != self.evidence.client_version
            or thread.get("forkedFromId") is not None
            or thread.get("parentThreadId") is not None
            or thread["source"] not in ("cli", "vscode", "appServer")
        ):
            return None
        created = datetime.fromtimestamp(thread["createdAt"], UTC)
        completed = datetime.fromtimestamp(thread["updatedAt"], UTC)
        if not cutoff <= created <= completed <= now - timedelta(minutes=15):
            return None
        if completed <= now - timedelta(days=30):
            return None
        path = _resolved_runtime_path(thread["cwd"])
        matches = [
            key
            for key, roots in self.projects.items()
            if key in self.grant.project_ids
            and any(path == root or path.is_relative_to(root) for root in roots)
            and created >= self.project_cutoffs.get(key, cutoff)
        ]
        if len(matches) > 1:
            raise AutonomyIntegrityError("completed chat matches overlapping registered projects")
        return matches[0] if matches else None


class ConfiguredCodexHabitSource:
    """Connect the installed source only after grant, credential and producer admission."""

    def __init__(self, config_path: Path, service: AutonomyApplicationService) -> None:
        self.config_path = config_path
        self.service = service

    def _evidence(self) -> StoredOriginEvidence:
        from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config
        from adaptation_compiler_lab.connectors.pins import load_dogfood_runtime_pins

        pin = load_dogfood_runtime_pins(_load_config(self.config_path).runtime_pin_path).codex
        return StoredOriginEvidence(
            self.service.store,
            client_version=pin.executable.package_version,
            binary_digest=pin.executable.executable_sha256,
        )

    def admitted(self) -> bool:
        from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config
        from adaptation_compiler_lab.connectors.pins import (
            RuntimeConformanceError,
            load_dogfood_runtime_pins,
            sha256_file,
        )

        grant = self.service.grant()
        if grant is None:
            return False
        try:
            config = _load_config(self.config_path)
            pin = load_dogfood_runtime_pins(config.runtime_pin_path).codex
            if sha256_file(config.codex_executable) != pin.executable.executable_sha256:
                return False
        except (OSError, ValueError, RuntimeConformanceError):
            return False
        return bool(
            grant
            and (
                grant.input_policy == "owner_authorized_conversations"
                or self._evidence().producers(grant)
            )
        )

    def verify_episode(self, episode: StyleEpisodeV1) -> bool:
        return self._evidence().verify_episode(episode, self.service.grant())

    def read_completed(self, cutoff: datetime, cursor: str | None) -> CapturePage:
        from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
            codex_dogfood_schemas,
            require_chatgpt_account,
        )
        from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config
        from adaptation_compiler_lab.connectors.pins import (
            load_dogfood_runtime_pins,
            verify_codex_runtime,
        )

        grant = self.service.grant()
        if (
            grant is None
            or not self.service.switch("learning")
            or not self.service.secure_store_available()
        ):
            raise AutonomyIntegrityError("completed-chat capture is paused")
        self.service.ensure_lease()
        evidence = self._evidence()
        if not evidence.producers(grant) and grant.input_policy != "owner_authorized_conversations":
            raise AutonomyIntegrityError("native human input producer is not admitted")
        config = _load_config(self.config_path)
        pin = load_dogfood_runtime_pins(config.runtime_pin_path).codex
        runtime = verify_codex_runtime(config.codex_executable, pin)
        schemas = codex_dogfood_schemas(pin)
        projects = {
            project.project_id: project.effective_source_roots for project in config.projects
        }
        binding = canonical_digest(
            {
                "binary": pin.executable.executable_sha256,
                "schemas": runtime.schema_bundle_digest,
                "home": str(config.source_codex_home.resolve()),
                "projects": {
                    key: [str(path.resolve()) for path in roots] for key, roots in projects.items()
                },
            }
        )
        with CodexAppServerProcess(
            runtime, codex_home=config.source_codex_home, schemas=schemas, experimental_api=True
        ) as rpc:
            require_chatgpt_account(rpc, schemas=schemas)
            source = CodexHabitSource(
                rpc,
                schemas=schemas,
                projects=projects,
                project_cutoffs={
                    project.project_id: datetime.fromtimestamp(
                        project.capture_after_epoch_seconds, UTC
                    )
                    for project in config.projects
                    if project.capture_after_epoch_seconds is not None
                },
                grant=grant,
                evidence=evidence,
                source_binding=binding,
                clock=self.service.clock,
            )
            page = source.poll(cutoff, cursor)
            if _load_config(self.config_path) != config or self.service.grant() != grant:
                raise AutonomyIntegrityError("learning scope changed during completed-chat pickup")
            return page
