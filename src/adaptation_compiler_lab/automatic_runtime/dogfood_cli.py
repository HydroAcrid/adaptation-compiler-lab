"""Local-only Codex dogfood commands for pickup, delivery, review, undo, and feedback."""

from __future__ import annotations

import base64
import difflib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from itertools import chain
from pathlib import Path
from time import monotonic
from typing import Annotated, Literal, NoReturn, cast

import typer
from pydantic import TypeAdapter, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodInteractionSource,
    CodexDogfoodSessionLauncher,
    CodexProjectPreview,
    CodexProjectScope,
    open_codex_dogfood,
    preview_codex_project,
)
from adaptation_compiler_lab.automatic_runtime.codex_gateway import CodexGatewayConversation
from adaptation_compiler_lab.automatic_runtime.codex_host import (
    CodexDogfoodHost,
    CodexDogfoodPickupReceipt,
)
from adaptation_compiler_lab.automatic_runtime.credentials import (
    CredentialStoreError,
    RuntimeSecrets,
    platform_credential_store,
)
from adaptation_compiler_lab.automatic_runtime.gate import (
    CodexDogfoodGateReport,
    build_codex_dogfood_gate_report,
)
from adaptation_compiler_lab.automatic_runtime.gateway_ledger import GatewayLedger
from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    CredentialEnvelopeMetadataRecord,
    GatewaySession,
    GatewaySessionStatus,
    GatewayTurnReceipt,
    RuntimeSuccessorReceipt,
    RuntimeWatcherLease,
    VerificationCommandSpec,
    VerificationReceipt,
)
from adaptation_compiler_lab.automatic_runtime.host import (
    RuntimeNoticeSink,
    RuntimeReviewSink,
)
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    CodexProjectRecoveryBindingV1,
    CodexProjectRegistration,
    FeedbackDetectorMode,
    InteractionObservation,
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeNotice,
    RuntimeReviewQueueItem,
    RuntimeTargetDeliveryAcknowledgement,
    StandingAutomationPolicy,
)
from adaptation_compiler_lab.automatic_runtime.product_dogfood import (
    TerminalAlphaSnapshot,
    build_review_mode_dogfood_snapshot,
    build_terminal_alpha_snapshot,
)
from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticEvaluationSplit,
    apply_semantic_corpus_adjudication,
    evaluate_semantic_feedback,
    load_semantic_corpus_adjudication,
    load_semantic_feedback_corpus,
)
from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    CodexSemanticFeedbackInterpreter,
)
from adaptation_compiler_lab.automatic_runtime.service import (
    AutomaticAdaptationRuntime,
    AutomaticRuntimeError,
    initial_runtime_state,
)
from adaptation_compiler_lab.automatic_runtime.watcher import (
    AutomaticRuntimeWatcher,
    DurableNotificationSink,
    FileWatcherLease,
    WindowsTaskScheduler,
    WindowsToastPublisher,
)
from adaptation_compiler_lab.automatic_runtime.workspace_gateway import (
    CapturedChangeBundle,
    EncryptedChangeBundleStore,
    GitWorktreeProvider,
    IndependentVerifier,
    RecoverableChangeApplier,
    require_protected_paths_unchanged,
)
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_DOGFOOD_RUNTIME_LOCK,
    RuntimeConformanceError,
    load_dogfood_runtime_pins,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ApprovalDecision,
    ArtifactRoute,
    FrozenModel,
    Identifier,
    PermittedUse,
    Scope,
    Sha256Digest,
    SourceClass,
    TaskRecordRef,
)
from adaptation_compiler_lab.governance import (
    GovernanceEvent,
    GovernanceEventType,
    SignerIdentity,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    sign_governance_event,
    verify_detached_envelope,
    verify_signed_governance,
)
from adaptation_compiler_lab.instruction_environment import (
    InstructionEnvironmentService,
    NativeReadStatus,
    NativeSourceKind,
    NativeTarget,
)
from adaptation_compiler_lab.instruction_environment.codex_semantic import (
    instruction_relation_analyzer_digest,
)
from adaptation_compiler_lab.modes import (
    CapabilityMode,
    ModePreparedTask,
    ModeReceiptStore,
    complete_mode_delivery,
    mode_by_id,
    prepare_mode_task,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.portability import PersonalModeOverlayV1
from adaptation_compiler_lab.runtime import RuntimeProjectionContext, build_runtime_projection
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.models import ScopeDimension

dogfood_app = typer.Typer(
    help="Run the local governed Codex dogfood loop with saved ChatGPT authentication.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

_SUPPORTED_DOGFOOD_CONFIG_VERSIONS = frozenset({"1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"})
credentials_app = typer.Typer(
    help="Manage automatic same-user runtime unlock and lost-credential succession."
)
watcher_app = typer.Typer(help="Operate the restart-safe local Codex feedback watcher.")
inbox_app = typer.Typer(help="Inspect raw-free durable runtime notifications.")
session_app = typer.Typer(help="Run governed Codex sessions in disposable writable workspaces.")
changes_app = typer.Typer(help="Inspect, apply, or discard encrypted session change bundles.")
project_app = typer.Typer(help="Preview and register prospective read-only Codex projects.")
dogfood_app.add_typer(credentials_app, name="credentials")
dogfood_app.add_typer(watcher_app, name="watcher")
dogfood_app.add_typer(inbox_app, name="inbox")
dogfood_app.add_typer(session_app, name="session")
dogfood_app.add_typer(changes_app, name="changes")
dogfood_app.add_typer(project_app, name="project")

ConfigOption = Annotated[
    Path,
    typer.Option(
        "--config",
        help="Explicit local Codex dogfood configuration outside every Git repository.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
]
PredecessorConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--predecessor-config",
        help=(
            "Exact preserved predecessor config required for cumulative reporting after "
            "lost-credential succession."
        ),
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
]


class CodexDogfoodProjectConfig(FrozenModel):
    """One exact target path plus source-CWD aliases for the same governed project."""

    project_id: Identifier
    root: Path
    scope: Scope
    source_roots: tuple[Path, ...] = ()
    verification_commands: tuple[VerificationCommandSpec, ...] = ()
    protected_verification_paths: tuple[str, ...] = ("pyproject.toml", "tests", "uv.lock")
    capture_after_epoch_seconds: int | None = None
    registration: CodexProjectRegistration | None = None
    registration_authorization: GovernanceEvent | None = None
    recovery_binding: CodexProjectRecoveryBindingV1 | None = None

    @field_validator("source_roots")
    @classmethod
    def source_roots_are_sorted_unique(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        rendered = tuple(str(item) for item in value)
        if rendered != tuple(sorted(set(rendered))):
            raise ValueError("dogfood source roots must be sorted and unique")
        return value

    @field_validator("protected_verification_paths")
    @classmethod
    def protected_paths_are_safe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.replace("\\", "/").rstrip("/") for item in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("protected verification paths must be sorted and unique")
        if any(
            not item
            or item.startswith("/")
            or any(part in {"", ".", ".."} for part in item.split("/"))
            for item in normalized
        ):
            raise ValueError("protected verification paths must be safe relative paths")
        return normalized

    @model_validator(mode="after")
    def project_scope_is_exact(self) -> CodexDogfoodProjectConfig:
        if self.scope.project_ids != (self.project_id,):
            raise ValueError("dogfood project scope must contain exactly its project ID")
        if (self.registration is None) != (self.registration_authorization is None):
            raise ValueError("project registration and authorization must be supplied together")
        if self.registration is None:
            if self.capture_after_epoch_seconds is not None:
                raise ValueError("legacy project cutoff must come from the root config")
        else:
            expected_roots = tuple(str(item) for item in self.effective_source_roots)
            registration_changed = (
                self.registration.project_root != str(self.root)
                or self.registration.source_roots != expected_roots
            )
            if (
                self.registration.project_id != self.project_id
                or self.registration.capture_after_epoch_seconds != self.capture_after_epoch_seconds
                or (registration_changed and self.recovery_binding is None)
            ):
                raise ValueError("project registration does not bind the exact project config")
        if self.recovery_binding is not None:
            expected_root = canonical_digest({"project_root": str(self.root)})
            expected_sources = canonical_digest(
                {"source_roots": [str(item) for item in self.effective_source_roots]}
            )
            if (
                self.recovery_binding.project_id != self.project_id
                or self.recovery_binding.restored_project_root_digest != expected_root
                or self.recovery_binding.restored_source_roots_digest != expected_sources
            ):
                raise ValueError("project recovery binding does not match restored paths")
        return self

    @property
    def effective_source_roots(self) -> tuple[Path, ...]:
        return self.source_roots or (self.root,)


class CodexDogfoodLocalConfig(FrozenModel):
    """No-secret local configuration; keys are DPAPI-managed or externally supplied."""

    config_version: str = "1.4.0"
    subject_id: Identifier
    repository_root: Path
    state_root: Path
    database_path: Path
    raw_store_path: Path
    source_codex_home: Path
    codex_executable: Path
    windows_interop: bool = False
    runtime_pin_path: Path
    capture_after_epoch_seconds: int
    policy: StandingAutomationPolicy
    policy_authorization: GovernanceEvent
    signer_identity: SignerIdentity
    projects: tuple[CodexDogfoodProjectConfig, ...]
    target_codex_home: Path | None = None
    target_codex_executable: Path | None = None
    target_windows_interop: bool | None = None
    target_runtime_pin_path: Path | None = None
    feedback_detector_mode: FeedbackDetectorMode = FeedbackDetectorMode.GRAMMAR
    semantic_model: str = "gpt-5.6-luna"
    semantic_reasoning_effort: str = "medium"
    semantic_promotion_evaluation_digest: Sha256Digest | None = None
    gateway_workspace_root: Path | None = None
    wsl_distribution: str = "Ubuntu"
    watcher_idle_seconds: int = 60
    watcher_maximum_backoff_seconds: int = 900
    notification_mode: Literal["inbox", "toast_and_inbox"] = "toast_and_inbox"
    gateway_model: str = "gpt-5.6-luna"
    gateway_reasoning_effort: str = "medium"
    gateway_windows_sandbox: Literal["elevated", "unelevated"] = "elevated"
    gateway_maximum_turns: int = 15
    gateway_maximum_session_seconds: int = 3_600
    gateway_maximum_turn_seconds: int = 600

    @field_validator("projects")
    @classmethod
    def projects_are_unique(
        cls, value: tuple[CodexDogfoodProjectConfig, ...]
    ) -> tuple[CodexDogfoodProjectConfig, ...]:
        ids = tuple(item.project_id for item in value)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("dogfood projects must be sorted and unique")
        return value

    @model_validator(mode="after")
    def paths_and_subject_are_consistent(self) -> CodexDogfoodLocalConfig:
        if self.config_version not in _SUPPORTED_DOGFOOD_CONFIG_VERSIONS:
            raise ValueError("unsupported dogfood config version")
        if self.config_version == "1.1.0" and (
            self.feedback_detector_mode is not FeedbackDetectorMode.GRAMMAR
            or self.semantic_promotion_evaluation_digest is not None
        ):
            raise ValueError("dogfood config v1.1 is grammar-only")
        if (
            self.feedback_detector_mode is FeedbackDetectorMode.CALIBRATED
            and self.semantic_promotion_evaluation_digest is None
        ):
            raise ValueError("calibrated semantic serving requires an evaluation digest")
        if not self.semantic_model.strip() or not self.semantic_reasoning_effort.strip():
            raise ValueError("semantic model and reasoning effort must not be empty")
        if not self.wsl_distribution.strip() or not self.gateway_model.strip():
            raise ValueError("gateway distribution and model must not be empty")
        if not 1 <= self.watcher_idle_seconds <= 300:
            raise ValueError("watcher idle cadence must be between 1 and 300 seconds")
        if self.watcher_maximum_backoff_seconds < self.watcher_idle_seconds:
            raise ValueError("watcher backoff must not be shorter than its idle cadence")
        if not 1 <= self.gateway_maximum_turns <= 15:
            raise ValueError("gateway maximum turns must be between 1 and 15")
        if not 1 <= self.gateway_maximum_session_seconds <= 3_600:
            raise ValueError("gateway session timeout must be between 1 and 3600 seconds")
        if not 1 <= self.gateway_maximum_turn_seconds <= 600:
            raise ValueError("gateway turn timeout must be between 1 and 600 seconds")
        if (
            self.policy.subject_id != self.subject_id
            or self.policy_authorization.subject_id != self.subject_id
            or self.signer_identity.subject_id != self.subject_id
        ):
            raise ValueError("dogfood config crossed its subject boundary")
        configured_project_ids = tuple(item.project_id for item in self.projects)
        if configured_project_ids != self.policy.scope.project_ids:
            raise ValueError("configured projects must equal the standing-policy project scope")
        root_policy = self.policy
        while root_policy.previous_policy is not None:
            root_policy = root_policy.previous_policy
        legacy_project_ids = tuple(
            item.project_id for item in self.projects if item.registration is None
        )
        if legacy_project_ids != root_policy.scope.project_ids:
            raise ValueError("unsigned project configs must equal the original signed policy")
        for project in self.projects:
            registration = project.registration
            authorization = project.registration_authorization
            if registration is None or authorization is None:
                continue
            if registration.subject_id != self.subject_id:
                raise ValueError("project registration crossed its subject boundary")
            try:
                verify_signed_governance(
                    authorization,
                    self.signer_identity,
                    effective_at=registration.registered_at,
                )
            except ValueError as error:
                raise ValueError("project-registration authorization is invalid") from error
            amendment = self.policy.policy_for_digest(registration.standing_policy_digest)
            if amendment is None or amendment.previous_policy is None:
                raise ValueError("project registration names no policy amendment")
            newly_authorized = set(amendment.scope.project_ids) - set(
                amendment.previous_policy.scope.project_ids
            )
            if newly_authorized != {project.project_id}:
                raise ValueError("project registration must bind one newly authorized project")
            if (
                authorization.event_type is not GovernanceEventType.ACTIVATION_DECISION
                or authorization.subject_id != self.subject_id
                or authorization.target_ref
                != f"codex-project-registration:{registration.registration_id}"
                or authorization.target_digest != registration.content_digest
                or authorization.decision != "registered_read_only"
                or authorization.policy_version != amendment.policy_version
                or authorization.occurred_at != registration.registered_at
            ):
                raise ValueError("project-registration authorization binding changed")
        for project in self.projects:
            binding = project.recovery_binding
            if binding is None:
                continue
            if (
                binding.subject_id != self.subject_id
                or binding.signature.signer_identity_id != self.signer_identity.identity_id
                or binding.signature.key_fingerprint != self.signer_identity.key_fingerprint
                or SignerRole.CUSTODY not in self.signer_identity.roles
            ):
                raise ValueError("project recovery binding crossed its owner authority")
            try:
                verify_detached_envelope(
                    binding.unsigned_payload,
                    binding.signature,
                    public_key_base64=self.signer_identity.public_key_base64,
                    expected_purpose="codex_project_recovery_binding",
                )
            except ValueError as error:
                raise ValueError("project recovery binding signature is invalid") from error
        mapped_roots = tuple(
            (project.project_id, root.expanduser().resolve())
            for project in self.projects
            for root in project.effective_source_roots
        )
        for index, (project_id, root) in enumerate(mapped_roots):
            for other_project_id, other_root in mapped_roots[index + 1 :]:
                if project_id == other_project_id:
                    continue
                if (
                    root == other_root
                    or root.is_relative_to(other_root)
                    or other_root.is_relative_to(root)
                ):
                    raise ValueError("dogfood source roots overlap across project scopes")
        if self.database_path.parent != self.state_root:
            raise ValueError("dogfood database must remain directly below its state root")
        if self.raw_store_path.parent != self.state_root:
            raise ValueError("dogfood raw store must remain directly below its state root")
        target_endpoint = (
            self.target_codex_home,
            self.target_codex_executable,
            self.target_windows_interop,
            self.target_runtime_pin_path,
        )
        if any(item is not None for item in target_endpoint) and not all(
            item is not None for item in target_endpoint
        ):
            raise ValueError(
                "dogfood target endpoint must be completely specified or inherit the source"
            )
        return self

    @property
    def credential_binding_digest(self) -> Sha256Digest:
        """Bind DPAPI enrollment to the complete no-secret runtime configuration."""

        return canonical_digest(self.model_dump(mode="json"))

    @property
    def legacy_credential_binding_digest(self) -> Sha256Digest:
        """Read compatibility for the first v1.3 enrollment binding."""

        return canonical_digest(
            {
                "config_version": self.config_version,
                "database_path": str(self.database_path),
                "policy_digest": str(self.policy.content_digest),
                "raw_store_path": str(self.raw_store_path),
                "repository_root": str(self.repository_root),
                "state_root": str(self.state_root),
                "subject_id": self.subject_id,
            }
        )

    @property
    def prior_full_credential_binding_digest(self) -> Sha256Digest:
        """Read compatibility for v1.3 before the Windows sandbox selector existed."""

        return canonical_digest(self.model_dump(mode="json", exclude={"gateway_windows_sandbox"}))

    @property
    def effective_target_codex_home(self) -> Path:
        return self.target_codex_home or self.source_codex_home

    @property
    def effective_target_codex_executable(self) -> Path:
        return self.target_codex_executable or self.codex_executable

    @property
    def effective_target_windows_interop(self) -> bool:
        if self.target_windows_interop is None:
            return self.windows_interop
        return self.target_windows_interop

    @property
    def effective_target_runtime_pin_path(self) -> Path:
        return self.target_runtime_pin_path or self.runtime_pin_path


@dataclass(frozen=True, slots=True)
class FreshCodexTaskResult:
    """Raw-free result summary plus the target's final message."""

    activation_id: str
    material_utf8_bytes: int
    status: str
    final_message: str | None


class _ConsoleNoticeSink(RuntimeNoticeSink):
    def publish(self, notice: RuntimeNotice) -> None:
        typer.echo(canonical_json(_json_notice(notice)))


def _json_notice(notice: RuntimeNotice) -> dict[str, object]:
    """Render one raw-free notice with JSON-safe typed values."""

    return {
        "created_at": notice.created_at.isoformat().replace("+00:00", "Z"),
        "kind": notice.kind.value,
        "notice_id": notice.notice_id,
        "summary": notice.summary,
        "undo_artifact_id": notice.undo_artifact_id,
    }


def _json_scope(scope: Scope) -> dict[str, object]:
    """Render one typed scope at the raw-free CLI boundary."""

    return scope.model_dump(mode="json")


def _json_review_proposal(item: RuntimeReviewQueueItem) -> dict[str, object]:
    """Render the normalized proposal while keeping supporting raw text encrypted."""

    detection = item.detection
    return {
        "affected_artifact_id": detection.affected_artifact_id,
        "behavior": detection.normalized_behavior,
        "context_only_action": "rejected",
        "future_use_confirmation_required": True,
        "owner_question": (
            "Should this behavior influence future sessions within the shown scope?"
        ),
        "proposal_digest": str(detection.content_digest),
        "proposal_purpose": "future_sessions",
        "route": None if detection.requested_route is None else detection.requested_route.value,
        "scope": _json_scope(detection.scope),
        "signal_kind": None if detection.signal_kind is None else detection.signal_kind.value,
    }


def _validate_review_decision_intent(
    decision: ApprovalDecision,
    *,
    confirm_future_use: bool,
) -> None:
    """Keep current-chat accuracy separate from authorization for future sessions."""

    if decision is ApprovalDecision.APPROVED and not confirm_future_use:
        raise AutomaticRuntimeError(
            "approval requires --confirm-future-use; current-chat accuracy alone is not "
            "durable authorization"
        )
    if decision is ApprovalDecision.REJECTED and confirm_future_use:
        raise AutomaticRuntimeError(
            "--confirm-future-use is valid only with an approved review decision"
        )


def _review_refined_scope(
    scope: Scope,
    *,
    project_ids: list[str] | None = None,
    task_classes: list[str] | None,
    environment_ids: list[str] | None,
    activation_conditions: list[str] | None,
    exclusions: list[str] | None,
) -> Scope | None:
    """Construct only an explicit deterministic narrowing of the proposed scope."""

    supplied = any(
        value is not None
        for value in (
            project_ids,
            task_classes,
            environment_ids,
            activation_conditions,
            exclusions,
        )
    )
    if not supplied:
        return None
    updates: dict[str, tuple[str, ...]] = {}
    for name, values in (
        ("project_ids", project_ids),
        ("task_classes", task_classes),
        ("environment_ids", environment_ids),
    ):
        if values is None:
            continue
        normalized = tuple(sorted({item.strip() for item in values if item.strip()}))
        if not normalized:
            raise AutomaticRuntimeError(f"--refine-{name.replace('_', '-')} cannot be empty")
        existing = set(getattr(scope, name))
        if existing and not set(normalized) <= existing:
            raise AutomaticRuntimeError(f"review refinement cannot widen {name}")
        updates[name] = normalized
    for name, values in (
        ("activation_conditions", activation_conditions),
        ("exclusions", exclusions),
    ):
        if values is None:
            continue
        normalized_set = {item.strip() for item in values if item.strip()}
        if not normalized_set:
            raise AutomaticRuntimeError(f"--refine-{name.replace('_', '-')} cannot be empty")
        updates[name] = tuple(sorted({*getattr(scope, name), *normalized_set}))
    return scope.model_copy(update=updates)


class _ConsoleReviewSink(RuntimeReviewSink):
    def enqueue(self, item: RuntimeReviewQueueItem) -> None:
        typer.echo(
            canonical_json(
                {
                    "proposal": _json_review_proposal(item),
                    "queue_id": item.queue_id,
                    "reasons": item.detection.reasons,
                    "scope": _json_scope(item.detection.scope),
                    "status": "review_required",
                }
            )
        )


class _SilentReviewSink(RuntimeReviewSink):
    """Let the durable ledger carry proposals when one cohesive snapshot follows the poll."""

    def enqueue(self, item: RuntimeReviewQueueItem) -> None:
        del item


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _outside_git(path: Path, *, repository_root: Path) -> Path:
    resolved = path.expanduser().resolve()
    root = repository_root.expanduser().resolve()
    if resolved == root or resolved.is_relative_to(root):
        raise ValueError("dogfood state must remain outside the project repository")
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            raise ValueError("dogfood state must remain outside every Git repository")
    return resolved


def _load_config(path: Path) -> CodexDogfoodLocalConfig:
    try:
        raw_config = path.read_text(encoding="utf-8")
    except OSError as error:
        raise AutomaticRuntimeError("Codex dogfood config is invalid") from error

    try:
        untrusted_envelope = json.loads(raw_config)
    except json.JSONDecodeError:
        untrusted_envelope = None
    if isinstance(untrusted_envelope, dict):
        declared_version = untrusted_envelope.get("config_version")
        if (
            isinstance(declared_version, str)
            and declared_version not in _SUPPORTED_DOGFOOD_CONFIG_VERSIONS
        ):
            raise AutomaticRuntimeError(
                "Unsupported Codex dogfood config version "
                f"{declared_version!r}; update the local Temper installation"
            )

    try:
        config = CodexDogfoodLocalConfig.model_validate_json(raw_config, strict=True)
    except ValueError as error:
        raise AutomaticRuntimeError("Codex dogfood config is invalid") from error
    _outside_git(config.state_root, repository_root=config.repository_root)
    return config


def _write_config(path: Path, config: CodexDogfoodLocalConfig) -> None:
    payload = (canonical_json(config) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _replace_config_with_credential_rebind(
    path: Path,
    current: CodexDogfoodLocalConfig,
    updated: CodexDogfoodLocalConfig,
) -> None:
    """Atomically replace config and roll back if an enrolled envelope cannot rebind."""

    credential_store = platform_credential_store(current.state_root)
    enrolled = credential_store.status()
    _write_config(path, updated)
    if enrolled is not None:
        try:
            credential_store.rebind(
                subject_id=current.subject_id,
                current_config_digest=_enrollment_binding_digest(current, enrolled),
                new_config_digest=updated.credential_binding_digest,
                signer_fingerprint=current.signer_identity.key_fingerprint,
            )
        except BaseException:
            _write_config(path, current)
            raise


def _ledger(config: CodexDogfoodLocalConfig) -> AutomaticRuntimeLedger:
    SqliteUnitOfWorkFactory(config.database_path).initialize()
    return AutomaticRuntimeLedger(config.database_path, subject_id=config.subject_id)


def _existing_ledger(config: CodexDogfoodLocalConfig) -> AutomaticRuntimeLedger:
    if not config.database_path.is_file():
        raise AutomaticRuntimeError("preserved predecessor ledger is unavailable")
    return AutomaticRuntimeLedger(config.database_path, subject_id=config.subject_id)


def _gate_lineage_ledgers(
    config: CodexDogfoodLocalConfig,
    predecessor_config_path: Path | None,
) -> tuple[AutomaticRuntimeLedger, ...]:
    receipt_path = config.state_root / "successor-receipt.json"
    if not receipt_path.exists():
        if predecessor_config_path is not None:
            raise AutomaticRuntimeError(
                "--predecessor-config is valid only for a signed successor lineage"
            )
        return (_ledger(config),)
    if predecessor_config_path is None:
        raise AutomaticRuntimeError(
            "successor gate reporting requires --predecessor-config so historical "
            "evidence cannot be omitted"
        )

    try:
        receipt = RuntimeSuccessorReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8"),
            strict=True,
        )
        predecessor = _load_config(predecessor_config_path)
        verify_signed_governance(
            receipt.authorization,
            config.signer_identity,
            effective_at=receipt.created_at,
        )
    except (OSError, ValueError) as error:
        raise AutomaticRuntimeError("successor gate lineage is invalid") from error
    if (
        predecessor.subject_id != config.subject_id
        or predecessor.state_root == config.state_root
        or receipt.subject_id != config.subject_id
        or receipt.predecessor_config_digest != predecessor.credential_binding_digest
        or receipt.predecessor_signer_fingerprint != predecessor.signer_identity.key_fingerprint
        or receipt.successor_signer_fingerprint != config.signer_identity.key_fingerprint
        or receipt.capture_after_epoch_seconds != config.capture_after_epoch_seconds
    ):
        raise AutomaticRuntimeError("successor gate lineage binding changed")
    return (_existing_ledger(predecessor), _ledger(config))


def _combined_gate_report(
    config: CodexDogfoodLocalConfig,
    ledgers: tuple[AutomaticRuntimeLedger, ...],
    *,
    generated_at: datetime,
) -> CodexDogfoodGateReport:
    return build_codex_dogfood_gate_report(
        subject_id=config.subject_id,
        learning_cycles=tuple(chain.from_iterable(item.learning_cycles() for item in ledgers)),
        learning_assessments=tuple(
            chain.from_iterable(item.learning_assessments() for item in ledgers)
        ),
        learning_review_resolutions=tuple(
            chain.from_iterable(item.learning_review_resolutions() for item in ledgers)
        ),
        learning_review_items=tuple(
            chain.from_iterable(item.learning_review_items() for item in ledgers)
        ),
        activations=tuple(chain.from_iterable(item.activations() for item in ledgers)),
        acknowledgements=tuple(
            chain.from_iterable(item.delivery_acknowledgements() for item in ledgers)
        ),
        activation_feedback=tuple(chain.from_iterable(item.feedback() for item in ledgers)),
        generated_at=generated_at,
    )


def _gateway_ledger(config: CodexDogfoodLocalConfig) -> GatewayLedger:
    SqliteUnitOfWorkFactory(config.database_path).initialize()
    return GatewayLedger(config.database_path, subject_id=config.subject_id)


def _runtime_secrets(config: CodexDogfoodLocalConfig) -> RuntimeSecrets:
    store = platform_credential_store(config.state_root)
    metadata = store.status()
    if metadata is None:
        return RuntimeSecrets.from_environment()
    return store.unlock(
        subject_id=config.subject_id,
        config_digest=_enrollment_binding_digest(config, metadata),
        signer_fingerprint=config.signer_identity.key_fingerprint,
    )


def _enrollment_binding_digest(
    config: CodexDogfoodLocalConfig,
    metadata: CredentialEnvelopeMetadataRecord,
) -> Sha256Digest:
    if metadata.config_digest == config.credential_binding_digest:
        return config.credential_binding_digest
    if metadata.config_digest == config.legacy_credential_binding_digest:
        return config.legacy_credential_binding_digest
    if metadata.config_digest == config.prior_full_credential_binding_digest:
        return config.prior_full_credential_binding_digest
    return config.credential_binding_digest


def _raw_store(config: CodexDogfoodLocalConfig) -> LocalRawPayloadStore:
    secrets = _runtime_secrets(config)
    key = secrets.raw_encryption_key(workspace_root=config.repository_root)
    return LocalRawPayloadStore(config.raw_store_path, encryption_key=key)


def _runtime(config: CodexDogfoodLocalConfig) -> AutomaticAdaptationRuntime:
    secrets = _runtime_secrets(config)
    private_key = secrets.private_key(workspace_root=config.repository_root)
    raw_key = secrets.raw_encryption_key(workspace_root=config.repository_root)
    signer = GovernanceSigner(
        private_key,
        identity_id=config.signer_identity.identity_id,
        subject_id=config.subject_id,
    )
    if signer.fingerprint != config.signer_identity.key_fingerprint:
        raise AutomaticRuntimeError("configured signing identity does not match the external key")
    return AutomaticAdaptationRuntime(
        policy=config.policy,
        policy_authorization=config.policy_authorization,
        signer=signer,
        signer_identity=config.signer_identity,
        raw_store=LocalRawPayloadStore(
            config.raw_store_path,
            encryption_key=raw_key,
        ),
    )


def _registration_signer(config: CodexDogfoodLocalConfig) -> GovernanceSigner:
    secrets = _runtime_secrets(config)
    signer = GovernanceSigner(
        secrets.private_key(workspace_root=config.repository_root),
        identity_id=config.signer_identity.identity_id,
        subject_id=config.subject_id,
    )
    if signer.fingerprint != config.signer_identity.key_fingerprint:
        raise AutomaticRuntimeError("configured signing identity does not match the external key")
    return signer


def _verify_current_policy(config: CodexDogfoodLocalConfig, *, effective_at: datetime) -> None:
    verify_signed_governance(
        config.policy_authorization,
        config.signer_identity,
        effective_at=effective_at,
    )
    event = config.policy_authorization
    if (
        event.event_type is not GovernanceEventType.ACTIVATION_DECISION
        or event.target_ref != config.policy.authorization_target_ref
        or event.target_digest != config.policy.content_digest
        or event.decision != "enabled"
        or event.policy_version != config.policy.policy_version
    ):
        raise AutomaticRuntimeError("configured policy authorization binding changed")
    if effective_at < config.policy.effective_at or effective_at >= config.policy.expires_at:
        raise AutomaticRuntimeError("standing policy is not active")


def _next_policy_version(current: str) -> str:
    major, minor, _patch = (int(item) for item in current.split("."))
    return f"{major}.{minor + 1}.0"


def renew_codex_dogfood_consent(
    config_path: Path,
    *,
    confirm_renewal: bool,
) -> CodexDogfoodLocalConfig:
    """Create a newly signed 30-day policy transition after explicit owner confirmation."""

    if not confirm_renewal:
        raise AutomaticRuntimeError("consent renewal requires explicit confirmation")
    config = _load_config(config_path)
    event = config.policy_authorization
    try:
        verify_signed_governance(
            event,
            config.signer_identity,
            effective_at=event.occurred_at,
        )
    except ValueError as error:
        raise AutomaticRuntimeError("current consent authorization is invalid") from error
    if (
        event.event_type is not GovernanceEventType.ACTIVATION_DECISION
        or event.target_ref != config.policy.authorization_target_ref
        or event.target_digest != config.policy.content_digest
        or event.decision != "enabled"
        or event.policy_version != config.policy.policy_version
    ):
        raise AutomaticRuntimeError("current consent authorization binding changed")
    now = _now()
    signer = _registration_signer(config)
    current_identity_expiry = config.signer_identity.expires_at
    renewed_identity = create_signer_identity(
        signer,
        roles=config.signer_identity.roles,
        created_at=config.signer_identity.created_at,
        expires_at=(
            None
            if current_identity_expiry is None
            else max(current_identity_expiry, now + timedelta(days=31))
        ),
    )
    renewed_policy = StandingAutomationPolicy.model_validate(
        config.policy.model_copy(
            update={
                "policy_version": _next_policy_version(config.policy.policy_version),
                "effective_at": now,
                "expires_at": now + timedelta(days=30),
                "previous_policy": config.policy,
            }
        ).model_dump(mode="python"),
        strict=True,
    )
    authorization = sign_governance_event(
        {
            "event_id": f"renew-{config.subject_id}-{int(now.timestamp())}",
            "subject_id": config.subject_id,
            "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
            "target_ref": renewed_policy.authorization_target_ref,
            "target_digest": renewed_policy.content_digest,
            "decision": "enabled",
            "reason": "Explicitly renew bounded local adaptation for 30 days.",
            "policy_version": renewed_policy.policy_version,
            "occurred_at": now.isoformat(),
        },
        signer,
    )
    updated = CodexDogfoodLocalConfig.model_validate(
        config.model_copy(
            update={
                "policy": renewed_policy,
                "policy_authorization": authorization,
                "signer_identity": renewed_identity,
            }
        ).model_dump(mode="python"),
        strict=True,
    )
    _replace_config_with_credential_rebind(config_path, config, updated)
    return updated


def _project(
    config: CodexDogfoodLocalConfig,
    workspace: Path,
) -> CodexDogfoodProjectConfig:
    resolved = workspace.expanduser().resolve()
    for project in config.projects:
        root = project.root.expanduser().resolve()
        if resolved == root or resolved.is_relative_to(root):
            return project
    raise AutomaticRuntimeError("target workspace is outside the dogfood project allowlist")


def _context(
    config: CodexDogfoodLocalConfig,
    project: CodexDogfoodProjectConfig,
    *,
    evaluated_at: datetime,
) -> RuntimeProjectionContext:
    return RuntimeProjectionContext(
        known_dimensions=(
            ScopeDimension.PROJECT_IDS,
            ScopeDimension.SUBJECT_IDS,
            ScopeDimension.TARGET_FAMILIES,
        ),
        target_profile_id="codex",
        subject_id=config.subject_id,
        project_id=project.project_id,
        target_family="codex",
        evaluated_at=evaluated_at,
    )


@contextmanager
def _isolated_target_home(config: CodexDogfoodLocalConfig) -> Iterator[Path]:
    auth = config.effective_target_codex_home / "auth.json"
    if not auth.is_file():
        raise AutomaticRuntimeError("saved ChatGPT auth file is unavailable")
    with tempfile.TemporaryDirectory(
        prefix="codex-target-",
        dir=config.state_root,
    ) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        target = root / "auth.json"
        shutil.copyfile(auth, target)
        target.chmod(0o600)
        (root / "config.toml").write_text(
            (
                'approval_policy = "never"\n'
                'sandbox_mode = "workspace-write"\n\n'
                "[windows]\n"
                f'sandbox = "{config.gateway_windows_sandbox}"\n'
            ),
            encoding="utf-8",
        )
        yield root


@dogfood_app.command("init")
def initialize_codex_dogfood(
    state_root: Annotated[
        Path,
        typer.Option("--state-root", file_okay=False, resolve_path=True),
    ],
    repository_root: Annotated[
        Path,
        typer.Option(
            "--repository-root",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    project_root: Annotated[
        Path,
        typer.Option(
            "--project-root",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    codex_executable: Annotated[
        Path,
        typer.Option(
            "--codex-executable",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    source_codex_home: Annotated[
        Path,
        typer.Option(
            "--source-codex-home",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    subject_id: Annotated[str, typer.Option("--subject-id")],
    project_id: Annotated[str, typer.Option("--project-id")],
    source_roots: Annotated[
        list[Path] | None,
        typer.Option(
            "--source-root",
            exists=True,
            file_okay=False,
            resolve_path=True,
            help=(
                "Repeatable Codex source-CWD alias for the governed project; "
                "defaults to --project-root."
            ),
        ),
    ] = None,
    identity_id: Annotated[str, typer.Option("--identity-id")] = "acl-runtime-owner",
    credential_mode: Annotated[
        Literal["managed", "external"],
        typer.Option(
            "--credential-mode",
            help=(
                "managed generates invisible same-user DPAPI credentials; external preserves "
                "the legacy ACLAB_* environment workflow."
            ),
        ),
    ] = "managed",
    runtime_pin: Annotated[
        Path,
        typer.Option(
            "--runtime-pin",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = DEFAULT_DOGFOOD_RUNTIME_LOCK,
    windows_interop: Annotated[
        bool,
        typer.Option(
            "--windows-interop",
            help="Launch a pinned Windows .exe from WSL and translate CODEX_HOME paths.",
        ),
    ] = False,
    target_codex_executable: Annotated[
        Path | None,
        typer.Option(
            "--target-codex-executable",
            exists=True,
            dir_okay=False,
            resolve_path=True,
            help="Optional separate pinned Codex executable for fresh target sessions.",
        ),
    ] = None,
    target_codex_home: Annotated[
        Path | None,
        typer.Option(
            "--target-codex-home",
            exists=True,
            file_okay=False,
            resolve_path=True,
            help="Saved ChatGPT-auth home for the optional separate target runtime.",
        ),
    ] = None,
    target_runtime_pin: Annotated[
        Path | None,
        typer.Option(
            "--target-runtime-pin",
            exists=True,
            dir_okay=False,
            resolve_path=True,
            help="Runtime lock for the optional separate target executable.",
        ),
    ] = None,
    target_windows_interop: Annotated[
        bool,
        typer.Option(
            "--target-windows-interop",
            help="Launch the separately configured target as a Windows executable from WSL.",
        ),
    ] = False,
) -> None:
    """Create one bounded policy with automatic same-user credentials by default."""

    try:
        repository = repository_root.resolve()
        state = _outside_git(state_root, repository_root=repository)
        if state.exists() and any(state.iterdir()):
            raise ValueError("dogfood state root already contains files")
        state.mkdir(parents=True, exist_ok=True)
        state.chmod(0o700)
        now = _now()
        secrets = (
            RuntimeSecrets.generate_managed()
            if credential_mode == "managed"
            else RuntimeSecrets.from_environment()
        )
        private_key = secrets.private_key(workspace_root=repository)
        secrets.raw_encryption_key(workspace_root=repository)
        signer = GovernanceSigner(
            private_key,
            identity_id=identity_id,
            subject_id=subject_id,
        )
        identity = create_signer_identity(
            signer,
            roles=(
                SignerRole.ACTIVATION,
                SignerRole.CONSENT,
                SignerRole.CUSTODY,
                SignerRole.RELEASE,
                SignerRole.REVIEW,
            ),
            created_at=now,
            expires_at=now + timedelta(days=31),
        )
        scope = Scope(
            subject_ids=(subject_id,),
            project_ids=(project_id,),
            target_families=("codex",),
        )
        policy = StandingAutomationPolicy(
            policy_id=f"{subject_id}-codex-dogfood",
            subject_id=subject_id,
            scope=scope,
            permitted_uses=(
                PermittedUse.AUDIT,
                PermittedUse.CONSTRUCTION,
                PermittedUse.PROMOTION,
                PermittedUse.TARGET_DELIVERY,
            ),
            allowed_routes=(
                ArtifactRoute.EXAMPLE,
                ArtifactRoute.MEMORY,
                ArtifactRoute.PREFERENCE,
                ArtifactRoute.PROCEDURE,
                ArtifactRoute.PROMPT_RULE,
            ),
            allowed_target_families=("codex",),
            effective_at=now,
            expires_at=now + timedelta(days=30),
        )
        authorization = sign_governance_event(
            {
                "event_id": f"enable-{subject_id}-codex-dogfood",
                "subject_id": subject_id,
                "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
                "target_ref": policy.authorization_target_ref,
                "target_digest": policy.content_digest,
                "decision": "enabled",
                "reason": "Enable bounded local Codex dogfood learning with notices and undo.",
                "policy_version": policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        pins = load_dogfood_runtime_pins(runtime_pin)
        with open_codex_dogfood(
            executable=codex_executable,
            codex_home=source_codex_home,
            pin=pins.codex,
            windows_interop=windows_interop,
        ):
            pass
        target_endpoint_parts = (
            target_codex_executable,
            target_codex_home,
            target_runtime_pin,
        )
        if any(item is not None for item in target_endpoint_parts) and not all(
            item is not None for item in target_endpoint_parts
        ):
            raise ValueError("separate target requires executable, Codex home, and runtime pin")
        if target_windows_interop and target_codex_executable is None:
            raise ValueError("--target-windows-interop requires a separate target executable")
        if target_codex_executable is not None:
            assert target_codex_home is not None
            assert target_runtime_pin is not None
            target_pins = load_dogfood_runtime_pins(target_runtime_pin)
            with open_codex_dogfood(
                executable=target_codex_executable,
                codex_home=target_codex_home,
                pin=target_pins.codex,
                windows_interop=target_windows_interop,
            ):
                pass
        normalized_source_roots = tuple(
            sorted(
                {
                    item.resolve()
                    for item in (source_roots if source_roots is not None else [project_root])
                },
                key=str,
            )
        )
        config = CodexDogfoodLocalConfig(
            subject_id=subject_id,
            repository_root=repository,
            state_root=state,
            database_path=state / "runtime.sqlite3",
            raw_store_path=state / "raw",
            source_codex_home=source_codex_home.resolve(),
            codex_executable=codex_executable.resolve(),
            windows_interop=windows_interop,
            runtime_pin_path=runtime_pin.resolve(),
            capture_after_epoch_seconds=int(now.timestamp()),
            policy=policy,
            policy_authorization=authorization,
            signer_identity=identity,
            projects=(
                CodexDogfoodProjectConfig(
                    project_id=project_id,
                    root=project_root.resolve(),
                    scope=scope,
                    source_roots=normalized_source_roots,
                ),
            ),
            target_codex_home=(None if target_codex_home is None else target_codex_home.resolve()),
            target_codex_executable=(
                None if target_codex_executable is None else target_codex_executable.resolve()
            ),
            target_windows_interop=(
                None if target_codex_executable is None else target_windows_interop
            ),
            target_runtime_pin_path=(
                None if target_runtime_pin is None else target_runtime_pin.resolve()
            ),
        )
        config_path = state / "config.json"
        config_path.write_text(canonical_json(config) + "\n", encoding="utf-8")
        config_path.chmod(0o600)
        if credential_mode == "managed":
            platform_credential_store(config.state_root).enroll(
                secrets,
                subject_id=config.subject_id,
                config_digest=config.credential_binding_digest,
                signer_fingerprint=config.signer_identity.key_fingerprint,
            )
        database = _ledger(config)
        database.initialize(initial_runtime_state(policy))
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(str(config_path))


@project_app.command("list")
def list_codex_dogfood_projects(config_path: ConfigOption) -> None:
    """List exact project boundaries and prospective cutoffs without reading Codex tasks."""

    try:
        config = _load_config(config_path)
        payload = {
            "access_mode": "read_only_completed_tasks",
            "modifies_existing_threads": False,
            "modifies_source_repositories": False,
            "projects": [
                {
                    "capture_after_epoch_seconds": (
                        config.capture_after_epoch_seconds
                        if project.capture_after_epoch_seconds is None
                        else project.capture_after_epoch_seconds
                    ),
                    "project_id": project.project_id,
                    "project_root": str(project.root),
                    "registration_digest": (
                        None
                        if project.registration is None
                        else str(project.registration.content_digest)
                    ),
                    "source_roots": [str(item) for item in project.effective_source_roots],
                }
                for project in config.projects
            ],
        }
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(payload))


@project_app.command("preview")
def preview_codex_dogfood_project(
    config_path: ConfigOption,
    project_root: Annotated[
        Path,
        typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True),
    ],
    source_roots: Annotated[
        list[Path] | None,
        typer.Option(
            "--source-root",
            exists=True,
            file_okay=False,
            resolve_path=True,
            help="Repeatable exact Codex CWD root; defaults to --project-root.",
        ),
    ] = None,
) -> None:
    """Preview content-free thread counts at a prospective cutoff using only thread/list."""

    try:
        config = _load_config(config_path)
        cutoff = int(_now().timestamp())
        roots = tuple(
            sorted(
                {
                    item.resolve()
                    for item in (source_roots if source_roots is not None else [project_root])
                },
                key=str,
            )
        )
        pins = load_dogfood_runtime_pins(config.runtime_pin_path)
        with open_codex_dogfood(
            executable=config.codex_executable,
            codex_home=config.source_codex_home,
            pin=pins.codex,
            windows_interop=config.windows_interop,
        ) as (_verified, schemas, rpc):
            preview: CodexProjectPreview = preview_codex_project(
                rpc,
                schemas=schemas,
                source_roots=roots,
                capture_after_epoch_seconds=cutoff,
            )
        payload = {
            **asdict(preview),
            "access_mode": "metadata_only_thread_list",
            "modifies_existing_threads": False,
            "modifies_source_repository": False,
            "project_root": str(project_root.resolve()),
            "source_roots": [str(item) for item in roots],
        }
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(payload))


@project_app.command("register")
def register_codex_dogfood_project(
    config_path: ConfigOption,
    project_id: Annotated[str, typer.Option("--project-id")],
    project_root: Annotated[
        Path,
        typer.Option("--project-root", exists=True, file_okay=False, resolve_path=True),
    ],
    source_roots: Annotated[
        list[Path] | None,
        typer.Option(
            "--source-root",
            exists=True,
            file_okay=False,
            resolve_path=True,
            help="Repeatable exact Codex CWD root; defaults to --project-root.",
        ),
    ] = None,
    confirm_prospective: Annotated[
        bool,
        typer.Option(
            "--confirm-prospective",
            help="Confirm that all tasks created before registration remain ineligible.",
        ),
    ] = False,
) -> None:
    """Append one signed read-only project registration without reading task content."""

    try:
        if not confirm_prospective:
            raise AutomaticRuntimeError("registration requires --confirm-prospective")
        config = _load_config(config_path)
        if project_id in {item.project_id for item in config.projects}:
            raise AutomaticRuntimeError("project ID is already registered")
        now = _now()
        _verify_current_policy(config, effective_at=now)
        roots = tuple(
            sorted(
                {
                    item.resolve()
                    for item in (source_roots if source_roots is not None else [project_root])
                },
                key=str,
            )
        )
        expanded_scope = config.policy.scope.model_copy(
            update={"project_ids": tuple(sorted((*config.policy.scope.project_ids, project_id)))}
        )
        amended_policy = StandingAutomationPolicy.model_validate(
            config.policy.model_copy(
                update={
                    "policy_version": _next_policy_version(config.policy.policy_version),
                    "scope": expanded_scope,
                    "effective_at": now,
                    "previous_policy": config.policy,
                }
            ).model_dump(mode="python"),
            strict=True,
        )
        signer = _registration_signer(config)
        policy_authorization = sign_governance_event(
            {
                "event_id": f"enable-{project_id}-{int(now.timestamp())}",
                "subject_id": config.subject_id,
                "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
                "target_ref": amended_policy.authorization_target_ref,
                "target_digest": amended_policy.content_digest,
                "decision": "enabled",
                "reason": "Add one prospective read-only Codex evidence project.",
                "policy_version": amended_policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        cutoff = int(now.timestamp())
        registration_id = f"project-registration-{project_id}-{cutoff}"
        registration = CodexProjectRegistration(
            registration_id=registration_id,
            subject_id=config.subject_id,
            project_id=project_id,
            project_root=str(project_root.resolve()),
            source_roots=tuple(str(item) for item in roots),
            capture_after_epoch_seconds=cutoff,
            standing_policy_digest=amended_policy.content_digest,
            registered_at=now,
        )
        registration_authorization = sign_governance_event(
            {
                "event_id": f"authorize-{registration_id}",
                "subject_id": config.subject_id,
                "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
                "target_ref": f"codex-project-registration:{registration_id}",
                "target_digest": registration.content_digest,
                "decision": "registered_read_only",
                "reason": "Authorize prospective read-only capture without modifying source tasks.",
                "policy_version": amended_policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        project_scope = Scope(
            subject_ids=(config.subject_id,),
            project_ids=(project_id,),
            target_families=("codex",),
        )
        project = CodexDogfoodProjectConfig(
            project_id=project_id,
            root=project_root.resolve(),
            scope=project_scope,
            source_roots=roots,
            capture_after_epoch_seconds=cutoff,
            registration=registration,
            registration_authorization=registration_authorization,
        )
        updated = CodexDogfoodLocalConfig.model_validate(
            config.model_copy(
                update={
                    "config_version": "1.4.0",
                    "policy": amended_policy,
                    "policy_authorization": policy_authorization,
                    "projects": tuple(
                        sorted((*config.projects, project), key=lambda item: item.project_id)
                    ),
                }
            ).model_dump(mode="python"),
            strict=True,
        )
        _replace_config_with_credential_rebind(config_path, config, updated)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "capture_after_epoch_seconds": cutoff,
                "modifies_existing_threads": False,
                "modifies_source_repository": False,
                "policy_digest": str(amended_policy.content_digest),
                "project_id": project_id,
                "registration_digest": str(registration.content_digest),
                "status": "registered_read_only",
            }
        )
    )


def _execute_poll(
    config: CodexDogfoodLocalConfig,
    *,
    limit: int,
    review_sink: RuntimeReviewSink,
    notice_sink: RuntimeNoticeSink,
) -> CodexDogfoodPickupReceipt:
    runtime = _runtime(config)
    ledger = _ledger(config)
    pins = load_dogfood_runtime_pins(config.runtime_pin_path)
    with (
        tempfile.TemporaryDirectory(
            prefix="semantic-feedback-",
            dir=config.state_root,
        ) as semantic_workspace,
        open_codex_dogfood(
            executable=config.codex_executable,
            codex_home=config.source_codex_home,
            pin=pins.codex,
            windows_interop=config.windows_interop,
            experimental_api=(config.feedback_detector_mode is not FeedbackDetectorMode.GRAMMAR),
        ) as (verified, schemas, rpc),
    ):
        source = CodexDogfoodInteractionSource(
            rpc,
            subject_id=config.subject_id,
            source_version=verified.version,
            source_schema_digest=verified.schema_bundle_digest,
            schemas=schemas,
            projects=tuple(
                CodexProjectScope(
                    root=root,
                    scope=item.scope,
                    capture_after_epoch_seconds=(
                        config.capture_after_epoch_seconds
                        if item.capture_after_epoch_seconds is None
                        else item.capture_after_epoch_seconds
                    ),
                )
                for item in config.projects
                for root in item.effective_source_roots
            ),
        )
        return CodexDogfoodHost(
            runtime=runtime,
            initial_state=initial_runtime_state(config.policy),
            ledger=ledger,
            source=source,
            review_sink=review_sink,
            notice_sink=notice_sink,
            detector_mode=config.feedback_detector_mode,
            semantic_interpreter=(
                None
                if config.feedback_detector_mode is FeedbackDetectorMode.GRAMMAR
                else CodexSemanticFeedbackInterpreter(
                    rpc,
                    schemas=schemas,
                    runtime=verified,
                    workspace_root=Path(semantic_workspace),
                    model=config.semantic_model,
                    reasoning_effort=config.semantic_reasoning_effort,
                )
            ),
        ).run_once(limit=limit)


def execute_codex_feedback_poll(
    config_path: Path,
    *,
    limit: int = 25,
    quiet: bool = True,
) -> CodexDogfoodPickupReceipt:
    """Run one bounded pickup through the existing governed source boundary."""

    if not 1 <= limit <= 100:
        raise AutomaticRuntimeError("poll limit must be between 1 and 100")
    config = _load_config(config_path)
    return _execute_poll(
        config,
        limit=limit,
        review_sink=_SilentReviewSink() if quiet else _ConsoleReviewSink(),
        notice_sink=_durable_notice_sink(config) if quiet else _ConsoleNoticeSink(),
    )


@dogfood_app.command("poll")
def poll_codex_feedback(
    config_path: ConfigOption,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 25,
) -> None:
    """Pick up new interactive user messages and commit the cursor after local notices."""

    try:
        receipt = execute_codex_feedback_poll(config_path, limit=limit, quiet=False)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(asdict(receipt)))


def execute_fresh_codex_task(
    config_path: Path,
    *,
    task: str,
    workspace: Path,
    activation_id: str | None = None,
) -> FreshCodexTaskResult:
    """Deliver the current scoped release once through the governed target launcher."""

    config = _load_config(config_path)
    runtime = _runtime(config)
    ledger = _ledger(config)
    ledger.initialize(initial_runtime_state(config.policy))
    state = ledger.current()
    if state is None or state.release is None:
        raise AutomaticRuntimeError("no governed adaptation release is available")
    unresolved = tuple(
        item.activation_id
        for item in ledger.activations()
        if ledger.delivery_acknowledgement(item.activation_id) is None
    )
    if unresolved:
        raise AutomaticRuntimeError(
            "an earlier activation has no delivery acknowledgement: " + ", ".join(unresolved)
        )
    now = _now()
    project = _project(config, workspace)
    normalized_task = task.strip()
    if not normalized_task:
        raise AutomaticRuntimeError("target task must not be empty")
    chosen_id = activation_id or (
        f"dogfood-{now.strftime('%Y%m%dT%H%M%S')}-"
        f"{str(sha256_text(normalized_task)).removeprefix('sha256:')[:12]}"
    )
    prepared = runtime.activate(
        activation_id=chosen_id,
        task_ref=TaskRecordRef(
            record_id=f"task-{chosen_id}",
            record_version="1.0.0",
        ),
        state=state,
        context=_context(config, project, evaluated_at=now),
        target_task=normalized_task,
        activated_at=now,
    )
    pins = load_dogfood_runtime_pins(config.effective_target_runtime_pin_path)
    with (
        _isolated_target_home(config) as target_home,
        open_codex_dogfood(
            executable=config.effective_target_codex_executable,
            codex_home=target_home,
            pin=pins.codex,
            windows_interop=config.effective_target_windows_interop,
            experimental_api=True,
        ) as (_verified, schemas, rpc),
    ):
        if not ledger.append_activation(prepared):
            raise AutomaticRuntimeError("activation already exists; automatic relaunch is refused")
        result = CodexDogfoodSessionLauncher(rpc, schemas=schemas).launch(
            prepared,
            workspace=workspace,
            ephemeral=True,
        )
        ledger.acknowledge_delivery(result.acknowledgement)
    return FreshCodexTaskResult(
        activation_id=chosen_id,
        material_utf8_bytes=prepared.task.receipt.material_utf8_bytes,
        status=result.acknowledgement.status,
        final_message=result.final_message,
    )


@dogfood_app.command("run")
def run_fresh_codex_task(
    config_path: ConfigOption,
    task: Annotated[str, typer.Argument(help="The exact new task for a fresh Codex session.")],
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    activation_id: Annotated[
        str | None,
        typer.Option("--activation-id", help="Stable retry/audit identifier."),
    ] = None,
) -> None:
    """Deliver the current scoped release once to a fresh isolated Codex session."""

    try:
        result = execute_fresh_codex_task(
            config_path,
            task=task,
            workspace=workspace,
            activation_id=activation_id,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "activation_id": result.activation_id,
                "material_utf8_bytes": result.material_utf8_bytes,
                "status": result.status,
            }
        )
    )
    if result.final_message:
        typer.echo(result.final_message)
    if result.status != "completed":
        raise typer.Exit(code=1)


@dogfood_app.command("detector-mode")
def configure_feedback_detector(
    config_path: ConfigOption,
    mode: Annotated[FeedbackDetectorMode, typer.Argument()],
    expected_current: Annotated[
        FeedbackDetectorMode,
        typer.Option(
            "--expected-current",
            help="Fail if another process or operator already changed the serving mode.",
        ),
    ],
    evaluation_digest: Annotated[
        str | None,
        typer.Option(
            "--evaluation-digest",
            help="Required frozen semantic evaluation digest for calibrated promotion.",
        ),
    ] = None,
) -> None:
    """Atomically change grammar/shadow/review/calibrated semantic serving."""

    try:
        config = _load_config(config_path)
        if config.feedback_detector_mode is not expected_current:
            raise AutomaticRuntimeError("feedback detector serving mode changed concurrently")
        if mode is FeedbackDetectorMode.CALIBRATED and evaluation_digest is None:
            raise AutomaticRuntimeError(
                "calibrated semantic serving requires a frozen evaluation digest"
            )
        if mode is not FeedbackDetectorMode.CALIBRATED and evaluation_digest is not None:
            raise AutomaticRuntimeError(
                "evaluation digest is accepted only for calibrated semantic serving"
            )
        updated = config.model_copy(
            update={
                "config_version": (
                    config.config_version
                    if config.config_version in {"1.3.0", "1.4.0"}
                    else "1.2.0"
                ),
                "feedback_detector_mode": mode,
                "semantic_promotion_evaluation_digest": evaluation_digest,
            }
        )
        updated = CodexDogfoodLocalConfig.model_validate(
            updated.model_dump(mode="python"),
            strict=True,
        )
        _write_config(config_path, updated)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "feedback_detector_mode": updated.feedback_detector_mode.value,
                "semantic_model": updated.semantic_model,
                "semantic_promotion_evaluation_digest": (
                    updated.semantic_promotion_evaluation_digest
                ),
            }
        )
    )


@dogfood_app.command("detector-evaluate")
def evaluate_feedback_detector(
    config_path: ConfigOption,
    corpus_path: Annotated[
        Path,
        typer.Argument(
            help="Frozen public synthetic semantic-feedback corpus.",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    split: Annotated[
        str,
        typer.Option("--split", help="Evaluate calibration or holdout cases."),
    ] = "calibration",
    adjudication_path: Annotated[
        Path | None,
        typer.Option(
            "--adjudication",
            help="Calibration-only ground-truth adjudication bound to the source corpus.",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="Write the raw-free report envelope to this file instead of standard output.",
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Run one isolated subscription-backed semantic batch and emit a raw-free report."""

    try:
        if split not in {"calibration", "holdout"}:
            raise AutomaticRuntimeError("semantic evaluation split must be calibration or holdout")
        selected_split = cast(SemanticEvaluationSplit, split)
        config = _load_config(config_path)
        source_corpus = load_semantic_feedback_corpus(corpus_path)
        adjudication = (
            None
            if adjudication_path is None
            else load_semantic_corpus_adjudication(adjudication_path)
        )
        corpus = (
            source_corpus
            if adjudication is None
            else apply_semantic_corpus_adjudication(source_corpus, adjudication)
        )
        if adjudication is not None and selected_split == "holdout":
            raise AutomaticRuntimeError(
                "calibration adjudication cannot be supplied to a holdout evaluation"
            )
        cases = corpus.select(selected_split)
        observations = tuple(
            InteractionObservation(
                observation_id=case.case_id,
                subject_id=config.subject_id,
                task_ref=TaskRecordRef(
                    record_id=f"semantic-evaluation-{case.case_id}",
                    record_version="1.0.0",
                ),
                turn_id=f"semantic-evaluation-turn-{case.case_id}",
                actor=ActorRef(actor_id=config.subject_id, kind=ActorKind.USER),
                source_class=SourceClass.SYNTHETIC,
                text=case.text,
                scope=config.policy.scope,
                observed_at=corpus.frozen_at,
                source_system="local_interaction_runtime",
                source_version=corpus.corpus_version,
                source_schema_digest=corpus.content_digest,
            )
            for case in cases
        )
        pins = load_dogfood_runtime_pins(config.runtime_pin_path)
        with (
            tempfile.TemporaryDirectory(
                prefix="semantic-evaluation-",
                dir=config.state_root,
            ) as semantic_workspace,
            open_codex_dogfood(
                executable=config.codex_executable,
                codex_home=config.source_codex_home,
                pin=pins.codex,
                windows_interop=config.windows_interop,
                experimental_api=True,
            ) as (verified, schemas, rpc),
        ):
            interpretations = CodexSemanticFeedbackInterpreter(
                rpc,
                schemas=schemas,
                runtime=verified,
                workspace_root=Path(semantic_workspace),
                model=config.semantic_model,
                reasoning_effort=config.semantic_reasoning_effort,
            ).interpret_batch(observations)
        report = evaluate_semantic_feedback(
            corpus,
            split=selected_split,
            interpretations=interpretations,
            source_corpus_digest=source_corpus.content_digest,
            adjudication_digest=(None if adjudication is None else adjudication.content_digest),
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    envelope = canonical_json(
        {
            "report": report.model_dump(mode="json"),
            "report_digest": report.content_digest,
        }
    )
    if output_path is None:
        typer.echo(envelope)
        return
    output_path.write_text(envelope + "\n", encoding="utf-8", newline="\n")
    typer.echo(canonical_json({"output": str(output_path), "report_digest": report.content_digest}))


@dogfood_app.command("status")
def show_codex_dogfood_status(config_path: ConfigOption) -> None:
    """Show state, review, activation, cursor, and feedback counts without raw payloads."""

    try:
        config = _load_config(config_path)
        ledger = _ledger(config)
        state = ledger.current()
        activations = ledger.activations()
        unresolved = tuple(
            item.activation_id
            for item in activations
            if ledger.delivery_acknowledgement(item.activation_id) is None
        )
        payload = {
            "active_artifact_count": (
                0
                if state is None or state.release is None
                else len(state.release.governed_release.active_artifacts)
            ),
            "activation_count": len(activations),
            "feedback_count": len(ledger.feedback()),
            "feedback_detector_mode": config.feedback_detector_mode.value,
            "generation": 0 if state is None else state.generation,
            "learning_cycle_count": len(ledger.learning_cycles()),
            "learning_assessment_count": len(ledger.learning_assessments()),
            "review_count": len(ledger.learning_review_items()),
            "resolved_review_count": len(ledger.learning_review_resolutions()),
            "unresolved_review_count": len(ledger.unresolved_learning_review_items()),
            "source_checkpointed": (
                ledger.current_checkpoint("codex-dogfood-interactive") is not None
            ),
            "unresolved_activation_ids": unresolved,
        }
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(payload))


def _watcher_is_active(config: CodexDogfoodLocalConfig, *, observed_at: datetime) -> bool:
    """Return true only for a current same-subject lease whose owner process still exists."""

    lease_path = config.state_root / "watcher-lease.json"
    if not lease_path.exists():
        return False
    try:
        lease = RuntimeWatcherLease.model_validate_json(lease_path.read_text(encoding="utf-8"))
        if lease.subject_id != config.subject_id or lease.expires_at <= observed_at:
            return False
        os.kill(lease.owner_pid, 0)
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def load_terminal_alpha_snapshot(
    config_path: Path,
    *,
    predecessor_config_path: Path | None = None,
    poll_now: bool = False,
    limit: int = 25,
) -> tuple[TerminalAlphaSnapshot, CodexDogfoodPickupReceipt | None]:
    """Load one governed raw-free product snapshot for any presentation surface."""

    if not 1 <= limit <= 100:
        raise AutomaticRuntimeError("poll limit must be between 1 and 100")
    config = _load_config(config_path)
    gate_ledgers = _gate_lineage_ledgers(config, predecessor_config_path)
    pickup = None
    if poll_now:
        pickup = _execute_poll(
            config,
            limit=limit,
            review_sink=_SilentReviewSink(),
            notice_sink=_durable_notice_sink(config),
        )
    observed_at = _now()
    ledger = _ledger(config)
    ledger.initialize(initial_runtime_state(config.policy))
    state = ledger.current()
    if state is None:
        raise AutomaticRuntimeError("Temper runtime state is unavailable")
    review_mode = build_review_mode_dogfood_snapshot(
        ledger,
        subject_id=config.subject_id,
        generated_at=observed_at,
        detector_mode=config.feedback_detector_mode,
        credential_enrolled=platform_credential_store(config.state_root).status() is not None,
        watcher_active=_watcher_is_active(config, observed_at=observed_at),
    )
    review_mode = review_mode.model_copy(
        update={
            "gate": _combined_gate_report(
                config,
                gate_ledgers,
                generated_at=observed_at,
            )
        }
    )
    configured_project_ids = (
        tuple(item.project_id for item in config.projects)
        if hasattr(config, "projects")
        else config.policy.scope.project_ids
    )
    terminal = build_terminal_alpha_snapshot(
        review_mode,
        state=state,
        configured_project_ids=configured_project_ids,
    )
    return terminal, pickup


@dogfood_app.command("daily")
def show_review_mode_daily_loop(
    config_path: ConfigOption,
    predecessor_config_path: PredecessorConfigOption = None,
    poll_now: Annotated[
        bool,
        typer.Option(
            "--poll-now",
            help="Run one bounded source pickup before producing the raw-free action snapshot.",
        ),
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 25,
) -> None:
    """Show Temper's cohesive review-mode action queue and longitudinal product measures."""

    try:
        terminal, pickup = load_terminal_alpha_snapshot(
            config_path,
            predecessor_config_path=predecessor_config_path,
            poll_now=poll_now,
            limit=limit,
        )
        snapshot = terminal.review_mode
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "pickup": None if pickup is None else asdict(pickup),
                "snapshot": snapshot.model_dump(mode="json", round_trip=True),
                "snapshot_digest": str(snapshot.content_digest),
            }
        )
    )


@dogfood_app.command("review")
def show_codex_dogfood_review(config_path: ConfigOption) -> None:
    """List unresolved normalized proposals without exposing supporting raw text."""

    try:
        config = _load_config(config_path)
        ledger = _ledger(config)
        items = ledger.unresolved_learning_review_items()
        resolved_count = len(ledger.learning_review_resolutions())
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "items": [
                    {
                        "queue_id": item.queue_id,
                        "cycle_id": item.cycle_id,
                        "proposal": _json_review_proposal(item),
                        "reasons": item.detection.reasons,
                        "status": "unresolved",
                    }
                    for item in items
                ],
                "resolved_count": resolved_count,
                "unresolved_count": len(items),
            }
        )
    )


def resolve_codex_dogfood_review(
    config_path: Path,
    *,
    queue_id: str,
    decision: ApprovalDecision,
    proposal_digest: str,
    confirm_future_use: bool = False,
    refine_project_id: list[str] | None = None,
    refine_task_class: list[str] | None = None,
    refine_environment_id: list[str] | None = None,
    refine_activation_condition: list[str] | None = None,
    refine_exclusion: list[str] | None = None,
) -> dict[str, object]:
    """Resolve one exact review through the governed runtime service."""

    _validate_review_decision_intent(decision, confirm_future_use=confirm_future_use)
    config = _load_config(config_path)
    ledger = _ledger(config)
    matches = tuple(item for item in ledger.learning_review_items() if item.queue_id == queue_id)
    if len(matches) != 1:
        raise AutomaticRuntimeError("review decision requires one exact queue item")
    item = matches[0]
    if proposal_digest != str(item.detection.content_digest):
        raise AutomaticRuntimeError("review proposal digest changed")
    refined_scope = _review_refined_scope(
        item.detection.scope,
        project_ids=refine_project_id,
        task_classes=refine_task_class,
        environment_ids=refine_environment_id,
        activation_conditions=refine_activation_condition,
        exclusions=refine_exclusion,
    )
    if refined_scope is not None and decision is not ApprovalDecision.APPROVED:
        raise AutomaticRuntimeError("scope refinement requires an approved review decision")
    existing = ledger.learning_review_resolution(queue_id)
    if existing is not None:
        existing_scope = (
            None if existing.scope_refinement is None else existing.scope_refinement.refined_scope
        )
        if (
            existing.decision is not decision
            or existing.queue_digest != item.content_digest
            or existing_scope != refined_scope
        ):
            raise AutomaticRuntimeError("review item already has another immutable decision")
        resolution = existing
        state = ledger.current()
        if state is None:
            raise AutomaticRuntimeError("review decision state is unavailable")
    else:
        cycle = ledger.learning_cycle(item.cycle_id)
        state = ledger.current()
        if cycle is None or state is None:
            raise AutomaticRuntimeError("review decision source state is unavailable")
        result = _runtime(config).resolve_review(
            item,
            cycle,
            state=state,
            decision=decision,
            resolved_at=_now(),
            refined_scope=refined_scope,
        )
        ledger.append_learning_review_resolution(
            result.resolution,
            result.state,
            release_event=result.release_event,
        )
        resolution = result.resolution
        state = result.state
    active_artifact_ids = (
        ()
        if state.release is None
        else tuple(
            artifact.artifact_ref.record_id
            for artifact in state.release.governed_release.active_artifacts
        )
    )
    return {
        "active_artifact_ids": active_artifact_ids,
        "assessment": resolution.assessment.outcome.value,
        "decision": resolution.decision.value,
        "future_use_authorized": resolution.decision is ApprovalDecision.APPROVED,
        "generation": state.generation,
        "queue_id": resolution.queue_id,
        "scope_refinement": (
            None
            if resolution.scope_refinement is None
            else {
                "digest": str(resolution.scope_refinement.content_digest),
                "refined_scope": _json_scope(resolution.scope_refinement.refined_scope),
            }
        ),
        "resolution_digest": str(resolution.content_digest),
        "resolution_id": resolution.resolution_id,
    }


@dogfood_app.command("review-decide")
def decide_codex_dogfood_review(
    config_path: ConfigOption,
    queue_id: Annotated[str, typer.Argument(help="Exact unresolved review queue item.")],
    decision: Annotated[ApprovalDecision, typer.Argument()],
    proposal_digest: Annotated[
        str,
        typer.Option(
            "--proposal-digest",
            help="Exact proposal digest shown by `runtime review`.",
        ),
    ],
    confirm_future_use: Annotated[
        bool,
        typer.Option(
            "--confirm-future-use",
            help=(
                "Required for approval: explicitly authorize this behavior for later sessions, "
                "not only the current chat."
            ),
        ),
    ] = False,
    refine_project_id: Annotated[
        list[str] | None,
        typer.Option(
            "--refine-project-id",
            help="Approve only for these registered projects; repeat for multiple values.",
        ),
    ] = None,
    refine_task_class: Annotated[
        list[str] | None,
        typer.Option(
            "--refine-task-class",
            help="Approve only for these task classes; repeat the option for multiple values.",
        ),
    ] = None,
    refine_environment_id: Annotated[
        list[str] | None,
        typer.Option(
            "--refine-environment-id",
            help="Approve only for these environments; repeat the option for multiple values.",
        ),
    ] = None,
    refine_activation_condition: Annotated[
        list[str] | None,
        typer.Option(
            "--refine-activation-condition",
            help="Add an exact activation condition; repeat the option for multiple values.",
        ),
    ] = None,
    refine_exclusion: Annotated[
        list[str] | None,
        typer.Option(
            "--refine-exclusion",
            help="Add an exact exclusion; repeat the option for multiple values.",
        ),
    ] = None,
) -> None:
    """Decide whether one proposal is authorized to influence future sessions."""

    try:
        response = resolve_codex_dogfood_review(
            config_path,
            queue_id=queue_id,
            decision=decision,
            proposal_digest=proposal_digest,
            confirm_future_use=confirm_future_use,
            refine_project_id=refine_project_id,
            refine_task_class=refine_task_class,
            refine_environment_id=refine_environment_id,
            refine_activation_condition=refine_activation_condition,
            refine_exclusion=refine_exclusion,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(response))


@dogfood_app.command("notices")
def show_codex_dogfood_notices(config_path: ConfigOption) -> None:
    """List immutable learning notices with exact undo artifact IDs."""

    try:
        config = _load_config(config_path)
        cycles = _ledger(config).learning_cycles()
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"notices": [_json_notice(item.notice) for item in cycles]}))


def revoke_active_codex_adaptation(config_path: Path, *, artifact_id: str) -> RuntimeNotice:
    """Revoke one exact active adaptation through the existing governed runtime."""

    config = _load_config(config_path)
    runtime = _runtime(config)
    ledger = _ledger(config)
    state = ledger.current()
    if state is None or state.release is None:
        raise AutomaticRuntimeError("no governed adaptation release is available")
    active = next(
        (
            item
            for item in state.release.governed_release.active_artifacts
            if item.artifact_ref.record_id == artifact_id
        ),
        None,
    )
    if active is None:
        raise AutomaticRuntimeError("undo target is not an active artifact")
    now = _now()
    suffix = str(sha256_text(f"{artifact_id}\0{now.isoformat()}")).removeprefix("sha256:")[:24]
    observation = InteractionObservation(
        observation_id=f"local-undo-{suffix}",
        subject_id=config.subject_id,
        task_ref=TaskRecordRef(
            record_id=f"local-undo-task-{suffix}",
            record_version="1.0.0",
        ),
        turn_id=f"local-undo-turn-{suffix}",
        actor=ActorRef(actor_id=config.subject_id, kind=ActorKind.USER),
        source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
        text=f"Revoke: {artifact_id}",
        scope=active.scope,
        observed_at=now,
        source_system="local_interaction_runtime",
        source_version="dogfood-cli-1.0.0",
        source_schema_digest=load_dogfood_runtime_pins(
            config.runtime_pin_path
        ).codex.schema_bundle_sha256,
    )
    result = runtime.learn(observation, state=state, processed_at=now)
    if not ledger.append_learning(
        result.cycle,
        result.state,
        release_event=result.release_event,
    ):
        raise AutomaticRuntimeError("undo observation unexpectedly already exists")
    return result.cycle.notice


@dogfood_app.command("undo")
def undo_codex_adaptation(
    config_path: ConfigOption,
    artifact_id: Annotated[str, typer.Argument(help="Exact active artifact ID from a notice.")],
) -> None:
    """Revoke one exact active adaptation and compile the next release immediately."""

    try:
        notice = revoke_active_codex_adaptation(config_path, artifact_id=artifact_id)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(notice))


def save_codex_activation_feedback(
    config_path: Path,
    *,
    activation_id: str,
    outcome: RuntimeFeedbackOutcome,
    relevant_artifact_ids: list[str] | None = None,
    correction_key: str | None = None,
) -> RuntimeActivationFeedback:
    """Persist one exact activation rating through the append-only runtime ledger."""

    config = _load_config(config_path)
    ledger = _ledger(config)
    activation = ledger.activation(activation_id)
    acknowledgement = ledger.delivery_acknowledgement(activation_id)
    if activation is None or acknowledgement is None:
        raise AutomaticRuntimeError(
            "feedback requires an exact activation and delivery acknowledgement"
        )
    now = _now()
    activated = activation.active_artifact_ids
    relevant = (
        tuple(sorted(set(relevant_artifact_ids)))
        if relevant_artifact_ids is not None
        else (() if outcome is RuntimeFeedbackOutcome.IRRELEVANT else activated)
    )
    feedback = RuntimeActivationFeedback(
        feedback_id=(
            f"feedback-{activation_id}-"
            f"{str(sha256_text(now.isoformat())).removeprefix('sha256:')[:12]}"
        ),
        subject_id=config.subject_id,
        cycle_id=activation_id,
        delivery_receipt_digest=activation.delivery_receipt_digest,
        outcome=outcome,
        relevant_artifact_ids=relevant,
        activated_artifact_ids=activated,
        correction_key=correction_key,
        recorded_at=now,
    )
    ledger.add_feedback(feedback)
    return feedback


@dogfood_app.command("feedback")
def record_codex_activation_feedback(
    config_path: ConfigOption,
    activation_id: Annotated[str, typer.Argument(help="Completed activation to rate.")],
    outcome: Annotated[RuntimeFeedbackOutcome, typer.Argument()],
    relevant_artifact_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--relevant-artifact-id",
            help=(
                "Repeatable artifact that should have applied. Defaults to the activated set "
                "for helped/hurt and the empty set for irrelevant."
            ),
        ),
    ] = None,
    correction_key: Annotated[
        str | None,
        typer.Option(
            "--correction-key",
            help="Stable behavior key used to count repeated corrections.",
        ),
    ] = None,
) -> None:
    """Record whether one exact completed activation helped, hurt, or was irrelevant."""

    try:
        feedback = save_codex_activation_feedback(
            config_path,
            activation_id=activation_id,
            outcome=outcome,
            relevant_artifact_ids=relevant_artifact_ids,
            correction_key=correction_key,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(feedback))


