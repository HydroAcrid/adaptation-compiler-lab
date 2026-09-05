from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.claude_delivery import (
    ClaudeCapturedAuthority,
    ClaudeHookAuthorizationV1,
    ClaudeHookDisposition,
    ClaudeHookLedger,
    ClaudeHookRuntimeError,
    ClaudeHookRuntimeHandler,
    LocalClaudeHookRuntimePort,
)
from adaptation_compiler_lab.domain import ArtifactRef, ReleaseRef
from adaptation_compiler_lab.governance import SignerIdentity, SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
)
from adaptation_compiler_lab.instruction_environment import InstructionEnvironmentService
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
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


def _authorization(**changes: object) -> ClaudeHookAuthorizationV1:
    return ClaudeHookAuthorizationV1(
        subject_id="temper-owner",
        project_id="green-meadow",
        consent_digest=DIGEST_A,
        project_registration_digest=DIGEST_B,
        learning_enabled=True,
        delivery_enabled=True,
        effective_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=20),
        retention_until=NOW + timedelta(days=30),
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
            target_profile_id="claude-code",
            subject_id="temper-owner",
            project_id="green-meadow",
            target_family="claude-code",
            evaluated_at=NOW,
        ),
        clauses=clauses,
    )


def _runtime(
    tmp_path: Path,
    *,
    authorization: ClaudeHookAuthorizationV1 | None = None,
) -> tuple[
    Path,
    LocalRawPayloadStore,
    ClaudeHookLedger,
    LocalClaudeHookRuntimePort,
    ClaudeHookRuntimeHandler,
    GovernanceSigner,
    SignerIdentity,
]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "CLAUDE.md").write_text(
        "Explain purpose before commands.\n",
        encoding="utf-8",
    )
    signer, identity = _signer()
    raw_store = LocalRawPayloadStore(
        tmp_path / "raw",
        encryption_key=RawEncryptionKey(bytes(range(32))),
    )
    ledger = ClaudeHookLedger(
        tmp_path / "state" / "claude" / "runtime-ledger.jsonl",
        signer=signer,
        signer_identity=identity,
    )
    instruction_environment = InstructionEnvironmentService(
        projects={"green-meadow": project},
        state_root=tmp_path / "state",
        include_persisted_global_roots=False,
    )
    selected_authorization = authorization or _authorization()
    port = LocalClaudeHookRuntimePort(
        projects={"green-meadow": project},
        signer=signer,
        signer_identity=identity,
        raw_store=raw_store,
        ledger=ledger,
        instruction_environment=instruction_environment,
        authorization_provider=lambda project_id, effective_at: (
            selected_authorization if project_id == "green-meadow" else None
        ),
        projection_provider=lambda project_id, effective_at: (
            _projection() if project_id == "green-meadow" else None
        ),
        clock=lambda: NOW,
    )
    handler = ClaudeHookRuntimeHandler(
        port,
        signer=signer,
        signer_identity=identity,
        clock=lambda: NOW,
    )
    return project, raw_store, ledger, port, handler, signer, identity


def _prompt_payload(project: Path) -> dict[str, object]:
    return {
        "session_id": "claude-session-one",
        "cwd": str(project / "src"),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "I prefer concrete project names.",
        "transcript_path": str(project / "never-read.jsonl"),
    }


def test_runtime_prepares_native_aware_lease_and_captures_exact_prompt_encrypted(
    tmp_path: Path,
) -> None:
    project, raw_store, ledger, port, handler, _signer_value, _identity = _runtime(tmp_path)

    lease = port.prepare_projection("green-meadow", issued_at=NOW)
    output = handler(_prompt_payload(project))

    assert lease is not None
    assert output is not None
    assert "Prefer names that represent real things." in json.dumps(output)
    assert "Explain purpose before commands." not in json.dumps(output)
    manifest = port.projection_manifest("green-meadow")
    assert manifest is not None
    assert len(manifest.included_clause_digests) == 1
    assert len(manifest.omitted_clause_digests) == 1
    assert len(ledger.entries) == 2
    capture = ledger.entries[0].capture_receipt
    assert capture is not None
    assert capture.authority is ClaudeCapturedAuthority.USER_AUTHORED_INPUT
    assert capture.consent_digest == DIGEST_A
    reference = RawPayloadRef(
        sha256=capture.raw_payload_sha256,
        size_bytes=capture.raw_payload_size_bytes,
        media_type=capture.media_type,
        relative_path=ledger.entries[0].raw_payload_relative_path or "",
    )
    assert raw_store.read(reference) == b"I prefer concrete project names."
    assert not (project / "never-read.jsonl").exists()
    assert ledger.entries[1].audit_receipt is not None
    assert ledger.entries[1].audit_receipt.disposition is ClaudeHookDisposition.DELIVERED


