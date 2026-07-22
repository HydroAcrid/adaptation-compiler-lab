"""Unit tests for deterministic, capability-aware file renderers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.domain.base import ActorRef
from adaptation_compiler_lab.domain.enums import (
    ActorKind,
    ArtifactKind,
    AuthorityClass,
    ClaimType,
    Partition,
    PermittedUse,
    PrivacyReviewState,
    SensitivityClass,
)
from adaptation_compiler_lab.domain.references import (
    ArtifactRef,
    EvaluationCaseRef,
    EvidenceRef,
    ReleaseRef,
)
from adaptation_compiler_lab.domain.values import (
    BehavioralContract,
    ClaimAuthority,
    ClaimAuthoritySet,
    EvidenceLinks,
    PrivacyContext,
    Scope,
)
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets import render_target_pack, write_rendered_pack
from adaptation_compiler_lab.targets.errors import TargetRenderError
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    FileTargetCapabilityProfile,
    ReleaseRenderProjection,
    TargetKind,
)
from adaptation_compiler_lab.targets.profiles import default_target_profile

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def digest(character: str) -> str:
    return f"sha256:{character * 64}"


def evidence_ref(record_id: str = "evidence-1") -> EvidenceRef:
    return EvidenceRef(
        record_id=record_id,
        record_version="1.0.0",
        content_digest=digest("a"),
    )


def evaluation_ref(record_id: str = "evaluation-1") -> EvaluationCaseRef:
    return EvaluationCaseRef(
        record_id=record_id,
        record_version="1.0.0",
        content_digest=digest("b"),
    )


def privacy(
    sensitivity: SensitivityClass = SensitivityClass.PRIVATE,
) -> PrivacyContext:
    reviewer = ActorRef(actor_id="reviewer-1", kind=ActorKind.HUMAN_REVIEWER)
    return PrivacyContext(
        sensitivity=sensitivity,
        consent_basis="synthetic-consent",
        permitted_uses=(PermittedUse.TARGET_DELIVERY,),
        review_state=PrivacyReviewState.APPROVED,
        reviewed_by=reviewer,
        reviewed_at=NOW,
    )


def artifact(
    artifact_id: str,
    kind: ArtifactKind = ArtifactKind.PREFERENCE,
    *,
    authority: AuthorityClass = AuthorityClass.USER_NORMATIVE,
    behavior: str = "Prefer a restrained visual treatment.",
    target_families: tuple[str, ...] = (),
    sensitivity: SensitivityClass = SensitivityClass.PRIVATE,
) -> ArtifactRenderProjection:
    return ArtifactRenderProjection(
        artifact_ref=ArtifactRef(
            record_id=artifact_id,
            record_version="1.0.0",
            content_digest=digest("c"),
        ),
        artifact_type=kind,
        behavioral_contract=BehavioralContract(
            intent=f"Apply {artifact_id}",
            required_behaviors=(behavior,),
            verification_requirements=("Verify the scoped behavior.",),
        ),
        scope=Scope(subject_ids=("subject-1",), target_families=target_families),
        evidence_links=EvidenceLinks(supporting=(evidence_ref(),)),
        evaluation_cases=(evaluation_ref(),),
        claim_authorities=ClaimAuthoritySet(
            entries=(
                ClaimAuthority(
                    claim_type=ClaimType.USER_PREFERENCE,
                    authority_class=authority,
                    evidence_refs=(evidence_ref(),),
                ),
            )
        ),
        privacy=privacy(sensitivity),
        precedence=10,
        source_partitions=(Partition.CONSTRUCTION,),
    )


def release(*artifacts: ArtifactRenderProjection) -> ReleaseRenderProjection:
    return ReleaseRenderProjection(
        release_ref=ReleaseRef(
            record_id="release-1",
            record_version="1.0.0",
            content_digest=digest("d"),
        ),
        release_version="1.0.0",
        policy_version="1.0.0",
        artifacts=tuple(artifacts),
    )


@pytest.mark.parametrize(
    ("target", "expected_path"),
    [
        (TargetKind.GENERIC_JSON, "adaptation-pack.json"),
        (TargetKind.GENERIC_MARKDOWN, "ADAPTATION.md"),
        (TargetKind.CODEX, "AGENTS.md"),
        (TargetKind.CLAUDE_CODE, ".claude/rules/preference-1.md"),
    ],
)
def test_all_renderers_are_deterministic(target: TargetKind, expected_path: str) -> None:
    source = release(artifact("preference-1"))
    profile = default_target_profile(target)

    first = render_target_pack(source, profile)
    second = render_target_pack(source, profile)

    assert first == second
    assert first.pack_digest == second.pack_digest
    assert expected_path in {item.path for item in first.files}
    assert ".adaptation-pack/manifest.json" in {item.path for item in first.files}
    assert first.entries[0].supporting_evidence_ids == ("evidence-1",)


@pytest.mark.parametrize(
    ("target", "skill_path"),
    [
        (TargetKind.CODEX, ".agents/skills/verify-work/SKILL.md"),
        (TargetKind.CLAUDE_CODE, ".claude/skills/verify-work/SKILL.md"),
    ],
)
def test_agent_renderers_emit_instruction_only_skills(target: TargetKind, skill_path: str) -> None:
    pack = render_target_pack(
        release(artifact("verify-work", ArtifactKind.PROCEDURE)),
        default_target_profile(target),
    )
    file_by_path = {item.path: item.content for item in pack.files}

    assert skill_path in file_by_path
    assert "description:" in file_by_path[skill_path]
    assert "allowed-tools:" not in file_by_path[skill_path]
    assert "/scripts/" not in file_by_path[skill_path]


def test_tool_recommendation_remains_advisory() -> None:
    pack = render_target_pack(
        release(artifact("tool-advice", ArtifactKind.TOOL_RECOMMENDATION)),
        default_target_profile(TargetKind.CODEX),
    )
    agents = next(item.content for item in pack.files if item.path == "AGENTS.md")

    assert "advisory only" in agents
    assert "Do not install, enable, authorize, or execute" in agents


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile.model_copy(
            update={
                "capabilities": profile.capabilities.model_copy(
                    update={"supported_artifact_kinds": (ArtifactKind.MEMORY,)}
                )
            }
        ),
        lambda profile: profile.model_copy(
            update={
                "capabilities": profile.capabilities.model_copy(
                    update={"supported_scope_dimensions": ("project_ids",)}
                )
            }
        ),
        lambda profile: profile.model_copy(
            update={
                "capabilities": profile.capabilities.model_copy(
                    update={"supports_evidence_trace": False}
                )
            }
        ),
        lambda profile: profile.model_copy(update={"max_primary_instruction_bytes": 1}),
    ],
)
def test_material_capability_loss_fails_closed(
    mutate: Callable[[FileTargetCapabilityProfile], FileTargetCapabilityProfile],
) -> None:
    profile = mutate(default_target_profile(TargetKind.GENERIC_MARKDOWN))

    with pytest.raises(TargetRenderError):
        render_target_pack(release(artifact("preference-1")), profile)


def test_out_of_target_artifact_is_recorded_as_non_material_omission() -> None:
    source = release(artifact("claude-only", target_families=(TargetKind.CLAUDE_CODE.value,)))

    pack = render_target_pack(source, default_target_profile(TargetKind.CODEX))

    assert not pack.entries
    assert pack.omissions[0].artifact_id == "claude-only"


def test_all_canonical_scope_and_review_bounds_are_preserved() -> None:
    scoped = artifact("scoped-rule").model_copy(
        update={
            "scope": Scope(
                subject_ids=("subject-1",),
                workspace_ids=("workspace-1",),
                project_ids=("project-1",),
                repository_ids=("repository-1",),
                task_classes=("website",),
                target_families=(TargetKind.GENERIC_MARKDOWN.value,),
                environment_ids=("local",),
                activation_conditions=("Only for frontend work.",),
                exclusions=("Do not apply to backend work.",),
                valid_from=NOW,
                valid_until=datetime(2026, 2, 1, tzinfo=UTC),
            ),
            "review_at": datetime(2026, 1, 15, tzinfo=UTC),
            "expires_at": datetime(2026, 2, 1, tzinfo=UTC),
        }
    )

    pack = render_target_pack(release(scoped), default_target_profile(TargetKind.GENERIC_MARKDOWN))
    content = next(item.content for item in pack.files if item.path == "ADAPTATION.md")

    for expected in (
        "workspace-1",
        "repository-1",
        "Only for frontend work.",
        "Do not apply to backend work.",
        "Valid from:",
        "Scope valid until:",
        "Review by:",
        "Expires at:",
    ):
        assert expected in content


def test_unrepresentable_canonical_scope_dimension_is_material_loss() -> None:
    scoped = artifact("workspace-rule").model_copy(
        update={"scope": Scope(subject_ids=("subject-1",), workspace_ids=("workspace-1",))}
    )
    profile = default_target_profile(TargetKind.GENERIC_MARKDOWN)
    dimensions = tuple(
        item for item in profile.capabilities.supported_scope_dimensions if item != "workspace_ids"
    )
    profile = profile.model_copy(
        update={
            "capabilities": profile.capabilities.model_copy(
                update={"supported_scope_dimensions": dimensions}
            )
        }
    )

    with pytest.raises(TargetRenderError, match="unsupported_scope"):
        render_target_pack(release(scoped), profile)


def test_multiple_claim_authorities_are_preserved_without_collapsing() -> None:
    second_evidence = evidence_ref("evidence-2")
    source = artifact("multi-authority").model_copy(
        update={
            "evidence_links": EvidenceLinks(
                supporting=(evidence_ref(), second_evidence),
            ),
            "claim_authorities": ClaimAuthoritySet(
                entries=(
                    ClaimAuthority(
                        claim_type=ClaimType.BEHAVIORAL_EFFECTIVENESS,
                        authority_class=AuthorityClass.AUTHORIZED_EVALUATOR,
                        evidence_refs=(second_evidence,),
                    ),
                    ClaimAuthority(
                        claim_type=ClaimType.USER_PREFERENCE,
                        authority_class=AuthorityClass.USER_NORMATIVE,
                        evidence_refs=(evidence_ref(),),
                    ),
                )
            ),
        }
    )

    pack = render_target_pack(release(source), default_target_profile(TargetKind.GENERIC_JSON))
    content = next(item.content for item in pack.files if item.path == "adaptation-pack.json")

    assert "behavioral_effectiveness" in content
    assert "authorized_evaluator" in content
    assert "user_preference" in content
    assert "user_normative" in content
    assert pack.entries[0].authority_digest == canonical_digest(source.claim_authorities)


def test_deployable_target_compatibility_mismatch_fails_closed() -> None:
    source = artifact("claude-only").model_copy(
        update={"target_compatibility": (TargetKind.CLAUDE_CODE.value,)}
    )

    with pytest.raises(TargetRenderError, match="artifact_target_compatibility_mismatch"):
        render_target_pack(release(source), default_target_profile(TargetKind.CODEX))


def test_target_without_authority_labels_fails_closed() -> None:
    profile = default_target_profile(TargetKind.GENERIC_JSON)
    profile = profile.model_copy(
        update={
            "capabilities": profile.capabilities.model_copy(
                update={"supports_authority_labels": False}
            )
        }
    )

    with pytest.raises(TargetRenderError, match="authority_labels_unsupported"):
        render_target_pack(release(artifact("preference-1")), profile)


def test_writer_materializes_only_into_new_or_empty_directory(tmp_path: Path) -> None:
    output = tmp_path / "pack"
    pack = render_target_pack(
        release(artifact("preference-1")),
        default_target_profile(TargetKind.GENERIC_JSON),
    )

    written = write_rendered_pack(pack, output)

    assert written
    with pytest.raises(FileExistsError):
        write_rendered_pack(pack, output)


def test_projection_rejects_unknown_raw_evidence_field() -> None:
    payload = artifact("preference-1").model_dump(mode="python")
    payload["raw_evidence"] = "must not cross the rendering boundary"

    with pytest.raises(ValidationError):
        ArtifactRenderProjection.model_validate(payload)


def test_writer_rechecks_rendered_file_digests(tmp_path: Path) -> None:
    pack = render_target_pack(
        release(artifact("preference-1")),
        default_target_profile(TargetKind.GENERIC_JSON),
    )
    changed = pack.files[0].model_copy(update={"content": pack.files[0].content + "tampered\n"})
    tampered = pack.model_copy(update={"files": (changed, *pack.files[1:])})

    with pytest.raises(ValueError, match="file digest"):
        write_rendered_pack(tampered, tmp_path / "tampered-pack")
