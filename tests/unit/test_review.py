"""Focused immutable human-review workflow tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from adaptation_compiler_lab.application.record_store import DomainRecordStore
from adaptation_compiler_lab.application.review import (
    HumanReviewWorkflow,
    ReviewPolicyError,
    ReviewProvenanceError,
    ReviewTransitionError,
    ReviewVersionError,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ApprovalDecision,
    Artifact,
    ArtifactKind,
    ArtifactRoute,
    ArtifactState,
    AssertionStatus,
    AuthorityClass,
    BehavioralContract,
    ClaimAuthority,
    ClaimAuthoritySet,
    ClaimType,
    ConfidenceAssessment,
    EnvironmentSnapshot,
    EvaluationAttestation,
    EvaluationCase,
    EvaluationCaseKind,
    EvaluationCaseRef,
    EvaluationCaseState,
    EvaluationResult,
    EvaluationSetup,
    Evidence,
    EvidenceLinks,
    EvidenceRef,
    EvidenceState,
    ExactRecordRef,
    LessonCandidate,
    LessonCandidateRef,
    LessonCandidateState,
    LessonKind,
    Outcome,
    OutcomeAssertion,
    OutcomeKind,
    OutcomeRef,
    Partition,
    PayloadReference,
    PermittedUse,
    PrivacyContext,
    PrivacyReviewState,
    RecordKind,
    RedactionState,
    Scope,
    ScoringRule,
    ScoringType,
    SensitivityClass,
    SourceClass,
    TaskRecord,
    TaskRecordRef,
)
from adaptation_compiler_lab.persistence.records import RecordKey
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.provenance import ViolationCode
from adaptation_compiler_lab.serialization import record_ref

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
USER = ActorRef(actor_id="user-kevin", kind=ActorKind.USER)
PROPOSER = ActorRef(actor_id="compiler-agent", kind=ActorKind.AGENT, version="1.0.0")
REVIEWER = ActorRef(actor_id="reviewer-alice", kind=ActorKind.HUMAN_REVIEWER)
SOURCE_AGENT = ActorRef(actor_id="codex", kind=ActorKind.AGENT, version="1.0.0")
SCOPE = Scope(subject_ids=("subject-kevin",), target_families=("generic",))
ENVIRONMENT = EnvironmentSnapshot(
    environment_id="review-test-env",
    harness_version="1.0.0",
)
SCORING = ScoringRule(
    scoring_type=ScoringType.OBJECTIVE,
    description="Pass when verification is recorded",
    pass_threshold=1.0,
)
CONTRACT = BehavioralContract(
    intent="Require verification before completion claims",
    required_behaviors=("Record the performed verification",),
    verification_requirements=("Pass the verification regression case",),
)


def _privacy() -> PrivacyContext:
    return PrivacyContext(
        sensitivity=SensitivityClass.INTERNAL,
        consent_basis="synthetic-review-fixture",
        permitted_uses=(
            PermittedUse.CONSTRUCTION,
            PermittedUse.DEVELOPMENT_EVALUATION,
            PermittedUse.PROMOTION,
            PermittedUse.TARGET_DELIVERY,
        ),
        review_state=PrivacyReviewState.APPROVED,
        reviewed_by=REVIEWER,
        reviewed_at=NOW,
    )


def _approval(
    decision: ApprovalDecision,
    *,
    at: datetime,
    approver: ActorRef = REVIEWER,
    policy_version: str = "1.0.0",
) -> Approval:
    return Approval(
        decision=decision,
        approver=approver,
        decided_at=at,
        policy_version=policy_version,
        rationale=f"Synthetic {decision.value} review decision",
    )


def _key(record: EvaluationCase | LessonCandidate | Artifact) -> RecordKey:
    return RecordKey(
        kind=record.record_type.value,
        record_id=record.record_id,
        version=record.record_version,
    )


@dataclass(frozen=True, slots=True)
class Foundation:
    store: DomainRecordStore
    workflow: HumanReviewWorkflow
    evidence: Evidence
    task: TaskRecord
    outcome: Outcome
    evaluation_candidate: EvaluationCase


def _foundation(tmp_path: Path) -> Foundation:
    factory = SqliteUnitOfWorkFactory(tmp_path / "ledger.sqlite3")
    factory.initialize()
    store = DomainRecordStore(factory, subject_id="subject-kevin")
    task_identity = TaskRecordRef(record_id="task-1", record_version="1.0.0")
    evidence = Evidence(
        record_id="evidence-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=USER,
        policy_version="1.0.0",
        observed_at=NOW,
        producer=USER,
        source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
        authority_class=AuthorityClass.USER_NORMATIVE,
        authority_reason="Direct attributable synthetic correction",
        allowed_claim_types=(ClaimType.USER_CORRECTION,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator="raw-evidence/sha256/11/synthetic",
            content_digest="sha256:" + "1" * 64,
            media_type="text/plain",
            byte_length=20,
        ),
        task_ref=task_identity,
        scope=SCOPE,
        privacy=_privacy(),
        partition=Partition.CONSTRUCTION,
    )
    evidence_ref = cast(EvidenceRef, record_ref(evidence))
    task = TaskRecord(
        record_id="task-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=PROPOSER,
        policy_version="1.0.0",
        subject_id="subject-kevin",
        scope=SCOPE,
        source_agent=SOURCE_AGENT,
        environment=ENVIRONMENT,
        started_at=NOW - timedelta(minutes=5),
        completed_at=NOW,
        prompt_evidence_refs=(evidence_ref,),
        privacy=_privacy(),
        partition=Partition.CONSTRUCTION,
    )
    task_ref = cast(TaskRecordRef, record_ref(task))
    outcome = Outcome(
        record_id="outcome-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=USER,
        policy_version="1.0.0",
        task_ref=task_ref,
        kind=OutcomeKind.CORRECTION,
        assessed_at=NOW,
        evaluator=USER,
        assertions=(
            OutcomeAssertion(
                assertion_id="missing-verification",
                claim_type=ClaimType.USER_CORRECTION,
                status=AssertionStatus.CORRECTED,
                statement="The agent skipped verification",
                observed_behavior="Completion was claimed without verification",
                expected_behavior="Record verification before completion",
                evaluation_setup="Run the synthetic completion task",
                evaluation_stimulus="Inspect the completion evidence",
                failure_criteria=("No verification event is recorded",),
                scoring_rule=SCORING,
                scope=SCOPE,
            ),
        ),
        supporting_evidence_refs=(evidence_ref,),
        scope=SCOPE,
        environment=ENVIRONMENT,
        privacy=_privacy(),
        partition=Partition.CONSTRUCTION,
    )
    outcome_ref = cast(OutcomeRef, record_ref(outcome))
    evaluation_candidate = EvaluationCase(
        record_id="case-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=PROPOSER,
        policy_version="1.0.0",
        state=EvaluationCaseState.CANDIDATE,
        kind=EvaluationCaseKind.REGRESSION,
        setup=EvaluationSetup(
            instructions="Run the synthetic completion task",
            stimulus="Inspect the completion evidence",
            allowed_context_refs=(task_ref,),
        ),
        expected_behaviors=("A verification event is recorded",),
        failure_criteria=("No verification event is recorded",),
        scoring_rule=SCORING,
        environment=ENVIRONMENT,
        scope=SCOPE,
        source_task_ref=task_ref,
        source_outcome_ref=outcome_ref,
        source_evidence_refs=(evidence_ref,),
        partition=Partition.DEVELOPMENT,
        privacy=_privacy(),
    )
    store.add_many((evidence, task, outcome, evaluation_candidate))
    return Foundation(
        store=store,
        workflow=HumanReviewWorkflow(store),
        evidence=evidence,
        task=task,
        outcome=outcome,
        evaluation_candidate=evaluation_candidate,
    )


def _approved_case(foundation: Foundation) -> EvaluationCase:
    return foundation.workflow.approve_evaluation_candidate(
        _key(foundation.evaluation_candidate),
        new_version="1.1.0",
        approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=1)),
    )


def _lesson(foundation: Foundation, evaluation_case: EvaluationCase) -> LessonCandidate:
    evidence_ref = cast(EvidenceRef, record_ref(foundation.evidence))
    task_ref = cast(TaskRecordRef, record_ref(foundation.task))
    outcome_ref = cast(OutcomeRef, record_ref(foundation.outcome))
    case_ref = cast(EvaluationCaseRef, record_ref(evaluation_case))
    return LessonCandidate(
        record_id="lesson-1",
        record_version="1.0.0",
        created_at=NOW + timedelta(minutes=2),
        created_by=PROPOSER,
        policy_version="1.0.0",
        state=LessonCandidateState.PROPOSED,
        lesson_kind=LessonKind.EXPLICIT_PREFERENCE,
        behavioral_contract=CONTRACT,
        claim_authorities=ClaimAuthoritySet(
            entries=(
                ClaimAuthority(
                    claim_type=ClaimType.USER_CORRECTION,
                    authority_class=AuthorityClass.USER_NORMATIVE,
                    evidence_refs=(evidence_ref,),
                ),
            )
        ),
        scope=SCOPE,
        evidence_links=EvidenceLinks(supporting=(evidence_ref,)),
        source_task_refs=(task_ref,),
        source_outcome_refs=(outcome_ref,),
        evaluation_case_refs=(case_ref,),
        confidence=ConfidenceAssessment(
            score=0.9,
            rationale="Explicit correction and independent regression pass",
            basis_evidence_refs=(evidence_ref,),
        ),
        proposed_routes=(ArtifactRoute.PREFERENCE,),
        privacy=_privacy(),
        authoring_method="synthetic-compiler",
        authoring_method_version="1.0.0",
    )


def _lesson_attestation(
    evaluation_case: EvaluationCase,
    *,
    version: str,
    at: datetime,
) -> EvaluationAttestation:
    return EvaluationAttestation(
        case_ref=cast(EvaluationCaseRef, record_ref(evaluation_case)),
        subject_ref=ExactRecordRef(
            record_type=RecordKind.LESSON_CANDIDATE,
            record_id="lesson-1",
            record_version=version,
        ),
        result=EvaluationResult.PASSED,
        evaluator=REVIEWER,
        evaluator_version="1.0.0",
        evaluated_at=at,
        result_digest="sha256:" + "2" * 64,
        partition=Partition.DEVELOPMENT,
        independent_of_proposer=True,
    )


def _approved_lesson(foundation: Foundation, evaluation_case: EvaluationCase) -> LessonCandidate:
    proposal = _lesson(foundation, evaluation_case)
    foundation.workflow.propose_lesson(proposal)
    return foundation.workflow.approve_lesson(
        _key(proposal),
        new_version="1.1.0",
        approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=3)),
        evaluation_attestations=(
            _lesson_attestation(
                evaluation_case,
                version="1.1.0",
                at=NOW + timedelta(minutes=2),
            ),
        ),
    )


def _artifact(lesson: LessonCandidate, *, contract: BehavioralContract = CONTRACT) -> Artifact:
    evidence_ref = lesson.evidence_links.supporting[0]
    lesson_ref = cast(LessonCandidateRef, record_ref(lesson))
    return Artifact(
        record_id="artifact-1",
        record_version="1.0.0",
        created_at=NOW + timedelta(minutes=4),
        created_by=PROPOSER,
        policy_version="1.0.0",
        artifact_kind=ArtifactKind.PREFERENCE,
        state=ArtifactState.DRAFT,
        behavioral_contract=contract,
        claim_authorities=lesson.claim_authorities,
        scope=SCOPE,
        source_candidate_refs=(lesson_ref,),
        evidence_links=EvidenceLinks(supporting=(evidence_ref,)),
        selected_route=ArtifactRoute.PREFERENCE,
        routing_rationale=("Preference is the least invasive effective representation",),
        privacy=_privacy(),
    )


def _artifact_attestation(
    evaluation_case: EvaluationCase,
    *,
    version: str,
    at: datetime,
    result: EvaluationResult = EvaluationResult.PASSED,
) -> EvaluationAttestation:
    return EvaluationAttestation(
        case_ref=cast(EvaluationCaseRef, record_ref(evaluation_case)),
        subject_ref=ExactRecordRef(
            record_type=RecordKind.ARTIFACT,
            record_id="artifact-1",
            record_version=version,
        ),
        result=result,
        evaluator=REVIEWER,
        evaluator_version="1.0.0",
        evaluated_at=at,
        result_digest="sha256:" + "3" * 64,
        partition=Partition.DEVELOPMENT,
        independent_of_proposer=True,
    )


@dataclass(frozen=True, slots=True)
class EvaluatedPipeline:
    foundation: Foundation
    evaluation_case: EvaluationCase
    lesson: LessonCandidate
    draft: Artifact
    evaluated: Artifact


def _evaluated_pipeline(
    tmp_path: Path,
    *,
    contract: BehavioralContract = CONTRACT,
) -> EvaluatedPipeline:
    foundation = _foundation(tmp_path)
    evaluation_case = _approved_case(foundation)
    lesson = _approved_lesson(foundation, evaluation_case)
    draft = _artifact(lesson, contract=contract)
    foundation.workflow.propose_artifact(draft)
    evaluated = foundation.workflow.evaluate_artifact_proposal(
        _key(draft),
        new_version="1.1.0",
        evaluation_attestations=(
            _artifact_attestation(
                evaluation_case,
                version="1.1.0",
                at=NOW + timedelta(minutes=5),
            ),
        ),
    )
    return EvaluatedPipeline(foundation, evaluation_case, lesson, draft, evaluated)


def test_evaluation_candidate_approval_is_attributable_and_immutable(tmp_path: Path) -> None:
    foundation = _foundation(tmp_path)

    approved = _approved_case(foundation)

    assert approved.state is EvaluationCaseState.APPROVED
    assert approved.record_version == "1.1.0"
    assert approved.review is not None
    assert approved.review.approver == REVIEWER
    original = foundation.store.require(_key(foundation.evaluation_candidate)).record
    assert isinstance(original, EvaluationCase)
    assert original.state is EvaluationCaseState.CANDIDATE
    with pytest.raises(ReviewTransitionError, match="closed"):
        foundation.workflow.approve_evaluation_candidate(
            _key(approved),
            new_version="1.2.0",
            approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=2)),
        )


def test_evaluation_rejection_and_review_identity_checks(tmp_path: Path) -> None:
    foundation = _foundation(tmp_path)
    rejected = foundation.workflow.reject_evaluation_candidate(
        _key(foundation.evaluation_candidate),
        new_version="1.1.0",
        approval=_approval(ApprovalDecision.REJECTED, at=NOW + timedelta(minutes=1)),
    )

    assert rejected.state is EvaluationCaseState.REJECTED
    assert rejected.review is not None
    assert rejected.review.decision is ApprovalDecision.REJECTED

    other = foundation.evaluation_candidate.model_copy(
        update={
            "record_id": "case-self-review",
            "created_by": REVIEWER,
        }
    )
    foundation.store.add(other)
    with pytest.raises(ReviewProvenanceError, match="proposer"):
        foundation.workflow.approve_evaluation_candidate(
            _key(other),
            new_version="1.1.0",
            approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=1)),
        )

    policy_case = foundation.evaluation_candidate.model_copy(update={"record_id": "case-policy"})
    foundation.store.add(policy_case)
    with pytest.raises(ReviewProvenanceError, match="policy version"):
        foundation.workflow.approve_evaluation_candidate(
            _key(policy_case),
            new_version="1.1.0",
            approval=_approval(
                ApprovalDecision.APPROVED,
                at=NOW + timedelta(minutes=1),
                policy_version="2.0.0",
            ),
        )


def test_lesson_proposal_and_decision_require_evaluation_first(tmp_path: Path) -> None:
    foundation = _foundation(tmp_path)
    evaluation_case = _approved_case(foundation)
    proposal = _lesson(foundation, evaluation_case)

    assert foundation.workflow.propose_lesson(proposal) == proposal
    with pytest.raises(ReviewProvenanceError, match="new lesson version"):
        foundation.workflow.approve_lesson(
            _key(proposal),
            new_version="1.1.0",
            approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=3)),
            evaluation_attestations=(
                _lesson_attestation(
                    evaluation_case,
                    version="1.0.0",
                    at=NOW + timedelta(minutes=2),
                ),
            ),
        )
    approved = foundation.workflow.approve_lesson(
        _key(proposal),
        new_version="1.1.0",
        approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=3)),
        evaluation_attestations=(
            _lesson_attestation(
                evaluation_case,
                version="1.1.0",
                at=NOW + timedelta(minutes=2),
            ),
        ),
    )

    assert approved.state is LessonCandidateState.APPROVED
    assert approved.approval is not None
    assert foundation.store.require(_key(proposal)).record == proposal
    with pytest.raises(ReviewVersionError, match="newer"):
        foundation.workflow.reject_lesson(
            _key(proposal),
            new_version="1.0.0",
            approval=_approval(ApprovalDecision.REJECTED, at=NOW + timedelta(minutes=3)),
        )


def test_artifact_proposal_cannot_bypass_least_invasive_routing(tmp_path: Path) -> None:
    foundation = _foundation(tmp_path)
    evaluation_case = _approved_case(foundation)
    lesson = _approved_lesson(foundation, evaluation_case)
    artifact = _artifact(lesson)
    mismatched = Artifact.model_validate(
        {
            **artifact.model_dump(mode="python"),
            "artifact_kind": ArtifactKind.EXAMPLE,
            "selected_route": ArtifactRoute.EXAMPLE,
        }
    )

    with pytest.raises(ReviewPolicyError, match="least-invasive routing"):
        foundation.workflow.propose_artifact(mismatched)

    assert foundation.store.list(record_kind=RecordKind.ARTIFACT.value) == ()


def test_artifact_full_review_requires_exact_approval_version_attestation(
    tmp_path: Path,
) -> None:
    pipeline = _evaluated_pipeline(tmp_path)
    approval_attestation = _artifact_attestation(
        pipeline.evaluation_case,
        version="1.2.0",
        at=NOW + timedelta(minutes=6),
    )

    approved = pipeline.foundation.workflow.approve_artifact_proposal(
        _key(pipeline.evaluated),
        new_version="1.2.0",
        approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=7)),
        evaluation_attestations=(approval_attestation,),
    )

    assert approved.state is ArtifactState.APPROVED
    assert approved.evaluation_attestations == (approval_attestation,)
    assert pipeline.foundation.store.require(_key(pipeline.draft)).record == pipeline.draft
    assert pipeline.foundation.store.require(_key(pipeline.evaluated)).record == pipeline.evaluated
    assert pipeline.foundation.store.list(record_kind=RecordKind.RELEASE.value) == ()


def test_artifact_rejection_is_human_attributable_without_promotion(
    tmp_path: Path,
) -> None:
    pipeline = _evaluated_pipeline(tmp_path)

    rejected = pipeline.foundation.workflow.reject_artifact_proposal(
        _key(pipeline.evaluated),
        new_version="1.2.0",
        approval=_approval(ApprovalDecision.REJECTED, at=NOW + timedelta(minutes=6)),
    )

    assert rejected.state is ArtifactState.REJECTED
    assert rejected.approval is not None
    assert rejected.approval.decision is ApprovalDecision.REJECTED
    with pytest.raises(ReviewTransitionError, match="closed"):
        pipeline.foundation.workflow.approve_artifact_proposal(
            _key(pipeline.draft),
            new_version="1.3.0",
            approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=7)),
            evaluation_attestations=(
                _artifact_attestation(
                    pipeline.evaluation_case,
                    version="1.3.0",
                    at=NOW + timedelta(minutes=6),
                ),
            ),
        )


def test_artifact_approval_rejects_prior_version_attestation_and_secret_text(
    tmp_path: Path,
) -> None:
    token = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    pipeline = _evaluated_pipeline(
        tmp_path,
        contract=BehavioralContract(
            intent=f"Never retain {token}",
            required_behaviors=("Keep credentials out of artifacts",),
            verification_requirements=("Pass the credential scan",),
        ),
    )
    prior_version = _artifact_attestation(
        pipeline.evaluation_case,
        version="1.1.0",
        at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(ReviewProvenanceError, match="new artifact version"):
        pipeline.foundation.workflow.approve_artifact_proposal(
            _key(pipeline.evaluated),
            new_version="1.2.0",
            approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=7)),
            evaluation_attestations=(prior_version,),
        )

    exact = _artifact_attestation(
        pipeline.evaluation_case,
        version="1.2.0",
        at=NOW + timedelta(minutes=6),
    )
    with pytest.raises(ReviewPolicyError) as raised:
        pipeline.foundation.workflow.approve_artifact_proposal(
            _key(pipeline.evaluated),
            new_version="1.2.0",
            approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=7)),
            evaluation_attestations=(exact,),
        )
    assert "provider_token" in str(raised.value)
    assert token not in str(raised.value)
    assert pipeline.foundation.store.list(record_kind=RecordKind.ARTIFACT.value)[
        -1
    ].key.version == ("1.1.0")


def test_artifact_approval_enforces_matching_evaluation_first_coverage(
    tmp_path: Path,
) -> None:
    pipeline = _evaluated_pipeline(tmp_path)
    unrelated_candidate = pipeline.foundation.evaluation_candidate.model_copy(
        update={"record_id": "case-unrelated"}
    )
    pipeline.foundation.store.add(unrelated_candidate)
    unrelated = pipeline.foundation.workflow.approve_evaluation_candidate(
        _key(unrelated_candidate),
        new_version="1.1.0",
        approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=6)),
    )
    unrelated_attestation = _artifact_attestation(
        unrelated,
        version="1.2.0",
        at=NOW + timedelta(minutes=7),
    )

    with pytest.raises(ReviewPolicyError) as raised:
        pipeline.foundation.workflow.approve_artifact_proposal(
            _key(pipeline.evaluated),
            new_version="1.2.0",
            approval=_approval(ApprovalDecision.APPROVED, at=NOW + timedelta(minutes=8)),
            evaluation_attestations=(unrelated_attestation,),
        )

    assert ViolationCode.EVALUATION_REQUIRED in {
        violation.code for violation in raised.value.violations
    }
    assert not any(
        item.key.version == "1.2.0"
        for item in pipeline.foundation.store.list(record_kind=RecordKind.ARTIFACT.value)
    )