@dogfood_app.command("learning-feedback")
def record_codex_learning_feedback(
    config_path: ConfigOption,
    cycle_id: Annotated[str, typer.Argument(help="Exact learning cycle to classify.")],
    outcome: Annotated[RuntimeLearningAssessmentOutcome, typer.Argument()],
) -> None:
    """Classify an exact learning decision as correct, false-positive, or missed."""

    try:
        config = _load_config(config_path)
        ledger = _ledger(config)
        cycle = ledger.learning_cycle(cycle_id)
        if cycle is None:
            raise AutomaticRuntimeError("learning assessment requires an exact cycle")
        if ledger.learning_review_item_for_cycle(cycle_id) is not None:
            raise AutomaticRuntimeError(
                "review-required learning must be assessed through runtime review-decide"
            )
        now = _now()
        assessment = RuntimeLearningAssessment(
            assessment_id=f"learning-assessment-{cycle_id}",
            subject_id=config.subject_id,
            cycle_id=cycle_id,
            cycle_digest=cycle.content_digest,
            outcome=outcome,
            recorded_at=now,
        )
        ledger.add_learning_assessment(assessment)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(assessment))


@dogfood_app.command("gate-report")
def show_codex_dogfood_gate_report(
    config_path: ConfigOption,
    predecessor_config_path: PredecessorConfigOption = None,
) -> None:
    """Report raw-free longitudinal readiness and product metrics."""

    try:
        config = _load_config(config_path)
        report = _combined_gate_report(
            config,
            _gate_lineage_ledgers(config, predecessor_config_path),
            generated_at=_now(),
        )
    except (AutomaticRuntimeError, OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(report))


