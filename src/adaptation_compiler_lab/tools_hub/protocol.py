"""Closed desktop and connected-agent operations; no arbitrary command/path dispatch."""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .connection import CodexHubConnection
from .continuity import Handoff
from .controller import fingerprint
from .portable_setup import (
    MAX_PACKAGE,
    Digest,
    FileName,
    ItemId,
    ProjectId,
    SetupDraft,
    SetupError,
    SetupPackage,
    build_package,
    package_path,
    parse_package,
    read_regular,
    write_package,
)
from .service import HubService
from .task_lifecycle import TaskOutcome, TaskOwner
from .workflow_runtime import MotionVideo, RenderCancellation
from .workflow_update import UpdateDirection, UpdateReview


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
    prior_task_receipt: dict[str, Any] | None = None


class Prepare(Task):
    continue_previous: bool = False


class Selection(Task):
    selection_ticket: dict[str, Any]
    choices: list[str] = Field(max_length=2)
    inspections: list[dict[str, Any]] = Field(max_length=3)


class Inspection(Parameters):
    selection_ticket: dict[str, Any]
    skill_id: str = Field(min_length=1, max_length=240)


class RuntimePreview(Parameters):
    node: str = Field(min_length=1, max_length=1024)
    node_modules: str = Field(min_length=1, max_length=1024)
    browser: str = Field(min_length=1, max_length=1024)


class Render(Parameters):
    task_receipt: dict[str, Any]
    spec: MotionVideo


class Finish(Parameters):
    task_receipt: dict[str, Any]
    outcome: TaskOutcome


class Checkpoint(Handoff):
    task_receipt: dict[str, Any]
    goal: str = Field(min_length=1, max_length=2000)
    expected_checkpoint_id: str | None = Field(pattern=r"^[a-f0-9]{32}$")


class ContinuityPreview(Parameters):
    project_id: str = Field(min_length=1, max_length=160)
    enabled: bool
    reset: bool = False


class ContinuityReference(Parameters):
    project_id: str = Field(min_length=1, max_length=160)
    checkpoint_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class Turn(Parameters):
    session_id: str = Field(min_length=1, max_length=160)
    turn_id: str = Field(min_length=1, max_length=160)


class SetupProject(Parameters):
    project_id: ProjectId


class SetupExport(Parameters):
    digest: Digest
    destination: FileName


class SetupImport(SetupProject):
    source: FileName


class SetupUpdateSource(SetupProject):
    directory: FileName
    replay: FileName


class SetupUpdateApproval(SetupProject):
    review_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class SetupReference(SetupProject):
    digest: Digest


class SetupApproval(SetupReference):
    active_digest: Digest | None


class SetupReset(SetupReference):
    pass


class SetupContext(SetupProject):
    task_receipt: dict[str, Any]


class SetupItemRequest(SetupContext):
    digest: Digest
    item_id: ItemId


class BindTurn(Turn):
    lifecycle_nonce: str = Field(min_length=32, max_length=32)


class EndTurn(Turn):
    outcome: Literal["completed", "cancelled"]


