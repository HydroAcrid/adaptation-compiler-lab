from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.domain import ArtifactRef, ReleaseRef
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.instruction_environment import (
    InstructionEnvironmentError,
    InstructionEnvironmentService,
    InstructionRelationKind,
)
from adaptation_compiler_lab.instruction_environment.models import (
    NativeInstructionClauseV1,
    NativeInstructionKind,
    NativeNormStrength,
    NativeTarget,
)
from adaptation_compiler_lab.instruction_environment.resolver import (
    build_instruction_delta_plan,
)
from adaptation_compiler_lab.instruction_environment.semantic import (
    ClauseRelationAnalysisV1,
    ClauseSemanticAnalysisV1,
    InstructionRelationPairV1,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
)
from adaptation_compiler_lab.targets.models import ScopeDimension

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class _SemanticAnalyzer:
    calls = 0

    def analyze(
        self, clauses: Sequence[NativeInstructionClauseV1]
    ) -> Mapping[str, ClauseSemanticAnalysisV1]:
        self.calls += 1
        return {
            clause.clause_id: ClauseSemanticAnalysisV1(
                clause_id=clause.clause_id,
                clause_text_digest=clause.text_digest,
                source_digest=clause.source_digest,
                kind=NativeInstructionKind.NORM,
                norm_strength=NativeNormStrength.INVARIANT,
                polarity="positive",
                explicit_exception=False,
                scope_labels=clause.scope_labels,
                confidence=0.97,
                interpreter_digest=DIGEST_A,
            )
            for clause in clauses
        }


class _RelationAnalyzer:
    calls = 0
    relation = InstructionRelationKind.SEMANTIC_EQUIVALENT

    def compare(
        self, pairs: Sequence[InstructionRelationPairV1]
    ) -> Mapping[str, ClauseRelationAnalysisV1]:
        self.calls += 1
        interpreter = DIGEST_A if self.calls % 2 else DIGEST_B
        return {
            pair.pair_id: ClauseRelationAnalysisV1(
                pair_id=pair.pair_id,
                temper_clause_digest=pair.temper_clause_digest,
                native_clause_id=pair.native_clause_id,
                native_clause_digest=pair.native_clause_digest,
                relation=self.relation,
                confidence=0.96,
                interpreter_digest=interpreter,
            )
            for pair in pairs
        }


def _projection() -> CanonicalRuntimeProjection:
    artifact = ArtifactRef(
        record_id="artifact-one",
        record_version="1.0.0",
        content_digest=DIGEST_A,
    )
    return CanonicalRuntimeProjection(
        external_release_digest=DIGEST_A,
        release_ref=ReleaseRef(
            record_id="release-one",
            record_version="1.0.0",
            content_digest=DIGEST_B,
        ),
        context=RuntimeProjectionContext(
            known_dimensions=(ScopeDimension.PROJECT_IDS, ScopeDimension.TARGET_FAMILIES),
            project_id="temper",
            target_family="codex",
        ),
        clauses=(
            RuntimeClause(
                text="Run the affected test before reporting completion.",
                roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                source_artifact_refs=(artifact,),
            ),
        ),
    )


def _service(
    tmp_path: Path,
    project: Path,
    *,
    raw_store: LocalRawPayloadStore | None = None,
    signer: GovernanceSigner | None = None,
) -> InstructionEnvironmentService:
    return InstructionEnvironmentService(
        projects={"temper": project},
        state_root=tmp_path / "state",
        raw_store=raw_store
        or LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"r" * 32)),
        signer=signer
        or GovernanceSigner(
            Ed25519PrivateKey.generate(), identity_id="temper-local", subject_id="kevin"
        ),
        clock=lambda: NOW,
    )


def test_global_sources_are_absent_until_explicit_preview_and_enable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    (home / ".agents" / "skills" / "personal").mkdir(parents=True)
    (home / ".agents" / "skills" / "personal" / "SKILL.md").write_text(
        "Use concrete names.\n", encoding="utf-8"
    )
    service = _service(tmp_path, project)

    before = service.summary(project_id="temper", target=NativeTarget.CODEX)
    preview = service.preview_global(target=NativeTarget.CODEX, root=home)
    enabled = service.enable_global(
        preview_token=preview.preview_token,
        target=NativeTarget.CODEX,
        idempotency_key="enable-personal-codex",
    )[0]

    assert before.source_count == 0
    assert preview.source_count == 1
    assert not preview.authorizes_learning
    assert enabled.global_sources_enabled
    assert enabled.skill_count == 1
    assert enabled.sources[0].observed_context_only


