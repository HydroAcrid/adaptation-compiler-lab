"""Raw-free types shared by every desktop presentation surface."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    AdaptationLayer,
    FeedbackSignalKind,
    RuntimeFeedbackOutcome,
)
from adaptation_compiler_lab.automatic_runtime.product_dogfood import TerminalAlphaSnapshot
from adaptation_compiler_lab.domain import (
    ArtifactRoute,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Scope,
    Sha256Digest,
)
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
ConnectionIntegrationState = Literal[
    "unavailable",
    "available",
    "connected",
    "attention",
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
    "undo",
    "preferences",
]
SuggestionDecision = Literal[
    "keep_suggested",
    "keep_project",
    "keep_narrowed",
    "ignore",
    "approve_revocation",
    "reject_revocation",
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
        "macos-keychain-security-framework",
        "unavailable",
    ]
    status: Literal["not_created", "ready", "locked", "unavailable"]


class AgentConnectionV1(FrozenModel):
    """Truthful source and target capabilities without executable or credential paths."""

    connection_version: Literal["1.1.0"] = "1.1.0"
    agent_id: Literal["codex", "claude"]
    display_name: Literal["Codex", "Claude Code"]
    installation_state: ConnectionInstallationState
    authentication_state: ConnectionAuthenticationState
    conformance_state: ConnectionConformanceState
    integration_state: ConnectionIntegrationState = "unavailable"
    version_label: str | None = None
    status_summary: NonEmptyStr
    learning_capability: NonEmptyStr
    delivery_capability: NonEmptyStr
    cost_posture: NonEmptyStr
    available_actions: tuple[Literal["refresh", "use_for_setup", "connect", "disconnect"], ...] = (
        "refresh",
    )
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


class SuggestionSummaryV1(FrozenModel):
    """One raw-free governed proposal safe for the everyday review interface."""

    summary_version: Literal["1.0.0"] = "1.0.0"
    review_number: int = Field(ge=1)
    queue_id: Identifier
    proposal_digest: Sha256Digest
    signal_kind: FeedbackSignalKind
    proposed_behavior: NonEmptyStr | None = None
    affected_artifact_id: Identifier | None = None
    route: ArtifactRoute | None = None
    layer: AdaptationLayer
    suggested_scope: Scope
    reason_summary: tuple[NonEmptyStr, ...]
    evidence_digest: Sha256Digest
    consent_digest: Sha256Digest
    capture_digest: Sha256Digest
    available_actions: tuple[SuggestionDecision, ...]
    created_at: datetime
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def shape_matches_signal(self) -> Self:
        if self.signal_kind.value == "revocation":
            if (
                self.proposed_behavior is not None
                or self.route is not None
                or self.affected_artifact_id is None
                or self.available_actions != ("approve_revocation", "reject_revocation")
            ):
                raise ValueError("revocation suggestion is inconsistent")
        elif (
            self.proposed_behavior is None
            or self.route is None
            or self.affected_artifact_id is not None
            or self.available_actions
            != ("keep_suggested", "keep_project", "keep_narrowed", "ignore")
        ):
            raise ValueError("learning suggestion is inconsistent")
        return self


class SuggestionDecisionRequestV1(FrozenModel):
    """Exact review decision, including only deterministic scope narrowing."""

    request_version: Literal["1.0.0"] = "1.0.0"
    queue_id: Identifier
    proposal_digest: Sha256Digest
    decision: SuggestionDecision
    project_id: Identifier | None = None
    refined_scope: Scope | None = None

    @model_validator(mode="after")
    def decision_parameters_are_exact(self) -> Self:
        if self.decision == "keep_project":
            if self.project_id is None or self.refined_scope is not None:
                raise ValueError("project-only decisions require exactly one project")
        elif self.decision == "keep_narrowed":
            if self.project_id is not None or self.refined_scope is None:
                raise ValueError("narrowed decisions require one explicit scope")
        elif self.project_id is not None or self.refined_scope is not None:
            raise ValueError("this decision does not accept scope parameters")
        return self


class AdaptationSummaryV1(FrozenModel):
    """Approved behavioral artifact without supporting raw evidence."""

    summary_version: Literal["1.0.0"] = "1.0.0"
    artifact_id: Identifier
    artifact_version: NonEmptyStr
    artifact_digest: Sha256Digest
    artifact_type: NonEmptyStr
    layer: AdaptationLayer
    intent: NonEmptyStr
    required_behaviors: tuple[NonEmptyStr, ...]
    scope: Scope
    evidence_count: int = Field(ge=1)
    review_at: datetime | None = None
    expires_at: datetime | None = None
    available_actions: tuple[Literal["revoke"], ...] = ("revoke",)
    raw_payloads_exposed: Literal[False] = False


class ActivationFeedbackSummaryV1(FrozenModel):
    """Exact completed delivery that can receive one owner rating."""

    summary_version: Literal["1.0.0"] = "1.0.0"
    activation_id: Identifier
    delivery_receipt_digest: Sha256Digest
    active_artifact_ids: tuple[Identifier, ...]
    projection_utf8_bytes: int = Field(ge=0)
    activated_at: datetime
    completed_at: datetime
    available_outcomes: tuple[RuntimeFeedbackOutcome, ...] = (
        RuntimeFeedbackOutcome.HELPED,
        RuntimeFeedbackOutcome.HURT,
        RuntimeFeedbackOutcome.IRRELEVANT,
    )
    raw_payloads_exposed: Literal[False] = False


class RecentUndoSummaryV1(FrozenModel):
    """A still-valid 24-hour undo handle bound to its immutable notice."""

    summary_version: Literal["1.0.0"] = "1.0.0"
    notice_id: Identifier
    notice_digest: Sha256Digest
    artifact_id: Identifier
    summary: NonEmptyStr
    created_at: datetime
    expires_at: datetime
    raw_payloads_exposed: Literal[False] = False


class MutationReceiptV1(FrozenModel):
    """Stable raw-free receipt returned for a product mutation."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    action: DesktopAction
    target_id: Identifier
    status: Literal["applied"] = "applied"
    code: NonEmptyStr
    message: NonEmptyStr
    resulting_snapshot_digest: Sha256Digest
    raw_payloads_exposed: Literal[False] = False


