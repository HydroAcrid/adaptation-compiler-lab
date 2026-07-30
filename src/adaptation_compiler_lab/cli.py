"""Explicit, local-only command-line interface for the research prototype.

The CLI is intentionally a thin adapter over validated application services.  It never invokes
an agent, installs a target pack, executes a recommended tool, or treats imported content as an
instruction.  Complex records cross the boundary as JSON files so every state-changing command
is inspectable and replayable.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal, NoReturn, cast

import typer
from pydantic import BaseModel, TypeAdapter, ValidationError

from adaptation_compiler_lab.application.exporter import (
    build_sanitized_release_export,
    write_sanitized_release_export,
)
from adaptation_compiler_lab.application.importer import import_task_bundle
from adaptation_compiler_lab.application.lifecycle import make_lifecycle_event
from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.application.release_candidate_store import (
    ReleaseCandidateSnapshotKey,
    ReleaseCandidateSnapshotStore,
)
from adaptation_compiler_lab.application.review import HumanReviewWorkflow
from adaptation_compiler_lab.application.source_capture import (
    PILOT_PERMITTED_USES,
    SourceCaptureRequest,
    SourceCaptureService,
)
from adaptation_compiler_lab.application.targeting import (
    TargetPackBuildContext,
    build_release_render_projection,
    build_validated_target_pack,
)
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import dogfood_app
from adaptation_compiler_lab.benchmark import (
    BenchmarkConfig,
    BenchmarkOutcomeRecord,
    benchmark_manifest_digest,
    canonical_benchmark_manifest,
    validate_benchmark_config,
    validate_benchmark_outcomes,
)
from adaptation_compiler_lab.connectors.codex_app_server import (
    DEFAULT_CODEX_DESKTOP_SCHEMA_ROOT,
    open_codex_source_connector,
)
from adaptation_compiler_lab.connectors.pins import load_source_runtime_pins
from adaptation_compiler_lab.domain import (
    ActorRef,
    Approval,
    ApprovalDecision,
    Artifact,
    ArtifactRef,
    ArtifactState,
    ConstructionBoundary,
    EvaluationAttestation,
    EvaluationCase,
    EvaluationCaseState,
    Evidence,
    LessonCandidate,
    LessonCandidateState,
    Outcome,
    Partition,
    RecordKind,
    Release,
    ReleaseCandidateState,
    ReleaseRef,
    Scope,
)
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import PermittedUse
from adaptation_compiler_lab.evaluation.candidates import (
    CandidateGenerationContext,
    generate_evaluation_candidates,
)
from adaptation_compiler_lab.governance import (
    CaptureReceipt,
    ConsentReceipt,
    GovernanceObjectKind,
    InvalidationAction,
    RecallTarget,
    SignerIdentity,
    SignerRole,
    SourceSelector,
)
from adaptation_compiler_lab.governance.signing import (
    SIGNING_KEY_PASSPHRASE_ENV,
    GovernanceSigner,
    create_signer_identity,
    governance_ref,
    load_private_key_from_environment,
    sign_capture,
    sign_consent,
    verify_signed_governance,
    write_new_private_key,
)
from adaptation_compiler_lab.persistence.errors import PersistenceError
from adaptation_compiler_lab.persistence.governance import GovernanceLedger
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.recall import RecallService
from adaptation_compiler_lab.release.activation import ActivationPointer, ActivationService
from adaptation_compiler_lab.release.proposals import ReleaseCandidate, propose_release_candidate
from adaptation_compiler_lab.release.service import CandidateEvaluation, ReleaseService
from adaptation_compiler_lab.routing import route_lesson
from adaptation_compiler_lab.serialization import (
    canonical_digest,
    deserialize_record,
    export_json_schemas,
)
from adaptation_compiler_lab.targets import (
    TargetKind,
    render_target_pack,
    write_rendered_pack,
)
from adaptation_compiler_lab.targets.profiles import default_target_profile
from adaptation_compiler_lab.workspace import (
    WorkspacePaths,
    initialize_workspace,
    load_workspace,
    prepare_new_output_directory,
)

app = typer.Typer(
    name="adaptation-compiler-lab",
    help="Compile reviewed local evidence into reversible external adaptation artifacts.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
workspace_app = typer.Typer(help="Create and inspect an explicit local workspace.")
record_app = typer.Typer(help="Validate, import, and inspect immutable domain records.")
evidence_app = typer.Typer(help="Inspect evidence metadata; raw bytes remain segregated.")
evaluation_app = typer.Typer(help="Derive proposal-only evaluation cases from structured outcomes.")
lesson_app = typer.Typer(help="Propose and review evidence-backed lesson candidates.")
artifact_app = typer.Typer(help="Review and inspect durable adaptation artifacts.")
release_app = typer.Typer(help="Manage release candidates and immutable releases.")
candidate_app = typer.Typer(help="Manage explicit release-candidate snapshots.")
pack_app = typer.Typer(help="Compile file-only target packs without installing or activating them.")
activation_app = typer.Typer(help="Manage explicit audited activation pointers.")
export_app = typer.Typer(help="Create sanitized, payload-free local exports.")
benchmark_app = typer.Typer(help="Validate blinded four-condition benchmark manifests.")
schema_app = typer.Typer(help="Export versioned JSON validation schemas.")
identity_app = typer.Typer(help="Create and verify dedicated local signing identities.")
consent_app = typer.Typer(help="Issue and verify exact signed consent receipts.")
capture_preview_app = typer.Typer(
    help="Create synthetic signed capture previews without accessing source tasks."
)
source_app = typer.Typer(
    help="List minimized Codex metadata and capture only exactly consented completed tasks."
)
recall_app = typer.Typer(
    help="Preview and explicitly confirm signed withdrawal and recall cascades."
)

app.add_typer(workspace_app, name="workspace")
app.add_typer(record_app, name="record")
app.add_typer(evidence_app, name="evidence")
app.add_typer(evaluation_app, name="evaluation")
app.add_typer(lesson_app, name="lesson")
app.add_typer(artifact_app, name="artifact")
app.add_typer(release_app, name="release")
release_app.add_typer(candidate_app, name="candidate")
app.add_typer(pack_app, name="pack")
app.add_typer(activation_app, name="activation")
app.add_typer(export_app, name="export")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(schema_app, name="schema")
app.add_typer(identity_app, name="identity")
app.add_typer(consent_app, name="consent")
app.add_typer(capture_preview_app, name="capture-preview")
app.add_typer(source_app, name="source")
app.add_typer(recall_app, name="recall")
app.add_typer(dogfood_app, name="runtime")

WorkspaceOption = Annotated[
    Path,
    typer.Option(
        "--workspace",
        "-w",
        help="Explicit adaptation-compiler-lab workspace root.",
        file_okay=False,
        resolve_path=True,
    ),
]


class CandidateCreateRequest(FrozenModel):
    """JSON request for creating, but not approving, a release candidate."""

    candidate_id: str
    candidate_version: SemVer
    created_at: UtcDateTime
    created_by: ActorRef
    policy_version: SemVer
    artifact_refs: tuple[ArtifactRef, ...]
    schema_versions: tuple[SemVer, ...]
    policy_versions: tuple[SemVer, ...]
    construction_boundary: ConstructionBoundary
    proposal_disposition_id: str
    proposal_rationale: str
    development_evaluations: tuple[EvaluationAttestation, ...] = ()
    predecessor_ref: ReleaseRef | None = None
    supersedes_refs: tuple[ReleaseRef, ...] = ()
    rollback_target_ref: ReleaseRef | None = None
    target_compatibility: tuple[str, ...] = ()


class CandidateEvaluationRequest(FrozenModel):
    evaluated_at: UtcDateTime
    evaluator: ActorRef
    disposition_id: str
    rationale: str


class CandidateFreezeRequest(FrozenModel):
    release_id: str
    record_version: SemVer
    release_version: SemVer
    released_at: UtcDateTime
    created_by: ActorRef
    disposition_id: str
    rationale: str


class CandidateExpiryRequest(FrozenModel):
    expired_at: UtcDateTime
    actor: ActorRef
    disposition_id: str
    rationale: str


class IdentityCreateRequest(FrozenModel):
    identity_id: Identifier
    subject_id: Identifier
    roles: tuple[SignerRole, ...]
    created_at: UtcDateTime
    expires_at: UtcDateTime | None = None


class ConsentIssueRequest(FrozenModel):
    receipt_id: Identifier
    subject_id: Identifier
    source_selector: SourceSelector
    scope: Scope
    permitted_uses: tuple[PermittedUse, ...]
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    retention_until: UtcDateTime
    policy_version: SemVer


class CapturePreviewRequest(FrozenModel):
    receipt_id: Identifier
    subject_id: Identifier
    consent_receipt_id: Identifier
    source_selector: SourceSelector
    source_version: NonEmptyStr
    source_schema_digest: Sha256Digest
    payload_digest: Sha256Digest
    captured_at: UtcDateTime
    synthetic: bool = True


class RecallImpactRequest(FrozenModel):
    impact_id: Identifier
    signer_identity_id: Identifier
    root_target: RecallTarget
    requested_action: InvalidationAction
    generated_at: UtcDateTime
    policy_version: SemVer


class RecallExecuteRequest(FrozenModel):
    impact_id: Identifier
    signer_identity_id: Identifier
    confirmation_digest: Sha256Digest
    completed_at: UtcDateTime
    reason: NonEmptyStr


def _validation_message(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or '$'}: {item['msg']}"
        for item in error.errors(include_url=False, include_input=False)
    )


def _fail(error: Exception | str) -> NoReturn:
    if isinstance(error, ValidationError):
        message = _validation_message(error)
        error_type = "validation_error"
    elif isinstance(error, str):
        message = error
        error_type = "command_error"
    else:
        message = str(error) or type(error).__name__
        error_type = type(error).__name__
    typer.echo(
        json.dumps({"error": {"message": message, "type": error_type}}, sort_keys=True),
        err=True,
    )
    raise typer.Exit(code=1)


@contextmanager
def _handled() -> Iterator[None]:
    try:
        yield
    except (ValidationError, PersistenceError, ValueError, OSError, sqlite3.Error) as error:
        _fail(error)


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", round_trip=True)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _emit(value: object) -> None:
    typer.echo(
        json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True, default=str)
    )


def _read_text(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"JSON input is not a regular file: {resolved}")
    return resolved.read_text(encoding="utf-8")


def _read_mapping(path: Path) -> Mapping[str, object]:
    value = json.loads(_read_text(path))
    if not isinstance(value, Mapping):
        raise ValueError("JSON input must be an object")
    return cast(Mapping[str, object], value)


def _load_model[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    return model.model_validate_json(_read_text(path))


def _write_new_text(path: Path, content: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite output: {resolved}")
    if not resolved.parent.is_dir():
        raise FileNotFoundError(f"output parent does not exist: {resolved.parent}")
    with resolved.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return resolved


def _preflight_optional_output(path: Path | None) -> None:
    if path is None:
        return
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite output: {resolved}")
    if not resolved.parent.is_dir():
        raise FileNotFoundError(f"output parent does not exist: {resolved.parent}")


def _emit_or_write(value: BaseModel | Mapping[str, object], output: Path | None) -> None:
    payload = (
        value.model_dump(mode="json", round_trip=True) if isinstance(value, BaseModel) else value
    )
    if output is None:
        _emit(payload)
        return
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    written = _write_new_text(output, rendered)
    _emit({"output": str(written)})


def _services(workspace: Path) -> tuple[WorkspacePaths, str, SqliteUnitOfWorkFactory]:
    paths, subject_id = load_workspace(workspace)
    if not paths.database.is_file():
        raise ValueError(f"workspace ledger is missing: {paths.database}")
    return paths, subject_id, SqliteUnitOfWorkFactory(paths.database)


def _record_store(workspace: Path) -> tuple[WorkspacePaths, DomainRecordStore]:
    paths, subject_id, factory = _services(workspace)
    return paths, DomainRecordStore(factory, subject_id=subject_id)


def _candidate_services(
    workspace: Path,
) -> tuple[
    WorkspacePaths,
    str,
    SqliteUnitOfWorkFactory,
    ReleaseCandidateSnapshotStore,
]:
    paths, subject_id, factory = _services(workspace)
    return (
        paths,
        subject_id,
        factory,
        ReleaseCandidateSnapshotStore(factory, subject_id=subject_id),
    )


def _review_workflow(workspace: Path) -> HumanReviewWorkflow:
    _, store = _record_store(workspace)
    return HumanReviewWorkflow(store)


def _governance_ledger(workspace: Path) -> tuple[WorkspacePaths, str, GovernanceLedger]:
    paths, subject_id = load_workspace(workspace)
    ledger = GovernanceLedger(paths.database, subject_id=subject_id)
    ledger.initialize()
    return paths, subject_id, ledger


def _governance_signer(paths: WorkspacePaths, identity: SignerIdentity) -> GovernanceSigner:
    private_key = load_private_key_from_environment(workspace_root=paths.root)
    signer = GovernanceSigner(
        private_key=private_key,
        identity_id=identity.identity_id,
        subject_id=identity.subject_id,
    )
    if signer.fingerprint != identity.key_fingerprint:
        raise ValueError("configured signing key does not match the registered identity")
    return signer


def _key(kind: RecordKind, record_id: str, version: str) -> RecordKey:
    return RecordKey(kind=kind.value, record_id=record_id, version=version)


def _pointer_payload(pointer: ActivationPointer | None) -> Mapping[str, object]:
    if pointer is None:
        return {"active": False}
    return {
        "action": pointer.action.value,
        "active": pointer.release is not None,
        "environment_id": pointer.environment_id,
        "event_id": pointer.event_id,
        "release": None if pointer.release is None else asdict(pointer.release),
        "target_pack": None if pointer.target_pack is None else asdict(pointer.target_pack),
    }


@workspace_app.command("init")
def workspace_init(
    root: Annotated[Path, typer.Argument(help="New or empty workspace directory.")],
    subject_id: Annotated[str, typer.Option("--subject-id", help="Single subject identifier.")],
) -> None:
    """Initialize local directories and the append-only SQLite ledger."""

    with _handled():
        paths = initialize_workspace(root, subject_id=subject_id)
        schema_version = SqliteUnitOfWorkFactory(paths.database).initialize()
        _emit(
            {
                "database_schema_version": schema_version,
                "subject_id": subject_id,
                "workspace": str(paths.root),
            }
        )


@workspace_app.command("status")
def workspace_status(workspace: WorkspaceOption) -> None:
    """Validate a workspace and report payload-free local counts."""

    with _handled():
        paths, subject_id, factory = _services(workspace)
        records = DomainRecordStore(factory, subject_id=subject_id).list()
        counts = Counter(item.key.kind for item in records)
        _emit(
            {
                "database": str(paths.database),
                "record_counts": dict(sorted(counts.items())),
                "record_total": len(records),
                "subject_id": subject_id,
                "workspace": str(paths.root),
            }
        )


@identity_app.command("create")
def identity_create(
    request_file: Annotated[Path, typer.Argument(help="Unsigned identity request JSON.")],
    key_file: Annotated[
        Path,
        typer.Option("--key-file", help="New encrypted Ed25519 key outside the workspace."),
    ],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    passphrase_env: Annotated[
        str,
        typer.Option("--passphrase-env", help="Environment variable holding the key passphrase."),
    ] = SIGNING_KEY_PASSPHRASE_ENV,
) -> None:
    """Create and register a self-signed public identity; never print private key bytes."""

    with _handled():
        paths, subject_id, ledger = _governance_ledger(workspace)
        request = _load_model(request_file, IdentityCreateRequest)
        _preflight_optional_output(output)
        if request.subject_id != subject_id:
            raise ValueError("identity subject does not match the workspace subject")
        if ledger.get(GovernanceObjectKind.SIGNER_IDENTITY, request.identity_id) is not None:
            raise ValueError("signer identity already exists")
        passphrase = os.environ.get(passphrase_env)
        if not passphrase:
            raise ValueError(
                f"signing-key passphrase environment variable is unavailable: {passphrase_env}"
            )
        private_key = write_new_private_key(
            key_file,
            passphrase=passphrase,
            workspace_root=paths.root,
        )
        signer = GovernanceSigner(
            private_key=private_key,
            identity_id=request.identity_id,
            subject_id=request.subject_id,
        )
        identity = create_signer_identity(
            signer,
            roles=request.roles,
            created_at=request.created_at,
            expires_at=request.expires_at,
        )
        ledger.add(identity)
        _emit_or_write(identity, output)


@identity_app.command("verify")
def identity_verify(
    identity_file: Annotated[Path, typer.Argument(help="Signed identity JSON.")],
) -> None:
    """Verify a self-signature without requiring private-key access."""

    with _handled():
        identity = _load_model(identity_file, SignerIdentity)
        verify_signed_governance(identity, identity)
        _emit({"content_digest": canonical_digest(identity), "valid": True})


@consent_app.command("issue")
def consent_issue(
    request_file: Annotated[Path, typer.Argument(help="Unsigned exact consent request JSON.")],
    identity_id: Annotated[str, typer.Option("--identity-id")],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Issue signed consent without reading any source payload."""

    with _handled():
        paths, subject_id, ledger = _governance_ledger(workspace)
        request = _load_model(request_file, ConsentIssueRequest)
        _preflight_optional_output(output)
        identity = ledger.require_identity(identity_id)
        if request.subject_id != subject_id:
            raise ValueError("consent subject does not match the workspace subject")
        if request.source_selector.source_system == "codex_app_server":
            if len(request.source_selector.source_ids) != 1:
                raise ValueError("real Codex consent must name exactly one task ID")
            if request.permitted_uses != PILOT_PERMITTED_USES:
                raise ValueError("real Codex consent must use the frozen pilot use set")
            if request.retention_until - request.issued_at > timedelta(days=30):
                raise ValueError("real Codex retention cannot exceed 30 days")
        signer = _governance_signer(paths, identity)
        receipt = sign_consent(request.model_dump(mode="json", round_trip=True), signer)
        ledger.add(receipt)
        _emit_or_write(receipt, output)


