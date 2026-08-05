"""Local-only Codex dogfood commands for pickup, delivery, review, undo, and feedback."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, cast

import typer
from pydantic import field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodInteractionSource,
    CodexDogfoodSessionLauncher,
    CodexProjectScope,
    open_codex_dogfood,
)
from adaptation_compiler_lab.automatic_runtime.codex_host import CodexDogfoodHost
from adaptation_compiler_lab.automatic_runtime.gate import (
    build_codex_dogfood_gate_report,
)
from adaptation_compiler_lab.automatic_runtime.host import (
    RuntimeNoticeSink,
    RuntimeReviewSink,
)
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackDetectorMode,
    InteractionObservation,
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeNotice,
    RuntimeReviewQueueItem,
    StandingAutomationPolicy,
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
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_DOGFOOD_RUNTIME_LOCK,
    RuntimeConformanceError,
    load_dogfood_runtime_pins,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
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
    load_private_key_from_environment,
    sign_governance_event,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
)
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.runtime import RuntimeProjectionContext
from adaptation_compiler_lab.serialization import canonical_json
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.models import ScopeDimension

dogfood_app = typer.Typer(
    help="Run the local governed Codex dogfood loop with saved ChatGPT authentication.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

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


class CodexDogfoodProjectConfig(FrozenModel):
    """One exact target path plus source-CWD aliases for the same governed project."""

    project_id: Identifier
    root: Path
    scope: Scope
    source_roots: tuple[Path, ...] = ()

    @field_validator("source_roots")
    @classmethod
    def source_roots_are_sorted_unique(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        rendered = tuple(str(item) for item in value)
        if rendered != tuple(sorted(set(rendered))):
            raise ValueError("dogfood source roots must be sorted and unique")
        return value

    @model_validator(mode="after")
    def project_scope_is_exact(self) -> CodexDogfoodProjectConfig:
        if self.scope.project_ids != (self.project_id,):
            raise ValueError("dogfood project scope must contain exactly its project ID")
        return self

    @property
    def effective_source_roots(self) -> tuple[Path, ...]:
        return self.source_roots or (self.root,)


class CodexDogfoodLocalConfig(FrozenModel):
    """No-secret local configuration; keys remain external environment dependencies."""

    config_version: str = "1.2.0"
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
        if self.config_version not in {"1.1.0", "1.2.0"}:
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
        if (
            self.policy.subject_id != self.subject_id
            or self.policy_authorization.subject_id != self.subject_id
            or self.signer_identity.subject_id != self.subject_id
        ):
            raise ValueError("dogfood config crossed its subject boundary")
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


class _ConsoleNoticeSink(RuntimeNoticeSink):
    def publish(self, notice: RuntimeNotice) -> None:
        typer.echo(
            canonical_json(
                {
                    "kind": notice.kind.value,
                    "notice_id": notice.notice_id,
                    "summary": notice.summary,
                    "undo_artifact_id": notice.undo_artifact_id,
                }
            )
        )


def _json_scope(scope: Scope) -> dict[str, object]:
    """Render one typed scope at the raw-free CLI boundary."""

    return scope.model_dump(mode="json")


class _ConsoleReviewSink(RuntimeReviewSink):
    def enqueue(self, item: RuntimeReviewQueueItem) -> None:
        typer.echo(
            canonical_json(
                {
                    "queue_id": item.queue_id,
                    "reasons": item.detection.reasons,
                    "scope": _json_scope(item.detection.scope),
                    "status": "review_required",
                }
            )
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(message: str) -> None:
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
        config = CodexDogfoodLocalConfig.model_validate_json(
            path.read_text(encoding="utf-8"),
            strict=True,
        )
    except (OSError, ValueError) as error:
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


def _ledger(config: CodexDogfoodLocalConfig) -> AutomaticRuntimeLedger:
    SqliteUnitOfWorkFactory(config.database_path).initialize()
    return AutomaticRuntimeLedger(config.database_path, subject_id=config.subject_id)


def _runtime(config: CodexDogfoodLocalConfig) -> AutomaticAdaptationRuntime:
    private_key = load_private_key_from_environment(
        workspace_root=config.repository_root,
    )
    signer = GovernanceSigner(
        private_key,
        identity_id=config.signer_identity.identity_id,
        subject_id=config.subject_id,
    )
    if signer.fingerprint != config.signer_identity.key_fingerprint:
        raise AutomaticRuntimeError("configured signing identity does not match the external key")
    raw_key = RawEncryptionKey.from_environment(workspace_root=config.repository_root)
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
    """Create one bounded signed policy and no-secret local dogfood configuration."""

    try:
        repository = repository_root.resolve()
        state = _outside_git(state_root, repository_root=repository)
        if state.exists() and any(state.iterdir()):
            raise ValueError("dogfood state root already contains files")
        state.mkdir(parents=True, exist_ok=True)
        state.chmod(0o700)
        now = _now()
        private_key = load_private_key_from_environment(workspace_root=repository)
        RawEncryptionKey.from_environment(workspace_root=repository)
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
        database = _ledger(config)
        database.initialize(initial_runtime_state(policy))
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(str(config_path))


@dogfood_app.command("poll")
def poll_codex_feedback(
    config_path: ConfigOption,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 25,
) -> None:
    """Pick up new interactive user messages and commit the cursor after local notices."""

    try:
        config = _load_config(config_path)
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
                experimental_api=(
                    config.feedback_detector_mode is not FeedbackDetectorMode.GRAMMAR
                ),
            ) as (verified, schemas, rpc),
        ):
            source = CodexDogfoodInteractionSource(
                rpc,
                subject_id=config.subject_id,
                source_version=verified.version,
                source_schema_digest=verified.schema_bundle_digest,
                schemas=schemas,
                projects=tuple(
                    CodexProjectScope(root=root, scope=item.scope)
                    for item in config.projects
                    for root in item.effective_source_roots
                ),
                capture_after_epoch_seconds=config.capture_after_epoch_seconds,
            )
            receipt = CodexDogfoodHost(
                runtime=runtime,
                initial_state=initial_runtime_state(config.policy),
                ledger=ledger,
                source=source,
                review_sink=_ConsoleReviewSink(),
                notice_sink=_ConsoleNoticeSink(),
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
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(asdict(receipt)))


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
                raise AutomaticRuntimeError(
                    "activation already exists; automatic relaunch is refused"
                )
            result = CodexDogfoodSessionLauncher(
                rpc,
                schemas=schemas,
            ).launch(
                prepared,
                workspace=workspace,
                ephemeral=True,
            )
            ledger.acknowledge_delivery(result.acknowledgement)
        typer.echo(
            canonical_json(
                {
                    "activation_id": chosen_id,
                    "material_utf8_bytes": prepared.task.receipt.material_utf8_bytes,
                    "status": result.acknowledgement.status,
                }
            )
        )
        if result.final_message:
            typer.echo(result.final_message)
        if result.acknowledgement.status != "completed":
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))


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
                "config_version": "1.2.0",
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
    typer.echo(
        canonical_json(
            {
                "report": report.model_dump(mode="json"),
                "report_digest": report.content_digest,
            }
        )
    )


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
            "source_checkpointed": (
                ledger.current_checkpoint("codex-dogfood-interactive") is not None
            ),
            "unresolved_activation_ids": unresolved,
        }
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(payload))


@dogfood_app.command("review")
def show_codex_dogfood_review(config_path: ConfigOption) -> None:
    """List raw-free review-required adaptations; this command does not approve them."""

    try:
        config = _load_config(config_path)
        items = _ledger(config).learning_review_items()
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "items": [
                    {
                        "queue_id": item.queue_id,
                        "reasons": item.detection.reasons,
                        "route": (
                            None
                            if item.detection.requested_route is None
                            else item.detection.requested_route.value
                        ),
                        "scope": _json_scope(item.detection.scope),
                    }
                    for item in items
                ]
            }
        )
    )


@dogfood_app.command("notices")
def show_codex_dogfood_notices(config_path: ConfigOption) -> None:
    """List immutable learning notices with exact undo artifact IDs."""

    try:
        config = _load_config(config_path)
        cycles = _ledger(config).learning_cycles()
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(
        canonical_json(
            {
                "notices": [
                    {
                        "created_at": item.notice.created_at,
                        "kind": item.notice.kind.value,
                        "notice_id": item.notice.notice_id,
                        "summary": item.notice.summary,
                        "undo_artifact_id": item.notice.undo_artifact_id,
                    }
                    for item in cycles
                ]
            }
        )
    )


@dogfood_app.command("undo")
def undo_codex_adaptation(
    config_path: ConfigOption,
    artifact_id: Annotated[str, typer.Argument(help="Exact active artifact ID from a notice.")],
) -> None:
    """Revoke one exact active adaptation and compile the next release immediately."""

    try:
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
    except (OSError, ValueError, RuntimeConformanceError) as error:
        _fail(str(error))
    typer.echo(canonical_json(result.cycle.notice))


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
def show_codex_dogfood_gate_report(config_path: ConfigOption) -> None:
    """Report raw-free longitudinal readiness and product metrics."""

    try:
        config = _load_config(config_path)
        ledger = _ledger(config)
        report = build_codex_dogfood_gate_report(
            subject_id=config.subject_id,
            learning_cycles=ledger.learning_cycles(),
            learning_assessments=ledger.learning_assessments(),
            activations=ledger.activations(),
            acknowledgements=ledger.delivery_acknowledgements(),
            activation_feedback=ledger.feedback(),
            generated_at=_now(),
        )
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(report))
