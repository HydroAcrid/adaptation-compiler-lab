from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.domain import ArtifactRef, ReleaseRef
from adaptation_compiler_lab.instruction_environment import (
    CodexInstructionSourceAdapter,
    InstructionRelationKind,
    InstructionRelationV1,
    apply_instruction_environment,
    bind_instruction_delta_manifest,
    build_instruction_delta_plan,
)
from adaptation_compiler_lab.instruction_environment.models import (
    InstructionEnvironmentSnapshotV1,
    InstructionResolution,
    NativeTarget,
)
from adaptation_compiler_lab.instruction_environment.semantic import (
    ClauseRelationAnalysisV1,
    InstructionRelationPairV1,
    bind_independent_relation_analyses,
)
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    ClauseProvenanceBinding,
    RuntimeClause,
    RuntimeClauseRole,
    RuntimeProjectionContext,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.models import ScopeDimension

NOW = datetime(2026, 8, 28, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _projection(text: str) -> CanonicalRuntimeProjection:
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
                text=text,
                roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
                source_artifact_refs=(artifact,),
            ),
        ),
    )


def _environment(root: Path, text: str) -> InstructionEnvironmentSnapshotV1:
    root.mkdir()
    (root / "AGENTS.md").write_text(text + "\n", encoding="utf-8")
    sources = CodexInstructionSourceAdapter().discover(project_id="temper", project_root=root)
    return InstructionEnvironmentSnapshotV1(
        project_id="temper",
        target=NativeTarget.CODEX,
        surface="codex-cli",
        surface_contract_version=CodexInstructionSourceAdapter.surface_contract_version,
        source_manifests=tuple(item.manifest for item in sources),
        clauses=tuple(clause for item in sources for clause in item.clauses),
        complete=True,
        generated_at=NOW,
    )


def test_exact_native_coverage_removes_duplicate_temper_clause(tmp_path: Path) -> None:
    projection = _projection("Run focused tests before claiming success.")
    environment = _environment(tmp_path / "project", "Run focused tests before claiming success.")

    plan = build_instruction_delta_plan(projection, environment)
    delta = apply_instruction_environment(projection, plan)

    assert not delta.clauses
    assert plan.omitted_temper_clause_digests == (projection.clauses[0].content_digest,)
    assert plan.output_utf8_bytes == 0
    assert plan.relations[0].relation is InstructionRelationKind.EXACT_DUPLICATE


def test_detected_skill_is_not_assumed_active_projection_coverage(tmp_path: Path) -> None:
    projection = _projection("Run focused tests before claiming success.")
    root = tmp_path / "project"
    skill = root / ".agents" / "skills" / "testing" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Run focused tests before claiming success.\n", encoding="utf-8")
    sources = CodexInstructionSourceAdapter().discover(project_id="temper", project_root=root)
    environment = InstructionEnvironmentSnapshotV1(
        project_id="temper",
        target=NativeTarget.CODEX,
        surface="codex-cli",
        surface_contract_version=CodexInstructionSourceAdapter.surface_contract_version,
        source_manifests=tuple(item.manifest for item in sources),
        clauses=tuple(clause for item in sources for clause in item.clauses),
        complete=True,
        generated_at=NOW,
    )

    plan = build_instruction_delta_plan(projection, environment)

    assert plan.included_temper_clause_digests == (projection.clauses[0].content_digest,)
    assert not plan.omitted_temper_clause_digests
    assert not plan.fully_optimized


def test_semantic_contradiction_blocks_only_affected_temper_clause(tmp_path: Path) -> None:
    projection = _projection("Always run tests before reporting completion.")
    environment = _environment(tmp_path / "project", "Never run tests in this repository.")
    native = environment.clauses[0]
    relation = InstructionRelationV1(
        temper_clause_digest=projection.clauses[0].content_digest,
        native_clause_id=native.clause_id,
        native_clause_digest=native.text_digest,
        relation=InstructionRelationKind.CONTRADICTION,
        confidence=0.98,
        deterministic=False,
        resolution=InstructionResolution.BLOCK_TEMPER,
        rationale="The clauses require mutually exclusive verification behavior.",
        interpreter_digests=(DIGEST_A, DIGEST_B),
    )

    plan = build_instruction_delta_plan(projection, environment, semantic_relations=(relation,))

    assert plan.blocked_temper_clause_digests == (projection.clauses[0].content_digest,)
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].severity == "blocking"
    assert not apply_instruction_environment(projection, plan).clauses


