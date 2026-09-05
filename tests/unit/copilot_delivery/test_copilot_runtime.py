from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.copilot_delivery import (
    COPILOT_CLI_TARGET_FAMILY,
    CopilotHookAuthorizationV1,
    CopilotHookHandler,
    CopilotProjectionCandidate,
    LocalCopilotHookRuntime,
    parse_copilot_hook_input,
)
from adaptation_compiler_lab.domain import ArtifactRef, ReleaseRef
from adaptation_compiler_lab.governance import SignerIdentity, SignerRole
from adaptation_compiler_lab.governance.signing import GovernanceSigner, create_signer_identity
from adaptation_compiler_lab.instruction_environment import InstructionEnvironmentService
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
)
from adaptation_compiler_lab.targets.models import ScopeDimension

NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _signer() -> tuple[GovernanceSigner, SignerIdentity]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-owner-key",
        subject_id="temper-owner",
    )
    identity = create_signer_identity(
        signer,
        roles=tuple(sorted(SignerRole, key=lambda item: item.value)),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=31),
    )
    return signer, identity


def _authorization(**changes: object) -> CopilotHookAuthorizationV1:
    return CopilotHookAuthorizationV1(
        subject_id="temper-owner",
        project_id="green-meadow",
        consent_digest=DIGEST_A,
        project_registration_digest=DIGEST_B,
        delivery_enabled=True,
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=20),
    ).model_copy(update=changes)


def _projection() -> CanonicalRuntimeProjection:
    artifact = ArtifactRef(
        record_id="artifact-one",
        record_version="1.0.0",
        content_digest=DIGEST_A,
    )
    clauses = tuple(
        sorted(
            (
                RuntimeClause(
                    text="Explain purpose before commands.",
                    roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                    source_artifact_refs=(artifact,),
                ),
                RuntimeClause(
                    text="Prefer names that represent real things.",
                    roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                    source_artifact_refs=(artifact,),
                ),
            ),
            key=lambda item: item.content_digest,
        )
    )
    return CanonicalRuntimeProjection(
        external_release_digest=DIGEST_A,
        release_ref=ReleaseRef(
            record_id="release-one",
            record_version="1.0.0",
            content_digest=DIGEST_B,
        ),
        context=RuntimeProjectionContext(
            known_dimensions=(
                ScopeDimension.PROJECT_IDS,
                ScopeDimension.SUBJECT_IDS,
                ScopeDimension.TARGET_FAMILIES,
            ),
            target_profile_id=COPILOT_CLI_TARGET_FAMILY,
            subject_id="temper-owner",
            project_id="green-meadow",
            target_family=COPILOT_CLI_TARGET_FAMILY,
            evaluated_at=NOW,
        ),
        clauses=clauses,
    )


def _runtime(
    tmp_path: Path,
    *,
    authorization: CopilotHookAuthorizationV1 | None = None,
) -> tuple[Path, LocalCopilotHookRuntime, CopilotHookHandler, Path]:
    project = tmp_path / "project"
    (project / ".github").mkdir(parents=True)
    (project / "src").mkdir()
    (project / ".github" / "copilot-instructions.md").write_text(
        "Explain purpose before commands.\n",
        encoding="utf-8",
    )
    signer, identity = _signer()
    environment = InstructionEnvironmentService(
        projects={"green-meadow": project},
        state_root=tmp_path / "state",
        include_persisted_global_roots=False,
    )
    selected = authorization or _authorization()
    receipt_path = tmp_path / "state" / "copilot-delivery" / "deliveries.jsonl"
    runtime = LocalCopilotHookRuntime(
        projects={"green-meadow": project},
        signer=signer,
        signer_identity=identity,
        instruction_environment=environment,
        authorization_provider=lambda project_id, effective_at: (
            selected if project_id == "green-meadow" else None
        ),
        projection_provider=lambda project_id, effective_at: (
            _projection() if project_id == "green-meadow" else None
        ),
        receipt_path=receipt_path,
        clock=lambda: NOW,
    )
    return project, runtime, CopilotHookHandler(runtime), receipt_path


def _payload(project: Path) -> dict[str, object]:
    return {
        "sessionId": "copilot-session-one",
        "timestamp": 1788610000000,
        "cwd": str(project / "src"),
        "prompt": "Use a real name for this module.",
        "transformedPrompt": "Use a real name for this module.",
    }


def test_parser_accepts_only_exact_official_shape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    parsed = parse_copilot_hook_input(_payload(project))
    assert parsed.session_id == "copilot-session-one"
    bad = _payload(project)
    bad["transcriptPath"] = "never-read.jsonl"
    try:
        parse_copilot_hook_input(bad)
    except ValueError as error:
        assert "fields changed" in str(error)
    else:
        raise AssertionError("unknown hook fields must fail closed")


def test_runtime_delivers_only_missing_delta_and_stores_no_prompt(tmp_path: Path) -> None:
    project, runtime, handler, receipt_path = _runtime(tmp_path)
    lease = runtime.prepare_projection("green-meadow", issued_at=NOW)
    output = handler(_payload(project))

    assert lease is not None and output is not None
    rendered = str(output["modifiedTransformedPrompt"])
    assert rendered.startswith("Use a real name for this module.")
    assert "Prefer names that represent real things." in rendered
    assert "Explain purpose before commands." not in rendered
    assert set(output) == {"modifiedTransformedPrompt"}
    manifest = runtime.projection_manifest("green-meadow")
    assert manifest is not None
    assert len(manifest.included_clause_digests) == 1
    assert len(manifest.omitted_clause_digests) == 1
    ledger = receipt_path.read_text(encoding="utf-8")
    assert "Use a real name for this module" not in ledger
    assert '"raw_payloads_stored":false' in ledger


def test_hook_path_uses_cached_lease_and_native_change_noops(tmp_path: Path) -> None:
    project, runtime, handler, receipt_path = _runtime(tmp_path)
    calls = 0
    original = runtime._projection_provider

    def counted(
        project_id: str, effective_at: datetime
    ) -> CanonicalRuntimeProjection | CopilotProjectionCandidate | None:
        nonlocal calls
        calls += 1
        return original(project_id, effective_at)

    runtime._projection_provider = counted
    assert runtime.prepare_projection("green-meadow", issued_at=NOW) is not None
    assert handler(_payload(project)) is not None
    assert calls == 1
    before = receipt_path.read_bytes()
    (project / ".github" / "copilot-instructions.md").write_text(
        "Explain purpose before commands.\nNever reveal credentials.\n",
        encoding="utf-8",
    )
    assert handler(_payload(project)) is None
    assert receipt_path.read_bytes() == before
    assert calls == 1


def test_unauthorized_or_unregistered_invocation_is_a_silent_noop(tmp_path: Path) -> None:
    expired = _authorization(expires_at=NOW)
    project, runtime, handler, receipt_path = _runtime(tmp_path, authorization=expired)
    assert runtime.prepare_projection("green-meadow", issued_at=NOW) is None
    assert handler(_payload(project)) is None
    assert not receipt_path.exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    assert handler(_payload(outside)) is None