def test_preview_apply_and_rollback_are_digest_bound_and_encrypted(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = project / "AGENTS.md"
    original = "# Project instructions\n\nKeep changes focused.\n"
    source.write_text(original, encoding="utf-8", newline="\n")
    raw_store = LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"r" * 32))
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(), identity_id="temper-local", subject_id="kevin"
    )
    service = _service(tmp_path, project, raw_store=raw_store, signer=signer)
    summary = service.summary(project_id="temper", target=NativeTarget.CODEX)
    source_id = summary.sources[0].source_id

    preview = service.preview_change(
        project_id="temper",
        target=NativeTarget.CODEX,
        source_id=source_id,
        expected_environment_digest=summary.environment_digest,
        instruction_text="Explain the purpose before procedural detail.",
    )
    receipt = service.apply_change(
        preview_token=preview.preview_token,
        target=NativeTarget.CODEX,
        expected_environment_digest=summary.environment_digest,
        idempotency_key="apply-managed-section",
    )

    assert "Temper-managed instructions" in source.read_text(encoding="utf-8")
    assert receipt.signature_base64
    assert receipt.backup_digest.startswith("sha256:")
    raw_files = [item for item in (tmp_path / "raw").rglob("*") if item.is_file()]
    assert raw_files
    assert all(original.encode("utf-8") not in item.read_bytes() for item in raw_files)

    reopened = _service(tmp_path, project, raw_store=raw_store, signer=signer)
    replay = reopened.apply_change(
        preview_token=preview.preview_token,
        target=NativeTarget.CODEX,
        expected_environment_digest=summary.environment_digest,
        idempotency_key="apply-managed-section",
    )
    rolled_back = reopened.rollback_change(
        receipt_id=receipt.receipt_id,
        target=NativeTarget.CODEX,
        expected_environment_digest=receipt.environment_digest_after,
        idempotency_key="rollback-managed-section",
    )

    assert replay == receipt
    assert rolled_back.status == "rolled_back"
    assert rolled_back.rollback_of_receipt_id == receipt.receipt_id
    assert source.read_text(encoding="utf-8") == original

    after_restart = _service(tmp_path, project, raw_store=raw_store, signer=signer)
    with pytest.raises(InstructionEnvironmentError, match="unavailable"):
        after_restart.rollback_change(
            receipt_id=receipt.receipt_id,
            target=NativeTarget.CODEX,
            expected_environment_digest=rolled_back.environment_digest_after,
            idempotency_key="second-rollback",
        )


def test_tampered_native_change_receipt_index_fails_closed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = project / "AGENTS.md"
    source.write_text("Original.\n", encoding="utf-8")
    raw_store = LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"r" * 32))
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(), identity_id="temper-local", subject_id="kevin"
    )
    service = _service(tmp_path, project, raw_store=raw_store, signer=signer)
    summary = service.summary(project_id="temper", target=NativeTarget.CODEX)
    preview = service.preview_change(
        project_id="temper",
        target=NativeTarget.CODEX,
        source_id=summary.sources[0].source_id,
        expected_environment_digest=summary.environment_digest,
        instruction_text="Keep changes focused.",
    )
    service.apply_change(
        preview_token=preview.preview_token,
        target=NativeTarget.CODEX,
        expected_environment_digest=summary.environment_digest,
        idempotency_key="write-before-tamper",
    )
    index = tmp_path / "state" / "instruction-environment" / "native-change-receipts.json"
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["entries"][0]["receipt"]["after_digest"] = "sha256:" + "0" * 64
    index.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InstructionEnvironmentError, match="verification"):
        _service(tmp_path, project, raw_store=raw_store, signer=signer)