@dogfood_app.command("gateway-report")
def show_gateway_instrument_report(config_path: ConfigOption) -> None:
    """Report 6A.2D instrument metrics without rewriting the longitudinal gate."""

    try:
        config = _load_config(config_path)
        metrics = _gateway_ledger(config).metrics(generated_at=_now())
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(metrics))


@dogfood_app.command("configure-gateway")
def configure_gateway(
    config_path: ConfigOption,
    gateway_workspace_root: Annotated[
        Path,
        typer.Option("--gateway-workspace-root", file_okay=False, resolve_path=True),
    ],
    project_id: Annotated[str, typer.Option("--project-id")],
    verification_specs: Annotated[
        Path,
        typer.Option(
            "--verification-specs",
            exists=True,
            dir_okay=False,
            resolve_path=True,
            help="JSON array of bounded VerificationCommandSpec objects.",
        ),
    ],
    windows_sandbox: Annotated[
        Literal["elevated", "unelevated"],
        typer.Option(
            "--windows-sandbox",
            help="Explicit native Windows sandbox implementation for isolated target homes.",
        ),
    ] = "elevated",
) -> None:
    """Upgrade a v1.1/v1.2 config and explicitly enable the writable v1.3 gateway."""

    try:
        config = _load_config(config_path)
        workspace_root = _outside_git(
            gateway_workspace_root,
            repository_root=config.repository_root,
        )
        specs = TypeAdapter(tuple[VerificationCommandSpec, ...]).validate_json(
            verification_specs.read_text(encoding="utf-8"),
            strict=True,
        )
        if not specs:
            raise AutomaticRuntimeError("gateway requires at least one verification command")
        if not any(item.runs_during("preflight") for item in specs):
            raise AutomaticRuntimeError("gateway requires a preflight verification command")
        if not any(item.runs_during("postflight") for item in specs):
            raise AutomaticRuntimeError("gateway requires a postflight verification command")
        found = False
        projects: list[CodexDogfoodProjectConfig] = []
        for project in config.projects:
            if project.project_id == project_id:
                project = project.model_copy(update={"verification_commands": specs})
                found = True
            projects.append(project)
        if not found:
            raise AutomaticRuntimeError("gateway project ID is not configured")
        upgraded_version = "1.4.0" if config.config_version == "1.4.0" else "1.3.0"
        upgraded = config.model_copy(
            update={
                "config_version": upgraded_version,
                "gateway_workspace_root": workspace_root,
                "gateway_windows_sandbox": windows_sandbox,
                "projects": tuple(projects),
            }
        )
        validated = CodexDogfoodLocalConfig.model_validate(upgraded.model_dump(), strict=True)
        _replace_config_with_credential_rebind(config_path, config, validated)
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"config_version": upgraded_version, "status": "configured"}))


