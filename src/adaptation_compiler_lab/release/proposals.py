"""Immutable release-candidate proposals and disposition history."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import (
    ActorRef,
    Approval,
    ApprovalDecision,
    ArtifactRef,
    ConstructionBoundary,
    EvaluationAttestation,
    FrozenModel,
    Identifier,
    ReleaseCandidateState,
    ReleaseRef,
    SemVer,
    Sha256Digest,
)
from adaptation_compiler_lab.domain.values import refs_are_sorted_unique, strings_are_sorted_unique
from adaptation_compiler_lab.release.transitions import validate_release_candidate_transition


class ReleaseCandidateError(ValueError):
    """A candidate proposal or disposition violated the closed workflow."""


class ReleaseCandidateDisposition(FrozenModel):
    """One attributable candidate-state decision, separate from a frozen Release."""

    disposition_id: Identifier
    previous_state: ReleaseCandidateState
    state: ReleaseCandidateState
    decided_at: datetime
    actor: ActorRef
    rationale: str = Field(min_length=1)
    gate_report_digest: Sha256Digest | None = None
    approval: Approval | None = None

    @model_validator(mode="after")
    def decision_metadata_matches_state(self) -> ReleaseCandidateDisposition:
        transition = validate_release_candidate_transition(self.previous_state, self.state)
        if not transition.allowed:
            raise ValueError(transition.reason)
        gated_states = {
            ReleaseCandidateState.EVALUATED,
            ReleaseCandidateState.APPROVED,
            ReleaseCandidateState.REJECTED,
            ReleaseCandidateState.FROZEN,
        }
        if self.state in gated_states and self.gate_report_digest is None:
            raise ValueError("evaluated or decided disposition requires a gate report digest")
        if self.state in {ReleaseCandidateState.APPROVED, ReleaseCandidateState.FROZEN}:
            if self.approval is None or self.approval.decision is not ApprovalDecision.APPROVED:
                raise ValueError("approved or frozen candidate requires human approval")
        elif self.state is ReleaseCandidateState.REJECTED:
            if self.approval is None or self.approval.decision is not ApprovalDecision.REJECTED:
                raise ValueError("rejected candidate requires a human rejection record")
        elif self.approval is not None:
            raise ValueError("non-decision candidate disposition cannot carry approval")
        return self


class ReleaseCandidate(FrozenModel):
    """Mutable-workflow intent represented as immutable snapshots and disposition events."""

    candidate_id: Identifier
    candidate_version: SemVer
    created_at: datetime
    created_by: ActorRef
    policy_version: SemVer
    artifact_refs: tuple[ArtifactRef, ...]
    schema_versions: Annotated[tuple[SemVer, ...], Field(min_length=1)]
    policy_versions: Annotated[tuple[SemVer, ...], Field(min_length=1)]
    construction_boundary: ConstructionBoundary
    development_evaluations: tuple[EvaluationAttestation, ...] = ()
    predecessor_ref: ReleaseRef | None = None
    supersedes_refs: tuple[ReleaseRef, ...] = ()
    rollback_target_ref: ReleaseRef | None = None
    target_compatibility: tuple[Identifier, ...] = ()
    state: ReleaseCandidateState
    dispositions: Annotated[tuple[ReleaseCandidateDisposition, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def candidate_is_consistent(self) -> ReleaseCandidate:
        if self.construction_boundary.construction_cutoff > self.created_at:
            raise ValueError("construction cutoff cannot postdate the release proposal")
        if not refs_are_sorted_unique(self.artifact_refs):
            raise ValueError("candidate artifact references must be sorted and unique")
        if not refs_are_sorted_unique(self.supersedes_refs):
            raise ValueError("candidate supersession references must be sorted and unique")
        for values in (self.schema_versions, self.policy_versions, self.target_compatibility):
            if not strings_are_sorted_unique(values):
                raise ValueError("candidate version and compatibility values must be sorted unique")
        if self.dispositions[-1].state is not self.state:
            raise ValueError("candidate state must equal its latest disposition")
        if self.dispositions[0].previous_state is not ReleaseCandidateState.DRAFT:
            raise ValueError("candidate disposition history must begin from draft")
        previous: ReleaseCandidateState = ReleaseCandidateState.DRAFT
        previous_time = self.created_at
        disposition_ids: set[str] = set()
        for disposition in self.dispositions:
            if disposition.disposition_id in disposition_ids:
                raise ValueError("candidate disposition identifiers must be unique")
            disposition_ids.add(disposition.disposition_id)
            if disposition.previous_state is not previous:
                raise ValueError("candidate disposition history is not contiguous")
            if disposition.decided_at < previous_time:
                raise ValueError("candidate disposition timestamps must be monotonic")
            previous = disposition.state
            previous_time = disposition.decided_at
            if disposition.approval is not None:
                if disposition.approval.policy_version != self.policy_version:
                    raise ValueError("candidate approval must use the candidate policy version")
                if (
                    disposition.state
                    in {ReleaseCandidateState.APPROVED, ReleaseCandidateState.REJECTED}
                    and disposition.approval.decided_at != disposition.decided_at
                ):
                    raise ValueError(
                        "candidate approval timestamp must equal its disposition timestamp"
                    )
                if disposition.approval.decided_at > disposition.decided_at:
                    raise ValueError("candidate approval cannot postdate its disposition")
        approval = self.dispositions[-1].approval
        if approval is not None and approval.approver.actor_id == self.created_by.actor_id:
            raise ValueError("release-candidate proposer cannot approve its own proposal")
        return self


def propose_release_candidate(
    *,
    candidate_id: str,
    candidate_version: str,
    created_at: datetime,
    created_by: ActorRef,
    policy_version: str,
    artifact_refs: tuple[ArtifactRef, ...],
    schema_versions: tuple[str, ...],
    policy_versions: tuple[str, ...],
    construction_boundary: ConstructionBoundary,
    proposal_disposition_id: str,
    proposal_rationale: str,
    development_evaluations: tuple[EvaluationAttestation, ...] = (),
    predecessor_ref: ReleaseRef | None = None,
    supersedes_refs: tuple[ReleaseRef, ...] = (),
    rollback_target_ref: ReleaseRef | None = None,
    target_compatibility: tuple[str, ...] = (),
) -> ReleaseCandidate:
    """Create a proposed candidate without creating or mutating a Release."""

    disposition = ReleaseCandidateDisposition(
        disposition_id=proposal_disposition_id,
        previous_state=ReleaseCandidateState.DRAFT,
        state=ReleaseCandidateState.PROPOSED,
        decided_at=created_at,
        actor=created_by,
        rationale=proposal_rationale,
    )
    return ReleaseCandidate(
        candidate_id=candidate_id,
        candidate_version=candidate_version,
        created_at=created_at,
        created_by=created_by,
        policy_version=policy_version,
        artifact_refs=artifact_refs,
        schema_versions=schema_versions,
        policy_versions=policy_versions,
        construction_boundary=construction_boundary,
        development_evaluations=development_evaluations,
        predecessor_ref=predecessor_ref,
        supersedes_refs=supersedes_refs,
        rollback_target_ref=rollback_target_ref,
        target_compatibility=target_compatibility,
        state=ReleaseCandidateState.PROPOSED,
        dispositions=(disposition,),
    )


def transition_release_candidate(
    candidate: ReleaseCandidate,
    *,
    requested: ReleaseCandidateState,
    disposition_id: str,
    decided_at: datetime,
    actor: ActorRef,
    rationale: str,
    gate_report_digest: str | None = None,
    approval: Approval | None = None,
) -> ReleaseCandidate:
    """Return a validated candidate snapshot with one appended disposition."""

    transition = validate_release_candidate_transition(candidate.state, requested)
    if not transition.allowed:
        raise ReleaseCandidateError(transition.reason)
    if gate_report_digest is None and candidate.dispositions:
        gate_report_digest = candidate.dispositions[-1].gate_report_digest
    disposition = ReleaseCandidateDisposition(
        disposition_id=disposition_id,
        previous_state=candidate.state,
        state=requested,
        decided_at=decided_at,
        actor=actor,
        rationale=rationale,
        gate_report_digest=gate_report_digest,
        approval=approval,
    )
    values = candidate.model_dump(mode="python", round_trip=True)
    values["state"] = requested
    values["dispositions"] = (*candidate.dispositions, disposition)
    return ReleaseCandidate.model_validate(values)