SCHEMAS: dict[str, type[BaseModel]] = {
    "tools_hub.status": Empty,
    "tools_hub.inventory": Empty,
    "tools_hub.maintenance": Empty,
    "tools_hub.permission.preview": PermissionPreview,
    "tools_hub.permission.enable": PreviewId,
    "tools_hub.control": Control,
    "tools_hub.prepare": Prepare,
    "tools_hub.inspect": Inspection,
    "tools_hub.select": Selection,
    "tools_hub.finish": Finish,
    "tools_hub.checkpoint": Checkpoint,
    "tools_hub.continuity.preview": ContinuityPreview,
    "tools_hub.continuity.apply": PreviewId,
    "tools_hub.continuity.read": ContinuityReference,
    "tools_hub.continuity.clear": ContinuityReference,
    "tools_hub.render": Render,
    "tools_hub.runtime.preview": RuntimePreview,
    "tools_hub.runtime.enable": PreviewId,
    "tools_hub.runtime.revoke": Empty,
    "tools_hub.connection.preview": Empty,
    "tools_hub.connection.apply": PreviewId,
    "tools_hub.refresh": Empty,
    "tools_hub.repair": Empty,
}
AGENT_METHODS = {
    "tools_hub.status",
    "tools_hub.prepare",
    "tools_hub.inspect",
    "tools_hub.select",
    "tools_hub.finish",
    "tools_hub.checkpoint",
    "tools_hub.render",
    "tools_hub.setup_context",
    "tools_hub.setup_skill",
    "tools_hub.setup_check",
}
SETUP_DESKTOP_SCHEMAS: dict[str, type[BaseModel]] = {
    "portable_setup.status": SetupProject,
    "portable_setup.export.preview": SetupDraft,
    "portable_setup.export.create": SetupExport,
    "portable_setup.import.preview": SetupImport,
    "portable_setup.import.approve": SetupApproval,
    "portable_setup.remove": SetupReference,
    "portable_setup.reset": SetupReset,
    "portable_setup.update.status": SetupProject,
    "portable_setup.update.source": SetupUpdateSource,
    "portable_setup.update.preview": SetupProject,
    "portable_setup.update.rollback_preview": SetupProject,
    "portable_setup.update.approve": SetupUpdateApproval,
    "portable_setup.update.disconnect": SetupProject,
}
SCHEMAS.update(
    {
        **SETUP_DESKTOP_SCHEMAS,
        "tools_hub.setup_context": SetupContext,
        "tools_hub.setup_skill": SetupItemRequest,
        "tools_hub.setup_check": SetupItemRequest,
    }
)
SETUP_MUTATIONS = {
    "portable_setup.export.create",
    "portable_setup.import.approve",
    "portable_setup.remove",
    "portable_setup.reset",
    "portable_setup.update.source",
    "portable_setup.update.approve",
    "portable_setup.update.disconnect",
}
SETUP_PREVIEW_SECONDS = 900