@credentials_app.command("rebootstrap")
def rebootstrap_runtime_credentials(
    config_path: ConfigOption,
    successor_state_root: Annotated[
        Path,
        typer.Option(
            "--successor-state-root",
            file_okay=False,
            resolve_path=True,
            help="New empty state root; the predecessor remains immutable and separate.",
        ),
    ],
    confirm_lost_credentials: Annotated[
        bool,
        typer.Option(
            "--confirm-lost-credentials",
            help="Confirm that the predecessor keys are unavailable and old ciphertext is lost.",
        ),
    ] = False,
) -> None:
    """Start a fresh DPAPI-managed lineage without rewriting unavailable-key history."""

    try:
        predecessor = _load_config(config_path)
        if not confirm_lost_credentials:
            raise CredentialStoreError(
                "rebootstrap requires --confirm-lost-credentials because prior ciphertext "
                "will not be copied or recoverable"
            )
        if platform_credential_store(predecessor.state_root).status() is not None:
            raise CredentialStoreError(
                "predecessor credential enrollment still exists; unlock or revoke it explicitly"
            )
        state = _outside_git(
            successor_state_root,
            repository_root=predecessor.repository_root,
        )
        if state == predecessor.state_root:
            raise CredentialStoreError("successor state root must differ from the predecessor")
        if state.exists() and any(state.iterdir()):
            raise CredentialStoreError("successor state root already contains files")
        state.mkdir(parents=True, exist_ok=True)
        state.chmod(0o700)

        now = _now()
        cutoff = int(now.timestamp())
        suffix = sha256_text(f"{predecessor.credential_binding_digest}:{cutoff}")[7:19]
        secrets = RuntimeSecrets.generate_managed()
        signer = GovernanceSigner(
            secrets.private_key(workspace_root=predecessor.repository_root),
            identity_id=f"{predecessor.signer_identity.identity_id}-successor-{suffix}",
            subject_id=predecessor.subject_id,
        )
        identity = create_signer_identity(
            signer,
            roles=(
                SignerRole.ACTIVATION,
                SignerRole.CONSENT,
                SignerRole.CUSTODY,
                SignerRole.RELEASE,
                SignerRole.REVIEW,
            ),
            created_at=now,
            expires_at=now + timedelta(days=31),
        )
        scope = predecessor.policy.scope.model_copy(
            update={
                "project_ids": tuple(project.project_id for project in predecessor.projects),
            }
        )
        policy = StandingAutomationPolicy(
            policy_id=f"{predecessor.policy.policy_id}-successor-{suffix}",
            subject_id=predecessor.subject_id,
            scope=scope,
            permitted_uses=predecessor.policy.permitted_uses,
            allowed_routes=predecessor.policy.allowed_routes,
            allowed_target_families=predecessor.policy.allowed_target_families,
            maximum_behavior_utf8_bytes=predecessor.policy.maximum_behavior_utf8_bytes,
            retention_days=predecessor.policy.retention_days,
            effective_at=now,
            expires_at=now + timedelta(days=predecessor.policy.retention_days),
        )
        policy_authorization = sign_governance_event(
            {
                "event_id": f"enable-successor-{suffix}",
                "subject_id": predecessor.subject_id,
                "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
                "target_ref": policy.authorization_target_ref,
                "target_digest": policy.content_digest,
                "decision": "enabled",
                "reason": "Start a fresh local lineage after confirmed credential loss.",
                "policy_version": policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        projects = tuple(
            project.model_copy(
                update={
                    "capture_after_epoch_seconds": None,
                    "registration": None,
                    "registration_authorization": None,
                }
            )
            for project in predecessor.projects
        )
        successor = CodexDogfoodLocalConfig.model_validate(
            predecessor.model_copy(
                update={
                    "config_version": "1.4.0",
                    "state_root": state,
                    "database_path": state / "runtime.sqlite3",
                    "raw_store_path": state / "raw",
                    "capture_after_epoch_seconds": cutoff,
                    "policy": policy,
                    "policy_authorization": policy_authorization,
                    "signer_identity": identity,
                    "projects": projects,
                }
            ).model_dump(),
            strict=True,
        )
        successor_config_path = state / "config.json"
        _write_config(successor_config_path, successor)
        platform_credential_store(state).enroll(
            secrets,
            subject_id=successor.subject_id,
            config_digest=successor.credential_binding_digest,
            signer_fingerprint=successor.signer_identity.key_fingerprint,
        )
        _ledger(successor).initialize(initial_runtime_state(policy))

        receipt_id = f"runtime-successor-{suffix}"
        receipt_digest = RuntimeSuccessorReceipt.model_construct(
            receipt_id=receipt_id,
            subject_id=predecessor.subject_id,
            predecessor_config_digest=predecessor.credential_binding_digest,
            predecessor_signer_fingerprint=predecessor.signer_identity.key_fingerprint,
            successor_config_digest=successor.credential_binding_digest,
            successor_signer_fingerprint=successor.signer_identity.key_fingerprint,
            capture_after_epoch_seconds=cutoff,
            created_at=now,
            authorization=policy_authorization,
        ).authorization_digest
        recovery_authorization = sign_governance_event(
            {
                "event_id": f"authorize-successor-{suffix}",
                "subject_id": predecessor.subject_id,
                "event_type": GovernanceEventType.CUSTODY_ACTION.value,
                "target_ref": f"runtime-successor:{receipt_id}",
                "target_digest": receipt_digest,
                "decision": "created_after_lost_credentials",
                "reason": (
                    "Preserve the prior ledger without copying evidence; old encrypted "
                    "payloads remain unavailable."
                ),
                "policy_version": policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        receipt = RuntimeSuccessorReceipt(
            receipt_id=receipt_id,
            subject_id=predecessor.subject_id,
            predecessor_config_digest=predecessor.credential_binding_digest,
            predecessor_signer_fingerprint=predecessor.signer_identity.key_fingerprint,
            successor_config_digest=successor.credential_binding_digest,
            successor_signer_fingerprint=successor.signer_identity.key_fingerprint,
            capture_after_epoch_seconds=cutoff,
            created_at=now,
            authorization=recovery_authorization,
        )
        verify_signed_governance(receipt.authorization, identity, effective_at=now)
        receipt_path = state / "successor-receipt.json"
        receipt_path.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
        receipt_path.chmod(0o600)
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "capture_after_epoch_seconds": cutoff,
                "config": str(successor_config_path),
                "evidence_copied": False,
                "historical_state_mutated": False,
                "prior_payload_recovery": "unavailable",
                "receipt": str(receipt_path),
                "status": "successor_ready",
            }
        )
    )


@credentials_app.command("enroll")
def enroll_runtime_credentials(config_path: ConfigOption) -> None:
    """Protect current external-key references for same-user unattended operation."""

    try:
        config = _load_config(config_path)
        if config.config_version not in {"1.3.0", "1.4.0"}:
            raise CredentialStoreError("credential enrollment requires dogfood config v1.3+")
        secrets = RuntimeSecrets.from_environment()
        # Validate every external dependency before protecting its locator and passphrase.
        secrets.private_key(workspace_root=config.repository_root)
        secrets.raw_encryption_key(workspace_root=config.repository_root)
        metadata = platform_credential_store(config.state_root).enroll(
            secrets,
            subject_id=config.subject_id,
            config_digest=config.credential_binding_digest,
            signer_fingerprint=config.signer_identity.key_fingerprint,
        )
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(metadata))


