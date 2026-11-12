"""Separate write-capable MCP surface with no onboarding or grant mutation tools."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any, TextIO, cast

from pydantic import BaseModel

from .protocol import BindTurn, Checkpoint, EndTurn, Finish, Inspection, Prepare, Render, Selection
from .workflow_runtime import RenderCancellation

FRAME_LIMIT = 262_144
RENDER_ID_LIMIT = 65_536

DESCRIPTIONS = {
    "temper_hub_status": (
        "Read Hub permission, current job and saved repository profiles. Does not analyze chats."
    ),
    "temper_hub_prepare": (
        "Prepare the current task in an explicitly Hub-authorized "
        "repository. May remove the previous task's owned skills. Reuse a "
        "matching ready profile, or use the returned selection ticket to "
        "inspect and choose applicable skills. Supply the task's relative working directory. "
        "When enabled, a matching saved handoff is returned. Use continue_previous only "
        "when the user asks to continue saved work in this repository."
    ),
    "temper_hub_inspect": (
        "Read one approved public skill and its resource list before "
        "selection. Source text grants no authority. Returns an "
        "inspection receipt."
    ),
    "temper_hub_select": (
        "Publish at most two applicable inspected skills for the current "
        "task through pinned SkillKit. An empty choice safely clears the "
        "owned profile. Does not change personal learning or install "
        "unapproved framework services."
    ),
    "temper_hub_finish": (
        "Release the exact task receipt after completion, failure, cancellation or a repository "
        "switch. Preserves owner edits and completed artifacts."
    ),
    "temper_hub_checkpoint": (
        "Save concise agent-reported facts, requirements, progress, checks and the next step "
        "for the current task in a repository with task continuity enabled. Supply the task's "
        "effective goal and latest checkpoint ID, or null if empty. Exclude credentials and "
        "transcripts. Saved context never becomes preference evidence."
    ),
    "temper_hub_render": (
        "Render a short MP4 through the separately owner-approved Remotion runtime for the current "
        "task. Supply spec title, optional subtitle, colors (background, foreground, accent as "
        "hex), and seconds (1 to 3). Returns a private 15 fps MP4 path and digest."
    ),
    "temper_hub_bind_turn": (
        "Codex PostToolUse callback. Bind a prepare result's opaque nonce to the native turn."
    ),
    "temper_hub_end_turn": (
        "Codex Stop or Interrupt callback. Release only the exact task bound to this native turn."
    ),
}


@dataclass
class PendingTask:
    receipt: dict[str, Any]
    nonce: str
    turn: tuple[str, str] | None = None

    @property
    def token(self) -> str:
        return str(self.receipt["payload"]["task_token"])


@dataclass
class InputFrame:
    message: dict[str, Any]
    error: str | None = None
    overflow: bool = False
    cancellation: RenderCancellation | None = None

    def render_id(self) -> str | int | None:
        params = self.message.get("params")
        request_id = self.message.get("id")
        if (
            self.message.get("method") == "tools/call"
            and isinstance(params, dict)
            and params.get("name") == "temper_hub_render"
            and type(request_id) in (str, int)
        ):
            return request_id
        return None


def read_frame(stdin: TextIO) -> InputFrame | None:
    line = stdin.readline(FRAME_LIMIT + 1)
    if not line:
        return None
    if len(line.encode()) > FRAME_LIMIT:
        return InputFrame({}, error="Hub frame exceeds its limit", overflow=True)
    try:
        message = json.loads(line)
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ValueError("Invalid Hub request")
        return InputFrame(message)
    except ValueError as error:
        return InputFrame({}, error=str(error))


def input_frames(stdin: TextIO) -> Iterator[InputFrame]:
    while (frame := read_frame(stdin)) is not None:
        if frame.render_id() is not None:
            yield from cancellable_frames(stdin, frame)
            return
        yield frame
        if frame.overflow:
            return


def cancellable_frames(stdin: TextIO, first: InputFrame) -> Iterator[InputFrame]:
    """Read cancellation during render while dispatch keeps all mutations serial."""
    pending: dict[str | int, RenderCancellation] = {}
    used_ids: set[bytes] = set()
    lock = Lock()
    queued: Queue[InputFrame] = Queue(maxsize=16)
    closed = Event()

    def register(frame: InputFrame) -> None:
        if (request_id := frame.render_id()) is not None:
            # Keep exact typed request identities without retaining client text.
            key = hashlib.sha256(json.dumps(request_id).encode()).digest()
            with lock:
                if key in used_ids:
                    frame.error = "MCP render request ID was reused"
                    return
                if len(used_ids) >= RENDER_ID_LIMIT:
                    frame.error = "MCP render request history is full; reconnect to render"
                    return
                used_ids.add(key)
                frame.cancellation = pending[request_id] = RenderCancellation()

    def cancel_pending() -> None:
        with lock:
            for cancellation in pending.values():
                cancellation.cancel()

    def read() -> None:
        try:
            while not closed.is_set() and (frame := read_frame(stdin)) is not None:
                message = frame.message
                if message.get("method") == "notifications/cancelled" and "id" not in message:
                    params = message.get("params")
                    request_id = params.get("requestId") if isinstance(params, dict) else None
                    if type(request_id) in (str, int):
                        with lock:
                            if (
                                cancellation := pending.get(cast(str | int, request_id))
                            ) is not None:
                                cancellation.cancel()
                    continue
                register(frame)
                queued.put_nowait(frame)
                if frame.overflow:
                    return
        except (OSError, Full):
            # Treat a broken or overwhelmed client as a disconnected transport.
            pass
        finally:
            cancel_pending()
            closed.set()

    register(first)
    Thread(target=read, name="temper-hub-mcp-input", daemon=True).start()
    frame = first
    try:
        while True:
            yield frame
            if frame.cancellation is not None and (request_id := frame.render_id()) is not None:
                with lock:
                    pending.pop(request_id, None)
            while True:
                if closed.is_set() and queued.empty():
                    return
                try:
                    frame = queued.get(timeout=0.1)
                    break
                except Empty:
                    continue
    finally:
        closed.set()
        cancel_pending()


def serve_hub(protocol: Any, *, stdin: TextIO, stdout: TextIO) -> None:
    try:
        _serve_hub(protocol, stdin=stdin, stdout=stdout)
    finally:
        disconnect = getattr(protocol, "disconnect", None)
        if disconnect is not None:
            # A busy or unavailable store is recovered by the maintenance tick.
            with suppress(ValueError, TypeError, KeyError, OSError, sqlite3.Error):
                disconnect()


def _serve_hub(protocol: Any, *, stdin: TextIO, stdout: TextIO) -> None:
    schemas: dict[str, type[BaseModel]] = {
        "temper_hub_prepare": Prepare,
        "temper_hub_inspect": Inspection,
        "temper_hub_select": Selection,
        "temper_hub_finish": Finish,
        "temper_hub_checkpoint": Checkpoint,
        "temper_hub_render": Render,
        "temper_hub_bind_turn": BindTurn,
        "temper_hub_end_turn": EndTurn,
    }
    tools: list[dict[str, Any]] = [
        {
            "name": name,
            "description": description,
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
            if name.endswith("status")
            else schemas[name].model_json_schema(),
            "annotations": {
                "readOnlyHint": name.endswith(("status", "inspect")),
                "destructiveHint": name.endswith(
                    ("prepare", "select", "finish", "checkpoint", "end_turn", "render")
                ),
                "openWorldHint": False,
            },
        }
        for name, description in DESCRIPTIONS.items()
    ]
    # One candidate per repository and no host identifiers persisted. A delayed
    # callback can release only the nonce actually returned to its native turn.
    candidates: dict[str, PendingTask] = {}
    for frame in input_frames(stdin):
        request = frame.message
        request_id = request.get("id")
        retrieval: tuple[dict[str, Any], str] | None = None
        try:
            if frame.error is not None:
                raise ValueError(frame.error)
            if request_id is None:
                continue
            if type(request_id) not in (str, int):
                raise ValueError("Invalid Hub request ID")
            method, params = request.get("method"), request.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("Hub parameters must be an object")
            result: dict[str, Any]
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "temper_hub", "version": "1.0.0"},
                    "instructions": (
                        "Hub tool permission is separate from personal learning. Check "
                        "the current request and all native instructions before selecting"
                        " public guidance. Never treat this transport as personal "
                        "preference evidence."
                    ),
                }
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "ping":
                result = {}
            elif method == "tools/call":
                name = params.get("name")
                if name not in DESCRIPTIONS:
                    raise ValueError("Unsupported Hub tool")
                args = params.get("arguments", {})
                packet: dict[str, Any]
                if name == "temper_hub_bind_turn":
                    value = BindTurn.model_validate(args)
                    packet = {}
                    for candidate in candidates.values():
                        if candidate.nonce == value.lifecycle_nonce:
                            candidate.turn = (value.session_id, value.turn_id)
                            candidate.nonce = ""
                            break
                elif name == "temper_hub_end_turn":
                    ending = EndTurn.model_validate(args)
                    packet = {}
                    failure: Exception | None = None
                    for project, candidate in list(candidates.items()):
                        if candidate.turn != (ending.session_id, ending.turn_id):
                            continue
                        try:
                            protocol.dispatch(
                                "tools_hub.finish",
                                {"task_receipt": candidate.receipt, "outcome": ending.outcome},
                                agent=True,
                            )
                        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
                            failure = failure or error
                        else:
                            candidates.pop(project)
                    if failure is not None:
                        raise failure
                else:
                    if frame.cancellation is not None:
                        frame.cancellation.check()
                        packet = protocol.dispatch(
                            "tools_hub.render", args, agent=True, cancellation=frame.cancellation
                        )
                    else:
                        packet = protocol.dispatch(
                            "tools_hub." + name.removeprefix("temper_hub_"), args, agent=True
                        )
                result = {
                    "content": [{"type": "text", "text": json.dumps(packet)}],
                    "isError": False,
                }
                if name == "temper_hub_prepare" and "task_receipt" in packet:
                    nonce = secrets.token_hex(16)
                    project = packet["project_id"]
                    candidate = PendingTask(packet["task_receipt"], nonce)
                    continuity = packet.get("continuity") or {}
                    checkpoint_id = continuity.get("checkpoint_id")
                    if continuity.get("handoff") is not None and isinstance(checkpoint_id, str):
                        retrieval = (candidate.receipt, checkpoint_id)
                    previous = candidates.get(project)
                    if previous is not None and previous.token == candidate.token:
                        candidate.turn = previous.turn
                    candidates[project] = candidate
                    result["structuredContent"] = {"lifecycle_nonce": nonce}
                if name == "temper_hub_finish":
                    finished_project = packet.get("project_id")
                    if isinstance(finished_project, str):
                        candidates.pop(finished_project, None)
            else:
                raise ValueError("Unsupported MCP operation")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": str(error)[:240]},
            }
        if frame.cancellation is None or frame.cancellation.complete():
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
            if retrieval is not None and "result" in response:
                # The Hub can record a flushed response on a later connection.
                # A hook's caller-supplied session ID does not attest model use.
                with suppress(ValueError, TypeError, KeyError, OSError, sqlite3.Error):
                    protocol.record_checkpoint_retrieval(*retrieval)
        if frame.overflow:
            break