@consent_app.command("verify")
def consent_verify(
    receipt_file: Annotated[Path, typer.Argument(help="Signed consent receipt JSON.")],
    identity_file: Annotated[Path, typer.Argument(help="Signer identity JSON.")],
) -> None:
    """Verify consent bytes, signer binding, and validity bounds."""

    with _handled():
        receipt = _load_model(receipt_file, ConsentReceipt)
        identity = _load_model(identity_file, SignerIdentity)
        verify_signed_governance(identity, identity)
        verify_signed_governance(receipt, identity)
        _emit({"content_digest": canonical_digest(receipt), "valid": True})


@capture_preview_app.command("create")
def capture_preview_create(
    request_file: Annotated[
        Path, typer.Argument(help="Unsigned synthetic capture-preview request JSON.")
    ],
    identity_id: Annotated[str, typer.Option("--identity-id")],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Sign metadata for a synthetic preview without reading or storing payload bytes."""

    with _handled():
        paths, subject_id, ledger = _governance_ledger(workspace)
        request = _load_model(request_file, CapturePreviewRequest)
        _preflight_optional_output(output)
        identity = ledger.require_identity(identity_id)
        consent_value = ledger.get(GovernanceObjectKind.CONSENT_RECEIPT, request.consent_receipt_id)
        if not isinstance(consent_value, ConsentReceipt):
            raise ValueError("referenced consent receipt is unavailable")
        if request.subject_id != subject_id:
            raise ValueError("capture subject does not match the workspace subject")
        if not request.synthetic or request.source_selector.source_system != "synthetic_fixture":
            raise ValueError("Milestone 1 capture previews accept synthetic selectors only")
        if request.source_selector != consent_value.source_selector:
            raise ValueError("capture selector must exactly match consent")
        signer = _governance_signer(paths, identity)
        unsigned = request.model_dump(mode="json", round_trip=True, exclude={"consent_receipt_id"})
        unsigned["consent_ref"] = governance_ref(consent_value).model_dump(mode="json")
        receipt = sign_capture(unsigned, signer)
        ledger.add(receipt)
        _emit_or_write(receipt, output)


@capture_preview_app.command("verify")
def capture_preview_verify(
    receipt_file: Annotated[Path, typer.Argument(help="Signed capture receipt JSON.")],
    consent_file: Annotated[Path, typer.Argument(help="Exact signed consent receipt JSON.")],
    identity_file: Annotated[Path, typer.Argument(help="Signer identity JSON.")],
) -> None:
    """Verify a preview and its exact consent linkage without payload access."""

    with _handled():
        receipt = _load_model(receipt_file, CaptureReceipt)
        consent = _load_model(consent_file, ConsentReceipt)
        identity = _load_model(identity_file, SignerIdentity)
        verify_signed_governance(identity, identity)
        verify_signed_governance(consent, identity)
        verify_signed_governance(receipt, identity)
        if receipt.consent_ref != governance_ref(consent):
            raise ValueError("capture receipt does not bind the supplied consent receipt")
        _emit({"content_digest": canonical_digest(receipt), "valid": True})


@source_app.command("inventory")
def source_inventory(
    codex_executable: Annotated[
        Path,
        typer.Option(
            "--codex-executable",
            help="External pinned Codex Desktop executable copied to a user-owned toolchain.",
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    codex_home: Annotated[
        Path,
        typer.Option(
            "--codex-home",
            help="Explicit Codex Desktop state root.",
            file_okay=False,
            resolve_path=True,
        ),
    ],
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 100,
) -> None:
    """List privacy-minimized completed-task metadata without persisting it."""

    with _handled():
        pins = load_source_runtime_pins()
        with open_codex_source_connector(
            executable=codex_executable,
            codex_home=codex_home,
            pin=pins.codex_desktop,
            schema_root=DEFAULT_CODEX_DESKTOP_SCHEMA_ROOT,
            windows_interop=True,
        ) as connector:
            _emit(connector.list_completed_tasks(limit=limit))


@source_app.command("capture")
def source_capture(
    request_file: Annotated[
        Path,
        typer.Argument(help="Exact task, consent, capture identity, and timestamp JSON."),
    ],
    identity_id: Annotated[str, typer.Option("--identity-id")],
    codex_executable: Annotated[
        Path,
        typer.Option(
            "--codex-executable",
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    codex_home: Annotated[
        Path,
        typer.Option(
            "--codex-home",
            file_okay=False,
            resolve_path=True,
        ),
    ],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Read and encrypt one task only after its exact signed consent exists."""

    with _handled():
        paths, subject_id, ledger = _governance_ledger(workspace)
        request = _load_model(request_file, SourceCaptureRequest)
        _preflight_optional_output(output)
        identity = ledger.require_identity(identity_id)
        signer = _governance_signer(paths, identity)
        raw_store = LocalRawPayloadStore.from_environment(
            paths.raw_evidence,
            workspace_root=paths.root,
            allow_legacy_plaintext=False,
        )
        pins = load_source_runtime_pins()
        with open_codex_source_connector(
            executable=codex_executable,
            codex_home=codex_home,
            pin=pins.codex_desktop,
            schema_root=DEFAULT_CODEX_DESKTOP_SCHEMA_ROOT,
            windows_interop=True,
        ) as connector:
            result = SourceCaptureService(
                connector=connector,
                raw_store=raw_store,
                governance_ledger=ledger,
                signer=signer,
                identity=identity,
                subject_id=subject_id,
            ).capture(request)
        _emit_or_write(result, output)


@recall_app.command("preflight")
def recall_preflight(
    request_file: Annotated[
        Path, typer.Argument(help="Signed-impact request with one exact root target.")
    ],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Compute and sign the full dependency impact without changing lifecycle state."""

    with _handled():
        paths, subject_id, factory = _services(workspace)
        request = _load_model(request_file, RecallImpactRequest)
        _preflight_optional_output(output)
        ledger = GovernanceLedger(paths.database, subject_id=subject_id)
        identity = ledger.require_identity(request.signer_identity_id)
        signer = _governance_signer(paths, identity)
        impact = RecallService(factory, subject_id=subject_id).preflight(
            impact_id=request.impact_id,
            root_target=request.root_target,
            requested_action=request.requested_action,
            generated_at=request.generated_at,
            policy_version=request.policy_version,
            signer=signer,
        )
        payload = impact.model_dump(mode="json", round_trip=True)
        payload["confirmation_digest"] = canonical_digest(impact)
        _emit_or_write(payload, output)


@recall_app.command("execute")
def recall_execute(
    request_file: Annotated[
        Path, typer.Argument(help="Execution request containing the exact impact digest.")
    ],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Execute an unchanged signed impact and fail closed without exact confirmation."""

    with _handled():
        paths, subject_id, factory = _services(workspace)
        request = _load_model(request_file, RecallExecuteRequest)
        _preflight_optional_output(output)
        ledger = GovernanceLedger(paths.database, subject_id=subject_id)
        identity = ledger.require_identity(request.signer_identity_id)
        signer = _governance_signer(paths, identity)
        impact = ledger.get(GovernanceObjectKind.DEPENDENCY_IMPACT, request.impact_id)
        if impact is None:
            raise ValueError("signed dependency impact is unavailable")
        raw_store = None
        if getattr(impact, "payloads", ()):
            raw_store = LocalRawPayloadStore.from_environment(
                paths.raw_evidence,
                workspace_root=paths.root,
            )
        report = RecallService(
            factory,
            subject_id=subject_id,
            raw_store=raw_store,
        ).execute(
            impact_id=request.impact_id,
            confirmation_digest=request.confirmation_digest,
            completed_at=request.completed_at,
            reason=request.reason,
            signer=signer,
        )
        _emit_or_write(report, output)


@record_app.command("validate")
def record_validate(
    input_file: Annotated[Path, typer.Argument(help="One canonical domain-record JSON file.")],
) -> None:
    """Validate and digest one record without storing it."""

    with _handled():
        record = deserialize_record(_read_text(input_file))
        _emit(
            {
                "content_digest": str(canonical_digest(record)),
                "record_id": record.record_id,
                "record_type": record.record_type.value,
                "record_version": record.record_version,
                "valid": True,
            }
        )


@record_app.command("list")
def record_list(
    workspace: WorkspaceOption,
    kind: Annotated[RecordKind | None, typer.Option("--kind")] = None,
    benchmark_role: Annotated[str | None, typer.Option("--benchmark-role")] = None,
) -> None:
    """List record identities without exposing record or evidence payloads."""

    with _handled():
        _, store = _record_store(workspace)
        records = store.list(
            record_kind=None if kind is None else kind.value,
            benchmark_role=benchmark_role,
        )
        _emit(
            {
                "records": [
                    {
                        "content_digest": str(canonical_digest(item.record)),
                        "record_id": item.key.record_id,
                        "record_type": item.key.kind,
                        "record_version": item.key.version,
                    }
                    for item in records
                ]
            }
        )


@record_app.command("show")
def record_show(
    kind: Annotated[RecordKind, typer.Argument()],
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show one exact validated record; raw evidence bytes remain segregated."""

    with _handled():
        _, store = _record_store(workspace)
        _emit(store.require(_key(kind, record_id, version)).record)


@record_app.command("import-bundle")
def record_import_bundle(
    bundle: Annotated[Path, typer.Argument(help="Structured Task/Outcome/Evidence bundle JSON.")],
    workspace: WorkspaceOption,
) -> None:
    """Explicitly import one channel-preserving source bundle."""

    with _handled():
        paths, subject_id, factory = _services(workspace)
        result = import_task_bundle(
            bundle,
            expected_subject_id=subject_id,
            record_store=DomainRecordStore(factory, subject_id=subject_id),
            raw_store=LocalRawPayloadStore.from_environment(
                paths.raw_evidence,
                workspace_root=paths.root,
            ),
        )
        _emit(result)


def _list_records_of_kind(
    workspace: Path,
    kind: RecordKind,
    *,
    benchmark_role: str | None = None,
) -> tuple[Mapping[str, object], ...]:
    _, store = _record_store(workspace)
    return tuple(
        {
            "content_digest": str(canonical_digest(item.record)),
            "record_id": item.key.record_id,
            "record_type": item.key.kind,
            "record_version": item.key.version,
            "state": getattr(item.record, "state", None),
        }
        for item in store.list(record_kind=kind.value, benchmark_role=benchmark_role)
    )


def _show_record_of_type[RecordT: BaseModel](
    workspace: Path,
    kind: RecordKind,
    record_id: str,
    version: str,
    expected_type: type[RecordT],
) -> RecordT:
    _, store = _record_store(workspace)
    record = store.require(_key(kind, record_id, version)).record
    if not isinstance(record, expected_type):
        raise ValueError(f"stored record is not {expected_type.__name__}")
    return record


def _load_domain_record[RecordT: BaseModel](
    path: Path, expected_type: type[RecordT], *, label: str
) -> RecordT:
    record = deserialize_record(_read_text(path))
    if not isinstance(record, expected_type):
        raise ValueError(f"{label} requires a {expected_type.__name__} record")
    return record


@evidence_app.command("list")
def evidence_list(
    workspace: WorkspaceOption,
    partition: Annotated[Partition | None, typer.Option("--partition")] = None,
) -> None:
    """List evidence identities and metadata digests without reading raw payload bytes."""

    with _handled():
        _emit(
            {
                "evidence": _list_records_of_kind(
                    workspace,
                    RecordKind.EVIDENCE,
                    benchmark_role=None if partition is None else partition.value,
                )
            }
        )


@evidence_app.command("show")
def evidence_show(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show validated Evidence metadata and references, never segregated raw bytes."""

    with _handled():
        _emit(_show_record_of_type(workspace, RecordKind.EVIDENCE, record_id, version, Evidence))


@evaluation_app.command("list")
def evaluation_list(
    workspace: WorkspaceOption,
    state: Annotated[EvaluationCaseState | None, typer.Option("--state")] = None,
) -> None:
    """List evaluation-case identities, optionally filtered by review state."""

    with _handled():
        records = _list_records_of_kind(workspace, RecordKind.EVALUATION_CASE)
        if state is not None:
            records = tuple(item for item in records if item["state"] == state)
        _emit({"evaluation_cases": records})


@evaluation_app.command("show")
def evaluation_show(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show one exact evaluation case."""

    with _handled():
        _emit(
            _show_record_of_type(
                workspace,
                RecordKind.EVALUATION_CASE,
                record_id,
                version,
                EvaluationCase,
            )
        )


@evaluation_app.command("approve")
def evaluation_approve(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument(help="Exact candidate input version.")],
    new_version: Annotated[str, typer.Option("--new-version")],
    approval_file: Annotated[Path, typer.Argument(help="Human Approval JSON file.")],
    workspace: WorkspaceOption,
) -> None:
    """Approve an evaluation candidate as a new immutable record version."""

    with _handled():
        reviewed = _review_workflow(workspace).approve_evaluation_candidate(
            _key(RecordKind.EVALUATION_CASE, record_id, version),
            new_version=new_version,
            approval=_load_model(approval_file, Approval),
        )
        _emit(reviewed)


@evaluation_app.command("reject")
def evaluation_reject(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument(help="Exact candidate input version.")],
    new_version: Annotated[str, typer.Option("--new-version")],
    rejection_file: Annotated[Path, typer.Argument(help="Human rejection JSON file.")],
    workspace: WorkspaceOption,
) -> None:
    """Reject an evaluation candidate as a new immutable record version."""

    with _handled():
        reviewed = _review_workflow(workspace).reject_evaluation_candidate(
            _key(RecordKind.EVALUATION_CASE, record_id, version),
            new_version=new_version,
            approval=_load_model(rejection_file, Approval),
        )
        _emit(reviewed)


@lesson_app.command("list")
def lesson_list(
    workspace: WorkspaceOption,
    state: Annotated[LessonCandidateState | None, typer.Option("--state")] = None,
) -> None:
    """List exact lesson-candidate versions and review states."""

    with _handled():
        records = _list_records_of_kind(workspace, RecordKind.LESSON_CANDIDATE)
        if state is not None:
            records = tuple(item for item in records if item["state"] == state)
        _emit({"lesson_candidates": records})


@lesson_app.command("propose")
def lesson_propose(
    candidate_file: Annotated[Path, typer.Argument(help="PROPOSED LessonCandidate JSON file.")],
    workspace: WorkspaceOption,
) -> None:
    """Persist a proposal only after construction provenance and evaluation-first checks."""

    with _handled():
        candidate = _load_domain_record(candidate_file, LessonCandidate, label="lesson propose")
        _emit(_review_workflow(workspace).propose_lesson(candidate))


@lesson_app.command("show")
def lesson_show(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show one exact evidence-backed lesson candidate."""

    with _handled():
        _emit(
            _show_record_of_type(
                workspace,
                RecordKind.LESSON_CANDIDATE,
                record_id,
                version,
                LessonCandidate,
            )
        )


def _lesson_decision(
    *,
    record_id: str,
    version: str,
    new_version: str,
    decision_file: Path,
    expected: ApprovalDecision,
    workspace: Path,
    attestations_file: Path | None = None,
) -> LessonCandidate:
    approval = _load_model(decision_file, Approval)
    if approval.decision is not expected:
        raise ValueError(f"lesson command requires a human {expected.value} decision")
    workflow = _review_workflow(workspace)
    key = _key(RecordKind.LESSON_CANDIDATE, record_id, version)
    if expected is ApprovalDecision.APPROVED:
        if attestations_file is None:
            raise ValueError("lesson approval requires an attestation JSON file")
        attestations = TypeAdapter(tuple[EvaluationAttestation, ...]).validate_json(
            _read_text(attestations_file)
        )
        return workflow.approve_lesson(
            key,
            new_version=new_version,
            approval=approval,
            evaluation_attestations=attestations,
        )
    return workflow.reject_lesson(key, new_version=new_version, approval=approval)


@lesson_app.command("approve")
def lesson_approve(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument(help="Exact proposed input version.")],
    new_version: Annotated[str, typer.Option("--new-version")],
    approval_file: Annotated[Path, typer.Argument(help="Human Approval JSON file.")],
    attestations_file: Annotated[
        Path,
        typer.Argument(help="JSON array of exact approval-version EvaluationAttestations."),
    ],
    workspace: WorkspaceOption,
) -> None:
    """Approve a lesson as a new version after evaluation-first and promotion gates."""

    with _handled():
        _emit(
            _lesson_decision(
                record_id=record_id,
                version=version,
                new_version=new_version,
                decision_file=approval_file,
                expected=ApprovalDecision.APPROVED,
                workspace=workspace,
                attestations_file=attestations_file,
            )
        )


@lesson_app.command("reject")
def lesson_reject(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument(help="Exact proposed input version.")],
    new_version: Annotated[str, typer.Option("--new-version")],
    rejection_file: Annotated[Path, typer.Argument(help="Human rejection JSON file.")],
    workspace: WorkspaceOption,
) -> None:
    """Reject a lesson as a new attributable immutable version."""

    with _handled():
        _emit(
            _lesson_decision(
                record_id=record_id,
                version=version,
                new_version=new_version,
                decision_file=rejection_file,
                expected=ApprovalDecision.REJECTED,
                workspace=workspace,
            )
        )


@lesson_app.command("route")
def lesson_route(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    policy_version: Annotated[str, typer.Option("--policy-version")],
    workspace: WorkspaceOption,
) -> None:
    """Inspect the deterministic least-invasive route without writing an Artifact."""

    with _handled():
        candidate = _show_record_of_type(
            workspace,
            RecordKind.LESSON_CANDIDATE,
            record_id,
            version,
            LessonCandidate,
        )
        if candidate.state is not LessonCandidateState.APPROVED:
            raise ValueError("lesson route requires an exact approved candidate version")
        _emit(route_lesson(candidate, policy_version=policy_version))


@artifact_app.command("list")
def artifact_list(
    workspace: WorkspaceOption,
    state: Annotated[ArtifactState | None, typer.Option("--state")] = None,
) -> None:
    """List exact durable-artifact versions and states."""

    with _handled():
        records = _list_records_of_kind(workspace, RecordKind.ARTIFACT)
        if state is not None:
            records = tuple(item for item in records if item["state"] == state)
        _emit({"artifacts": records})


@artifact_app.command("propose")
def artifact_propose(
    artifact_file: Annotated[Path, typer.Argument(help="DRAFT Artifact JSON file.")],
    workspace: WorkspaceOption,
) -> None:
    """Persist a draft only when exact source lessons select the same least-invasive route."""

    with _handled():
        artifact = _load_domain_record(artifact_file, Artifact, label="artifact propose")
        _, store = _record_store(workspace)
        for reference in artifact.source_candidate_refs:
            source = store.require(
                RecordKey(
                    kind=RecordKind.LESSON_CANDIDATE.value,
                    record_id=reference.record_id,
                    version=reference.record_version,
                )
            ).record
            if not isinstance(source, LessonCandidate):
                raise ValueError("artifact source did not decode as a LessonCandidate")
            if reference.content_digest != canonical_digest(source):
                raise ValueError("artifact source lesson digest is not exact")
            decision = route_lesson(source, policy_version=artifact.policy_version)
            if (
                not decision.eligible_for_artifact
                or decision.selected_route is not artifact.selected_route
                or decision.durable_artifact_kind is not artifact.artifact_kind
            ):
                raise ValueError(
                    "artifact selected route disagrees with deterministic source-lesson routing"
                )
        _emit(HumanReviewWorkflow(store).propose_artifact(artifact))


@artifact_app.command("show")
def artifact_show(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show one exact durable artifact and its evidence links."""

    with _handled():
        _emit(_show_record_of_type(workspace, RecordKind.ARTIFACT, record_id, version, Artifact))


@evaluation_app.command("derive")
def evaluation_derive(
    outcome_file: Annotated[Path, typer.Argument(help="Validated Outcome JSON file.")],
    context_file: Annotated[Path, typer.Argument(help="Candidate-generation context JSON file.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    persist: Annotated[
        bool,
        typer.Option(
            "--persist",
            help="Explicitly add generated evaluation records to the workspace ledger.",
        ),
    ] = False,
    workspace: Annotated[Path | None, typer.Option("--workspace", "-w")] = None,
) -> None:
    """Derive deterministic evaluation candidates; never promote them automatically."""

    with _handled():
        record = deserialize_record(_read_text(outcome_file))
        if not isinstance(record, Outcome):
            raise ValueError("evaluation derive requires an Outcome record")
        context = _load_model(context_file, CandidateGenerationContext)
        batch = generate_evaluation_candidates(record, context)
        persisted: list[str] = []
        if persist:
            if workspace is None:
                raise ValueError("--persist requires --workspace")
            _, store = _record_store(workspace)
            keys = store.add_many(batch.candidates)
            persisted = [f"{key.kind}:{key.record_id}@{key.version}" for key in keys]
        payload = batch.model_dump(mode="json", round_trip=True)
        payload["persisted_record_keys"] = persisted
        _emit_or_write(payload, output)


@candidate_app.command("create")
def candidate_create(
    request_file: Annotated[
        Path,
        typer.Argument(help="Candidate creation request JSON; this cannot contain approval."),
    ],
    workspace: WorkspaceOption,
) -> None:
    """Create and persist a proposed release-candidate snapshot."""

    with _handled():
        request = _load_model(request_file, CandidateCreateRequest)
        candidate = propose_release_candidate(
            candidate_id=request.candidate_id,
            candidate_version=request.candidate_version,
            created_at=request.created_at,
            created_by=request.created_by,
            policy_version=request.policy_version,
            artifact_refs=request.artifact_refs,
            schema_versions=request.schema_versions,
            policy_versions=request.policy_versions,
            construction_boundary=request.construction_boundary,
            proposal_disposition_id=request.proposal_disposition_id,
            proposal_rationale=request.proposal_rationale,
            development_evaluations=request.development_evaluations,
            predecessor_ref=request.predecessor_ref,
            supersedes_refs=request.supersedes_refs,
            rollback_target_ref=request.rollback_target_ref,
            target_compatibility=request.target_compatibility,
        )
        *_, store = _candidate_services(workspace)
        snapshot = store.put(candidate)
        _emit(
            {
                "candidate": candidate.model_dump(mode="json", round_trip=True),
                "content_digest": snapshot.content_digest,
                "snapshot_key": asdict(snapshot.key),
            }
        )


@artifact_app.command("evaluate")
def artifact_evaluate(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument(help="Exact draft input version.")],
    new_version: Annotated[str, typer.Option("--new-version")],
    attestations_file: Annotated[
        Path,
        typer.Argument(help="JSON array of exact development EvaluationAttestations."),
    ],
    workspace: WorkspaceOption,
) -> None:
    """Attach validated attestations as a new evaluated Artifact version."""

    with _handled():
        attestations = TypeAdapter(tuple[EvaluationAttestation, ...]).validate_json(
            _read_text(attestations_file)
        )
        evaluated = _review_workflow(workspace).evaluate_artifact_proposal(
            _key(RecordKind.ARTIFACT, record_id, version),
            new_version=new_version,
            evaluation_attestations=attestations,
        )
        _emit(evaluated)


@artifact_app.command("approve")
def artifact_approve(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument(help="Exact evaluated input version.")],
    new_version: Annotated[str, typer.Option("--new-version")],
    approval_file: Annotated[Path, typer.Argument(help="Human Approval JSON file.")],
    attestations_file: Annotated[
        Path,
        typer.Argument(help="JSON array of exact approval-version EvaluationAttestations."),
    ],
    workspace: WorkspaceOption,
) -> None:
    """Approve an evaluated Artifact after provenance, evaluation, and privacy gates."""

    with _handled():
        attestations = TypeAdapter(tuple[EvaluationAttestation, ...]).validate_json(
            _read_text(attestations_file)
        )
        approved = _review_workflow(workspace).approve_artifact_proposal(
            _key(RecordKind.ARTIFACT, record_id, version),
            new_version=new_version,
            approval=_load_model(approval_file, Approval),
            evaluation_attestations=attestations,
        )
        _emit(approved)


@artifact_app.command("reject")
def artifact_reject(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument(help="Exact evaluated input version.")],
    new_version: Annotated[str, typer.Option("--new-version")],
    rejection_file: Annotated[Path, typer.Argument(help="Human rejection JSON file.")],
    workspace: WorkspaceOption,
) -> None:
    """Reject an evaluated Artifact as a new attributable immutable version."""

    with _handled():
        rejected = _review_workflow(workspace).reject_artifact_proposal(
            _key(RecordKind.ARTIFACT, record_id, version),
            new_version=new_version,
            approval=_load_model(rejection_file, Approval),
        )
        _emit(rejected)


def _require_candidate_snapshot(
    store: ReleaseCandidateSnapshotStore,
    candidate_id: str,
    candidate_version: str,
    disposition_id: str,
) -> ReleaseCandidate:
    key = ReleaseCandidateSnapshotKey(
        candidate_id=candidate_id,
        candidate_version=candidate_version,
        disposition_id=disposition_id,
    )
    return store.require(key).candidate


def _verify_evaluation_snapshot(
    store: ReleaseCandidateSnapshotStore, evaluation: CandidateEvaluation
) -> None:
    candidate = evaluation.candidate
    persisted = _require_candidate_snapshot(
        store,
        candidate.candidate_id,
        candidate.candidate_version,
        candidate.dispositions[-1].disposition_id,
    )
    if persisted != candidate:
        raise ValueError("evaluation file does not match its persisted candidate snapshot")
    report_digest = str(canonical_digest(evaluation.report))
    if candidate.dispositions[-1].gate_report_digest != report_digest:
        raise ValueError("evaluation report digest does not match its persisted disposition")


@candidate_app.command("evaluate")
def candidate_evaluate(
    candidate_id: Annotated[str, typer.Argument()],
    candidate_version: Annotated[str, typer.Argument()],
    disposition_id: Annotated[str, typer.Argument(help="Latest persisted disposition ID.")],
    request_file: Annotated[Path, typer.Argument(help="Evaluation request JSON file.")],
    workspace: WorkspaceOption,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="New JSON handoff file for approval or rejection."),
    ] = None,
) -> None:
    """Evaluate release gates and persist an evaluated snapshot; never approve it."""

    with _handled():
        _, subject_id, factory, store = _candidate_services(workspace)
        candidate = _require_candidate_snapshot(
            store, candidate_id, candidate_version, disposition_id
        )
        request = _load_model(request_file, CandidateEvaluationRequest)
        result = ReleaseService(factory, subject_id=subject_id).evaluate(
            candidate,
            evaluated_at=request.evaluated_at,
            evaluator=request.evaluator,
            disposition_id=request.disposition_id,
            rationale=request.rationale,
        )
        store.put(result.candidate)
        _emit_or_write(result, output)


@candidate_app.command("approve")
def candidate_approve(
    evaluation_file: Annotated[Path, typer.Argument(help="CandidateEvaluation JSON file.")],
    approval_file: Annotated[Path, typer.Argument(help="Explicit human Approval JSON file.")],
    disposition_id: Annotated[str, typer.Option("--disposition-id")],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Persist an approved candidate snapshot after successful gates and human approval."""

    with _handled():
        _, subject_id, factory, store = _candidate_services(workspace)
        evaluation = _load_model(evaluation_file, CandidateEvaluation)
        _verify_evaluation_snapshot(store, evaluation)
        approval = _load_model(approval_file, Approval)
        candidate = ReleaseService(factory, subject_id=subject_id).approve(
            evaluation,
            approval=approval,
            disposition_id=disposition_id,
        )
        store.put(candidate)
        _emit_or_write(candidate, output)


@candidate_app.command("reject")
def candidate_reject(
    evaluation_file: Annotated[Path, typer.Argument(help="CandidateEvaluation JSON file.")],
    rejection_file: Annotated[Path, typer.Argument(help="Explicit human rejection JSON file.")],
    disposition_id: Annotated[str, typer.Option("--disposition-id")],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Persist a rejected candidate snapshot; rejection never creates a Release."""

    with _handled():
        _, subject_id, factory, store = _candidate_services(workspace)
        evaluation = _load_model(evaluation_file, CandidateEvaluation)
        _verify_evaluation_snapshot(store, evaluation)
        rejection = _load_model(rejection_file, Approval)
        candidate = ReleaseService(factory, subject_id=subject_id).reject(
            evaluation,
            rejection=rejection,
            disposition_id=disposition_id,
        )
        store.put(candidate)
        _emit_or_write(candidate, output)


@candidate_app.command("freeze")
def candidate_freeze(
    candidate_id: Annotated[str, typer.Argument()],
    candidate_version: Annotated[str, typer.Argument()],
    disposition_id: Annotated[str, typer.Argument(help="Approved disposition ID.")],
    request_file: Annotated[Path, typer.Argument(help="Immutable Release creation request JSON.")],
    workspace: WorkspaceOption,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Re-run release gates, persist an immutable Release, and freeze the candidate."""

    with _handled():
        _, subject_id, factory, store = _candidate_services(workspace)
        candidate = _require_candidate_snapshot(
            store, candidate_id, candidate_version, disposition_id
        )
        request = _load_model(request_file, CandidateFreezeRequest)
        result = ReleaseService(factory, subject_id=subject_id).freeze(
            candidate,
            release_id=request.release_id,
            record_version=request.record_version,
            release_version=request.release_version,
            released_at=request.released_at,
            created_by=request.created_by,
            disposition_id=request.disposition_id,
            rationale=request.rationale,
        )
        store.put(result.candidate)
        _emit_or_write(result, output)


@candidate_app.command("expire")
def candidate_expire(
    candidate_id: Annotated[str, typer.Argument()],
    candidate_version: Annotated[str, typer.Argument()],
    disposition_id: Annotated[str, typer.Argument(help="Latest persisted disposition ID.")],
    request_file: Annotated[Path, typer.Argument(help="Expiry request JSON file.")],
    workspace: WorkspaceOption,
) -> None:
    """Expire a non-frozen candidate as an immutable snapshot; never delete history."""

    with _handled():
        _, subject_id, factory, store = _candidate_services(workspace)
        candidate = _require_candidate_snapshot(
            store, candidate_id, candidate_version, disposition_id
        )
        request = _load_model(request_file, CandidateExpiryRequest)
        expired = ReleaseService(factory, subject_id=subject_id).expire(
            candidate,
            expired_at=request.expired_at,
            actor=request.actor,
            disposition_id=request.disposition_id,
            rationale=request.rationale,
        )
        store.put(expired)
        _emit(expired)


@candidate_app.command("list")
def candidate_list(
    workspace: WorkspaceOption,
    candidate_id: Annotated[str | None, typer.Option("--candidate-id")] = None,
    state: Annotated[ReleaseCandidateState | None, typer.Option("--state")] = None,
) -> None:
    """List subject-scoped candidate snapshots without selecting a mutable latest alias."""

    with _handled():
        *_, store = _candidate_services(workspace)
        snapshots = store.list(candidate_id=candidate_id, state=state)
        _emit(
            {
                "snapshots": [
                    {
                        "candidate_id": item.key.candidate_id,
                        "candidate_version": item.key.candidate_version,
                        "content_digest": item.content_digest,
                        "disposition_id": item.key.disposition_id,
                        "state": item.candidate.state.value,
                    }
                    for item in snapshots
                ]
            }
        )


@candidate_app.command("show")
def candidate_show(
    candidate_id: Annotated[str, typer.Argument()],
    candidate_version: Annotated[str, typer.Argument()],
    disposition_id: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show one exact immutable candidate disposition snapshot."""

    with _handled():
        *_, store = _candidate_services(workspace)
        _emit(_require_candidate_snapshot(store, candidate_id, candidate_version, disposition_id))


@release_app.command("list")
def release_list(workspace: WorkspaceOption) -> None:
    """List frozen immutable Releases."""

    with _handled():
        _, store = _record_store(workspace)
        records = store.list(record_kind=RecordKind.RELEASE.value)
        _emit(
            {
                "releases": [
                    {
                        "content_digest": str(canonical_digest(item.record)),
                        "record_id": item.key.record_id,
                        "record_version": item.key.version,
                    }
                    for item in records
                ]
            }
        )


@release_app.command("show")
def release_show(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show one exact immutable Release."""

    with _handled():
        _, store = _record_store(workspace)
        stored = store.require(_key(RecordKind.RELEASE, record_id, version)).record
        if not isinstance(stored, Release):
            raise ValueError("stored record is not a Release")
        _emit(stored)


@pack_app.command("compile")
def pack_compile(
    target: Annotated[TargetKind, typer.Argument(help="One of the four file-only targets.")],
    release_id: Annotated[str, typer.Argument()],
    release_version: Annotated[str, typer.Argument()],
    context_file: Annotated[
        Path,
        typer.Argument(help="TargetPackBuildContext JSON with attributable privacy review."),
    ],
    output_name: Annotated[str, typer.Option("--output-name")],
    workspace: WorkspaceOption,
) -> None:
    """Compile, validate, and store a pack without installing or activating it."""

    with _handled():
        paths, subject_id, factory = _services(workspace)
        store = DomainRecordStore(factory, subject_id=subject_id)
        records = tuple(item.record for item in store.list())
        release_record = store.require(_key(RecordKind.RELEASE, release_id, release_version)).record
        if not isinstance(release_record, Release):
            raise ValueError("selected record is not a Release")
        release_state = store.current_lifecycle_state(
            _key(RecordKind.RELEASE, release_id, release_version)
        )
        if release_state != "released":
            raise ValueError(
                f"only an active released lifecycle can be rendered; found {release_state!r}"
            )
        context = _load_model(context_file, TargetPackBuildContext)
        projection = build_release_render_projection(
            release_record,
            records,
            evaluated_at=context.created_at,
        )
        profile = default_target_profile(target)
        rendered = render_target_pack(projection, profile)
        artifacts: list[Artifact] = []
        for reference in release_record.artifact_refs:
            artifact = store.require(
                RecordKey(
                    kind=RecordKind.ARTIFACT.value,
                    record_id=reference.record_id,
                    version=reference.record_version,
                )
            ).record
            if not isinstance(artifact, Artifact):
                raise ValueError("release member did not decode as an Artifact")
            artifacts.append(artifact)
        target_pack = build_validated_target_pack(
            rendered,
            profile,
            release_record,
            artifacts,
            context=context,
        )
        target_key = _key(
            RecordKind.TARGET_PACK,
            target_pack.record_id,
            target_pack.record_version,
        )
        existing = store.get(target_key)
        if existing is not None and existing.record != target_pack:
            raise ValueError("target-pack identity already names different immutable content")
        output = prepare_new_output_directory(paths.packs, output_name)
        written = write_rendered_pack(rendered, output)
        if existing is None:
            built_event_id = (
                f"target-pack-{target_pack.record_id}-{target_pack.record_version}-built"
            )
            built_event = make_lifecycle_event(
                event_id=built_event_id,
                entity=target_key,
                from_state=None,
                to_state="built",
                previous_event_id=None,
                actor=context.created_by,
                policy_version=target_pack.policy_version,
                reason="Build immutable target-pack files",
                occurred_at=context.created_at,
            )
            validated_event = make_lifecycle_event(
                event_id=(
                    f"target-pack-{target_pack.record_id}-{target_pack.record_version}-validated"
                ),
                entity=target_key,
                from_state="built",
                to_state="validated",
                previous_event_id=built_event_id,
                actor=context.created_by,
                policy_version=target_pack.policy_version,
                reason="Validate target-pack capability and trace preservation",
                occurred_at=context.created_at,
            )
            store.add_with_lifecycle(target_pack, (built_event, validated_event))
        _emit(
            {
                "activated": False,
                "files": [str(path) for path in written],
                "pack_digest": rendered.pack_digest,
                "target": target.value,
                "target_pack": {
                    "record_id": target_pack.record_id,
                    "record_version": target_pack.record_version,
                },
            }
        )


@pack_app.command("list")
def pack_list(workspace: WorkspaceOption) -> None:
    """List compiled target-pack records without reading rendered file contents."""

    with _handled():
        _emit({"target_packs": _list_records_of_kind(workspace, RecordKind.TARGET_PACK)})


@pack_app.command("show")
def pack_show(
    record_id: Annotated[str, typer.Argument()],
    version: Annotated[str, typer.Argument()],
    workspace: WorkspaceOption,
) -> None:
    """Show one exact payload-free TargetPack manifest."""

    from adaptation_compiler_lab.domain import TargetPack

    with _handled():
        _emit(
            _show_record_of_type(workspace, RecordKind.TARGET_PACK, record_id, version, TargetPack)
        )


def _activation_change(
    *,
    action: str,
    environment_id: str,
    release_id: str,
    release_version: str,
    target_pack_id: str,
    target_pack_version: str,
    approval_file: Path,
    workspace: Path,
) -> ActivationPointer:
    _, _, factory = _services(workspace)
    service = ActivationService(factory)
    operation = getattr(service, action)
    approval = _load_model(approval_file, Approval)
    return cast(
        ActivationPointer,
        operation(
            environment_id=environment_id,
            release=_key(RecordKind.RELEASE, release_id, release_version),
            target_pack=_key(RecordKind.TARGET_PACK, target_pack_id, target_pack_version),
            approval=approval,
        ),
    )


@activation_app.command("canary")
def activation_canary(
    environment_id: Annotated[str, typer.Argument()],
    approval_file: Annotated[Path, typer.Argument(help="Human Approval JSON file.")],
    release_id: Annotated[str, typer.Option("--release-id")],
    release_version: Annotated[str, typer.Option("--release-version")],
    target_pack_id: Annotated[str, typer.Option("--target-pack-id")],
    target_pack_version: Annotated[str, typer.Option("--target-pack-version")],
    workspace: WorkspaceOption,
) -> None:
    """Create an explicit canary pointer after validating an exact Release/TargetPack pair."""

    with _handled():
        pointer = _activation_change(
            action="canary",
            environment_id=environment_id,
            release_id=release_id,
            release_version=release_version,
            target_pack_id=target_pack_id,
            target_pack_version=target_pack_version,
            approval_file=approval_file,
            workspace=workspace,
        )
        _emit(_pointer_payload(pointer))


@activation_app.command("activate")
def activation_activate(
    environment_id: Annotated[str, typer.Argument()],
    approval_file: Annotated[Path, typer.Argument(help="Human Approval JSON file.")],
    release_id: Annotated[str, typer.Option("--release-id")],
    release_version: Annotated[str, typer.Option("--release-version")],
    target_pack_id: Annotated[str, typer.Option("--target-pack-id")],
    target_pack_version: Annotated[str, typer.Option("--target-pack-version")],
    workspace: WorkspaceOption,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Acknowledge this explicit activation state change."),
    ] = False,
) -> None:
    """Activate an exact pair only with an explicit confirmation flag."""

    with _handled():
        if not confirm:
            raise ValueError("activation requires --confirm; no state was changed")
        pointer = _activation_change(
            action="activate",
            environment_id=environment_id,
            release_id=release_id,
            release_version=release_version,
            target_pack_id=target_pack_id,
            target_pack_version=target_pack_version,
            approval_file=approval_file,
            workspace=workspace,
        )
        _emit(_pointer_payload(pointer))


@activation_app.command("rollback")
def activation_rollback(
    environment_id: Annotated[str, typer.Argument()],
    approval_file: Annotated[Path, typer.Argument(help="Human Approval JSON file.")],
    release_id: Annotated[str, typer.Option("--release-id")],
    release_version: Annotated[str, typer.Option("--release-version")],
    target_pack_id: Annotated[str, typer.Option("--target-pack-id")],
    target_pack_version: Annotated[str, typer.Option("--target-pack-version")],
    workspace: WorkspaceOption,
) -> None:
    """Rollback only to an exact pair previously used in the same environment."""

    with _handled():
        pointer = _activation_change(
            action="rollback",
            environment_id=environment_id,
            release_id=release_id,
            release_version=release_version,
            target_pack_id=target_pack_id,
            target_pack_version=target_pack_version,
            approval_file=approval_file,
            workspace=workspace,
        )
        _emit(_pointer_payload(pointer))


@activation_app.command("status")
def activation_status(
    environment_id: Annotated[str, typer.Argument()], workspace: WorkspaceOption
) -> None:
    """Show the current derived activation pointer without changing it."""

    with _handled():
        _, _, factory = _services(workspace)
        _emit(_pointer_payload(ActivationService(factory).current(environment_id)))


@export_app.command("sanitized")
def export_sanitized(
    release_id: Annotated[str, typer.Argument()],
    release_version: Annotated[str, typer.Argument()],
    output_name: Annotated[str, typer.Option("--output-name")],
    workspace: WorkspaceOption,
) -> None:
    """Export promoted records and opaque evidence references, never raw evidence payloads."""

    with _handled():
        paths, store = _record_store(workspace)
        release_record = store.require(_key(RecordKind.RELEASE, release_id, release_version)).record
        if not isinstance(release_record, Release):
            raise ValueError("selected record is not a Release")
        artifacts: list[Artifact] = []
        for reference in release_record.artifact_refs:
            record = store.require(
                RecordKey(
                    kind=RecordKind.ARTIFACT.value,
                    record_id=reference.record_id,
                    version=reference.record_version,
                )
            ).record
            if not isinstance(record, Artifact):
                raise ValueError("release member did not decode as an Artifact")
            artifacts.append(record)
        export = build_sanitized_release_export(release_record, artifacts)
        output = prepare_new_output_directory(paths.exports, output_name)
        written = write_sanitized_release_export(export, output)
        _emit(
            {
                "export_digest": export.export_digest,
                "files": [str(path) for path in written],
                "output": str(output),
            }
        )


@benchmark_app.command("validate")
def benchmark_validate(
    config_file: Annotated[Path, typer.Argument(help="BenchmarkConfig JSON file.")],
    outcomes_file: Annotated[
        Path | None,
        typer.Option("--outcomes", help="Optional JSON array of blinded benchmark outcomes."),
    ] = None,
    manifest_output: Annotated[Path | None, typer.Option("--manifest-output")] = None,
) -> None:
    """Validate design boundaries without revealing condition identities or held-out payloads."""

    with _handled():
        config = validate_benchmark_config(_load_model(config_file, BenchmarkConfig))
        outcomes: tuple[BenchmarkOutcomeRecord, ...] = ()
        if outcomes_file is not None:
            outcomes = TypeAdapter(tuple[BenchmarkOutcomeRecord, ...]).validate_json(
                _read_text(outcomes_file)
            )
            validate_benchmark_outcomes(config, outcomes)
        digest = benchmark_manifest_digest(config)
        if manifest_output is not None:
            _write_new_text(manifest_output, canonical_benchmark_manifest(config))
        _emit(
            {
                "condition_count": len(config.condition_bundles),
                "manifest_digest": digest,
                "manifest_output": None
                if manifest_output is None
                else str(manifest_output.resolve()),
                "outcome_count": len(outcomes),
                "valid": True,
            }
        )


@schema_app.command("export")
def schema_export(
    output_directory: Annotated[Path, typer.Argument(help="New or empty output directory.")],
    version: Annotated[str, typer.Option("--version")] = "1.0",
) -> None:
    """Export immutable v1.0 schemas or the additive Evidence v1.1 schema."""

    with _handled():
        if version not in {"1.0", "1.1"}:
            raise ValueError("schema version must be 1.0 or 1.1")
        resolved = output_directory.expanduser().resolve()
        if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
            raise FileExistsError("schema output directory must be new or empty")
        written = export_json_schemas(resolved, version=cast(Literal["1.0", "1.1"], version))
        _emit({"count": len(written), "files": [str(path) for path in written]})


def main() -> None:
    """Console-script entry point."""

    app()


if __name__ == "__main__":  # pragma: no cover - console script path
    main()