@credentials_app.command("status")
def show_runtime_credential_status(config_path: ConfigOption) -> None:
    """Show only non-secret enrollment metadata."""

    try:
        config = _load_config(config_path)
        metadata = platform_credential_store(config.state_root).status()
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "enrolled": metadata is not None,
                "metadata": None if metadata is None else metadata.model_dump(mode="json"),
            }
        )
    )


@credentials_app.command("revoke")
def revoke_runtime_credentials(config_path: ConfigOption) -> None:
    """Delete the recoverable local enrollment envelope."""

    try:
        config = _load_config(config_path)
        removed = platform_credential_store(config.state_root).revoke()
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"revoked": removed}))


def _durable_notice_sink(config: CodexDogfoodLocalConfig) -> DurableNotificationSink:
    toast = WindowsToastPublisher() if config.notification_mode == "toast_and_inbox" else None
    return DurableNotificationSink(
        _gateway_ledger(config),
        subject_id=config.subject_id,
        toast=toast,
    )


@watcher_app.command("run")
def run_runtime_watcher(
    config_path: ConfigOption,
    maximum_polls: Annotated[
        int | None,
        typer.Option("--maximum-polls", min=1, help="Test-only bounded watcher run."),
    ] = None,
) -> None:
    """Run the foreground watcher; use install for user-login startup."""

    try:
        execute_runtime_watcher(config_path, maximum_polls=maximum_polls)
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))


