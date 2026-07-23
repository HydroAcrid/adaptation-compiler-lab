"""Release gate tests over a fully validated synthetic promotion graph."""

from datetime import UTC, datetime, timedelta
from typing import cast

from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    Approval,
    ApprovalDecision,
    Artifact,
    ArtifactKind,
    ArtifactRef,
    ArtifactRoute,
    ArtifactState,
    AssertionStatus,
    AuthorityClass,
    BehavioralContract,
    ClaimAuthority,
    ClaimAuthoritySet,
    ClaimType,
    ConfidenceAssessment,
    ConstructionBoundary,
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
    VersionedRecord,
)
from adaptation_compiler_lab.release.gates import ReleaseGateCode, evaluate_release_gates
from adaptation_compiler_lab.release.proposals import ReleaseCandidate, propose_release_candidate
from adaptation_compiler_lab.serialization import record_ref

NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)
USER = ActorRef(actor_id="user-kevin", kind=ActorKind.USER)
AGENT = ActorRef(actor_id="source-agent", kind=ActorKind.AGENT, version="1.0.0")
CREATOR = ActorRef(actor_id="creator", kind=ActorKind.AGENT, version="1.0.0")
REVIEWER = ActorRef(actor_id="reviewer", kind=ActorKind.HUMAN_REVIEWER)
SCOPE = Scope(subject_ids=("subject-kevin",), target_families=("generic",))
ENVIRONMENT = EnvironmentSnapshot(
    environment_id="synthetic-env",
    harness_version="1.0.0",
)
CONTRACT = BehavioralContract(
    intent="Preserve the explicit user preference",
    required_behaviors=("Use the accepted compact layout",),
    verification_requirements=("Pass the compact-layout evaluation",),
)


def _privacy(*, target_delivery: bool = True) -> PrivacyContext:
    uses = [PermittedUse.CONSTRUCTION, PermittedUse.PROMOTION]
    if target_delivery:
        uses.append(PermittedUse.TARGET_DELIVERY)
    return PrivacyContext(
        sensitivity=SensitivityClass.INTERNAL,
        consent_basis="synthetic-consent",
        permitted_uses=tuple(uses),
        review_state=PrivacyReviewState.APPROVED,
        reviewed_by=REVIEWER,
        reviewed_at=NOW,
    )


def _approval(*, rationale: str) -> Approval:
    return Approval(
        decision=ApprovalDecision.APPROVED,
        approver=REVIEWER,
        decided_at=NOW,
        policy_version="1.0.0",
        rationale=rationale,
    )


def _attestation(
    *, case_ref: EvaluationCaseRef, subject_type: RecordKind, subject_id: str
) -> EvaluationAttestation:
    return EvaluationAttestation(
        case_ref=case_ref,
        subject_ref=ExactRecordRef(
            record_type=subject_type,
            record_id=subject_id,
            record_version="1.0.0",
        ),
        result=EvaluationResult.PASSED,
        evaluator=REVIEWER,
        evaluator_version="1.0.0",
        evaluated_at=NOW,
        result_digest="sha256:" + "e" * 64,
        partition=Partition.DEVELOPMENT,
        independent_of_proposer=True,
    )