def test_native_instruction_change_invalidates_prepared_lease_without_recompiling(
    tmp_path: Path,
) -> None:
    project, _raw_store, ledger, port, handler, _signer_value, _identity = _runtime(tmp_path)
    assert port.prepare_projection("green-meadow", issued_at=NOW) is not None
    (project / "CLAUDE.md").write_text(
        "Explain purpose before commands.\nNever reveal credentials.\n",
        encoding="utf-8",
    )

    output = handler(_prompt_payload(project))

    assert output is None
    audit = ledger.entries[-1].audit_receipt
    assert audit is not None
    assert audit.disposition is ClaudeHookDisposition.NOOP_INVALID_PROJECTION


def test_hook_path_uses_cached_projection_and_never_calls_projection_provider(
    tmp_path: Path,
) -> None:
    project, _raw_store, _ledger, port, handler, _signer_value, _identity = _runtime(tmp_path)
    calls = 0
    original = port._projection_provider

    def counted(project_id: str, effective_at: datetime) -> CanonicalRuntimeProjection | None:
        nonlocal calls
        calls += 1
        return original(project_id, effective_at)

    port._projection_provider = counted
    assert port.prepare_projection("green-meadow", issued_at=NOW) is not None
    assert calls == 1

    assert handler(_prompt_payload(project)) is not None
    assert handler(_prompt_payload(project)) is not None
    assert calls == 1


@pytest.mark.parametrize(
    ("payload", "authority", "disposition"),
    [
        (
            {
                "session_id": "claude-session-one",
                "hook_event_name": "Stop",
                "last_assistant_message": "I changed the module.",
            },
            ClaudeCapturedAuthority.UNTRUSTED_ASSISTANT_CONTEXT,
            ClaudeHookDisposition.OUTCOME_CAPTURED,
        ),
        (
            {
                "session_id": "claude-session-one",
                "hook_event_name": "StopFailure",
                "error": "tool_failure",
                "error_details": "The bounded command failed.",
            },
            ClaudeCapturedAuthority.UNTRUSTED_FAILURE_CONTEXT,
            ClaudeHookDisposition.FAILURE_CAPTURED,
        ),
    ],
)
def test_assistant_and_failure_capture_remain_explicitly_untrusted(
    tmp_path: Path,
    payload: dict[str, object],
    authority: ClaudeCapturedAuthority,
    disposition: ClaudeHookDisposition,
) -> None:
    project, _raw_store, ledger, _port, handler, _signer_value, _identity = _runtime(tmp_path)
    payload["cwd"] = str(project)

    assert handler(payload) is None

    capture = ledger.entries[0].capture_receipt
    audit = ledger.entries[1].audit_receipt
    assert capture is not None and capture.authority is authority
    assert audit is not None and audit.disposition is disposition


def test_unauthorized_project_neither_captures_nor_delivers(tmp_path: Path) -> None:
    expired = _authorization(expires_at=NOW, retention_until=NOW + timedelta(days=1))
    project, _raw_store, ledger, port, handler, _signer_value, _identity = _runtime(
        tmp_path,
        authorization=expired,
    )

    assert port.prepare_projection("green-meadow", issued_at=NOW) is None
    assert handler(_prompt_payload(project)) is None
    assert len(ledger.entries) == 1
    audit = ledger.entries[0].audit_receipt
    assert audit is not None
    assert audit.disposition is ClaudeHookDisposition.NOOP_UNAUTHORIZED


def test_ledger_detects_signed_entry_tampering_on_restart(tmp_path: Path) -> None:
    project, _raw_store, _ledger, port, handler, signer, identity = _runtime(tmp_path)
    assert port.prepare_projection("green-meadow", issued_at=NOW) is not None
    assert handler(_prompt_payload(project)) is not None
    path = tmp_path / "state" / "claude" / "runtime-ledger.jsonl"
    payload = path.read_text(encoding="utf-8").replace(
        "green-meadow",
        "green-meadow-tampered",
        1,
    )
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ClaudeHookRuntimeError, match="verification failed"):
        ClaudeHookLedger(path, signer=signer, signer_identity=identity)


def test_runtime_rejects_overlapping_registered_projects(tmp_path: Path) -> None:
    project = tmp_path / "project"
    nested = project / "nested"
    nested.mkdir(parents=True)
    signer, identity = _signer()
    raw_store = LocalRawPayloadStore(
        tmp_path / "raw",
        encryption_key=RawEncryptionKey(bytes(range(32))),
    )
    ledger = ClaudeHookLedger(
        tmp_path / "state" / "ledger.jsonl",
        signer=signer,
        signer_identity=identity,
    )
    environment = InstructionEnvironmentService(
        projects={"parent": project, "nested": nested},
        state_root=tmp_path / "state",
        include_persisted_global_roots=False,
    )

    with pytest.raises(ClaudeHookRuntimeError, match="overlap"):
        LocalClaudeHookRuntimePort(
            projects={"parent": project, "nested": nested},
            signer=signer,
            signer_identity=identity,
            raw_store=raw_store,
            ledger=ledger,
            instruction_environment=environment,
            authorization_provider=lambda project_id, effective_at: None,
            projection_provider=lambda project_id, effective_at: None,
        )