def execute_runtime_watcher(
    config_path: Path,
    *,
    maximum_polls: int | None = None,
) -> None:
    """Run the restart-safe watcher without crossing through Typer presentation code."""

    config = _load_config(config_path)
    if platform_credential_store(config.state_root).status() is None:
        raise CredentialStoreError("watcher requires explicit DPAPI credential enrollment")
    watcher = AutomaticRuntimeWatcher(
        poll=lambda: _execute_poll(
            config,
            limit=25,
            review_sink=_SilentReviewSink(),
            notice_sink=_durable_notice_sink(config),
        ),
        ledger=_gateway_ledger(config),
        lease=FileWatcherLease(config.state_root, subject_id=config.subject_id),
        state_root=config.state_root,
        idle_seconds=config.watcher_idle_seconds,
        maximum_backoff_seconds=config.watcher_maximum_backoff_seconds,
    )
    watcher.run(maximum_polls=maximum_polls)


def _watcher_task_name(config: CodexDogfoodLocalConfig) -> str:
    return f"AdaptationCompilerLab-{config.subject_id}"


@watcher_app.command("install")
def install_runtime_watcher(config_path: ConfigOption) -> None:
    """Install an explicit limited same-user login task; never enroll credentials implicitly."""

    try:
        config = _load_config(config_path)
        if platform_credential_store(config.state_root).status() is None:
            raise CredentialStoreError("watcher installation requires credential enrollment")
        runtime_python = (config.repository_root / ".venv" / "bin" / "python3").resolve()
        if not runtime_python.is_file():
            raise AutomaticRuntimeError("locked project Python is unavailable; run uv sync first")
        action = subprocess.list2cmdline(
            [
                "wsl.exe",
                "-d",
                config.wsl_distribution,
                "--cd",
                str(config.repository_root),
                str(runtime_python),
                "-m",
                "adaptation_compiler_lab.cli",
                "runtime",
                "watcher",
                "run",
                "--config",
                str(config_path),
            ]
        )
        WindowsTaskScheduler().install(task_name=_watcher_task_name(config), action=action)
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"installed": True, "task": _watcher_task_name(config)}))