class DesktopSnapshot(FrozenModel):
    """One immutable raw-free desktop read model."""

    snapshot_version: Literal["1.1.0"] = "1.1.0"
    product_name: Literal["Temper"] = "Temper"
    health: DesktopHealth
    consent: ConsentStatus
    background_enabled: bool
    aggregate_reporting_enabled: bool
    decision_notifications_enabled: bool
    launch_at_login_enabled: bool
    terminal: TerminalAlphaSnapshot
    projects: tuple[DesktopProject, ...]
    suggestions: tuple[SuggestionSummaryV1, ...]
    adaptations: tuple[AdaptationSummaryV1, ...]
    activation_feedback: tuple[ActivationFeedbackSummaryV1, ...]
    recent_undos: tuple[RecentUndoSummaryV1, ...]
    generated_at: datetime
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def projects_match_terminal_snapshot(self) -> Self:
        project_ids = tuple(item.project_id for item in self.projects)
        if project_ids != self.terminal.configured_project_ids:
            raise ValueError("desktop projects do not match the governed runtime snapshot")
        if len(self.suggestions) != self.terminal.review_mode.metrics.pending_review_count:
            raise ValueError("desktop suggestions do not match the governed runtime snapshot")
        if (
            len(self.activation_feedback)
            != self.terminal.review_mode.metrics.pending_feedback_count
        ):
            raise ValueError("desktop feedback does not match the governed runtime snapshot")
        if tuple(item.artifact_id for item in self.adaptations) != tuple(
            item.artifact_id for item in self.terminal.active_adaptations
        ):
            raise ValueError("desktop adaptations do not match the governed runtime snapshot")
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


class DiagnosticsSummaryV1(FrozenModel):
    """Raw-free local instrument posture for the native Advanced surface."""

    diagnostics_version: Literal["1.0.0"] = "1.0.0"
    snapshot_version: NonEmptyStr
    project_count: int = Field(ge=0)
    pending_review_count: int = Field(ge=0)
    active_adaptation_count: int = Field(ge=0)
    pending_feedback_count: int = Field(ge=0)
    consent_current: bool
    secure_store_ready: bool
    raw_payloads_exposed: Literal[False] = False


class DesktopChangeReview(FrozenModel):
    """Transient local diff preview required before a captured bundle can be applied."""

    session_id: Identifier
    expected_head: NonEmptyStr
    changed_files: tuple[NonEmptyStr, ...]
    diff_text: str
    binary_change_count: int = Field(ge=0)