def test_semantic_omission_requires_two_exact_agreeing_passes(tmp_path: Path) -> None:
    projection = _projection("Verify the affected test before reporting success.")
    environment = _environment(
        tmp_path / "project", "Run the relevant test before claiming the work is done."
    )
    pair = InstructionRelationPairV1.bind(projection.clauses[0], environment.clauses[0])

    def analysis(relation: InstructionRelationKind, digest: str) -> ClauseRelationAnalysisV1:
        return ClauseRelationAnalysisV1(
            pair_id=pair.pair_id,
            temper_clause_digest=pair.temper_clause_digest,
            native_clause_id=pair.native_clause_id,
            native_clause_digest=pair.native_clause_digest,
            relation=relation,
            confidence=0.96,
            interpreter_digest=digest,
        )

    agreed = bind_independent_relation_analyses(
        (pair,),
        {pair.pair_id: analysis(InstructionRelationKind.SEMANTIC_EQUIVALENT, DIGEST_A)},
        {pair.pair_id: analysis(InstructionRelationKind.SEMANTIC_EQUIVALENT, DIGEST_B)},
    )
    disagreed = bind_independent_relation_analyses(
        (pair,),
        {pair.pair_id: analysis(InstructionRelationKind.SEMANTIC_EQUIVALENT, DIGEST_A)},
        {pair.pair_id: analysis(InstructionRelationKind.COMPLEMENTARY, DIGEST_B)},
    )

    assert agreed[0].resolution is InstructionResolution.OMIT_TEMPER
    assert disagreed[0].relation is InstructionRelationKind.UNKNOWN
    assert disagreed[0].resolution is InstructionResolution.NEEDS_REVIEW


def test_runtime_manifest_binds_exact_environment_and_omissions(tmp_path: Path) -> None:
    projection = _projection("Keep changes small.")
    environment = _environment(tmp_path / "project", "Keep changes small.")
    plan = build_instruction_delta_plan(projection, environment)
    empty_delta = apply_instruction_environment(projection, plan)
    manifest = RuntimeProjectionManifest(
        external_release_digest=projection.external_release_digest,
        runtime_projection_digest=empty_delta.content_digest,
        target_renderer_id="codex-runtime",
        target_renderer_version="1.0.0",
        rendered_content_digest=canonical_digest({"text": ""}),
        rendered_utf8_bytes=0,
        clause_bindings=(),
    )

    bound = bind_instruction_delta_manifest(manifest, plan)

    assert bound.instruction_environment_digest == environment.content_digest
    assert bound.native_source_chain_digest == environment.source_chain_digest
    assert bound.native_omitted_clause_digests == plan.omitted_temper_clause_digests
    assert bound.native_delta_fully_optimized


def test_manifest_rejects_overlapping_native_dispositions() -> None:
    binding = ClauseProvenanceBinding(
        clause_digest=DIGEST_A,
        rendered_fragment_digest=DIGEST_B,
        source_binding_digests=(DIGEST_A,),
    )
    try:
        RuntimeProjectionManifest(
            external_release_digest=DIGEST_A,
            runtime_projection_digest=DIGEST_B,
            target_renderer_id="codex-runtime",
            target_renderer_version="1.0.0",
            rendered_content_digest=DIGEST_A,
            rendered_utf8_bytes=1,
            clause_bindings=(binding,),
            instruction_environment_digest=DIGEST_A,
            native_target_id="codex",
            native_target_surface="codex-cli",
            native_target_surface_version="test-contract-v1",
            native_source_chain_digest=DIGEST_B,
            native_included_clause_digests=(DIGEST_A,),
            native_omitted_clause_digests=(DIGEST_A,),
            native_delta_fully_optimized=True,
        )
    except ValueError as error:
        assert "dispositions overlap" in str(error)
    else:
        raise AssertionError("overlapping native dispositions were accepted")