@watcher_app.command("uninstall")
def uninstall_runtime_watcher(config_path: ConfigOption) -> None:
    """Remove the same-user startup task without deleting evidence or credentials."""

    try:
        config = _load_config(config_path)
        WindowsTaskScheduler().uninstall(task_name=_watcher_task_name(config))
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"installed": False, "task": _watcher_task_name(config)}))


@watcher_app.command("start")
def start_runtime_watcher(config_path: ConfigOption) -> None:
    """Start the already-installed same-user watcher task."""

    try:
        config = _load_config(config_path)
        result = subprocess.run(
            ["schtasks.exe", "/Run", "/TN", _watcher_task_name(config)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise AutomaticRuntimeError("installed Windows watcher task could not be started")
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"started": True, "task": _watcher_task_name(config)}))


@watcher_app.command("stop")
def stop_runtime_watcher(config_path: ConfigOption) -> None:
    """Ask the watcher to stop at its next bounded poll boundary."""

    try:
        config = _load_config(config_path)
        (config.state_root / "watcher-stop").touch(exist_ok=True)
    except OSError as error:
        _fail(str(error))
    typer.echo(canonical_json({"stop_requested": True}))


@watcher_app.command("status")
def show_runtime_watcher_status(config_path: ConfigOption) -> None:
    """Show raw-free local watcher state."""

    try:
        config = _load_config(config_path)
        lease_path = config.state_root / "watcher-lease.json"
        lease = None if not lease_path.is_file() else lease_path.read_text(encoding="utf-8")
    except OSError as error:
        _fail(str(error))
    typer.echo(canonical_json({"lease": None if lease is None else "active"}))


@inbox_app.command("list")
def list_runtime_inbox(config_path: ConfigOption) -> None:
    """List durable raw-free notification summaries."""

    try:
        config = _load_config(config_path)
        entries = _gateway_ledger(config).inbox()
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"entries": entries}))


@inbox_app.command("show")
def show_runtime_inbox_entry(
    config_path: ConfigOption,
    entry_id: Annotated[str, typer.Argument()],
) -> None:
    """Show one exact raw-free notification entry."""

    try:
        config = _load_config(config_path)
        matches = tuple(
            item for item in _gateway_ledger(config).inbox() if item.entry_id == entry_id
        )
        if len(matches) != 1:
            raise AutomaticRuntimeError("notification entry is unavailable")
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(matches[0]))


@inbox_app.command("acknowledge")
def acknowledge_runtime_inbox_entry(
    config_path: ConfigOption,
    entry_id: Annotated[str, typer.Argument()],
) -> None:
    """Append an acknowledgement without changing the original inbox entry."""

    try:
        config = _load_config(config_path)
        ledger = _gateway_ledger(config)
        matches = tuple(item for item in ledger.inbox() if item.entry_id == entry_id)
        if len(matches) != 1:
            raise AutomaticRuntimeError("notification entry is unavailable")
        from adaptation_compiler_lab.automatic_runtime.gateway_models import (
            RuntimeNotificationReceipt,
        )

        receipt = RuntimeNotificationReceipt(
            receipt_id=f"notice-ack-{entry_id}",
            entry_id=entry_id,
            channel="local_inbox",
            status="acknowledged",
            recorded_at=_now(),
        )
        ledger.append_notification_receipt(receipt)
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(receipt))


def _gateway_project(config: CodexDogfoodLocalConfig, project_id: str) -> CodexDogfoodProjectConfig:
    matches = tuple(item for item in config.projects if item.project_id == project_id)
    if len(matches) != 1:
        raise AutomaticRuntimeError("gateway requires one exact configured project")
    if not matches[0].verification_commands:
        raise AutomaticRuntimeError("gateway project has no independent verification commands")
    if not any(item.runs_during("preflight") for item in matches[0].verification_commands):
        raise AutomaticRuntimeError("gateway project has no preflight verification command")
    if not any(item.runs_during("postflight") for item in matches[0].verification_commands):
        raise AutomaticRuntimeError("gateway project has no postflight verification command")
    return matches[0]


def _verification_specs(
    project: CodexDogfoodProjectConfig,
    phase: Literal["preflight", "postflight"],
) -> tuple[VerificationCommandSpec, ...]:
    return tuple(item for item in project.verification_commands if item.runs_during(phase))


