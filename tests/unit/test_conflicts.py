"""Milestone 2 conflict precedence is deterministic and fail closed."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from adaptation_compiler_lab.conflicts import resolve_artifact_conflict
from adaptation_compiler_lab.domain import (
    Artifact,
    AuthorityClass,
    ClaimAuthority,
    ClaimAuthoritySet,
    ClaimType,
    ConflictResolution,
    Evidence,
    EvidenceLinks,
    EvidenceRef,
    Scope,
)
from adaptation_compiler_lab.serialization import record_ref
from tests.unit.test_domain_policy import NOW, synthetic_graph


def _artifact(
    source: Artifact,
    *,
    record_id: str,
    evidence: Evidence,
    authority: AuthorityClass = AuthorityClass.USER_NORMATIVE,
    claim_type: ClaimType = ClaimType.USER_CORRECTION,
    scope: Scope | None = None,
) -> Artifact:
    reference = cast(EvidenceRef, record_ref(evidence))
    return source.model_copy(
        update={
            "record_id": record_id,
            "scope": source.scope if scope is None else scope,
            "evidence_links": EvidenceLinks(supporting=(reference,)),
            "claim_authorities": ClaimAuthoritySet(
                entries=(
                    ClaimAuthority(
                        claim_type=claim_type,
                        authority_class=authority,
                        evidence_refs=(reference,),
                    ),
                )
            ),
        }
    )


def _evidence(source: Evidence, *, record_id: str, minutes: int) -> Evidence:
    return source.model_copy(
        update={
            "record_id": record_id,
            "observed_at": source.observed_at + timedelta(minutes=minutes),
        }
    )


def test_revoked_material_is_excluded_before_other_precedence() -> None:
    graph = synthetic_graph()
    later = _evidence(graph.evidence, record_id="evidence-later", minutes=1)
    left = _artifact(graph.artifact, record_id="artifact-left", evidence=graph.evidence)
    right = _artifact(graph.artifact, record_id="artifact-right", evidence=later)

    decision = resolve_artifact_conflict(
        left,
        right,
        claim_type=ClaimType.USER_CORRECTION,
        evidence=(graph.evidence, later),
        evaluated_at=NOW + timedelta(hours=1),
        unavailable={("artifact", right.record_id, right.record_version)},
    )

    assert decision.resolution is ConflictResolution.EXCLUDED
    assert decision.winner_ref is not None
    assert decision.winner_ref.record_id == left.record_id


def test_narrower_scope_outranks_broader_scope() -> None:
    graph = synthetic_graph()
    narrow_scope = Scope(
        subject_ids=("user-kevin",),
        project_ids=("project-lab",),
        repository_ids=("repository-one",),
    )
    broad = _artifact(graph.artifact, record_id="artifact-broad", evidence=graph.evidence)
    narrow = _artifact(
        graph.artifact,
        record_id="artifact-narrow",
        evidence=graph.evidence,
        scope=narrow_scope,
    )

    decision = resolve_artifact_conflict(
        broad,
        narrow,
        claim_type=ClaimType.USER_CORRECTION,
        evidence=(graph.evidence,),
        evaluated_at=NOW + timedelta(hours=1),
    )

    assert decision.resolution is ConflictResolution.NARROWED
    assert decision.winner_ref is not None
    assert decision.winner_ref.record_id == narrow.record_id


def test_later_explicit_correction_outranks_at_equal_scope() -> None:
    graph = synthetic_graph()
    later = _evidence(graph.evidence, record_id="evidence-later", minutes=5)
    earlier_artifact = _artifact(
        graph.artifact,
        record_id="artifact-earlier",
        evidence=graph.evidence,
    )
    later_artifact = _artifact(
        graph.artifact,
        record_id="artifact-later",
        evidence=later,
    )

    decision = resolve_artifact_conflict(
        earlier_artifact,
        later_artifact,
        claim_type=ClaimType.USER_CORRECTION,
        evidence=(graph.evidence, later),
        evaluated_at=NOW + timedelta(hours=1),
    )

    assert decision.resolution is ConflictResolution.SUPERSEDES
    assert decision.winner_ref is not None
    assert decision.winner_ref.record_id == later_artifact.record_id


def test_claim_specific_authority_breaks_remaining_tie() -> None:
    graph = synthetic_graph()
    evaluator_evidence = _evidence(graph.evidence, record_id="evidence-evaluator", minutes=0)
    user_artifact = _artifact(
        graph.artifact,
        record_id="artifact-user",
        evidence=graph.evidence,
        claim_type=ClaimType.USER_PREFERENCE,
    )
    evaluator_artifact = _artifact(
        graph.artifact,
        record_id="artifact-evaluator",
        evidence=evaluator_evidence,
        authority=AuthorityClass.AUTHORIZED_EVALUATOR,
        claim_type=ClaimType.USER_PREFERENCE,
    )

    decision = resolve_artifact_conflict(
        evaluator_artifact,
        user_artifact,
        claim_type=ClaimType.USER_PREFERENCE,
        evidence=(graph.evidence, evaluator_evidence),
        evaluated_at=NOW + timedelta(hours=1),
    )

    assert decision.resolution is ConflictResolution.PRECEDENCE
    assert decision.winner_ref is not None
    assert decision.winner_ref.record_id == user_artifact.record_id


def test_equal_authority_conflict_remains_unresolved() -> None:
    graph = synthetic_graph()
    peer = _evidence(graph.evidence, record_id="evidence-peer", minutes=0)
    left = _artifact(graph.artifact, record_id="artifact-left", evidence=graph.evidence)
    right = _artifact(graph.artifact, record_id="artifact-right", evidence=peer)

    decision = resolve_artifact_conflict(
        left,
        right,
        claim_type=ClaimType.USER_CORRECTION,
        evidence=(graph.evidence, peer),
        evaluated_at=NOW + timedelta(hours=1),
    )

    assert decision.resolution is ConflictResolution.UNRESOLVED
    assert decision.winner_ref is None
