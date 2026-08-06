"""Pinned multi-turn Codex transport for the writable governed gateway."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodRpc,
    CodexDogfoodSchemaSet,
    _resolved_runtime_path,
    require_chatgpt_account,
)
from adaptation_compiler_lab.connectors.codex_app_server import (
    CodexProtocolError,
    _object,
    _string,
)
from adaptation_compiler_lab.connectors.models import JsonObject


@dataclass(frozen=True, slots=True)
class GatewayTurnResult:
    turn_id: str
    status: str
    final_message: str


class CodexGatewayConversation:
    """One fresh fixed-policy Codex thread supporting at most fifteen bounded turns."""

    def __init__(
        self,
        rpc: CodexDogfoodRpc,
        *,
        schemas: CodexDogfoodSchemaSet,
        workspace: Path,
        rpc_workspace: str | None = None,
        model: str = "gpt-5.6-luna",
        reasoning_effort: str = "medium",
        maximum_turns: int = 15,
        turn_timeout_seconds: float = 600.0,
    ) -> None:
        if not 1 <= maximum_turns <= 15:
            raise ValueError("gateway turn limit must be between 1 and 15")
        if not 1 <= turn_timeout_seconds <= 600:
            raise ValueError("gateway turn timeout must be between 1 and 600 seconds")
        self._rpc = rpc
        self._schemas = schemas
        self._workspace = workspace.expanduser().resolve()
        self._rpc_workspace = rpc_workspace or str(self._workspace)
        self._model = model
        self._effort = reasoning_effort
        self._maximum_turns = maximum_turns
        self._timeout = turn_timeout_seconds
        self._thread_id: str | None = None
        self._turn_count = 0

    @property
    def thread_id(self) -> str:
        if self._thread_id is None:
            raise CodexProtocolError("gateway conversation has not started")
        return self._thread_id

    @property
    def turn_count(self) -> int:
        return self._turn_count

    def start(self) -> None:
        if self._thread_id is not None:
            raise CodexProtocolError("gateway conversation already started")
        if not self._workspace.is_dir():
            raise CodexProtocolError("gateway workspace is unavailable")
        require_chatgpt_account(self._rpc, schemas=self._schemas)
        params: JsonObject = {
            "approvalPolicy": "never",
            "cwd": self._rpc_workspace,
            "dynamicTools": [],
            "environments": [],
            "ephemeral": True,
            "model": self._model,
            "personality": "none",
            "runtimeWorkspaceRoots": [self._rpc_workspace],
            "sandbox": "workspace-write",
            "selectedCapabilityRoots": [],
            "threadSource": "adaptationCompilerLab",
        }
        self._schemas.validate("thread_start_params", params)
        response = self._rpc.request("thread/start", params)
        self._schemas.validate("thread_start_response", response)
        thread = _object(response.get("thread"), field="started thread")
        thread_id = _string(thread.get("id"), field="started thread id")
        if response.get("model") != self._model or response.get("approvalPolicy") != "never":
            raise CodexProtocolError("Codex changed the frozen gateway model or policy")
        if (
            _resolved_runtime_path(_string(response.get("cwd"), field="started cwd"))
            != self._workspace
        ):
            raise CodexProtocolError("Codex changed the gateway working directory")
        sandbox = _object(response.get("sandbox"), field="gateway sandbox")
        if (
            sandbox.get("type") != "workspaceWrite"
            or sandbox.get("networkAccess", False) is not False
        ):
            raise CodexProtocolError("Codex did not establish network-denied workspace-write")
        writable = sandbox.get("writableRoots")
        roots = response.get("runtimeWorkspaceRoots")
        if not isinstance(writable, list) or not isinstance(roots, list):
            raise CodexProtocolError("Codex returned invalid gateway workspace roots")
        for values in (writable, roots):
            if (
                len(values) != 1
                or _resolved_runtime_path(_string(values[0], field="gateway workspace root"))
                != self._workspace
            ):
                raise CodexProtocolError("Codex widened or changed the gateway workspace roots")
        sources = response.get("instructionSources", [])
        if not isinstance(sources, list):
            raise CodexProtocolError("Codex instruction sources must be an array")
        for raw in sources:
            source = _resolved_runtime_path(_string(raw, field="instruction source"))
            if source != self._workspace and not source.is_relative_to(self._workspace):
                raise CodexProtocolError("Codex loaded an instruction source outside the workspace")
        self._thread_id = thread_id

    def turn(self, message: str, *, client_message_id: str) -> GatewayTurnResult:
        if self._thread_id is None:
            raise CodexProtocolError("gateway conversation has not started")
        if self._turn_count >= self._maximum_turns:
            raise CodexProtocolError("gateway conversation reached its turn limit")
        text = message.strip()
        if not text:
            raise CodexProtocolError("gateway turn must not be empty")
        params: JsonObject = {
            "clientUserMessageId": client_message_id,
            "cwd": self._rpc_workspace,
            "effort": self._effort,
            "input": [{"type": "text", "text": text, "text_elements": []}],
            "model": self._model,
            "threadId": self._thread_id,
        }
        self._schemas.validate("turn_start_params", params)
        response = self._rpc.request("turn/start", params)
        self._schemas.validate("turn_start_response", response)
        turn = _object(response.get("turn"), field="started turn")
        turn_id = _string(turn.get("id"), field="started turn id")
        messages: list[str] = []
        deadline = monotonic() + self._timeout
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise CodexProtocolError("gateway turn timed out")
            notification = self._rpc.next_notification(timeout_seconds=min(remaining, 30.0))
            method = notification.get("method")
            notification_params = _object(notification.get("params"), field="notification params")
            if method == "item/completed":
                self._schemas.validate("item_completed", notification_params)
                self._assert_notification_ids(notification_params, turn_id=turn_id)
                item = _object(notification_params.get("item"), field="completed item")
                if item.get("type") == "agentMessage":
                    messages.append(_string(item.get("text"), field="agent message"))
            elif method == "turn/completed":
                self._schemas.validate("turn_completed", notification_params)
                if notification_params.get("threadId") != self._thread_id:
                    raise CodexProtocolError("completion crossed the gateway thread")
                completed = _object(notification_params.get("turn"), field="completed turn")
                if completed.get("id") != turn_id:
                    raise CodexProtocolError("completion crossed the gateway turn")
                self._turn_count += 1
                return GatewayTurnResult(
                    turn_id=turn_id,
                    status=_string(completed.get("status"), field="turn status"),
                    final_message="\n".join(messages).strip(),
                )

    def _assert_notification_ids(self, params: JsonObject, *, turn_id: str) -> None:
        if params.get("threadId") != self._thread_id or params.get("turnId") != turn_id:
            raise CodexProtocolError("item notification crossed the gateway turn")
