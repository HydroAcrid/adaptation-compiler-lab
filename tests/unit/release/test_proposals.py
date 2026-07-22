"""Release-candidate proposal and disposition tests."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ApprovalDecision,
    ConstructionBoundary,
    ReleaseCandidateState,
)
from adaptation_compiler_lab.release.proposals import (
    ReleaseCandidate,
    ReleaseCandidateError,
    propose_release_candidate,
    transition_release_candidate,
)

NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)
CREATOR = ActorRef(actor_id="creator", kind=ActorKind.AGENT, version="1.0.0")
REVIEWER = ActorRef(actor_id="reviewer", kind=ActorKind.HUMAN_REVIEWER)
BOUNDARY = ConstructionBoundary(
    construction_cutoff=NOW,
    split_manifest_digest="sha256:" + "a" * 64,
    custody_policy_version="1.0.0",
)


def candidate() -> ReleaseCandidate:
    return propose_release_candidate(
        candidate_id="candidate-1",
        candidate_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        artifact_refs=(),
        schema_versions=("1.0.0",),
        policy_versions=("1.0.0",),
        construction_boundary=BOUNDARY,
        proposal_disposition_id="proposal-1",
        proposal_rationale="propose an explicit empty release",
    )


def test_candidate_dispositions_are_separate_immutable_history() -> None:
    proposed = candidate()
    assert proposed.state is ReleaseCandidateState.PROPOSED

    evaluated = transition_release_candidate(
        proposed,
        requested=ReleaseCandidateState.EVALUATED,
        disposition_id="evaluation-1",
        decided_at=NOW + timedelta(minutes=1),
        actor=REVIEWER,
        rationale="all gates evaluated",
        gate_report_digest="sha256:" + "b" * 64,
    )

    assert proposed.state is ReleaseCandidateState.PROPOSED
    assert evaluated.state is ReleaseCandidateState.EVALUATED
    assert tuple(item.state for item in evaluated.dispositions) == (
        ReleaseCandidateState.PROPOSED,
        ReleaseCandidateState.EVALUATED,
    )


def test_closed_transition_graph_rejects_direct_approval() -> None:
    with pytest.raises(ReleaseCandidateError):
        transition_release_candidate(
            candidate(),
            requested=ReleaseCandidateState.APPROVED,
            disposition_id="approval-1",
            decided_at=NOW + timedelta(minutes=1),
            actor=REVIEWER,
            rationale="skip evaluation",
            gate_report_digest="sha256:" + "b" * 64,
            approval=Approval(
                decision=ApprovalDecision.APPROVED,
                approver=REVIEWER,
                decided_at=NOW + timedelta(minutes=1),
                policy_version="1.0.0",
                rationale="approve",
            ),
        )


def test_candidate_creator_cannot_approve_own_proposal() -> None:
    proposed = candidate()
    evaluated = transition_release_candidate(
        proposed,
        requested=ReleaseCandidateState.EVALUATED,
        disposition_id="evaluation-1",
        decided_at=NOW + timedelta(minutes=1),
        actor=CREATOR,
        rationale="evaluated",
        gate_report_digest="sha256:" + "b" * 64,
    )
    self_approval = Approval(
        decision=ApprovalDecision.APPROVED,
        approver=ActorRef(actor_id="creator", kind=ActorKind.HUMAN_REVIEWER),
        decided_at=NOW + timedelta(minutes=2),
        policy_version="1.0.0",
        rationale="self approve",
    )

    with pytest.raises(ValidationError, match="cannot approve"):
        transition_release_candidate(
            evaluated,
            requested=ReleaseCandidateState.APPROVED,
            disposition_id="approval-1",
            decided_at=NOW + timedelta(minutes=2),
            actor=self_approval.approver,
            rationale=self_approval.rationale,
            approval=self_approval,
        )
