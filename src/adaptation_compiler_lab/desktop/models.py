"""Raw-free types shared by every desktop presentation surface."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.product_dogfood import TerminalAlphaSnapshot
from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest

DesktopHealth = Literal["ready", "needs_attention", "paused", "consent_expired"]
DesktopAction = Literal[
    "load",
    "poll",
    "approve",
    "reject",
    "revoke",
    "feedback",
    "run_task",
    "pause",
    "resume",
    "renew",
    "apply_changes",
    "discard_changes",
]


class ConsentStatus(FrozenModel):
    """The bounded authorization state shown without exposing policy internals."""

    effective_at: datetime
    expires_at: datetime
    retention_days: int = Field(ge=1, le=30)
    days_remaining: int = Field(ge=0, le=30)
    renewal_required: bool


class DesktopProject(FrozenModel):
    """A registered project label safe for the local owner-facing UI."""

    project_id: Identifier
    display_name: NonEmptyStr
    registered_prospectively: bool
    task_runner_enabled: bool


class DesktopSnapshot(FrozenModel):
    """One immutable raw-free desktop read model."""

    snapshot_version: Literal["1.0.0"] = "1.0.0"
    product_name: Literal["Temper"] = "Temper"
    health: DesktopHealth
    consent: ConsentStatus
    background_enabled: bool
    aggregate_reporting_enabled: bool
    terminal: TerminalAlphaSnapshot
    projects: tuple[DesktopProject, ...]
    generated_at: datetime
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def projects_match_terminal_snapshot(self) -> Self:
        project_ids = tuple(item.project_id for item in self.projects)
        if project_ids != self.terminal.configured_project_ids:
            raise ValueError("desktop projects do not match the governed runtime snapshot")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ActionResult(FrozenModel):
    """Stable UI result that never serializes exception or raw source text."""

    action: DesktopAction
    ok: bool
    code: NonEmptyStr
    message: NonEmptyStr
    snapshot_digest: Sha256Digest | None = None


class DesktopTaskResult(FrozenModel):
    """Raw-free task receipt plus the transient final agent response."""

    activation_id: Identifier
    status: NonEmptyStr
    projection_utf8_bytes: int = Field(ge=0)
    final_message: str | None = None
    change_review: DesktopChangeReview | None = None


class DesktopChangeReview(FrozenModel):
    """Transient local diff preview required before a captured bundle can be applied."""

    session_id: Identifier
    expected_head: NonEmptyStr
    changed_files: tuple[NonEmptyStr, ...]
    diff_text: str
    binary_change_count: int = Field(ge=0)
