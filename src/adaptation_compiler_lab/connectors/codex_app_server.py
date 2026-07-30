"""Pinned Codex app-server source connector.

This adapter speaks the documented app-server protocol over stdio. It never opens, searches, or
parses Codex rollout/session files itself.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from types import TracebackType
from typing import ClassVar, Final, Literal, Protocol, cast

from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError, ValidationError

from adaptation_compiler_lab.connectors.models import (
    JsonObject,
    JsonValue,
    SourceTaskPage,
    SourceTaskSnapshot,
    SourceTaskSummary,
    SourceTurnDescriptor,
    TerminalTurnStatus,
)
from adaptation_compiler_lab.connectors.pins import (
    CodexAppServerPin,
    RuntimeConformanceError,
    VerifiedCodexRuntime,
    _as_windows_interop_path,
    sha256_bytes,
    verify_codex_runtime,
)
from adaptation_compiler_lab.domain.base import Sha256Digest
from adaptation_compiler_lab.serialization.canonical import canonical_bytes, canonical_digest

DEFAULT_CODEX_SCHEMA_ROOT: Final = (
    Path(__file__).resolve().parent / "schema_snapshots" / "codex" / "0.145.0"
)
DEFAULT_CODEX_DESKTOP_SCHEMA_ROOT: Final = (
    Path(__file__).resolve().parent / "schema_snapshots" / "codex" / "0.145.0-alpha.30"
)
_TERMINAL_TURN_STATUSES: Final = frozenset(item.value for item in TerminalTurnStatus)
_EOF: Final = object()


class RpcClient(Protocol):
    """Minimal synchronous request surface used by the source adapter."""

    def request(self, method: str, params: JsonObject) -> JsonObject:
        """Issue one request and return its result object."""


class CodexProtocolError(RuntimeConformanceError):
    """The app server violated the pinned source protocol."""


class CodexSchemaSet:
    """Exact generated request/response validators used by the connector."""

    _FILES: ClassVar[dict[str, str]] = {
        "initialize_params": "v1/InitializeParams.json",
        "initialize_response": "v1/InitializeResponse.json",
        "thread_list_params": "v2/ThreadListParams.json",
        "thread_list_response": "v2/ThreadListResponse.json",
        "thread_read_params": "v2/ThreadReadParams.json",
        "thread_read_response": "v2/ThreadReadResponse.json",
    }

    def __init__(self, root: Path = DEFAULT_CODEX_SCHEMA_ROOT) -> None:
        self._validators: dict[str, Draft7Validator] = {}
        for key, relative in self._FILES.items():
            path = root / relative
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(schema, dict):
                    raise TypeError("schema root must be an object")
                Draft7Validator.check_schema(schema)
                self._validators[key] = Draft7Validator(schema)
            except (OSError, ValueError, TypeError, SchemaError) as exc:
                raise CodexProtocolError(
                    f"invalid pinned Codex schema snapshot: {relative}"
                ) from exc

    def validate(self, name: str, payload: JsonObject) -> None:
        try:
            validator = self._validators[name]
        except KeyError as exc:
            raise CodexProtocolError(f"unknown Codex schema validator: {name}") from exc
        try:
            validator.validate(payload)
        except ValidationError as exc:
            raise CodexProtocolError(
                f"Codex payload violates pinned {name} schema at {list(exc.absolute_path)!r}"
            ) from exc


class CodexAppServerProcess:
    """One initialized stdio app-server process with bounded synchronous requests."""

    def __init__(
        self,
        runtime: VerifiedCodexRuntime,
        *,
        codex_home: Path,
        schemas: CodexSchemaSet,
        request_timeout_seconds: float = 30.0,
        experimental_api: bool = False,
    ) -> None:
        resolved_home = codex_home.expanduser().resolve()
        if not resolved_home.is_dir():
            raise CodexProtocolError("explicit CODEX_HOME is unavailable")
        self._runtime = runtime
        self._codex_home = resolved_home
        self._schemas = schemas
        self._request_timeout_seconds = request_timeout_seconds
        self._experimental_api = experimental_api
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[JsonObject | object] = queue.Queue()
        self._reader_error: BaseException | None = None
        self._stderr_chunks: list[str] = []
        self._pending_notifications: deque[JsonObject] = deque()
        self._request_id = 0
        self._write_lock = threading.Lock()

    def __enter__(self) -> CodexAppServerProcess:
        environment = os.environ.copy()
        environment["CODEX_HOME"] = (
            _as_windows_interop_path(self._codex_home)
            if self._runtime.windows_interop
            else str(self._codex_home)
        )
        environment["CODEX_ANALYTICS_ENABLED"] = "false"
        environment.pop("CODEX_API_KEY", None)
        environment.pop("CODEX_ACCESS_TOKEN", None)
        environment.pop("OPENAI_API_KEY", None)
        environment.pop("OPENAI_ACCESS_TOKEN", None)
        try:
            process = subprocess.Popen(
                [
                    str(self._runtime.executable),
                    "app-server",
                    "--stdio",
                    "--strict-config",
                    "-c",
                    "analytics.enabled=false",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                bufsize=1,
                env=environment,
                start_new_session=True,
            )
        except OSError as exc:
            raise CodexProtocolError("unable to start pinned Codex app server") from exc
        self._process = process
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            initialize: JsonObject = {
                "clientInfo": {
                    "name": "adaptation-compiler-lab",
                    "title": "Adaptation Compiler Lab",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": self._experimental_api},
            }
            self._schemas.validate("initialize_params", initialize)
            response = self.request("initialize", initialize)
            self._schemas.validate("initialize_response", response)
            self.notify("initialized", {})
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                if not line.strip():
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict) or not all(
                    isinstance(key, str) for key in payload
                ):
                    raise CodexProtocolError("Codex app-server message must be a JSON object")
                self._messages.put(cast(JsonObject, payload))
        except BaseException as exc:  # transported to the synchronous caller
            self._reader_error = exc
        finally:
            self._messages.put(_EOF)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        stderr = process.stderr
        for chunk in iter(lambda: stderr.read(4096), ""):
            if not chunk:
                break
            if sum(len(item) for item in self._stderr_chunks) < 16_384:
                self._stderr_chunks.append(chunk)

    def _write(self, payload: JsonObject) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise CodexProtocolError("Codex app server is not running")
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        with self._write_lock:
            try:
                process.stdin.write(encoded + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError, UnicodeError) as exc:
                raise CodexProtocolError("failed to write to Codex app server") from exc

    def notify(self, method: str, params: JsonObject) -> None:
        self._write({"method": method, "params": params})

    def request(self, method: str, params: JsonObject) -> JsonObject:
        self._request_id += 1
        request_id = self._request_id
        self._write({"id": request_id, "method": method, "params": params})
        while True:
            try:
                message = self._messages.get(timeout=self._request_timeout_seconds)
            except queue.Empty as exc:
                raise CodexProtocolError(f"Codex app-server request timed out: {method}") from exc
            if message is _EOF:
                if self._reader_error is not None:
                    raise CodexProtocolError("Codex app-server output reader failed") from (
                        self._reader_error
                    )
                diagnostic = "".join(self._stderr_chunks).strip()[:500]
                raise CodexProtocolError(f"Codex app server closed before responding: {diagnostic}")
            payload = cast(JsonObject, message)
            response_id = payload.get("id")
            if response_id is None:
                self._pending_notifications.append(payload)
                continue
            if response_id != request_id:
                raise CodexProtocolError("Codex app server returned an unexpected response ID")
            if "error" in payload:
                error = payload.get("error")
                code: object = None
                error_message: object = None
                if isinstance(error, dict):
                    code = error.get("code")
                    error_message = error.get("message")
                safe_code = code if isinstance(code, int | str) else "unknown"
                safe_message = (
                    "unspecified"
                    if not isinstance(error_message, str)
                    else " ".join(error_message.split())[:240]
                )
                raise CodexProtocolError(
                    f"Codex app server returned RPC error {safe_code}: {safe_message}"
                )
            result = payload.get("result")
            if not isinstance(result, dict) or not all(isinstance(key, str) for key in result):
                raise CodexProtocolError("Codex app-server result must be a JSON object")
            return result

    def next_notification(self, *, timeout_seconds: float | None = None) -> JsonObject:
        """Return the next notification while refusing unhandled server requests."""

        timeout = self._request_timeout_seconds if timeout_seconds is None else timeout_seconds
        if timeout <= 0:
            raise ValueError("notification timeout must be positive")
        if self._pending_notifications:
            return self._pending_notifications.popleft()
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise CodexProtocolError("Codex app-server notification timed out") from exc
        if message is _EOF:
            if self._reader_error is not None:
                raise CodexProtocolError("Codex app-server output reader failed") from (
                    self._reader_error
                )
            diagnostic = "".join(self._stderr_chunks).strip()[:500]
            raise CodexProtocolError(f"Codex app server closed before notification: {diagnostic}")
        payload = cast(JsonObject, message)
        if payload.get("id") is not None:
            raise CodexProtocolError("unhandled Codex server request or out-of-order response")
        method = payload.get("method")
        params = payload.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            raise CodexProtocolError("Codex notification must contain method and object params")
        return payload

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        if process.stdin is not None:
            with suppress(OSError):
                process.stdin.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        self._process = None


def _object(value: JsonValue | object, *, field: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CodexProtocolError(f"Codex {field} must be an object")
    return cast(JsonObject, value)


def _string(value: JsonValue | object, *, field: str) -> str:
    if not isinstance(value, str):
        raise CodexProtocolError(f"Codex {field} must be a string")
    return value


def _integer(value: JsonValue | object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CodexProtocolError(f"Codex {field} must be an integer")
    return value


class CodexSourceConnector:
    """SourceConnector backed only by pinned `thread/list` and `thread/read` calls."""

    def __init__(
        self,
        rpc: RpcClient,
        *,
        source_version: str,
        source_schema_digest: Sha256Digest,
        schemas: CodexSchemaSet,
    ) -> None:
        self._rpc = rpc
        self._source_version = source_version
        self._source_schema_digest = source_schema_digest
        self._schemas = schemas

    @property
    def source_version(self) -> str:
        return self._source_version

    @property
    def source_schema_digest(self) -> Sha256Digest:
        return self._source_schema_digest

    def list_completed_tasks(
        self,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> SourceTaskPage:
        if limit < 1 or limit > 1000:
            raise ValueError("source list limit must be between 1 and 1000")
        params: JsonObject = {
            "archived": False,
            "cursor": cursor,
            "limit": limit,
            "sortDirection": "desc",
            "sortKey": "updated_at",
            "useStateDbOnly": True,
        }
        self._schemas.validate("thread_list_params", params)
        response = self._rpc.request("thread/list", params)
        self._schemas.validate("thread_list_response", response)
        data = response.get("data")
        if not isinstance(data, list):
            raise CodexProtocolError("Codex thread/list data must be an array")
        summaries: list[SourceTaskSummary] = []
        for raw_thread in data:
            thread = _object(raw_thread, field="thread")
            status = _object(thread.get("status"), field="thread status")
            status_type = _string(status.get("type"), field="thread status type")
            if status_type not in {"idle", "notLoaded"} or thread.get("ephemeral") is not False:
                continue
            name = thread.get("name")
            display_name = name.strip() if isinstance(name, str) and name.strip() else None
            source = thread.get("source")
            cwd = _string(thread.get("cwd"), field="thread cwd")
            summaries.append(
                SourceTaskSummary(
                    task_id=_string(thread.get("id"), field="thread id"),
                    created_at_epoch_seconds=_integer(
                        thread.get("createdAt"),
                        field="thread createdAt",
                    ),
                    updated_at_epoch_seconds=_integer(
                        thread.get("updatedAt"),
                        field="thread updatedAt",
                    ),
                    cli_version=_string(thread.get("cliVersion"), field="thread cliVersion"),
                    status=cast(Literal["idle", "notLoaded"], status_type),
                    source_digest=canonical_digest({"source": source}),
                    cwd_digest=canonical_digest({"cwd": cwd}),
                    display_name=display_name,
                )
            )
        next_cursor = response.get("nextCursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise CodexProtocolError("Codex nextCursor must be a string or null")
        return SourceTaskPage(tasks=tuple(summaries), next_cursor=next_cursor)

    def read_completed_task(self, task_id: str) -> SourceTaskSnapshot:
        params: JsonObject = {"threadId": task_id, "includeTurns": True}
        self._schemas.validate("thread_read_params", params)
        response = self._rpc.request("thread/read", params)
        self._schemas.validate("thread_read_response", response)
        thread = _object(response.get("thread"), field="thread")
        returned_id = _string(thread.get("id"), field="thread id")
        if returned_id != task_id:
            raise CodexProtocolError("Codex thread/read returned a different task ID")
        status = _object(thread.get("status"), field="thread status")
        if status.get("type") not in {"idle", "notLoaded"}:
            raise CodexProtocolError("source task is still active")
        raw_turns = thread.get("turns")
        if not isinstance(raw_turns, list) or not raw_turns:
            raise CodexProtocolError("source task has no persisted turns")
        turns: list[SourceTurnDescriptor] = []
        for raw_turn in raw_turns:
            turn = _object(raw_turn, field="turn")
            status_value = _string(turn.get("status"), field="turn status")
            if status_value not in _TERMINAL_TURN_STATUSES:
                raise CodexProtocolError("source task contains a non-terminal turn")
            items_view = turn.get("itemsView", "full")
            if items_view != "full":
                raise CodexProtocolError("source task did not return full persisted turn items")
            items = turn.get("items")
            if not isinstance(items, list):
                raise CodexProtocolError("Codex turn items must be an array")
            turns.append(
                SourceTurnDescriptor(
                    turn_id=_string(turn.get("id"), field="turn id"),
                    status=TerminalTurnStatus(status_value),
                    item_count=len(items),
                )
            )
        raw_payload = canonical_bytes(thread)
        return SourceTaskSnapshot(
            task_id=returned_id,
            source_version=self._source_version,
            source_schema_digest=self._source_schema_digest,
            raw_payload=raw_payload,
            payload_digest=sha256_bytes(raw_payload),
            turns=tuple(turns),
        )


@contextmanager
def open_codex_source_connector(
    *,
    executable: Path,
    codex_home: Path,
    pin: CodexAppServerPin,
    schema_root: Path = DEFAULT_CODEX_SCHEMA_ROOT,
    windows_interop: bool = False,
) -> Iterator[CodexSourceConnector]:
    """Verify, start, initialize, and tear down one pinned source connection."""

    runtime = verify_codex_runtime(
        executable,
        pin,
        windows_interop=windows_interop,
    )
    schemas = CodexSchemaSet(schema_root)
    with CodexAppServerProcess(
        runtime,
        codex_home=codex_home,
        schemas=schemas,
    ) as rpc:
        yield CodexSourceConnector(
            rpc,
            source_version=runtime.version,
            source_schema_digest=runtime.schema_bundle_digest,
            schemas=schemas,
        )