class HubProtocol:
    def __init__(
        self, service: HubService, *, config_path: Any = None, task_owner: TaskOwner | None = None
    ) -> None:
        self.service, self.config_path = service, config_path
        self.task_owner = task_owner
        self.replays: dict[str, tuple[str, dict[str, Any]]] = {}
        self.export_setup: tuple[float, SetupPackage] | None = None
        self.update_review: tuple[float, str, UpdateReview] | None = None
        self.import_setup: (
            tuple[
                float, SetupPackage, tuple[dict[str, Any], dict[str, Any], str | None], str | None
            ]
            | None
        ) = None

    def dispatch(
        self,
        method: str,
        params: dict[str, Any],
        *,
        expected_digest: str | None = None,
        idempotency_key: str | None = None,
        agent: bool = False,
        cancellation: RenderCancellation | None = None,
    ) -> dict[str, Any]:
        if method not in SCHEMAS or (agent and method not in AGENT_METHODS):
            raise ValueError("Unsupported repository setup operation")
        if method == "portable_setup.export.preview":
            self.export_setup = None
        if method == "portable_setup.import.preview":
            self.import_setup = None
        try:
            value = SCHEMAS[method].model_validate(params)
        except ValidationError as error:
            if method not in SETUP_DESKTOP_SCHEMAS:
                raise
            issue = error.errors(include_input=False, include_context=False, include_url=False)[0]
            if issue["type"] == "value_error":
                raise SetupError(
                    "Review the setup for unsafe, invalid, or oversized content"
                ) from error
            raise SetupError(
                "Complete the setup fields using the supported types and limits"
            ) from error
        if agent and self.task_owner is None:
            self.task_owner = TaskOwner.current()
        owner = self.task_owner if agent else None
        request_digest = fingerprint({"method": method, "params": params})
        if idempotency_key in self.replays:
            before, result = self.replays[idempotency_key]
            if before != request_digest:
                raise ValueError("Idempotency key was reused for a different operation")
            return result
        if method in SETUP_DESKTOP_SCHEMAS:
            if method in SETUP_MUTATIONS and (not idempotency_key or len(idempotency_key) > 160):
                raise SetupError("This setup change needs a fresh approval request")
            result = (
                self.desktop_setup_update(method, value)
                if method.startswith("portable_setup.update.") and isinstance(value, SetupProject)
                else self.desktop_setup(value)
            )
            if method in SETUP_MUTATIONS and idempotency_key:
                self.remember(idempotency_key, request_digest, result)
            return result
        if isinstance(value, SetupContext):
            if owner is None:
                raise SetupError("Use the connected agent to access an approved setup")
            if isinstance(value, SetupItemRequest):
                return self.service.setup_for_task(
                    value.project_id,
                    value.task_receipt,
                    owner,
                    digest=value.digest,
                    item_id=value.item_id,
                    kind="skill" if method == "tools_hub.setup_skill" else "check",
                )
            return self.service.setup_for_task(value.project_id, value.task_receipt, owner)
        if method == "tools_hub.status":
            return self.service.state()
        if method == "tools_hub.inventory":
            return {"projects": self.service.inventory()}
        if method == "tools_hub.maintenance":
            return self.service.tick()
        if method == "tools_hub.continuity.read" and isinstance(value, ContinuityReference):
            return self.service.read_continuity(value.project_id, value.checkpoint_id)
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
        elif isinstance(value, ContinuityPreview):
            result = self.service.preview_continuity(
                value.project_id, value.enabled, reset=value.reset
            )
        elif method == "tools_hub.continuity.apply" and isinstance(value, PreviewId):
            result = self.service.apply_continuity(value.preview_id)
        elif method == "tools_hub.continuity.clear" and isinstance(value, ContinuityReference):
            result = self.service.clear_continuity(value.project_id, value.checkpoint_id)
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
                    owner=owner,
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
                result = self.service.inspect(value.selection_ticket, value.skill_id, owner=owner)
        elif isinstance(value, Prepare):
            # Do not run a manager or persist a goal when the repository is unapproved.
            self.service.require_project(value.project_id)
            if value.continue_previous and not agent:
                raise ValueError("Continue saved work through a connected agent")

            def prepare_task() -> dict[str, Any]:
                return self.service.prepare(
                    value.project_id,
                    value.goal,
                    value.task_class,
                    value.relative_directory,
                    owner=owner,
                    prior_task_receipt=value.prior_task_receipt,
                    continue_previous=value.continue_previous,
                )

            if agent:
                result = self.service.agent_work(value.project_id, "prepare", prepare_task)
            else:
                result = self.service.start("prepare", prepare_task)
        elif isinstance(value, Finish) and owner is not None:
            result = self.service.finish(value.task_receipt, owner, value.outcome)
        elif isinstance(value, Checkpoint) and owner is not None:
            result = self.service.save_checkpoint(
                value.task_receipt,
                owner,
                value.goal,
                value.expected_checkpoint_id,
                Handoff.model_validate(
                    value.model_dump(
                        exclude={
                            "task_receipt",
                            "goal",
                            "expected_checkpoint_id",
                        }
                    )
                ),
            )
        elif isinstance(value, Render) and owner is not None:
            result = self.service.render(
                value.task_receipt, owner, value.spec.model_dump(), cancellation=cancellation
            )
        elif isinstance(value, RuntimePreview):
            result = self.service.preview_runtime(value.node, value.node_modules, value.browser)
        elif method == "tools_hub.runtime.enable" and isinstance(value, PreviewId):
            result = self.service.enable_runtime(value.preview_id)
        elif method == "tools_hub.runtime.revoke":
            result = self.service.revoke_runtime()
        elif method == "tools_hub.connection.preview":
            self.service.grant(active=True)
            connection = CodexHubConnection(self.service.codex_home, self.config_path)

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
                grant.update(bridge_configured=True, native_hooks_configured=True)
                self.service.seals.write(self.service.home / "permission.json", grant, "permission")
                (self.service.home / "connection-pending.json").unlink()
            result = {
                "status": "connected",
                "new_chat_required": True,
                "native_hook_trust_required": True,
                "learning_permission_changed": False,
            }
        else:
            raise ValueError("Unsupported repository setup request")
        if idempotency_key:
            self.remember(idempotency_key, request_digest, result)
        return result

    def remember(self, key: str, digest: str, result: dict[str, Any]) -> None:
        self.replays[key] = (digest, result)
        if len(self.replays) > 128:
            self.replays.pop(next(iter(self.replays)))

    def desktop_setup(self, value: BaseModel) -> dict[str, Any]:
        now = time.monotonic()
        if isinstance(value, SetupDraft):
            package = build_package(value, self.service.seals)
            self.export_setup = (now + SETUP_PREVIEW_SECONDS, package)
            return package.preview()
        if isinstance(value, SetupExport):
            pending = self.export_setup
            if pending is None or pending[0] <= now or pending[1].digest != value.digest:
                raise SetupError("Preview this exact setup again before saving it")
            write_package(Path(value.destination), pending[1])
            self.export_setup = None
            return pending[1].preview()
        if isinstance(value, SetupImport):
            grant, project, revision, current = self.service.setup_status(
                value.project_id, active=True
            )
            source = package_path(Path(value.source))
            try:
                package = parse_package(read_regular(source, MAX_PACKAGE))
            except OSError as error:
                raise SetupError("The selected setup file could not be read") from error
            active_digest = current.digest if current else None
            self.import_setup = (
                now + SETUP_PREVIEW_SECONDS,
                package,
                (grant, project, revision),
                active_digest,
            )
            return {
                **package.preview(),
                "project_id": value.project_id,
                "active_digest": active_digest,
                "source_name": source.name,
            }
        if isinstance(value, SetupApproval):
            reviewed = self.import_setup
            if (
                reviewed is None
                or reviewed[0] <= now
                or reviewed[1].digest != value.digest
                or reviewed[2][1]["id"] != value.project_id
                or reviewed[3] != value.active_digest
            ):
                raise SetupError(
                    "Preview this exact setup and repository again before approving it"
                )
            self.service.change_setup(
                value.project_id, value.active_digest, reviewed[1], reviewed_binding=reviewed[2]
            )
            self.import_setup = None
            return reviewed[1].preview()
        if isinstance(value, SetupReset):
            self.service.reset_setup(value.project_id, value.digest)
            return {"active": None}
        if isinstance(value, SetupReference):
            self.service.change_setup(value.project_id, value.digest, None)
            return {"active": None}
        if isinstance(value, SetupProject):
            return self.service.setup_desktop_status(value.project_id)
        raise SetupError("Unsupported portable setup operation")

    def desktop_setup_update(self, method: str, value: SetupProject) -> dict[str, Any]:
        project_id = value.project_id
        if isinstance(value, SetupUpdateSource):
            return self.service.set_update_source(
                project_id, directory=Path(value.directory), replay=Path(value.replay)
            )
        if isinstance(value, SetupUpdateApproval):
            pending = self.update_review
            if (
                pending is None
                or pending[0] <= time.monotonic()
                or pending[1] != value.review_id
                or pending[2].project["id"] != project_id
            ):
                raise SetupError("Review this exact workflow change again before approving it")
            self.update_review = None
            return self.service.approve_setup_update(project_id, pending[2])
        if method == "portable_setup.update.status":
            return self.service.setup_update_status(project_id)
        if method == "portable_setup.update.disconnect":
            return self.service.set_update_source(project_id)
        if method in {"portable_setup.update.preview", "portable_setup.update.rollback_preview"}:
            self.update_review = None
            direction: UpdateDirection = (
                "rollback" if method.endswith(".rollback_preview") else "update"
            )
            review = self.service.preview_setup_update(project_id, direction)
            review_id = secrets.token_hex(16)
            self.update_review = (time.monotonic() + SETUP_PREVIEW_SECONDS, review_id, review)
            return review.preview(review_id)
        raise SetupError("Unsupported workflow update operation")

    def record_checkpoint_retrieval(self, receipt: dict[str, Any], checkpoint_id: str) -> None:
        if self.task_owner is not None:
            self.service.record_checkpoint_retrieval(receipt, self.task_owner, checkpoint_id)