def _valid_graph(
    *, target_delivery: bool = True, held_out_release_attestation: bool = False
) -> tuple[ReleaseCandidate, tuple[VersionedRecord, ...]]:
    task_ref = TaskRecordRef(record_id="task-1", record_version="1.0.0")
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
        authority_reason="direct attributable user preference",
        allowed_claim_types=(ClaimType.USER_PREFERENCE,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator="raw-evidence/sha256/aa/synthetic",
            content_digest="sha256:" + "1" * 64,
            media_type="text/plain",
            byte_length=24,
        ),
        task_ref=task_ref,
        scope=SCOPE,
        privacy=_privacy(),
        partition=Partition.CONSTRUCTION,
    )
    evidence_ref = cast(EvidenceRef, record_ref(evidence))
    task = TaskRecord(
        record_id="task-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        subject_id="subject-kevin",
        scope=SCOPE,
        source_agent=AGENT,
        environment=ENVIRONMENT,
        started_at=NOW - timedelta(minutes=2),
        completed_at=NOW - timedelta(minutes=1),
        prompt_evidence_refs=(evidence_ref,),
        privacy=_privacy(),
        partition=Partition.CONSTRUCTION,
    )
    task_ref = cast(TaskRecordRef, record_ref(task))
    scoring_rule = ScoringRule(
        scoring_type=ScoringType.OBJECTIVE,
        description="Compact layout is present",
        pass_threshold=1.0,
    )
    outcome = Outcome(
        record_id="outcome-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=REVIEWER,
        policy_version="1.0.0",
        task_ref=task_ref,
        kind=OutcomeKind.ACCEPTED,
        assessed_at=NOW,
        evaluator=USER,
        assertions=(
            OutcomeAssertion(
                assertion_id="accepted-layout",
                claim_type=ClaimType.USER_PREFERENCE,
                status=AssertionStatus.PASSED,
                statement="The compact layout was accepted",
                observed_behavior="The result used the compact layout",
                expected_behavior="Future applicable work uses a compact layout",
                evaluation_setup="Render the synthetic fixture",
                evaluation_stimulus="Inspect layout density",
                failure_criteria=("Layout is not compact",),
                scoring_rule=scoring_rule,
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
    evaluation_case = EvaluationCase(
        record_id="case-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        state=EvaluationCaseState.APPROVED,
        kind=EvaluationCaseKind.PROMOTION,
        setup=EvaluationSetup(
            instructions="Render a synthetic layout",
            stimulus="Apply the user's compact-layout preference",
        ),
        expected_behaviors=("Layout is compact",),
        failure_criteria=("Layout is not compact",),
        scoring_rule=scoring_rule,
        environment=ENVIRONMENT,
        scope=SCOPE,
        source_task_ref=task_ref,
        source_outcome_ref=outcome_ref,
        source_evidence_refs=(evidence_ref,),
        partition=Partition.DEVELOPMENT,
        privacy=_privacy(),
        review=_approval(rationale="approve synthetic promotion case"),
    )
    case_ref = cast(EvaluationCaseRef, record_ref(evaluation_case))
    evidence_links = EvidenceLinks(supporting=(evidence_ref,))
    claim_authorities = ClaimAuthoritySet(
        entries=(
            ClaimAuthority(
                claim_type=ClaimType.USER_PREFERENCE,
                authority_class=AuthorityClass.USER_NORMATIVE,
                evidence_refs=(evidence_ref,),
            ),
        )
    )
    lesson_attestation = _attestation(
        case_ref=case_ref,
        subject_type=RecordKind.LESSON_CANDIDATE,
        subject_id="lesson-1",
    )
    lesson = LessonCandidate(
        record_id="lesson-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        state=LessonCandidateState.APPROVED,
        lesson_kind=LessonKind.SUCCESSFUL_EXAMPLE,
        behavioral_contract=CONTRACT,
        claim_authorities=claim_authorities,
        scope=SCOPE,
        evidence_links=evidence_links,
        source_task_refs=(task_ref,),
        source_outcome_refs=(outcome_ref,),
        evaluation_case_refs=(case_ref,),
        evaluation_attestations=(lesson_attestation,),
        confidence=ConfidenceAssessment(
            score=0.9,
            rationale="direct user evidence and a passing evaluation",
            basis_evidence_refs=(evidence_ref,),
        ),
        proposed_routes=(ArtifactRoute.EXAMPLE,),
        privacy=_privacy(),
        authoring_method="deterministic-fixture",
        authoring_method_version="1.0.0",
        approval=_approval(rationale="approve scoped lesson"),
    )
    lesson_ref = cast(LessonCandidateRef, record_ref(lesson))
    artifact_attestation = _attestation(
        case_ref=case_ref,
        subject_type=RecordKind.ARTIFACT,
        subject_id="artifact-1",
    )
    artifact = Artifact(
        record_id="artifact-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        artifact_kind=ArtifactKind.EXAMPLE,
        state=ArtifactState.APPROVED,
        behavioral_contract=CONTRACT,
        claim_authorities=claim_authorities,
        scope=SCOPE,
        source_candidate_refs=(lesson_ref,),
        evidence_links=evidence_links,
        evaluation_attestations=(artifact_attestation,),
        selected_route=ArtifactRoute.EXAMPLE,
        routing_rationale=("An example is the least invasive faithful representation",),
        privacy=_privacy(target_delivery=target_delivery),
        approval=_approval(rationale="approve evaluated artifact"),
    )
    artifact_ref = cast(ArtifactRef, record_ref(artifact))
    release_attestation = artifact_attestation.model_copy(
        update={
            "partition": (
                Partition.HELD_OUT if held_out_release_attestation else Partition.DEVELOPMENT
            )
        }
    )
    candidate = propose_release_candidate(
        candidate_id="candidate-1",
        candidate_version="1.0.0",
        created_at=NOW,
        created_by=CREATOR,
        policy_version="1.0.0",
        artifact_refs=(artifact_ref,),
        schema_versions=("1.0.0",),
        policy_versions=("1.0.0",),
        construction_boundary=ConstructionBoundary(
            construction_cutoff=NOW,
            split_manifest_digest="sha256:" + "a" * 64,
            custody_policy_version="1.0.0",
        ),
        development_evaluations=(release_attestation,),
        proposal_disposition_id="proposal-1",
        proposal_rationale="evaluate exact artifact membership",
    )
    records: tuple[VersionedRecord, ...] = (
        task,
        evidence,
        outcome,
        evaluation_case,
        lesson,
        artifact,
    )
    return candidate, records


def test_valid_exact_artifact_passes_all_release_gates() -> None:
    candidate, records = _valid_graph()

    report = evaluate_release_gates(candidate, records, evaluated_at=NOW)

    assert report.passed
    assert report.violations == ()


def test_secret_like_artifact_text_cannot_pass_release_gates() -> None:
    candidate, records = _valid_graph()
    source = next(record for record in records if isinstance(record, Artifact))
    contract = BehavioralContract(
        intent="Preserve a compact layout",
        required_behaviors=("Use api_key = sk-proj-abcdefghijklmnopqrstuvwxyz012345",),
        verification_requirements=("Pass the compact-layout evaluation",),
    )
    data = source.model_dump(mode="python")
    data["behavioral_contract"] = contract
    artifact = Artifact.model_validate(data)
    candidate_data = candidate.model_dump(mode="python")
    candidate_data["artifact_refs"] = (record_ref(artifact),)
    updated_candidate = ReleaseCandidate.model_validate(candidate_data)
    updated_records = tuple(artifact if record is source else record for record in records)

    report = evaluate_release_gates(updated_candidate, updated_records, evaluated_at=NOW)

    assert not report.passed
    assert ReleaseGateCode.SECRET in {violation.code for violation in report.violations}


def test_digest_mismatch_fails_exact_membership_gate() -> None:
    candidate, records = _valid_graph()
    bad_ref = candidate.artifact_refs[0].model_copy(update={"content_digest": "sha256:" + "0" * 64})
    candidate = candidate.model_copy(update={"artifact_refs": (bad_ref,)})

    report = evaluate_release_gates(candidate, records, evaluated_at=NOW)

    assert not report.passed
    assert ReleaseGateCode.MISSING_EXACT_ARTIFACT in {item.code for item in report.violations}


def test_release_gate_rechecks_least_invasive_routing() -> None:
    candidate, records = _valid_graph()
    source = next(record for record in records if isinstance(record, Artifact))
    escalated = source.model_copy(
        update={
            "artifact_kind": ArtifactKind.SKILL,
            "selected_route": ArtifactRoute.SKILL,
        }
    )
    updated_candidate = candidate.model_copy(update={"artifact_refs": (record_ref(escalated),)})
    updated_records = tuple(escalated if record is source else record for record in records)

    report = evaluate_release_gates(updated_candidate, updated_records, evaluated_at=NOW)

    assert not report.passed
    assert ReleaseGateCode.ARTIFACT_POLICY in {violation.code for violation in report.violations}


def test_privacy_and_held_out_material_fail_closed() -> None:
    candidate, records = _valid_graph(
        target_delivery=False,
        held_out_release_attestation=True,
    )

    report = evaluate_release_gates(candidate, records, evaluated_at=NOW)

    codes = {item.code for item in report.violations}
    assert ReleaseGateCode.PRIVACY in codes
    assert ReleaseGateCode.HELD_OUT in codes


def test_construction_boundary_rejects_post_cutoff_provenance() -> None:
    candidate, records = _valid_graph()
    boundary = candidate.construction_boundary.model_copy(
        update={"construction_cutoff": NOW - timedelta(seconds=1)}
    )
    candidate = candidate.model_copy(update={"construction_boundary": boundary})

    report = evaluate_release_gates(candidate, records, evaluated_at=NOW)

    assert not report.passed
    assert ReleaseGateCode.CONSTRUCTION_BOUNDARY in {item.code for item in report.violations}


def test_restricted_evidence_cannot_support_a_release() -> None:
    candidate, records = _valid_graph()
    evidence = next(record for record in records if isinstance(record, Evidence))

    report = evaluate_release_gates(
        candidate,
        records,
        evaluated_at=NOW,
        record_states={
            (evidence.record_type.value, evidence.record_id, evidence.record_version): "restricted"
        },
    )

    assert not report.passed
    assert ReleaseGateCode.REVOKED_OR_EXPIRED in {item.code for item in report.violations}
