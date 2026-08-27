"""Raw-free types shared by every desktop presentation surface."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.product_dogfood import TerminalAlphaSnapshot
from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest

DesktopHealth = Literal["ready", "needs_attention", "paused", "consent_expired"]
ConfigurationState = Literal[
    "unconfigured",
    "existing_available",
    "configured",
    "incompatible",
]
ConnectionInstallationState = Literal["not_installed", "installed"]
ConnectionAuthenticationState = Literal["unknown", "signed_out", "signed_in"]
ConnectionConformanceState = Literal[
    "not_applicable",
    "unverified",
    "compatible",
    "update_required",
]
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


class SecureStoreStatus(FrozenModel):
    """Raw-free native credential posture shown during setup and recovery."""

    platform: Literal["windows", "macos", "development"]
    protector: Literal[
        "windows-dpapi-current-user",
        "macos-keychain-current-user",
        "unavailable",
    ]
    status: Literal["not_created", "ready", "locked", "unavailable"]


class AgentConnectionV1(FrozenModel):
    """Truthful source and target capabilities without executable or credential paths."""

    connection_version: Literal["1.0.0"] = "1.0.0"
    agent_id: Literal["codex", "claude"]
    display_name: Literal["Codex", "Claude Code"]
    installation_state: ConnectionInstallationState
    authentication_state: ConnectionAuthenticationState
    conformance_state: ConnectionConformanceState
    version_label: str | None = None
    status_summary: NonEmptyStr
    learning_capability: NonEmptyStr
    delivery_capability: NonEmptyStr
    cost_posture: NonEmptyStr
    available_actions: tuple[Literal["refresh", "use_for_setup"], ...] = ("refresh",)
    raw_payloads_exposed: Literal[False] = False


class ExistingInstallationSummary(FrozenModel):
    """Safe first-run summary of a previously governed local installation."""

    signer_fingerprint: Sha256Digest
    project_count: int = Field(ge=0)
    consent_expires_at: datetime
    secure_store_ready: bool


class ProjectCandidatePreviewV1(FrozenModel):
    """Opaque prospective registration preview; the renderer never receives its path."""

    preview_version: Literal["1.0.0"] = "1.0.0"
    preview_token: NonEmptyStr
    project_id: Identifier
    display_name: NonEmptyStr
    capture_after_epoch_seconds: int = Field(ge=0)
    historical_tasks_eligible: Literal[False] = False
    modifies_existing_tasks: Literal[False] = False
    modifies_repository: Literal[False] = False
    expires_at: datetime


class SetupSnapshotV1(FrozenModel):
    """Raw-free setup state available before a governed runtime exists."""

    setup_version: Literal["1.0.0"] = "1.0.0"
    product_name: Literal["Temper"] = "Temper"
    configuration_state: ConfigurationState
    secure_store: SecureStoreStatus
    connections: tuple[AgentConnectionV1, AgentConnectionV1]
    existing_installation: ExistingInstallationSummary | None = None
    learning_enabled: Literal[False] = False
    automatic_promotion_enabled: Literal[False] = False
    aggregate_reporting_enabled: Literal[False] = False
    launch_at_login_enabled: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SetupCompletionReceiptV1(FrozenModel):
    """Safe completion receipt returned before the engine restarts configured."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    signer_fingerprint: Sha256Digest
    project_id: Identifier
    capture_after_epoch_seconds: int = Field(ge=0)
    consent_expires_at: datetime
    learning_enabled: Literal[False] = False
    aggregate_reporting_enabled: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False


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