def _rpc_workspace(path: Path, *, windows_interop: bool) -> str:
    if not windows_interop:
        return str(path)
    result = subprocess.run(
        ["wslpath", "-w", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise AutomaticRuntimeError("gateway workspace could not be mapped to Windows")
    return result.stdout.strip()


def _execute_gateway_session(
    config: CodexDogfoodLocalConfig,
    *,
    project: CodexDogfoodProjectConfig,
    initial_task: str,
    followups: Iterable[str],
    mode_id: str | None = None,
    mode: CapabilityMode | None = None,
    personal_overlay: PersonalModeOverlayV1 | None = None,
) -> str:
    if config.config_version not in {"1.3.0", "1.4.0"} or config.gateway_workspace_root is None:
        raise AutomaticRuntimeError("writable gateway requires configured dogfood v1.3+")
    if personal_overlay is not None and mode_id is None and mode is None:
        raise AutomaticRuntimeError("a personal overlay requires one exact temporary Mode")
    if config.effective_target_windows_interop:
        parts = config.gateway_workspace_root.expanduser().resolve().parts
        if len(parts) < 4 or parts[:2] != ("/", "mnt"):
            raise AutomaticRuntimeError(
                "Windows target gateway workspaces must be on a local /mnt/<drive> volume"
            )
    runtime = _runtime(config)
    runtime_ledger = _ledger(config)
    runtime_ledger.initialize(initial_runtime_state(config.policy))
    state = runtime_ledger.current()
    if state is None or state.release is None:
        raise AutomaticRuntimeError("no governed adaptation release is available")
    unresolved = tuple(
        item.activation_id
        for item in runtime_ledger.activations()
        if runtime_ledger.delivery_acknowledgement(item.activation_id) is None
    )
    if unresolved:
        raise AutomaticRuntimeError("an earlier activation lacks acknowledgement")
    started = _now()
    normalized = initial_task.strip()
    if not normalized:
        raise AutomaticRuntimeError("gateway task must not be empty")
    session_id = (
        f"gateway-{started.strftime('%Y%m%dT%H%M%S')}-"
        f"{str(sha256_text(normalized)).removeprefix('sha256:')[:12]}"
    )
    instruction_service = InstructionEnvironmentService(
        projects={project.project_id: project.root},
        state_root=config.state_root / "instruction-environment",
        raw_store=_raw_store(config),
        relation_analyzer_digest=instruction_relation_analyzer_digest(
            model=config.semantic_model,
            reasoning_effort=config.semantic_reasoning_effort,
        ),
        include_persisted_global_roots=False,
        codex_cli_version=load_dogfood_runtime_pins(
            config.effective_target_runtime_pin_path
        ).codex.executable.package_version,
    )
    instruction_environment = instruction_service.refresh(
        project_id=project.project_id,
        target=NativeTarget.CODEX,
        working_directory=project.root,
    )
    if not instruction_environment.complete:
        raise AutomaticRuntimeError(
            "managed delivery requires a complete readable Codex instruction environment"
        )
    projection_context = _context(config, project, evaluated_at=started)
    base_projection = build_runtime_projection(
        state.release.governed_release,
        projection_context,
    )
    cached_relations = instruction_service.cached_relations(
        base_projection,
        instruction_environment,
    )
    prepared = runtime.activate(
        activation_id=session_id,
        task_ref=TaskRecordRef(record_id=f"task-{session_id}", record_version="1.0.0"),
        state=state,
        context=projection_context,
        target_task=normalized,
        activated_at=started,
        instruction_environment=instruction_environment,
        instruction_relations=cached_relations,
    )
    provider = GitWorktreeProvider(config.gateway_workspace_root)
    workspace = provider.create(
        canonical_root=project.root,
        project_id=project.project_id,
        session_id=session_id,
        created_at=started,
    )
    verifier = IndependentVerifier()
    preflight = verifier.run(
        session_id=f"preflight-{session_id}",
        workspace=workspace.root,
        specs=_verification_specs(project, "preflight"),
    )
    gateway_ledger = _gateway_ledger(config)
    for receipt in preflight:
        gateway_ledger.append_verification(receipt)
    failed_preflight = tuple(
        item.command_id for item in preflight if item.exit_code != 0 or item.timed_out
    )
    if failed_preflight:
        provider.teardown(canonical_root=project.root, workspace=workspace.root)
        raise AutomaticRuntimeError(
            "gateway baseline failed independent verification: " + ", ".join(failed_preflight)
        )
    mode_prepared: ModePreparedTask | None = None
    mode_store: ModeReceiptStore | None = None
    if mode_id is not None or mode is not None:
        if mode is not None and mode_id is not None and mode.mode_id != mode_id:
            provider.teardown(canonical_root=project.root, workspace=workspace.root)
            raise AutomaticRuntimeError("temporary Mode selection is inconsistent")
        selected_mode = mode or mode_by_id(cast(str, mode_id))
        if selected_mode is None:
            provider.teardown(canonical_root=project.root, workspace=workspace.root)
            raise AutomaticRuntimeError("the requested temporary Mode is unavailable")
        mode_prepared = prepare_mode_task(
            selected_mode,
            activation_id=f"mode-{session_id}",
            subject_id=config.subject_id,
            project_id=project.project_id,
            target_family="codex",
            task=normalized,
            base_delivered_task=prepared.task.delivered_task,
            base_delivery_digest=prepared.task.receipt.delivered_task_digest,
            prior_core_release_digest=state.release.content_digest,
            signer=_registration_signer(config),
            activated_at=started,
            personal_overlay=personal_overlay,
        )
        mode_store = ModeReceiptStore(config.state_root / "modes" / "receipts")
        mode_store.append_activation(mode_prepared.activation, mode_prepared.delivery)
    effective_task = (
        prepared.task.delivered_task if mode_prepared is None else mode_prepared.delivered_task
    )
    effective_projection_digest = canonical_digest(
        {
            "core_material_digest": prepared.task.rendered_material.content_digest,
            "mode_delivery_digest": (
                None if mode_prepared is None else mode_prepared.delivery.content_digest
            ),
        }
    )
    effective_projection_utf8_bytes = prepared.task.receipt.material_utf8_bytes + (
        0 if mode_prepared is None else mode_prepared.delivery.mode_material_utf8_bytes
    )
    runtime_ledger.append_activation(prepared)
    turns: list[GatewayTurnReceipt] = []
    transcript: list[dict[str, object]] = []
    target_thread_id: str | None = None
    last_turn_id: str | None = None
    captured: CapturedChangeBundle | None = None
    postflight: tuple[VerificationReceipt, ...] = ()
    mode_outcome: Literal["completed", "failed", "cancelled"] = "failed"
    try:
        pins = load_dogfood_runtime_pins(config.effective_target_runtime_pin_path)
        with (
            _isolated_target_home(config) as target_home,
            open_codex_dogfood(
                executable=config.effective_target_codex_executable,
                codex_home=target_home,
                pin=pins.codex,
                windows_interop=config.effective_target_windows_interop,
                experimental_api=True,
            ) as (_verified, schemas, rpc),
        ):
            conversation = CodexGatewayConversation(
                rpc,
                schemas=schemas,
                workspace=workspace.root,
                rpc_workspace=_rpc_workspace(
                    workspace.root,
                    windows_interop=config.effective_target_windows_interop,
                ),
                model=config.gateway_model,
                reasoning_effort=config.gateway_reasoning_effort,
                maximum_turns=config.gateway_maximum_turns,
                turn_timeout_seconds=config.gateway_maximum_turn_seconds,
            )
            current_instruction_environment = instruction_service.refresh(
                project_id=project.project_id,
                target=NativeTarget.CODEX,
                working_directory=project.root,
            )
            if (
                not current_instruction_environment.complete
                or current_instruction_environment.content_digest
                != instruction_environment.content_digest
            ):
                raise AutomaticRuntimeError(
                    "Codex instructions changed after projection; review the refreshed delta"
                )
            conversation.start()
            reported_sources = {
                source.relative_to(workspace.root).as_posix()
                for source in conversation.instruction_sources
            }
            predicted_sources = {
                item.display_path.replace("\\", "/")
                for item in instruction_environment.source_manifests
                if item.read_status is NativeReadStatus.READY
                and item.source_kind is NativeSourceKind.PROJECT_INSTRUCTIONS
            }
            if reported_sources != predicted_sources:
                raise AutomaticRuntimeError(
                    "Codex instruction discovery disagreed with Temper's source prediction"
                )
            target_thread_id = conversation.thread_id
            messages = chain((effective_task,), followups)
            session_deadline = monotonic() + config.gateway_maximum_session_seconds
            for sequence, message in enumerate(messages, start=1):
                if monotonic() >= session_deadline:
                    raise AutomaticRuntimeError("gateway session reached its time limit")
                turn_started = _now()
                result = conversation.turn(
                    message,
                    client_message_id=f"{session_id}-turn-{sequence}",
                )
                last_turn_id = result.turn_id
                turn_completed = _now()
                turns.append(
                    GatewayTurnReceipt(
                        receipt_id=f"turn-{session_id}-{sequence}",
                        session_id=session_id,
                        sequence=sequence,
                        user_message_digest=sha256_text(message),
                        agent_message_digest=(
                            None if not result.final_message else sha256_text(result.final_message)
                        ),
                        status=cast(Literal["completed", "failed", "interrupted"], result.status),
                        started_at=turn_started,
                        completed_at=turn_completed,
                    )
                )
                transcript.append(
                    {
                        "agent": result.final_message,
                        "events": result.events,
                        "sequence": sequence,
                        "status": result.status,
                        "turn_id": result.turn_id,
                        "user": message,
                    }
                )
                if result.final_message:
                    typer.echo(result.final_message)
                if result.status != "completed":
                    raise AutomaticRuntimeError(f"gateway target turn ended as {result.status}")
        bundle_store = EncryptedChangeBundleStore(_raw_store(config))
        unverified_bundle = bundle_store.capture(
            session_id=session_id,
            subject_id=config.subject_id,
            workspace=workspace.root,
            baseline=workspace.baseline,
            release_digest=prepared.activation.external_release_digest,
            projection_digest=effective_projection_digest,
            verification_receipts=(),
        )
        require_protected_paths_unchanged(
            unverified_bundle.receipt,
            protected_paths=project.protected_verification_paths,
        )
        verification_workspace = provider.create(
            canonical_root=project.root,
            project_id=project.project_id,
            session_id=f"{session_id}-verify",
        )
        try:
            verification_application, postflight = RecoverableChangeApplier(bundle_store).apply(
                unverified_bundle,
                canonical_root=verification_workspace.root,
                expected_head=workspace.baseline.commit_sha,
                verification_specs=_verification_specs(project, "postflight"),
                verifier=verifier,
                verification_session_id=f"validation-{session_id}",
            )
            if verification_application.status.value != "applied":
                raise AutomaticRuntimeError("clean independent verification failed")
        finally:
            provider.teardown(
                canonical_root=project.root,
                workspace=verification_workspace.root,
            )
        trace_reference = _raw_store(config).put(
            (canonical_json({"session_id": session_id, "turns": transcript}) + "\n").encode(),
            media_type="application/vnd.adaptation-compiler.gateway-trace+json",
        )
        completed = _now()
        session = GatewaySession(
            session_id=session_id,
            subject_id=config.subject_id,
            project_id=project.project_id,
            activation_id=prepared.activation.activation_id,
            release_digest=prepared.activation.external_release_digest,
            projection_digest=effective_projection_digest,
            baseline_digest=canonical_digest(workspace.baseline),
            model=config.gateway_model,
            reasoning_effort=config.gateway_reasoning_effort,
            maximum_turns=config.gateway_maximum_turns,
            maximum_session_seconds=config.gateway_maximum_session_seconds,
            maximum_turn_seconds=config.gateway_maximum_turn_seconds,
            projection_utf8_bytes=effective_projection_utf8_bytes,
            encrypted_trace_digest=Sha256Digest(f"sha256:{trace_reference.sha256}"),
            started_at=started,
            completed_at=completed,
            status=GatewaySessionStatus.COMPLETED,
        )
        gateway_ledger.append_session(session)
        for turn in turns:
            gateway_ledger.append_turn(turn)
        for receipt in postflight:
            gateway_ledger.append_verification(receipt)
        captured = bundle_store.capture(
            session_id=session_id,
            subject_id=config.subject_id,
            workspace=workspace.root,
            baseline=workspace.baseline,
            release_digest=prepared.activation.external_release_digest,
            projection_digest=effective_projection_digest,
            verification_receipts=postflight,
        )
        gateway_ledger.append_change_bundle(captured)
        acknowledgement = RuntimeTargetDeliveryAcknowledgement(
            acknowledgement_id=f"target-ack-{session_id}",
            activation_id=session_id,
            subject_id=config.subject_id,
            target_family="codex",
            activation_digest=prepared.activation.content_digest,
            external_session_digest=(
                None if target_thread_id is None else sha256_text(target_thread_id)
            ),
            external_turn_digest=None if last_turn_id is None else sha256_text(last_turn_id),
            result_digest=canonical_digest(
                {"status": "completed", "trace_digest": str(session.encrypted_trace_digest)}
            ),
            status="completed",
            acknowledged_at=completed,
        )
        runtime_ledger.acknowledge_delivery(acknowledgement)
        mode_outcome = "completed"
    except BaseException as error:
        gateway_ledger = _gateway_ledger(config)
        if gateway_ledger.session(session_id) is None:
            try:
                failed_trace = _raw_store(config).put(
                    (
                        canonical_json(
                            {
                                "failure_class": type(error).__name__,
                                "session_id": session_id,
                                "turns": transcript,
                            }
                        )
                        + "\n"
                    ).encode(),
                    media_type="application/vnd.adaptation-compiler.gateway-trace+json",
                )
                failed_session = GatewaySession(
                    session_id=session_id,
                    subject_id=config.subject_id,
                    project_id=project.project_id,
                    activation_id=prepared.activation.activation_id,
                    release_digest=prepared.activation.external_release_digest,
                    projection_digest=effective_projection_digest,
                    baseline_digest=canonical_digest(workspace.baseline),
                    model=config.gateway_model,
                    reasoning_effort=config.gateway_reasoning_effort,
                    maximum_turns=config.gateway_maximum_turns,
                    maximum_session_seconds=config.gateway_maximum_session_seconds,
                    maximum_turn_seconds=config.gateway_maximum_turn_seconds,
                    projection_utf8_bytes=effective_projection_utf8_bytes,
                    encrypted_trace_digest=Sha256Digest(f"sha256:{failed_trace.sha256}"),
                    started_at=started,
                    completed_at=_now(),
                    status=GatewaySessionStatus.FAILED,
                    failure_class=type(error).__name__,
                )
                gateway_ledger.append_session(failed_session)
                for turn in turns:
                    gateway_ledger.append_turn(turn)
                for receipt in postflight:
                    gateway_ledger.append_verification(receipt)
                try:
                    failed_bundle = EncryptedChangeBundleStore(_raw_store(config)).capture(
                        session_id=session_id,
                        subject_id=config.subject_id,
                        workspace=workspace.root,
                        baseline=workspace.baseline,
                        release_digest=prepared.activation.external_release_digest,
                        projection_digest=effective_projection_digest,
                        verification_receipts=postflight,
                    )
                    gateway_ledger.append_change_bundle(failed_bundle)
                except (OSError, ValueError):
                    pass
            except (OSError, ValueError):
                pass
        if runtime_ledger.delivery_acknowledgement(session_id) is None:
            runtime_ledger.acknowledge_delivery(
                RuntimeTargetDeliveryAcknowledgement(
                    acknowledgement_id=f"target-ack-{session_id}",
                    activation_id=session_id,
                    subject_id=config.subject_id,
                    target_family="codex",
                    activation_digest=prepared.activation.content_digest,
                    external_session_digest=(
                        None if target_thread_id is None else sha256_text(target_thread_id)
                    ),
                    external_turn_digest=(
                        None if last_turn_id is None else sha256_text(last_turn_id)
                    ),
                    status="failed",
                    failure_class=type(error).__name__,
                    acknowledged_at=_now(),
                )
            )
        raise
    finally:
        if mode_prepared is not None and mode_store is not None:
            deactivation = complete_mode_delivery(
                mode_prepared,
                outcome=mode_outcome,
                restored_core_release_digest=state.release.content_digest,
                signer=_registration_signer(config),
                deactivated_at=_now(),
            )
            mode_store.append_deactivation(deactivation)
        provider.teardown(canonical_root=project.root, workspace=workspace.root)
    if captured is None:
        raise AutomaticRuntimeError("gateway did not capture its change bundle")
    return session_id


@session_app.command("run")
def run_gateway_task(
    config_path: ConfigOption,
    task: Annotated[str, typer.Argument(help="Exact task for the governed fresh session.")],
    project_id: Annotated[str, typer.Option("--project")],
    mode_id: Annotated[str | None, typer.Option("--mode")] = None,
) -> None:
    """Run one writable, independently verified Codex task and preserve its review bundle."""

    try:
        session_id = execute_governed_gateway_task(
            config_path,
            task=task,
            project_id=project_id,
            mode_id=mode_id,
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"session_id": session_id, "status": "review_available"}))


def execute_governed_gateway_task(
    config_path: Path,
    *,
    task: str,
    project_id: str,
    mode_id: str | None = None,
    mode: CapabilityMode | None = None,
    personal_overlay: PersonalModeOverlayV1 | None = None,
) -> str:
    """Run one isolated task and retain changes for explicit review rather than direct apply."""

    config = _load_config(config_path)
    return _execute_gateway_session(
        config,
        project=_gateway_project(config, project_id),
        initial_task=task,
        followups=(),
        mode_id=mode_id,
        mode=mode,
        personal_overlay=personal_overlay,
    )


@session_app.command("chat")
def run_gateway_chat(
    config_path: ConfigOption,
    project_id: Annotated[str, typer.Option("--project")],
) -> None:
    """Run an interactive multi-turn gateway session with a frozen adaptation projection."""

    try:
        config = _load_config(config_path)
        initial = typer.prompt("Task").strip()

        def followups() -> Iterator[str]:
            for _ in range(config.gateway_maximum_turns - 1):
                value = typer.prompt("You (/finish, /status)").strip()
                if value == "/finish":
                    return
                if value == "/status":
                    typer.echo("Projection is frozen; workspace is isolated; network is denied.")
                    continue
                if value == "/abort":
                    raise AutomaticRuntimeError("gateway session aborted by the user")
                yield value

        session_id = _execute_gateway_session(
            config,
            project=_gateway_project(config, project_id),
            initial_task=initial,
            followups=followups(),
        )
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json({"session_id": session_id, "status": "review_available"}))


@changes_app.command("show")
def show_gateway_changes(
    config_path: ConfigOption,
    session_id: Annotated[str, typer.Argument()],
) -> None:
    """Decrypt and show a locally authorized review diff plus its governed metadata."""

    try:
        config = _load_config(config_path)
        bundle = _gateway_ledger(config).change_bundle(session_id)
        if bundle is None:
            raise AutomaticRuntimeError("gateway change bundle is unavailable")
        value = EncryptedChangeBundleStore(_raw_store(config)).load(bundle)
        raw_changes = value.get("changes")
        if not isinstance(raw_changes, list):
            raise AutomaticRuntimeError("gateway change bundle is invalid")
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(bundle.receipt))
    for raw in raw_changes:
        if not isinstance(raw, dict):
            _fail("gateway change bundle contains an invalid entry")
        path = str(raw.get("path", ""))
        before = raw.get("before")
        after = raw.get("after")
        if before is not None and not isinstance(before, str):
            _fail("gateway change bundle contains invalid before-bytes")
        if after is not None and not isinstance(after, str):
            _fail("gateway change bundle contains invalid after-bytes")
        try:
            before_bytes = b"" if before is None else base64.b64decode(before, validate=True)
            after_bytes = b"" if after is None else base64.b64decode(after, validate=True)
        except ValueError as error:
            _fail(f"gateway change bundle contains invalid bytes: {error}")
        if b"\x00" in before_bytes or b"\x00" in after_bytes:
            typer.echo(f"Binary change: {path}")
            continue
        try:
            before_text = before_bytes.decode("utf-8")
            after_text = after_bytes.decode("utf-8")
        except UnicodeDecodeError:
            typer.echo(f"Binary change: {path}")
            continue
        typer.echo(
            "".join(
                difflib.unified_diff(
                    before_text.splitlines(keepends=True),
                    after_text.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        )


@changes_app.command("discard")
def discard_gateway_changes(
    config_path: ConfigOption,
    session_id: Annotated[str, typer.Argument()],
) -> None:
    """Record an explicit discard without modifying the canonical repository."""

    try:
        config = _load_config(config_path)
        ledger = _gateway_ledger(config)
        bundle = ledger.change_bundle(session_id)
        if bundle is None:
            raise AutomaticRuntimeError("gateway change bundle is unavailable")
        existing = ledger.application(session_id)
        if existing is not None:
            raise AutomaticRuntimeError(
                f"gateway changes already have a recorded {existing.status.value} decision"
            )
        from adaptation_compiler_lab.automatic_runtime.gateway_models import (
            ChangeApplicationReceipt,
            ChangeApplicationStatus,
        )

        receipt = ChangeApplicationReceipt(
            receipt_id=f"apply-{session_id}",
            session_id=session_id,
            change_receipt_digest=bundle.receipt.content_digest,
            expected_head="0" * 40,
            status=ChangeApplicationStatus.DISCARDED,
            verification_receipt_digests=(),
            recorded_at=_now(),
        )
        ledger.append_application_outcome(receipt, ())
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(receipt))


@changes_app.command("apply")
def apply_gateway_changes(
    config_path: ConfigOption,
    session_id: Annotated[str, typer.Argument()],
    expected_head: Annotated[str, typer.Option("--expected-head")],
) -> None:
    """Apply an entire reviewed bundle only to its unchanged clean canonical project."""

    try:
        config = _load_config(config_path)
        ledger = _gateway_ledger(config)
        session = ledger.session(session_id)
        bundle = ledger.change_bundle(session_id)
        if session is None or bundle is None:
            raise AutomaticRuntimeError("gateway session or change bundle is unavailable")
        existing = ledger.application(session_id)
        if existing is not None:
            raise AutomaticRuntimeError(
                f"gateway changes already have a recorded {existing.status.value} decision"
            )
        project = _gateway_project(config, session.project_id)
        receipt, verifications = RecoverableChangeApplier(
            EncryptedChangeBundleStore(_raw_store(config))
        ).apply(
            bundle,
            canonical_root=project.root,
            expected_head=expected_head,
            verification_specs=_verification_specs(project, "postflight"),
            verifier=IndependentVerifier(),
            verification_session_id=f"application-{session_id}",
            on_applied=ledger.append_application_outcome,
        )
        if receipt.status.value != "applied":
            ledger.append_application_outcome(receipt, verifications)
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(receipt))
    if receipt.status.value != "applied":
        raise typer.Exit(code=1)
