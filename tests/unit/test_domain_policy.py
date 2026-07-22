"""Synthetic contract, trust, routing, serialization, and lifecycle tests."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from adaptation_compiler_lab.domain import (
    ActivationState,
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
    EvaluationCaseRef,
    EvaluationCaseState,
    EvaluationResult,
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
    Release,
    ReleaseCandidateState,
    ReleaseRef,
    RenderedEntry,
    Scope,
    ScoringRule,
    ScoringType,
    SensitivityClass,
    SourceClass,
    TargetCapabilityProfile,
    TargetPack,
    TargetPackState,
    TaskRecord,
    TaskRecordRef,
    Transformation,
    scope_is_within,
)
from adaptation_compiler_lab.evaluation import (
    CandidateGenerationContext,
    DeterministicEvaluationCandidateGenerator,
    generate_evaluation_candidates,
    validate_evaluation_first,
)
from adaptation_compiler_lab.provenance import (
    ViolationCode,
    index_records,
    validate_artifact_promotion,
    validate_evidence_authority,
    validate_lesson_candidate,
    validate_release_membership,
    validate_target_pack,
)
from adaptation_compiler_lab.release import (
    validate_activation_transition,
    validate_artifact_transition,
    validate_release_candidate_transition,
    validate_target_pack_transition,
)
from adaptation_compiler_lab.routing import artifact_kind_for_route, route_lesson
from adaptation_compiler_lab.serialization import (
    canonical_digest,
    canonical_json,
    deserialize_record,
    record_ref,
    round_trip,
    schema_bundle,
)

NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)


def digest(character: str) -> str:
    return f"sha256:{character * 64}"


USER = ActorRef(actor_id="user-alex", kind=ActorKind.USER, display_name="Alex Example")
AGENT = ActorRef(
    actor_id="agent-codex", kind=ActorKind.AGENT, display_name="Codex", version="1.0.0"
)
REVIEWER = ActorRef(actor_id="reviewer-1", kind=ActorKind.HUMAN_REVIEWER, display_name="Reviewer")
SYSTEM = ActorRef(actor_id="compiler-policy", kind=ActorKind.SYSTEM, version="1.0.0")


def privacy(*, approved: bool = True) -> PrivacyContext:
    uses = tuple(sorted(tuple(PermittedUse), key=lambda item: item.value))
    if approved:
        return PrivacyContext(
            sensitivity=SensitivityClass.PRIVATE,
            consent_basis="consent-synthetic",
            permitted_uses=uses,
            review_state=PrivacyReviewState.APPROVED,
            reviewed_by=REVIEWER,
            reviewed_at=NOW,
        )
    return PrivacyContext(
        sensitivity=SensitivityClass.PRIVATE,
        consent_basis="consent-synthetic",
        permitted_uses=uses,
    )


SCOPE = Scope(subject_ids=("user-kevin",), project_ids=("project-lab",))
ENVIRONMENT = EnvironmentSnapshot(
    environment_id="env-synthetic",
    harness_version="1.0.0",
    repository_digest=digest("a"),
    model_id="synthetic-model",
    agent_version="synthetic-agent",
    tool_ids=("pytest",),
)


def approval(decision: ApprovalDecision = ApprovalDecision.APPROVED) -> Approval:
    return Approval(
        decision=decision,
        approver=REVIEWER,
        decided_at=NOW,
        policy_version="1.0.0",
        rationale="Synthetic human review decision.",
    )


@dataclass(frozen=True)
class SyntheticGraph:
    evidence: Evidence
    task: TaskRecord
    outcome: Outcome
    evaluation_case: EvaluationCase
    candidate: LessonCandidate
    artifact: Artifact
    release: Release
    target_pack: TargetPack


def synthetic_graph() -> SyntheticGraph:
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
        authority_reason="Direct attributable synthetic user correction.",
        allowed_claim_types=(ClaimType.USER_CORRECTION,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator="evidence://synthetic/evidence-1",
            content_digest=digest("b"),
            media_type="text/plain",
            byte_length=24,
        ),
        task_ref=task_identity,
        scope=SCOPE,
        privacy=privacy(),
        partition=Partition.CONSTRUCTION,
    )
    evidence_reference = record_ref(evidence)
    assert evidence_reference.record_type is RecordKind.EVIDENCE
    task = TaskRecord(
        record_id="task-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=SYSTEM,
        policy_version="1.0.0",
        subject_id="user-kevin",
        scope=SCOPE,
        source_agent=AGENT,
        environment=ENVIRONMENT,
        started_at=NOW - timedelta(minutes=10),
        completed_at=NOW,
        prompt_evidence_refs=(evidence_reference,),
        privacy=privacy(),
        partition=Partition.CONSTRUCTION,
    )
    task_reference = record_ref(task)
    assert isinstance(task_reference, TaskRecordRef)
    assertion = OutcomeAssertion(
        assertion_id="assertion-1",
        claim_type=ClaimType.USER_CORRECTION,
        status=AssertionStatus.CORRECTED,
        statement="The agent skipped required visual verification.",
        observed_behavior="The deliverable was returned without visual inspection.",
        expected_behavior="Inspect the rendered result before claiming completion.",
        evaluation_setup="Prepare a synthetic rendered-interface task.",
        evaluation_stimulus="Complete the task and report verification performed.",
        failure_criteria=("Claims completion without recorded visual inspection.",),
        scoring_rule=ScoringRule(
            scoring_type=ScoringType.OBJECTIVE,
            description="Pass when a visual inspection event is recorded.",
            pass_threshold=1.0,
        ),
        scope=SCOPE,
    )
    outcome = Outcome(
        record_id="outcome-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=USER,
        policy_version="1.0.0",
        task_ref=task_reference,
        kind=OutcomeKind.CORRECTION,
        assessed_at=NOW,
        evaluator=USER,
        assertions=(assertion,),
        supporting_evidence_refs=(evidence_reference,),
        scope=SCOPE,
        environment=ENVIRONMENT,
        privacy=privacy(),
        partition=Partition.CONSTRUCTION,
    )
    batch = generate_evaluation_candidates(
        outcome,
        CandidateGenerationContext(
            generator=SYSTEM,
            generator_version="1.0.0",
            policy_version="1.0.0",
            generated_at=NOW,
        ),
    )
    proposed_case = batch.candidates[0]
    case_data = proposed_case.model_dump(mode="python")
    case_data.update({"state": EvaluationCaseState.REVIEWED, "review": approval()})
    evaluation_case = EvaluationCase.model_validate(case_data)
    case_reference = record_ref(evaluation_case)
    outcome_reference = record_ref(outcome)
    assert isinstance(case_reference, EvaluationCaseRef)
    assert isinstance(outcome_reference, OutcomeRef)
    candidate_subject = ExactRecordRef(
        record_type=RecordKind.LESSON_CANDIDATE,
        record_id="lesson-1",
        record_version="1.0.0",
    )
    candidate_attestation = EvaluationAttestation(
        case_ref=case_reference,
        subject_ref=candidate_subject,
        result=EvaluationResult.PASSED,
        evaluator=REVIEWER,
        evaluator_version="1.0.0",
        evaluated_at=NOW,
        result_digest=digest("c"),
        partition=Partition.DEVELOPMENT,
        independent_of_proposer=True,
    )
    contract = BehavioralContract(
        intent="Require visual verification before completion claims.",
        required_behaviors=("Inspect the rendered result before claiming completion.",),
        non_goals=("Do not prescribe a specific browser automation tool.",),
        verification_requirements=("Record the performed visual inspection.",),
    )
    links = EvidenceLinks(supporting=(evidence_reference,))
    claim_authorities = ClaimAuthoritySet(
        entries=(
            ClaimAuthority(
                claim_type=ClaimType.USER_CORRECTION,
                authority_class=AuthorityClass.USER_NORMATIVE,
                evidence_refs=(evidence_reference,),
            ),
        )
    )
    candidate = LessonCandidate(
        record_id="lesson-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=SYSTEM,
        policy_version="1.0.0",
        state=LessonCandidateState.APPROVED,
        lesson_kind=LessonKind.EXPLICIT_PREFERENCE,
        behavioral_contract=contract,
        claim_authorities=claim_authorities,
        scope=SCOPE,
        evidence_links=links,
        source_task_refs=(task_reference,),
        source_outcome_refs=(outcome_reference,),
        evaluation_case_refs=(case_reference,),
        evaluation_attestations=(candidate_attestation,),
        confidence=ConfidenceAssessment(
            score=0.9,
            rationale="Explicit correction with a passing regression case.",
            basis_evidence_refs=(evidence_reference,),
        ),
        proposed_routes=(ArtifactRoute.PREFERENCE,),
        privacy=privacy(),
        authoring_method="deterministic-synthetic",
        authoring_method_version="1.0.0",
        approval=approval(),
    )
    candidate_reference = record_ref(candidate)
    assert isinstance(candidate_reference, LessonCandidateRef)
    artifact_attestation = EvaluationAttestation(
        case_ref=case_reference,
        subject_ref=ExactRecordRef(
            record_type=RecordKind.ARTIFACT,
            record_id="artifact-1",
            record_version="1.0.0",
        ),
        result=EvaluationResult.PASSED,
        evaluator=REVIEWER,
        evaluator_version="1.0.0",
        evaluated_at=NOW,
        result_digest=digest("d"),
        partition=Partition.DEVELOPMENT,
        independent_of_proposer=True,
    )
    artifact = Artifact(
        record_id="artifact-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=SYSTEM,
        policy_version="1.0.0",
        artifact_kind=ArtifactKind.PREFERENCE,
        state=ArtifactState.APPROVED,
        behavioral_contract=contract,
        claim_authorities=claim_authorities,
        scope=SCOPE,
        source_candidate_refs=(candidate_reference,),
        evidence_links=links,
        evaluation_attestations=(artifact_attestation,),
        selected_route=ArtifactRoute.PREFERENCE,
        routing_rationale=("Preference is the narrowest effective representation.",),
        privacy=privacy(),
        target_compatibility=("claude-code",),
        approval=approval(),
    )
    artifact_reference = record_ref(artifact)
    assert isinstance(artifact_reference, ArtifactRef)
    release = Release(
        record_id="release-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=SYSTEM,
        policy_version="1.0.0",
        release_version="1.0.0",
        released_at=NOW,
        artifact_refs=(artifact_reference,),
        is_empty_release=False,
        schema_versions=("1.0.0",),
        policy_versions=("1.0.0",),
        construction_boundary=ConstructionBoundary(
            construction_cutoff=NOW,
            split_manifest_digest=digest("e"),
            custody_policy_version="1.0.0",
        ),
        development_evaluations=(artifact_attestation,),
        approval=approval(),
        target_compatibility=("claude-code",),
    )
    release_reference = record_ref(release)
    assert isinstance(release_reference, ReleaseRef)
    target_pack = TargetPack(
        record_id="pack-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=SYSTEM,
        policy_version="1.0.0",
        state=TargetPackState.VALIDATED,
        release_ref=release_reference,
        target_profile=TargetCapabilityProfile(
            profile_id="claude-code-synthetic",
            profile_version="1.0.0",
            target_family="claude-code",
            supported_artifact_kinds=(ArtifactKind.PREFERENCE,),
            supported_scope_dimensions=("project_ids", "subject_ids"),
            supports_precedence=True,
            supports_evidence_trace=True,
            supports_authority_labels=True,
            supports_expiry=True,
            max_context_tokens=1024,
            maximum_sensitivity=SensitivityClass.PRIVATE,
        ),
        renderer_version="1.0.0",
        entries=(
            RenderedEntry(
                entry_id="entry-1",
                output_path="adaptation.md",
                content_digest=digest("f"),
                byte_length=128,
                artifact_ref=artifact_reference,
                evidence_refs=(evidence_reference,),
                precedence=0,
                scope_digest=digest("1"),
                behavioral_contract_digest=canonical_digest(contract),
                authority_digest=canonical_digest(claim_authorities),
            ),
        ),
        ordering_rationale=("Single scoped preference requires no tie-break.",),
        context_token_cost=64,
        privacy=privacy(),
        material_semantics_preserved=True,
    )
    return SyntheticGraph(
        evidence=evidence,
        task=task,
        outcome=outcome,
        evaluation_case=evaluation_case,
        candidate=candidate,
        artifact=artifact,
        release=release,
        target_pack=target_pack,
    )


def test_all_eight_records_are_strict_frozen_and_round_trip() -> None:
    graph = synthetic_graph()
    records = (
        graph.task,
        graph.outcome,
        graph.evidence,
        graph.evaluation_case,
        graph.candidate,
        graph.artifact,
        graph.release,
        graph.target_pack,
    )
    assert {record.record_type for record in records} == set(RecordKind)
    for record in records:
        assert round_trip(record) == record
        assert canonical_json(record) == canonical_json(round_trip(record))
    with pytest.raises(ValidationError):
        TaskRecord.model_validate({**graph.task.model_dump(mode="python"), "unknown": True})
    with pytest.raises(ValidationError):
        graph.task.record_id = "changed"


def test_unknown_schema_version_is_rejected_before_dispatch() -> None:
    payload = canonical_json(synthetic_graph().task).replace(
        '"schema_version":"1.0"', '"schema_version":"2.0"'
    )
    with pytest.raises(ValueError, match="unsupported schema version"):
        deserialize_record(payload)


def test_scope_monotonicity_rejects_broadening() -> None:
    child = Scope(
        subject_ids=("user-kevin",),
        project_ids=("project-lab",),
        task_classes=("website",),
        exclusions=("secret-bearing",),
    )
    assert scope_is_within(child, SCOPE)
    assert not scope_is_within(SCOPE, child)


@given(
    st.sets(
        st.sampled_from(("project-a", "project-b", "project-c")),
        min_size=1,
    )
)
def test_scope_is_reflexive_and_extra_constraints_only_narrow(projects: set[str]) -> None:
    parent = Scope(
        subject_ids=("user-kevin",),
        project_ids=tuple(sorted(projects)),
    )
    child = Scope(
        subject_ids=("user-kevin",),
        project_ids=tuple(sorted(projects)),
        task_classes=("website",),
        exclusions=("secret-bearing",),
    )
    assert scope_is_within(parent, parent)
    assert scope_is_within(child, parent)


def test_untrusted_content_cannot_claim_user_authority() -> None:
    graph = synthetic_graph()
    data = graph.evidence.model_dump(mode="python")
    data.update(
        {
            "source_class": SourceClass.REPOSITORY_CONTENT,
            "authority_class": AuthorityClass.USER_NORMATIVE,
        }
    )
    laundered = Evidence.model_validate(data)
    decision = validate_evidence_authority(laundered, index_records((laundered,)))
    assert not decision.allowed
    assert {item.code for item in decision.violations} >= {
        ViolationCode.AUTHORITY_MISMATCH,
        ViolationCode.CLAIM_NOT_AUTHORIZED,
    }


def test_derived_evidence_cannot_elevate_parent_authority() -> None:
    graph = synthetic_graph()
    parent = graph.evidence.model_copy(
        update={
            "record_id": "evidence-untrusted-parent",
            "source_class": SourceClass.REPOSITORY_CONTENT,
            "authority_class": AuthorityClass.UNTRUSTED_CONTEXT,
            "allowed_claim_types": (ClaimType.REPOSITORY_FACT,),
        }
    )
    parent_ref = record_ref(parent)
    assert isinstance(parent_ref, EvidenceRef)
    child = graph.evidence.model_copy(
        update={
            "record_id": "evidence-laundered-child",
            "state": EvidenceState.DERIVED,
            "parent_evidence_refs": (parent_ref,),
            "transformation": Transformation(
                method="synthetic-minimization",
                transformer_version="1.0.0",
                policy_version="1.0.0",
                actor=SYSTEM,
                transformed_at=NOW,
                input_evidence_refs=(parent_ref,),
            ),
        }
    )

    decision = validate_evidence_authority(child, index_records((parent, child)))

    assert not decision.allowed
    assert ViolationCode.AUTHORITY_ESCALATION in {item.code for item in decision.violations}


def test_derived_evidence_preserves_parent_partition_and_privacy() -> None:
    graph = synthetic_graph()
    held_out_privacy = privacy().model_copy(
        update={
            "permitted_uses": (PermittedUse.AUDIT, PermittedUse.BENCHMARK),
        }
    )
    parent = graph.evidence.model_copy(
        update={
            "record_id": "evidence-heldout-parent",
            "partition": Partition.HELD_OUT,
            "privacy": held_out_privacy,
        }
    )
    parent_ref = record_ref(parent)
    assert isinstance(parent_ref, EvidenceRef)
    child = graph.evidence.model_copy(
        update={
            "record_id": "evidence-construction-child",
            "state": EvidenceState.DERIVED,
            "parent_evidence_refs": (parent_ref,),
            "transformation": Transformation(
                method="synthetic-minimization",
                transformer_version="1.0.0",
                policy_version="1.0.0",
                actor=SYSTEM,
                transformed_at=NOW,
                input_evidence_refs=(parent_ref,),
            ),
        }
    )

    decision = validate_evidence_authority(child, index_records((parent, child)))

    assert not decision.allowed
    assert {item.code for item in decision.violations} >= {
        ViolationCode.HELD_OUT_CONTAMINATION,
        ViolationCode.PRIVACY_BROADENING,
    }


def test_held_out_evidence_cannot_be_marked_for_promotion() -> None:
    graph = synthetic_graph()
    data = graph.evidence.model_dump(mode="python")
    data["partition"] = Partition.HELD_OUT
    with pytest.raises(ValidationError, match="held-out evidence"):
        Evidence.model_validate(data)


def test_lesson_scope_cannot_broaden_any_cited_source() -> None:
    graph = synthetic_graph()
    broadened = graph.candidate.model_copy(update={"scope": Scope(subject_ids=("user-kevin",))})
    records = (graph.evidence, graph.task, graph.outcome, graph.evaluation_case)

    decision = validate_lesson_candidate(
        broadened,
        records,
        required_use=PermittedUse.PROMOTION,
        require_approved=True,
    )

    assert not decision.allowed
    assert ViolationCode.SCOPE_BROADENING in {item.code for item in decision.violations}


def test_candidate_and_artifact_cannot_understate_source_privacy() -> None:
    graph = synthetic_graph()
    public_privacy = privacy().model_copy(update={"sensitivity": SensitivityClass.PUBLIC})
    candidate = graph.candidate.model_copy(update={"privacy": public_privacy})
    artifact = graph.artifact.model_copy(
        update={
            "privacy": public_privacy,
            "source_candidate_refs": (record_ref(candidate),),
        }
    )
    records = (graph.evidence, graph.task, graph.outcome, graph.evaluation_case, candidate)

    decision = validate_artifact_promotion(artifact, records)

    assert not decision.allowed
    assert ViolationCode.PRIVACY_BROADENING in {item.code for item in decision.violations}


def test_promotion_rechecks_least_invasive_route_for_directly_persisted_artifact() -> None:
    graph = synthetic_graph()
    escalated = graph.artifact.model_copy(
        update={
            "artifact_kind": ArtifactKind.SKILL,
            "selected_route": ArtifactRoute.SKILL,
        }
    )
    records = (
        graph.evidence,
        graph.task,
        graph.outcome,
        graph.evaluation_case,
        graph.candidate,
    )

    decision = validate_artifact_promotion(escalated, records)

    assert not decision.allowed
    assert ViolationCode.ROUTING_MISMATCH in {item.code for item in decision.violations}


def test_candidate_generation_is_deterministic_and_evaluation_first_passes() -> None:
    graph = synthetic_graph()
    context = CandidateGenerationContext(
        generator=SYSTEM,
        generator_version="1.0.0",
        policy_version="1.0.0",
        generated_at=NOW,
    )
    first = generate_evaluation_candidates(graph.outcome, context)
    second = generate_evaluation_candidates(graph.outcome, context)
    assert first == second
    assert DeterministicEvaluationCandidateGenerator().generate(graph.outcome, context) == first
    assert first.candidates[0].state is EvaluationCaseState.CANDIDATE
    records = (graph.task, graph.evidence, graph.outcome, graph.evaluation_case)
    assert validate_evaluation_first(
        graph.candidate, records, require_passing_attestation=True
    ).allowed
    assert not validate_evaluation_first(
        graph.candidate,
        (graph.task, graph.evidence, graph.outcome),
        require_passing_attestation=True,
    ).allowed


def test_artifact_attestation_must_target_the_exact_promoted_version() -> None:
    graph = synthetic_graph()
    attestation = graph.artifact.evaluation_attestations[0].model_copy(
        update={
            "subject_ref": ExactRecordRef(
                record_type=RecordKind.ARTIFACT,
                record_id=graph.artifact.record_id,
                record_version="9.9.9",
            )
        }
    )
    artifact = graph.artifact.model_copy(update={"evaluation_attestations": (attestation,)})
    records = (
        graph.task,
        graph.evidence,
        graph.outcome,
        graph.evaluation_case,
        graph.candidate,
    )

    decision = validate_artifact_promotion(artifact, records)

    assert not decision.allowed
    assert ViolationCode.EVALUATION_FAILED in {item.code for item in decision.violations}


def test_candidate_attestation_must_target_the_exact_approved_version() -> None:
    graph = synthetic_graph()
    attestation = graph.candidate.evaluation_attestations[0].model_copy(
        update={
            "subject_ref": ExactRecordRef(
                record_type=RecordKind.LESSON_CANDIDATE,
                record_id=graph.candidate.record_id,
                record_version="9.9.9",
            )
        }
    )
    candidate = graph.candidate.model_copy(update={"evaluation_attestations": (attestation,)})
    records = (graph.task, graph.evidence, graph.outcome, graph.evaluation_case)

    decision = validate_evaluation_first(candidate, records, require_passing_attestation=True)

    assert not decision.allowed
    assert ViolationCode.EVALUATION_FAILED in {item.code for item in decision.violations}


def test_triggering_outcome_requires_a_triggering_assertion() -> None:
    outcome = synthetic_graph().outcome
    assertion = outcome.assertions[0].model_copy(update={"status": AssertionStatus.PASSED})
    data = outcome.model_dump(mode="python")
    data["assertions"] = (assertion,)
    with pytest.raises(ValidationError, match="requires a triggering assertion"):
        Outcome.model_validate(data)


def test_routing_is_advisory_and_proposal_only_routes_never_map_to_artifacts() -> None:
    graph = synthetic_graph()
    preference = route_lesson(graph.candidate, policy_version="1.0.0")
    assert preference.selected_route is ArtifactRoute.PREFERENCE
    assert preference.durable_artifact_kind is ArtifactKind.PREFERENCE
    missing_capability = graph.candidate.model_copy(
        update={
            "lesson_kind": LessonKind.MISSING_CAPABILITY,
            "proposed_routes": (ArtifactRoute.INACTIVE_TOOL_CANDIDATE,),
        }
    )
    tool = route_lesson(missing_capability, policy_version="1.0.0")
    assert tool.selected_route is ArtifactRoute.INACTIVE_TOOL_CANDIDATE
    assert not tool.eligible_for_artifact
    adapter_pattern = graph.candidate.model_copy(
        update={
            "lesson_kind": LessonKind.ADAPTER_DATASET_PATTERN,
            "proposed_routes": (ArtifactRoute.INACTIVE_ADAPTER_DATASET_CANDIDATE,),
        }
    )
    adapter = route_lesson(adapter_pattern, policy_version="1.0.0")
    assert adapter.selected_route is ArtifactRoute.INACTIVE_ADAPTER_DATASET_CANDIDATE
    assert artifact_kind_for_route(adapter.selected_route) is None
    blocked = graph.candidate.model_copy(update={"state": LessonCandidateState.REVIEWED})
    assert (
        route_lesson(blocked, policy_version="1.0.0").selected_route
        is ArtifactRoute.EVALUATION_ONLY
    )


@given(
    st.sampled_from(
        (
            ArtifactRoute.EVALUATION_ONLY,
            ArtifactRoute.INACTIVE_TOOL_CANDIDATE,
            ArtifactRoute.INACTIVE_ADAPTER_DATASET_CANDIDATE,
        )
    )
)
def test_proposal_only_route_never_has_a_durable_kind(route: ArtifactRoute) -> None:
    assert artifact_kind_for_route(route) is None


def test_artifact_model_refuses_proposal_only_route() -> None:
    artifact = synthetic_graph().artifact
    data = artifact.model_dump(mode="python")
    data["selected_route"] = ArtifactRoute.INACTIVE_ADAPTER_DATASET_CANDIDATE
    with pytest.raises(ValidationError, match="selected route"):
        Artifact.model_validate(data)


def test_secret_classification_cannot_be_promoted() -> None:
    artifact = synthetic_graph().artifact
    secret_privacy = privacy().model_copy(
        update={"sensitivity": SensitivityClass.PROHIBITED_SECRET}
    )
    data = artifact.model_dump(mode="python")
    data["privacy"] = secret_privacy
    with pytest.raises(ValidationError, match="secret-bearing"):
        Artifact.model_validate(data)


def test_cross_record_promotion_release_and_target_pack_validation() -> None:
    graph = synthetic_graph()
    construction_records = (
        graph.evidence,
        graph.task,
        graph.outcome,
        graph.evaluation_case,
        graph.candidate,
    )
    assert validate_artifact_promotion(graph.artifact, construction_records).allowed
    assert validate_release_membership(graph.release, (graph.artifact,)).allowed
    assert validate_target_pack(
        graph.target_pack,
        (graph.release, graph.artifact, graph.evidence),
    ).allowed
    assert "payload" not in canonical_json(graph.target_pack)
    changed_entry = graph.target_pack.entries[0].model_copy(
        update={"authority_digest": digest("9")}
    )
    changed_pack = graph.target_pack.model_copy(update={"entries": (changed_entry,)})
    assert not validate_target_pack(
        changed_pack,
        (graph.release, graph.artifact, graph.evidence),
    ).allowed


def test_schema_bundle_has_one_schema_for_each_top_level_record() -> None:
    assert set(schema_bundle()) == {kind.value for kind in RecordKind}


def test_separate_lifecycle_transition_graphs_fail_closed() -> None:
    assert validate_artifact_transition(ArtifactState.DRAFT, ArtifactState.EVALUATED).allowed
    assert not validate_artifact_transition(ArtifactState.DRAFT, ArtifactState.APPROVED).allowed
    assert validate_release_candidate_transition(
        ReleaseCandidateState.DRAFT, ReleaseCandidateState.PROPOSED
    ).allowed
    assert validate_release_candidate_transition(
        ReleaseCandidateState.PROPOSED, ReleaseCandidateState.EXPIRED
    ).allowed
    assert validate_target_pack_transition(TargetPackState.BUILT, TargetPackState.VALIDATED).allowed
    assert validate_activation_transition(ActivationState.CANARY, ActivationState.ACTIVE).allowed
    assert validate_activation_transition(ActivationState.ACTIVE, ActivationState.ACTIVE).allowed
    assert not validate_activation_transition(
        ActivationState.ROLLED_BACK, ActivationState.INACTIVE
    ).allowed
