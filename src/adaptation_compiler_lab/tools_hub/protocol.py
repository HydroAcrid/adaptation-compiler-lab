"""Closed desktop and connected-agent operations; no arbitrary command/path dispatch."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .connection import CodexHubConnection
from .controller import fingerprint
from .service import HubService


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Parameters):
    pass


class PermissionPreview(Parameters):
    project_ids: list[str] = Field(min_length=1, max_length=100)
    source_ids: list[str] = Field(min_length=1, max_length=3)


class PreviewId(Parameters):
    preview_id: str = Field(min_length=1, max_length=64)


class Control(Parameters):
    operation: Literal["pause", "resume", "stop", "rollback"]
    project_id: str | None = Field(default=None, max_length=160)


class Task(Parameters):
    project_id: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1, max_length=2000)
    task_class: Literal["implementation", "debugging", "review", "documentation", "planning"]
    relative_directory: str = Field(default=".", min_length=1, max_length=512)


class Selection(Task):
    selection_ticket: dict[str, Any]
    choices: list[str] = Field(max_length=2)
    inspections: list[dict[str, Any]] = Field(max_length=3)


class Inspection(Parameters):
    selection_ticket: dict[str, Any]
    skill_id: str = Field(min_length=1, max_length=240)


SCHEMAS: dict[str, type[Parameters]] = {
    "tools_hub.status": Empty,
    "tools_hub.inventory": Empty,
    "tools_hub.maintenance": Empty,
    "tools_hub.permission.preview": PermissionPreview,
    "tools_hub.permission.enable": PreviewId,
    "tools_hub.control": Control,
    "tools_hub.prepare": Task,
    "tools_hub.inspect": Inspection,
    "tools_hub.select": Selection,
    "tools_hub.connection.preview": Empty,
    "tools_hub.connection.apply": PreviewId,
    "tools_hub.refresh": Empty,
    "tools_hub.repair": Empty,
}
AGENT_METHODS = {"tools_hub.status", "tools_hub.prepare", "tools_hub.inspect", "tools_hub.select"}


class HubProtocol:
    def __init__(self, service: HubService, *, config_path: Any = None) -> None:
        self.service, self.config_path = service, config_path
        self.replays: dict[str, tuple[str, dict[str, Any]]] = {}

    def dispatch(
        self,
        method: str,
        params: dict[str, Any],
        *,
        expected_digest: str | None = None,
        idempotency_key: str | None = None,
        agent: bool = False,
    ) -> dict[str, Any]:
        if method not in SCHEMAS or (agent and method not in AGENT_METHODS):
            raise ValueError("Unsupported repository setup operation")
        value = SCHEMAS[method].model_validate(params)
        request_digest = fingerprint({"method": method, "params": params})
        if idempotency_key in self.replays:
            before, result = self.replays[idempotency_key]
            if before != request_digest:
                raise ValueError("Idempotency key was reused for a different operation")
            return result
        if method == "tools_hub.status":
            return self.service.state()
        if method == "tools_hub.inventory":
            return {"projects": self.service.inventory()}
        if method == "tools_hub.maintenance":
            return self.service.tick()
        if method not in AGENT_METHODS and (
            not idempotency_key
            or len(idempotency_key) > 160
            or expected_digest != self.service.state()["digest"]
        ):
            raise ValueError("Repository setup changed; refresh before trying again")
        if isinstance(value, PermissionPreview):
            result = self.service.preview(value.project_ids, value.source_ids)
        elif method == "tools_hub.permission.enable" and isinstance(value, PreviewId):
            result = self.service.enable(value.preview_id)
        elif isinstance(value, Control):
            result = self.service.control(value.operation, value.project_id)
        elif method == "tools_hub.refresh":
            result = self.service.start("maintenance", lambda: self.service.maintain(force=True))
        elif method == "tools_hub.repair":
            result = self.service.start("repair", self.service.repair)
        elif isinstance(value, Selection):

            def select_task() -> dict[str, Any]:
                return self.service.select(
                    value.selection_ticket,
                    value.project_id,
                    value.goal,
                    value.task_class,
                    value.choices,
                    value.inspections,
                    value.relative_directory,
                )

            if agent:
                # MCP has its own process; awaiting a bounded native operation
                # here does not occupy the desktop IPC worker or require a
                # second polling conversation to retrieve a selection ticket.
                result = self.service.agent_work(value.project_id, "selection", select_task)
            else:
                result = self.service.start("selection", select_task)
        elif isinstance(value, Inspection):
            from .paths import writer_lock

            with writer_lock(self.service.home):
                result = self.service.inspect(value.selection_ticket, value.skill_id)
        elif isinstance(value, Task):
            # Do not run a manager or persist a goal when the repository is unapproved.
            self.service.require_project(value.project_id)

            def prepare_task() -> dict[str, Any]:
                return self.service.prepare(
                    value.project_id, value.goal, value.task_class, value.relative_directory
                )

            if agent:
                result = self.service.agent_work(value.project_id, "prepare", prepare_task)
            else:
                result = self.service.start("prepare", prepare_task)
        elif method == "tools_hub.connection.preview":
            self.service.grant(active=True)
            connection = CodexHubConnection(self.service.codex_home, self.config_path)
            import secrets
            import time

            previous_path = self.service.home / "connection-state.json"
            previous = (
                self.service.seals.read(previous_path, "connection_state")
                if previous_path.is_file()
                else None
            )
            pending_path = self.service.home / "connection-pending.json"
            if pending_path.is_file():
                pending = self.service.seals.read(pending_path, "connection_pending")
                if previous and pending["preview_id"] == previous["preview_id"]:
                    connection.check_owned(previous)
                else:
                    connection.recover(pending)
                pending_path.unlink()
            result = {
                **connection.preview(previous),
                "preview_id": secrets.token_hex(16),
                "expires": time.time() + 900,
            }
            self.service.seals.write(
                self.service.home / "connection-preview.json", result, "connection_preview"
            )
        elif method == "tools_hub.connection.apply" and isinstance(value, PreviewId):
            import time

            from .paths import writer_lock

            with writer_lock(self.service.home):
                grant = self.service.grant(active=True)
                preview = self.service.seals.read(
                    self.service.home / "connection-preview.json", "connection_preview"
                )
                if preview["preview_id"] != value.preview_id or preview["expires"] < time.time():
                    raise ValueError("Connection preview expired")
                self.service.seals.write(
                    self.service.home / "connection-pending.json", preview, "connection_pending"
                )
                CodexHubConnection(self.service.codex_home, self.config_path).apply(preview)
                self.service.seals.write(
                    self.service.home / "connection-state.json", preview, "connection_state"
                )
                assert grant is not None
                grant["bridge_configured"] = True
                self.service.seals.write(self.service.home / "permission.json", grant, "permission")
                (self.service.home / "connection-pending.json").unlink()
            result = {
                "status": "connected",
                "new_chat_required": True,
                "learning_permission_changed": False,
            }
        else:
            raise ValueError("Unsupported repository setup request")
        if idempotency_key:
            self.replays[idempotency_key] = (request_digest, result)
            if len(self.replays) > 128:
                self.replays.pop(next(iter(self.replays)))
        return result