def test_stale_preview_refuses_write_without_changing_source(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = project / "AGENTS.md"
    source.write_text("Original.\n", encoding="utf-8")
    service = _service(tmp_path, project)
    summary = service.summary(project_id="temper", target=NativeTarget.CODEX)
    preview = service.preview_change(
        project_id="temper",
        target=NativeTarget.CODEX,
        source_id=summary.sources[0].source_id,
        expected_environment_digest=summary.environment_digest,
        instruction_text="New managed behavior.",
    )
    source.write_text("Human changed this.\n", encoding="utf-8")

    with pytest.raises(InstructionEnvironmentError, match="changed after preview"):
        service.apply_change(
            preview_token=preview.preview_token,
            target=NativeTarget.CODEX,
            expected_environment_digest=summary.environment_digest,
            idempotency_key="stale-write",
        )

    assert source.read_text(encoding="utf-8") == "Human changed this.\n"


def test_idempotency_key_cannot_be_reused_for_another_global_action(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    service = _service(tmp_path, project)
    preview = service.preview_global(target=NativeTarget.CODEX, root=home)
    service.enable_global(
        preview_token=preview.preview_token,
        target=NativeTarget.CODEX,
        idempotency_key="same-key",
    )

    with pytest.raises(InstructionEnvironmentError, match="reused"):
        service.disable_global(target=NativeTarget.CODEX, idempotency_key="same-key")


def test_semantic_classification_and_independent_relations_are_encrypted_and_cached(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(
        "Verify the relevant test before saying the work is done.\n",
        encoding="utf-8",
    )
    projection = _projection()
    semantic = _SemanticAnalyzer()
    relations = _RelationAnalyzer()
    raw_store = LocalRawPayloadStore(
        tmp_path / "raw",
        encryption_key=RawEncryptionKey(b"r" * 32),
    )
    service = InstructionEnvironmentService(
        projects={"temper": project},
        state_root=tmp_path / "state",
        raw_store=raw_store,
        semantic_analyzer=semantic,
        analyzer_digest=DIGEST_A,
        relation_analyzer=relations,
        relation_analyzer_digest=DIGEST_B,
        projection_provider=lambda _project, _target: projection,
        clock=lambda: NOW,
    )

    assert (
        service.summary(project_id="temper", target=NativeTarget.CODEX).semantic_analysis_status
        == "not_requested"
    )
    analyzed = service.analyze(project_id="temper", target=NativeTarget.CODEX)
    cached = service.cached_relations(projection, analyzed)
    plan = build_instruction_delta_plan(projection, analyzed, semantic_relations=cached)
    service.analyze(project_id="temper", target=NativeTarget.CODEX)

    assert semantic.calls == 1
    assert relations.calls == 2
    assert cached[0].relation is InstructionRelationKind.SEMANTIC_EQUIVALENT
    assert plan.omitted_temper_clause_digests == (projection.clauses[0].content_digest,)
    assert plan.output_utf8_bytes == 0
    assert (
        service.summary(project_id="temper", target=NativeTarget.CODEX).semantic_analysis_status
        == "current"
    )
    encrypted = [item.read_bytes() for item in (tmp_path / "raw").rglob("*") if item.is_file()]
    assert encrypted
    assert all(b"Verify the relevant test" not in item for item in encrypted)

    (project / "AGENTS.md").write_text(
        "Verify focused and full tests before saying the work is done.\n",
        encoding="utf-8",
    )
    service.refresh(project_id="temper", target=NativeTarget.CODEX)
    assert (
        service.summary(project_id="temper", target=NativeTarget.CODEX).semantic_analysis_status
        == "stale"
    )


def test_blocking_conflict_summary_is_bounded_and_raw_free(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(
        "Never run the affected test in this project.\n", encoding="utf-8"
    )

    class ContradictionAnalyzer(_RelationAnalyzer):
        relation = InstructionRelationKind.CONTRADICTION

    service = InstructionEnvironmentService(
        projects={"temper": project},
        state_root=tmp_path / "state",
        raw_store=LocalRawPayloadStore(
            tmp_path / "raw", encryption_key=RawEncryptionKey(b"r" * 32)
        ),
        semantic_analyzer=_SemanticAnalyzer(),
        analyzer_digest=DIGEST_A,
        relation_analyzer=ContradictionAnalyzer(),
        relation_analyzer_digest=DIGEST_B,
        projection_provider=lambda _project, _target: _projection(),
        clock=lambda: NOW,
    )

    service.analyze(project_id="temper", target=NativeTarget.CODEX)
    summary = service.summary(project_id="temper", target=NativeTarget.CODEX)

    assert summary.status == "conflicting"
    assert summary.blocking_conflict_count == 1
    assert summary.conflicts[0].source_display_path == "AGENTS.md"
    assert summary.conflicts[0].temper_behavior == (
        "Run the affected test before reporting completion."
    )
    assert summary.conflicts[0].native_behavior == ("Never run the affected test in this project.")
    assert summary.conflicts[0].raw_payloads_exposed is False
