"""Release-candidate evaluation, approval, rejection, expiry, and immutable freeze service."""

from __future__ import annotations

from datetime import datetime

from adaptation_compiler_lab.application.lifecycle import make_lifecycle_event
from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.domain import (
    ActorRef,
    Approval,
    ApprovalDecision,
    FrozenModel,
    Release,
    ReleaseCandidateState,
)
from adaptation_compiler_lab.persistence.ports import UnitOfWorkFactory
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.provenance import validate_release_membership
from adaptation_compiler_lab.release.gates import ReleaseGateReport, evaluate_release_gates
from adaptation_compiler_lab.release.proposals import (
    ReleaseCandidate,
    transition_release_candidate,
)
from adaptation_compiler_lab.serialization import canonical_digest


class ReleaseServiceError(ValueError):
    """A release workflow operation failed a gate or lifecycle precondition."""


class CandidateEvaluation(FrozenModel):
    candidate: ReleaseCandidate
    report: ReleaseGateReport


class FreezeResult(FrozenModel):
    candidate: ReleaseCandidate
    report: ReleaseGateReport
    release: Release


class ReleaseService:
    """Coordinate pure gates with exact local persistence; never edit a Release in place."""

    def __init__(self, factory: UnitOfWorkFactory, *, subject_id: str) -> None:
        self._factory = factory
        self._records = DomainRecordStore(factory, subject_id=subject_id)

    def evaluate(
        self,
        candidate: ReleaseCandidate,
        *,
        evaluated_at: datetime,
        evaluator: ActorRef,
        disposition_id: str,
        rationale: str,
    ) -> CandidateEvaluation:
        if candidate.state is not ReleaseCandidateState.PROPOSED:
            raise ReleaseServiceError("only a proposed release candidate can be evaluated")
        records = tuple(item.record for item in self._records.list())
        report = evaluate_release_gates(candidate, records, evaluated_at=evaluated_at)
        evaluated = transition_release_candidate(
            candidate,
            requested=ReleaseCandidateState.EVALUATED,
            disposition_id=disposition_id,
            decided_at=evaluated_at,
            actor=evaluator,
            rationale=rationale,
            gate_report_digest=str(canonical_digest(report)),
        )
        return CandidateEvaluation(candidate=evaluated, report=report)

    def approve(
        self,
        evaluation: CandidateEvaluation,
        *,
        approval: Approval,
        disposition_id: str,
    ) -> ReleaseCandidate:
        if not evaluation.report.passed:
            raise ReleaseServiceError("a candidate with failed release gates cannot be approved")
        if approval.decision is not ApprovalDecision.APPROVED:
            raise ReleaseServiceError("approval operation requires an approved decision")
        if approval.policy_version != evaluation.candidate.policy_version:
            raise ReleaseServiceError(
                "approval policy version must match the exact release candidate"
            )
        if approval.decided_at < evaluation.report.evaluated_at:
            raise ReleaseServiceError("approval cannot predate release-gate evaluation")
        return transition_release_candidate(
            evaluation.candidate,
            requested=ReleaseCandidateState.APPROVED,
            disposition_id=disposition_id,
            decided_at=approval.decided_at,
            actor=approval.approver,
            rationale=approval.rationale,
            gate_report_digest=str(canonical_digest(evaluation.report)),
            approval=approval,
        )

    def reject(
        self,
        evaluation: CandidateEvaluation,
        *,
        rejection: Approval,
        disposition_id: str,
    ) -> ReleaseCandidate:
        if rejection.decision is not ApprovalDecision.REJECTED:
            raise ReleaseServiceError("reject operation requires a rejected decision")
        if rejection.policy_version != evaluation.candidate.policy_version:
            raise ReleaseServiceError(
                "rejection policy version must match the exact release candidate"
            )
        if rejection.decided_at < evaluation.report.evaluated_at:
            raise ReleaseServiceError("rejection cannot predate release-gate evaluation")
        return transition_release_candidate(
            evaluation.candidate,
            requested=ReleaseCandidateState.REJECTED,
            disposition_id=disposition_id,
            decided_at=rejection.decided_at,
            actor=rejection.approver,
            rationale=rejection.rationale,
            gate_report_digest=str(canonical_digest(evaluation.report)),
            approval=rejection,
        )

    def expire(
        self,
        candidate: ReleaseCandidate,
        *,
        expired_at: datetime,
        actor: ActorRef,
        disposition_id: str,
        rationale: str,
    ) -> ReleaseCandidate:
        return transition_release_candidate(
            candidate,
            requested=ReleaseCandidateState.EXPIRED,
            disposition_id=disposition_id,
            decided_at=expired_at,
            actor=actor,
            rationale=rationale,
        )

    def freeze(
        self,
        candidate: ReleaseCandidate,
        *,
        release_id: str,
        record_version: str,
        release_version: str,
        released_at: datetime,
        created_by: ActorRef,
        disposition_id: str,
        rationale: str,
    ) -> FreezeResult:
        """Recheck gates, persist one immutable Release, and return a frozen candidate snapshot."""

        if candidate.state is not ReleaseCandidateState.APPROVED:
            raise ReleaseServiceError("only an approved release candidate can be frozen")
        approval = candidate.dispositions[-1].approval
        if approval is None or approval.decision is not ApprovalDecision.APPROVED:
            raise ReleaseServiceError("frozen candidate lacks attributable human approval")
        records = tuple(item.record for item in self._records.list())
        report = evaluate_release_gates(candidate, records, evaluated_at=released_at)
        if not report.passed:
            raise ReleaseServiceError("release gates failed during freeze revalidation")
        frozen_candidate = transition_release_candidate(
            candidate,
            requested=ReleaseCandidateState.FROZEN,
            disposition_id=disposition_id,
            decided_at=released_at,
            actor=created_by,
            rationale=rationale,
            gate_report_digest=str(canonical_digest(report)),
            approval=approval,
        )
        release = Release(
            record_id=release_id,
            record_version=record_version,
            created_at=released_at,
            created_by=created_by,
            policy_version=candidate.policy_version,
            release_version=release_version,
            released_at=released_at,
            artifact_refs=candidate.artifact_refs,
            is_empty_release=not candidate.artifact_refs,
            schema_versions=candidate.schema_versions,
            policy_versions=candidate.policy_versions,
            construction_boundary=candidate.construction_boundary,
            development_evaluations=candidate.development_evaluations,
            approval=approval,
            predecessor_ref=candidate.predecessor_ref,
            supersedes_refs=candidate.supersedes_refs,
            rollback_target_ref=candidate.rollback_target_ref,
            target_compatibility=candidate.target_compatibility,
        )
        membership = validate_release_membership(release, records)
        if not membership.allowed:
            raise ReleaseServiceError("release membership changed after candidate gate evaluation")
        key = RecordKey(
            kind=release.record_type.value,
            record_id=release.record_id,
            version=release.record_version,
        )
        event = make_lifecycle_event(
            event_id=f"release-{release.record_id}-{release.record_version}-released",
            entity=key,
            from_state=None,
            to_state="released",
            previous_event_id=None,
            actor=created_by,
            policy_version=release.policy_version,
            reason=rationale,
            occurred_at=released_at,
        )
        self._records.add_with_lifecycle(release, (event,))
        return FreezeResult(candidate=frozen_candidate, report=report, release=release)
