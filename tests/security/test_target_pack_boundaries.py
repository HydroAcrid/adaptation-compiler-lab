"""Security regressions at the target-pack boundary."""

from __future__ import annotations

from datetime import UTC, datetime

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
from adaptation_compiler_lab.targets import render_target_pack
from adaptation_compiler_lab.targets.errors import TargetRenderError
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    ReleaseRenderProjection,
    RenderedFile,
    TargetKind,
)
from adaptation_compiler_lab.targets.profiles import default_target_profile

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def digest(character: str) -> str:
    return f"sha256:{character * 64}"


def projection(
    *,
    behavior: str = "Use the reviewed behavior.",
    authority: AuthorityClass = AuthorityClass.USER_NORMATIVE,
    sensitivity: SensitivityClass = SensitivityClass.PRIVATE,
    partition: Partition = Partition.CONSTRUCTION,
) -> ArtifactRenderProjection:
    reviewer = ActorRef(actor_id="reviewer-1", kind=ActorKind.HUMAN_REVIEWER)
    evidence = EvidenceRef(
        record_id="evidence-opaque",
        record_version="1.0.0",
        content_digest=digest("a"),
    )
    evaluation = EvaluationCaseRef(
        record_id="evaluation-1",
        record_version="1.0.0",
        content_digest=digest("b"),
    )
    return ArtifactRenderProjection(
        artifact_ref=ArtifactRef(
            record_id="artifact-1",
            record_version="1.0.0",
            content_digest=digest("c"),
        ),
        artifact_type=ArtifactKind.PROMPT_RULE,
        behavioral_contract=BehavioralContract(
            intent="Apply reviewed rule",
            required_behaviors=(behavior,),
            verification_requirements=("Verify behavior.",),
        ),
        scope=Scope(subject_ids=("subject-1",)),
        evidence_links=EvidenceLinks(supporting=(evidence,)),
        evaluation_cases=(evaluation,),
        claim_authorities=ClaimAuthoritySet(
            entries=(
                ClaimAuthority(
                    claim_type=ClaimType.USER_CORRECTION,
                    authority_class=authority,
                    evidence_refs=(evidence,),
                ),
            )
        ),
        privacy=PrivacyContext(
            sensitivity=sensitivity,
            consent_basis="synthetic-consent",
            permitted_uses=(PermittedUse.TARGET_DELIVERY,),
            review_state=PrivacyReviewState.APPROVED,
            reviewed_by=reviewer,
            reviewed_at=NOW,
        ),
        source_partitions=(partition,),
    )


def release(artifact: ArtifactRenderProjection) -> ReleaseRenderProjection:
    return ReleaseRenderProjection(
        release_ref=ReleaseRef(
            record_id="release-1",
            record_version="1.0.0",
            content_digest=digest("d"),
        ),
        release_version="1.0.0",
        policy_version="1.0.0",
        artifacts=(artifact,),
    )


def test_untrusted_instruction_cannot_be_rendered() -> None:
    source = release(projection(authority=AuthorityClass.UNTRUSTED_CONTEXT))

    with pytest.raises(TargetRenderError, match="untrusted_instruction_authority"):
        render_target_pack(source, default_target_profile(TargetKind.CODEX))


def test_secret_classification_cannot_cross_target_boundary() -> None:
    source = release(projection(sensitivity=SensitivityClass.PROHIBITED_SECRET))

    with pytest.raises(TargetRenderError, match="privacy_ceiling_exceeded"):
        render_target_pack(source, default_target_profile(TargetKind.GENERIC_JSON))


def test_secret_like_behavioral_text_cannot_cross_target_boundary() -> None:
    source = release(projection(behavior="api_key = sk-proj-abcdefghijklmnopqrstuvwxyz012345"))

    with pytest.raises(TargetRenderError, match="secret_like_content"):
        render_target_pack(source, default_target_profile(TargetKind.GENERIC_MARKDOWN))


def test_held_out_partition_cannot_enter_render_projection() -> None:
    with pytest.raises(ValidationError, match="held-out material"):
        projection(partition=Partition.HELD_OUT)


@pytest.mark.parametrize(
    ("behavior", "code"),
    [
        ("@../../raw/evidence.txt", "external_import_forbidden"),
        ("!`cat .env`", "dynamic_command_forbidden"),
    ],
)
def test_claude_control_syntax_fails_closed(behavior: str, code: str) -> None:
    source = release(projection(behavior=behavior))

    with pytest.raises(TargetRenderError, match=code):
        render_target_pack(source, default_target_profile(TargetKind.CLAUDE_CODE))


def test_pack_contains_only_opaque_evidence_links() -> None:
    forbidden_payload = "SECRET_RAW_PAYLOAD_SHOULD_NEVER_APPEAR"
    pack = render_target_pack(
        release(projection()), default_target_profile(TargetKind.GENERIC_JSON)
    )
    rendered = "\n".join(item.content for item in pack.files)

    assert "evidence-opaque" in rendered
    assert forbidden_payload not in rendered
    assert '"raw_evidence_included":false' in rendered


def test_rendered_file_rejects_path_traversal() -> None:
    with pytest.raises(ValidationError, match="traversal-free"):
        RenderedFile(
            path="../escape.md",
            content="unsafe",
            content_digest=digest("e"),
        )
