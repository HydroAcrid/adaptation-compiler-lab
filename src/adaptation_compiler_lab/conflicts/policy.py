"""Pure, deterministic implementation of Milestone 2 conflict precedence."""

from __future__ import annotations

from collections.abc import Iterable, Set
from datetime import datetime
from typing import cast

from adaptation_compiler_lab.domain import (
    Artifact,
    ArtifactRef,
    AuthorityClass,
    ClaimType,
    ConflictResolution,
    Evidence,
    FrozenModel,
    SourceClass,
    scope_is_within,
)
from adaptation_compiler_lab.serialization import record_ref, reference_matches

ArtifactKey = tuple[str, str, str]


class ConflictDecision(FrozenModel):
    """Machine-explainable result of applying the closed precedence order."""

    claim_type: ClaimType
    resolution: ConflictResolution
    winner_ref: ArtifactRef | None = None
    loser_ref: ArtifactRef | None = None
    rationale: str


_AUTHORITY_RANK: dict[AuthorityClass, int] = {
    AuthorityClass.SYNTHETIC_ONLY: 0,
    AuthorityClass.UNTRUSTED_CONTEXT: 1,
    AuthorityClass.PROPOSAL_ONLY: 2,
    AuthorityClass.OBSERVATIONAL: 3,
    AuthorityClass.PROJECT_POLICY: 4,
    AuthorityClass.AUTHORIZED_EVALUATOR: 5,
    AuthorityClass.USER_NORMATIVE: 6,
}


def resolve_artifact_conflict(
    left: Artifact,
    right: Artifact,
    *,
    claim_type: ClaimType,
    evidence: Iterable[Evidence],
    evaluated_at: datetime,
    unavailable: Set[ArtifactKey] = frozenset(),
) -> ConflictDecision:
    """Resolve one declared conflict using the roadmap's exact precedence order."""

    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("conflict evaluation time must be timezone-aware")
    if left.record_id == right.record_id and left.record_version == right.record_version:
        raise ValueError("an artifact cannot conflict with itself")

    left_ref = cast(ArtifactRef, record_ref(left))
    right_ref = cast(ArtifactRef, record_ref(right))
    left_unavailable = _unavailable(left, evaluated_at=evaluated_at, unavailable=unavailable)
    right_unavailable = _unavailable(right, evaluated_at=evaluated_at, unavailable=unavailable)
    if left_unavailable != right_unavailable:
        return _decision(
            claim_type,
            ConflictResolution.EXCLUDED,
            right_ref if left_unavailable else left_ref,
            left_ref if left_unavailable else right_ref,
            "Revoked or expired material is excluded before other precedence rules.",
        )
    if left_unavailable and right_unavailable:
        return ConflictDecision(
            claim_type=claim_type,
            resolution=ConflictResolution.UNRESOLVED,
            rationale="Both conflicting artifacts are revoked or expired and therefore excluded.",
        )

    left_within_right = scope_is_within(left.scope, right.scope)
    right_within_left = scope_is_within(right.scope, left.scope)
    if left_within_right != right_within_left:
        return _decision(
            claim_type,
            ConflictResolution.NARROWED,
            left_ref if left_within_right else right_ref,
            right_ref if left_within_right else left_ref,
            "The narrower applicable scope outranks the broader scope.",
        )

    materialized_evidence = tuple(evidence)
    left_correction = _latest_explicit_correction(left, materialized_evidence)
    right_correction = _latest_explicit_correction(right, materialized_evidence)
    if left_correction != right_correction and (
        left_correction is not None or right_correction is not None
    ):
        left_wins = right_correction is None or (
            left_correction is not None and left_correction > right_correction
        )
        return _decision(
            claim_type,
            ConflictResolution.SUPERSEDES,
            left_ref if left_wins else right_ref,
            right_ref if left_wins else left_ref,
            "At equal scope, the later explicit user correction supersedes the earlier claim.",
        )

    left_authority = _claim_authority(left, claim_type)
    right_authority = _claim_authority(right, claim_type)
    if left_authority != right_authority:
        left_wins = left_authority > right_authority
        return _decision(
            claim_type,
            ConflictResolution.PRECEDENCE,
            left_ref if left_wins else right_ref,
            right_ref if left_wins else left_ref,
            "Claim-specific authority outranks lower authority after scope and correction time.",
        )

    return ConflictDecision(
        claim_type=claim_type,
        resolution=ConflictResolution.UNRESOLVED,
        rationale="Equal-scope, equal-time, equal-authority conflict blocks release.",
    )


def _decision(
    claim_type: ClaimType,
    resolution: ConflictResolution,
    winner: ArtifactRef,
    loser: ArtifactRef,
    rationale: str,
) -> ConflictDecision:
    return ConflictDecision(
        claim_type=claim_type,
        resolution=resolution,
        winner_ref=winner,
        loser_ref=loser,
        rationale=rationale,
    )


def _unavailable(
    artifact: Artifact,
    *,
    evaluated_at: datetime,
    unavailable: Set[ArtifactKey],
) -> bool:
    key = (artifact.record_type.value, artifact.record_id, artifact.record_version)
    return key in unavailable or (
        artifact.expires_at is not None and artifact.expires_at <= evaluated_at
    )


def _latest_explicit_correction(
    artifact: Artifact,
    evidence: tuple[Evidence, ...],
) -> datetime | None:
    references = {
        reference
        for entry in artifact.claim_authorities.entries
        if entry.claim_type is ClaimType.USER_CORRECTION
        and entry.authority_class is AuthorityClass.USER_NORMATIVE
        for reference in entry.evidence_refs
    }
    matches = (
        item.observed_at
        for item in evidence
        if item.source_class is SourceClass.EXPLICIT_USER_FEEDBACK
        and item.authority_class is AuthorityClass.USER_NORMATIVE
        and any(reference_matches(reference, item) for reference in references)
    )
    return max(matches, default=None)


def _claim_authority(artifact: Artifact, claim_type: ClaimType) -> int:
    return max(
        (
            _AUTHORITY_RANK[entry.authority_class]
            for entry in artifact.claim_authorities.entries
            if entry.claim_type is claim_type
        ),
        default=-1,
    )
