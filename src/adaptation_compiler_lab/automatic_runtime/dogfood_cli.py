"""Local-only Codex dogfood commands for pickup, delivery, review, undo, and feedback."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from pydantic import field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodInteractionSource,
    CodexDogfoodSessionLauncher,
    CodexProjectScope,
    open_codex_dogfood,
)
from adaptation_compiler_lab.automatic_runtime.codex_host import CodexDogfoodHost
from adaptation_compiler_lab.automatic_runtime.host import (
    RuntimeNoticeSink,
    RuntimeReviewSink,
)
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    InteractionObservation,
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeNotice,
    RuntimeReviewQueueItem,
    StandingAutomationPolicy,
)
from adaptation_compiler_lab.automatic_runtime.service import (
    AutomaticAdaptationRuntime,
    AutomaticRuntimeError,
    initial_runtime_state,
)
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_DOGFOOD_RUNTIME_LOCK,
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
    """One exact target path and its governed context scope."""

    project_id: Identifier
    root: Path
    scope: Scope

    @model_validator(mode="after")
    def project_scope_is_exact(self) -> CodexDogfoodProjectConfig:
        if self.scope.project_ids != (self.project_id,):
            raise ValueError("dogfood project scope must contain exactly its project ID")
        return self


class CodexDogfoodLocalConfig(FrozenModel):
    """No-secret local configuration; keys remain external environment dependencies."""

    config_version: str = "1.0.0"
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
        return self


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


class _ConsoleReviewSink(RuntimeReviewSink):
    def enqueue(self, item: RuntimeReviewQueueItem) -> None:
        typer.echo(
            canonical_json(
                {
                    "queue_id": item.queue_id,
                    "reasons": item.detection.reasons,
                    "scope": item.detection.scope,
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
    auth = config.source_codex_home / "auth.json"
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
                ),
            ),
        )
        config_path = state / "config.json"
        config_path.write_text(canonical_json(config) + "\n", encoding="utf-8")
        config_path.chmod(0o600)
        database = _ledger(config)
        database.initialize(initial_runtime_state(policy))
    except (OSError, ValueError) as error:
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
        with open_codex_dogfood(
            executable=config.codex_executable,
            codex_home=config.source_codex_home,
            pin=pins.codex,
            windows_interop=config.windows_interop,
        ) as (verified, schemas, rpc):
            source = CodexDogfoodInteractionSource(
                rpc,
                subject_id=config.subject_id,
                source_version=verified.version,
                source_schema_digest=verified.schema_bundle_digest,
                schemas=schemas,
                projects=tuple(
                    CodexProjectScope(root=item.root, scope=item.scope) for item in config.projects
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
            ).run_once(limit=limit)
    except (OSError, ValueError) as error:
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
        pins = load_dogfood_runtime_pins(config.runtime_pin_path)
        with (
            _isolated_target_home(config) as target_home,
            open_codex_dogfood(
                executable=config.codex_executable,
                codex_home=target_home,
                pin=pins.codex,
                windows_interop=config.windows_interop,
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
    except (OSError, ValueError) as error:
        _fail(str(error))


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
            "generation": 0 if state is None else state.generation,
            "learning_cycle_count": len(ledger.learning_cycles()),
            "review_count": len(ledger.learning_review_items()),
            "source_checkpointed": (
                ledger.current_checkpoint("codex-dogfood-interactive") is not None
            ),
            "unresolved_activation_ids": unresolved,
        }
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(payload))


@dogfood_app.command("review")
def show_codex_dogfood_review(config_path: ConfigOption) -> None:
    """List raw-free review-required adaptations; this command does not approve them."""

    try:
        config = _load_config(config_path)
        items = _ledger(config).learning_review_items()
    except (OSError, ValueError) as error:
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
                        "scope": item.detection.scope,
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
    except (OSError, ValueError) as error:
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
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(result.cycle.notice))


@dogfood_app.command("feedback")
def record_codex_activation_feedback(
    config_path: ConfigOption,
    activation_id: Annotated[str, typer.Argument(help="Completed activation to rate.")],
    outcome: Annotated[RuntimeFeedbackOutcome, typer.Argument()],
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
        feedback = RuntimeActivationFeedback(
            feedback_id=(
                f"feedback-{activation_id}-"
                f"{str(sha256_text(now.isoformat())).removeprefix('sha256:')[:12]}"
            ),
            subject_id=config.subject_id,
            cycle_id=activation_id,
            delivery_receipt_digest=activation.delivery_receipt_digest,
            outcome=outcome,
            relevant_artifact_ids=activation.active_artifact_ids,
            activated_artifact_ids=activation.active_artifact_ids,
            recorded_at=now,
        )
        ledger.add_feedback(feedback)
    except (OSError, ValueError) as error:
        _fail(str(error))
    typer.echo(canonical_json(feedback))
