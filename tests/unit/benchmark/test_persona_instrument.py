from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.models import (
    AdaptationLayer,
    AutomationDisposition,
    DetectedFeedback,
    FeedbackDetectorMode,
    FeedbackSignalKind,
    InteractionObservation,
    SemanticAssertionKind,
    SemanticExampleIntent,
    SemanticFeatureVector,
    SemanticFeedbackInterpretation,
    SemanticFeedbackSignal,
    SemanticInterpreterReceipt,
    SemanticNormStrength,
    SemanticRouteResolution,
    SemanticScopeHint,
    SemanticSignalClarity,
    SemanticSignalDurability,
    SemanticTransitionIntent,
    SemanticWorkflowStructure,
)
from adaptation_compiler_lab.benchmark.persona_calibration import (
    build_calibration_history,
    build_calibration_profile,
    build_calibration_sensor_records,
    run_disposable_calibration,
)
from adaptation_compiler_lab.benchmark.persona_evaluation import PersonaPreference
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaExpectedClaim,
    PersonaGuidanceOutcome,
    PersonaHiddenOracle,
    PersonaMaterialSource,
    PersonaObjectiveScore,
    PersonaPublicCase,
    PersonaSensorRecord,
    PersonaV21ExecutionReceipt,
    PersonaV21JudgeDecision,
    PersonaV21ModelJudgeDecision,
    PersonaV21Protocol,
    audit_public_payload,
    bind_reviewed_profile_material,
    bind_sensor_record,
    bind_v21_judge_decision,
    build_profile_author_packet,
    build_profile_review_packet,
    build_stage_evidence,
    build_v21_evaluation_report,
    build_v21_judge_packet,
    compile_sensor_material,
    persona_v21_judge_output_schema,
    persona_v21_profile_output_schema,
    resolve_v21_guidance,
    score_objective_state,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ArtifactRoute,
    Scope,
    SourceClass,
    TaskRecordRef,
)

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
ROOT = Path(__file__).resolve().parents[3]


def _scope(project: str, *, special: bool = False) -> Scope:
    return Scope(
        subject_ids=("calibration-user",),
        project_ids=(project,),
        activation_conditions=(("incident",) if special else ()),
    )


def _case(stage: int, *, project: str = "lantern-docs") -> PersonaPublicCase:
    checkpoint = (3, 7, 11, 15)[stage - 1]
    return PersonaPublicCase.model_validate(
        {
            "case_id": f"test-stage-{stage}-{project}",
            "persona_id": "calibration-alex",
            "stage": stage,
            "checkpoint_turn": checkpoint,
            "current_scope": _scope(project),
            "context_label": f"project:{project}",
            "scenario": "Prepare a concise handoff.",
        }
    )


def _sensor_records_through(turn: int) -> tuple[PersonaSensorRecord, ...]:
    return tuple(item for item in build_calibration_sensor_records() if item.turn <= turn)


def test_author_and_reviewer_packets_strip_labels_and_future_evidence() -> None:
    history = build_calibration_history()
    author = build_profile_author_packet(history, 1)
    review = build_profile_review_packet(author, build_calibration_profile(1))

    assert author.evidence.checkpoint_turn == 3
    assert tuple(message.turn for message in author.evidence.messages) == (1, 2, 3)
    assert "expected_trait" not in author.model_dump_json()
    assert "hidden-old" not in author.model_dump_json()
    assert review.persona_id == author.persona_id
    audit_public_payload(author)
    audit_public_payload(review)


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"expected_trait_ids": ["answer"]}, "hidden keys"),
        ({"content": "Strong static profile"}, "presentation cue"),
        ({"condition": "mystery"}, "hidden keys"),
    ],
)
def test_public_packet_audit_fails_closed(payload: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        audit_public_payload(payload)


def test_reviewed_profile_cannot_cite_future_evidence() -> None:
    history = build_calibration_history()
    stage_one = build_stage_evidence(history, 1)
    reviewed = build_calibration_profile(1)
    future = reviewed.model_copy(
        update={
            "snapshot": reviewed.snapshot.model_copy(
                update={"claims": (build_calibration_profile(3).snapshot.claims[1],)}
            )
        }
    )
    with pytest.raises(ValueError, match="hidden or future"):
        bind_reviewed_profile_material(case=_case(1), evidence=stage_one, reviewed=future)


def test_compiled_lifecycle_and_objective_state_are_deterministic() -> None:
    history = build_calibration_history()
    evidence = build_stage_evidence(history, 3)
    material = compile_sensor_material(
        case=_case(3),
        evidence=evidence,
        records=_sensor_records_through(11),
    )
    oracle = PersonaHiddenOracle(
        case_id=material.case_id,
        persona_id=material.persona_id,
        sentinel=False,
        active_claims=(
            PersonaExpectedClaim(
                source_turn=10,
                route=ArtifactRoute.PREFERENCE,
                scope=_scope("lantern-docs"),
            ),
        ),
        forbidden_source_turns=(2,),
    )

    score = score_objective_state(material, oracle)
    assert score.exact is True
    assert score.correct_count == 1
    assert score.forbidden_source_turns == ()
    assert tuple(claim.source_turns for claim in material.claims) == ((10,),)

    unrelated = compile_sensor_material(
        case=_case(3, project="other-project"),
        evidence=evidence,
        records=_sensor_records_through(11),
    )
    assert unrelated.claims == ()
    after_revoke = compile_sensor_material(
        case=_case(4),
        evidence=build_stage_evidence(history, 4),
        records=_sensor_records_through(15),
    )
    assert after_revoke.claims == ()

    with pytest.raises(ValueError, match="stage-bounded evidence"):
        compile_sensor_material(
            case=_case(3),
            evidence=evidence,
            records=_sensor_records_through(15),
        )
    with pytest.raises(ValueError, match="unique by evidence turn"):
        compile_sensor_material(
            case=_case(3),
            evidence=evidence,
            records=(_sensor_records_through(11)[0],) * 2,
        )


def test_objective_score_reports_route_scope_and_lifecycle_errors() -> None:
    history = build_calibration_history()
    evidence = build_stage_evidence(history, 3)
    static = bind_reviewed_profile_material(
        case=_case(3),
        evidence=evidence,
        reviewed=build_calibration_profile(),
    )
    oracle = PersonaHiddenOracle(
        case_id=static.case_id,
        persona_id=static.persona_id,
        sentinel=False,
        active_claims=(
            PersonaExpectedClaim(
                source_turn=10,
                route=ArtifactRoute.PROMPT_RULE,
                scope=_scope("lantern-docs", special=True),
            ),
        ),
        forbidden_source_turns=(6,),
    )
    score = score_objective_state(static, oracle)
    assert score.exact is False
    assert score.route_mismatch_source_turns == (10,)
    assert score.scope_mismatch_source_turns == (10,)


def test_guidance_packet_is_counterbalanced_and_host_bound() -> None:
    history = build_calibration_history()
    evidence = build_stage_evidence(history, 3)
    case = _case(3)
    compiled = compile_sensor_material(
        case=case,
        evidence=evidence,
        records=_sensor_records_through(11),
    )
    static = bind_reviewed_profile_material(
        case=case,
        evidence=evidence,
        reviewed=build_calibration_profile(),
    )
    first, mapping = build_v21_judge_packet(
        seed=b"x" * 32,
        case=case,
        evidence=evidence,
        compiled=compiled,
        static=static,
        replicate=1,
    )
    second, _ = build_v21_judge_packet(
        seed=b"x" * 32,
        case=case,
        evidence=evidence,
        compiled=compiled,
        static=static,
        replicate=2,
    )
    assert tuple(item.alternative_id for item in second.alternatives) == tuple(
        reversed(tuple(item.alternative_id for item in first.alternatives))
    )
    assert set(mapping.values()) == {PersonaMaterialSource.COMPILED, PersonaMaterialSource.STATIC}
    decision = bind_v21_judge_decision(
        first,
        PersonaV21ModelJudgeDecision(
            preference=PersonaPreference.FIRST,
            rationale="The first option is more precise for the supplied evidence and scenario.",
            limitations=("This judgment is limited to the fictional evidence packet.",),
        ),
    )
    assert decision.preferred_alternative_id == first.alternatives[0].alternative_id


def test_guidance_resolution_follows_substance_across_reversed_order() -> None:
    history = build_calibration_history()
    evidence = build_stage_evidence(history, 3)
    case = _case(3)
    compiled = compile_sensor_material(
        case=case,
        evidence=evidence,
        records=_sensor_records_through(11),
    )
    static = bind_reviewed_profile_material(
        case=case,
        evidence=evidence,
        reviewed=build_calibration_profile(),
    )
    first_packet, mapping = build_v21_judge_packet(
        seed=b"y" * 32,
        case=case,
        evidence=evidence,
        compiled=compiled,
        static=static,
        replicate=1,
    )
    second_packet, _ = build_v21_judge_packet(
        seed=b"y" * 32,
        case=case,
        evidence=evidence,
        compiled=compiled,
        static=static,
        replicate=2,
    )
    first = bind_v21_judge_decision(
        first_packet,
        PersonaV21ModelJudgeDecision(
            preference=PersonaPreference.FIRST,
            rationale="The first guidance is better aligned with the supplied evidence and scope.",
            limitations=("The alternatives happen to be semantically close.",),
        ),
    )
    second = bind_v21_judge_decision(
        second_packet,
        PersonaV21ModelJudgeDecision(
            preference=PersonaPreference.SECOND,
            rationale="The second guidance is better aligned with the supplied evidence and scope.",
            limitations=("The alternatives happen to be semantically close.",),
        ),
    )
    outcome = resolve_v21_guidance(first=first, second=second, mapping=mapping)
    assert outcome.independent_agreement is True
    assert outcome.resolved_source is PersonaMaterialSource.COMPILED

    with pytest.raises(ValueError, match="private condition mapping"):
        resolve_v21_guidance(
            first=first,
            second=second,
            mapping={
                "alternative-wrong-a": PersonaMaterialSource.COMPILED,
                "alternative-wrong-b": PersonaMaterialSource.STATIC,
            },
        )

    second_disagrees = bind_v21_judge_decision(
        second_packet,
        PersonaV21ModelJudgeDecision(
            preference=PersonaPreference.FIRST,
            rationale="The first guidance appears more appropriate for this specific scenario.",
            limitations=("The two alternatives are close in overall quality.",),
        ),
    )
    adjudicator_packet, _ = build_v21_judge_packet(
        seed=b"y" * 32,
        case=case,
        evidence=evidence,
        compiled=compiled,
        static=static,
        replicate=3,
    )
    adjudicator = bind_v21_judge_decision(
        adjudicator_packet,
        PersonaV21ModelJudgeDecision(
            preference=PersonaPreference.TIE,
            rationale="Neither guidance has a sufficiently clear advantage in this close case.",
            limitations=("This adjudication is limited to the visible evidence.",),
        ),
    )
    unresolved = resolve_v21_guidance(
        first=first,
        second=second_disagrees,
        mapping=mapping,
        adjudicator=adjudicator,
    )
    assert unresolved.adjudicated is True
    assert unresolved.unresolved is True


def test_execution_receipt_fails_closed_on_role_configuration_drift() -> None:
    base = {
        "execution_id": "receipt-role-binding",
        "role": "profile_author",
        "persona_id": "calibration-alex",
        "packet_digest": DIGEST,
        "model": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "trace_digest": DIGEST,
        "encrypted_trace_ref": DIGEST,
        "command_digest": DIGEST,
        "environment_digest": DIGEST,
    }
    PersonaV21ExecutionReceipt.model_validate(base)
    with pytest.raises(ValueError, match="unregistered model configuration"):
        PersonaV21ExecutionReceipt.model_validate(
            {**base, "model": "gpt-5.6-luna", "reasoning_effort": "medium"}
        )
    with pytest.raises(ValueError, match="case binding"):
        PersonaV21ExecutionReceipt.model_validate({**base, "role": "guidance_judge"})


def test_v21_report_applies_frozen_validity_gate_before_comparison() -> None:
    protocol = PersonaV21Protocol()
    case_ids = tuple(f"report-case-{index:02d}" for index in range(24))
    compiled_scores = tuple(
        PersonaObjectiveScore(
            case_id=case_id,
            source=PersonaMaterialSource.COMPILED,
            expected_count=1,
            correct_count=1,
            missing_source_turns=(),
            unexpected_source_turns=(),
            forbidden_source_turns=(),
            route_mismatch_source_turns=(),
            scope_mismatch_source_turns=(),
            lineage_complete=True,
            exact=True,
        )
        for case_id in case_ids
    )
    static_scores = tuple(
        item.model_copy(update={"source": PersonaMaterialSource.STATIC}) for item in compiled_scores
    )
    outcomes = tuple(
        PersonaGuidanceOutcome(
            case_id=case_id,
            independent_agreement=True,
            adjudicated=False,
            resolved_source=PersonaMaterialSource.COMPILED,
            resolved_tie=False,
            unresolved=False,
        )
        for case_id in case_ids
    )
    decisions = tuple(
        PersonaV21JudgeDecision(
            packet_id=f"packet-{index:02d}",
            case_id=case_ids[index // 2],
            ordered_alternative_ids=("alternative-first", "alternative-second"),
            preference=(PersonaPreference.FIRST if index % 2 == 0 else PersonaPreference.SECOND),
            rationale="This deterministic fixture records a counterbalanced independent decision.",
            limitations=("This is a disposable report-construction fixture.",),
        )
        for index in range(48)
    )
    report = build_v21_evaluation_report(
        protocol=protocol,
        compiled_scores=compiled_scores,
        static_scores=static_scores,
        outcomes=outcomes,
        independent_decisions=decisions,
        sentinel_case_ids=case_ids[-6:],
    )
    assert report.instrument_valid is True
    assert report.interpretation == "compiled_directional_positive"
    assert report.first_position_selection_rate == 0.5

    neutral_outcomes = tuple(
        item.model_copy(
            update={
                "resolved_source": None,
                "resolved_tie": True,
            }
        )
        if item.case_id in case_ids[-6:]
        else item
        for item in outcomes
    )
    neutral = build_v21_evaluation_report(
        protocol=protocol,
        compiled_scores=compiled_scores,
        static_scores=static_scores,
        outcomes=neutral_outcomes,
        independent_decisions=decisions,
        sentinel_case_ids=case_ids[-6:],
    )
    assert neutral.instrument_valid is True
    assert neutral.sentinel_accuracy == 1.0

    weak_static_scores = tuple(
        item.model_copy(update={"exact": index >= 7}) for index, item in enumerate(static_scores)
    )
    weak_static = build_v21_evaluation_report(
        protocol=protocol,
        compiled_scores=compiled_scores,
        static_scores=weak_static_scores,
        outcomes=outcomes,
        independent_decisions=decisions,
        sentinel_case_ids=case_ids[-6:],
    )
    assert weak_static.instrument_valid is False
    assert weak_static.interpretation == "instrument_failure"

    invalid_outcomes = tuple(
        item.model_copy(
            update={
                "independent_agreement": False,
                "adjudicated": True,
            }
        )
        if index < 7
        else item
        for index, item in enumerate(outcomes)
    )
    invalid = build_v21_evaluation_report(
        protocol=protocol,
        compiled_scores=compiled_scores,
        static_scores=static_scores,
        outcomes=invalid_outcomes,
        independent_decisions=decisions,
        sentinel_case_ids=case_ids[-6:],
    )
    assert invalid.instrument_valid is False
    assert invalid.interpretation == "instrument_failure"


def test_model_schemas_are_closed_and_identity_free() -> None:
    def keys(node: object) -> set[str]:
        if isinstance(node, dict):
            return set(node) | {key for value in node.values() for key in keys(value)}
        if isinstance(node, list):
            return {key for value in node for key in keys(value)}
        return set()

    for schema in (persona_v21_profile_output_schema(), persona_v21_judge_output_schema()):
        assert schema["additionalProperties"] is False
        assert "expected_trait_ids" not in keys(schema)
        assert "condition" not in keys(schema)
    judge = persona_v21_judge_output_schema()
    assert "packet_id" not in str(judge)
    assert "alternative_id" not in str(judge)


def test_live_semantic_types_bind_to_one_exact_sensor_record() -> None:
    text = "for lantern docs, i usually want the result first and then the details"
    scope = _scope("lantern-docs")
    observation = InteractionObservation(
        observation_id="calibration-observation-2",
        subject_id="calibration-user",
        task_ref=TaskRecordRef(record_id="calibration-task", record_version="1.0.0"),
        turn_id="calibration-turn-2",
        actor=ActorRef(actor_id="calibration-user", kind=ActorKind.USER),
        source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
        text=text,
        scope=scope,
        observed_at=NOW,
        source_system="local_interaction_runtime",
        source_version="persona-calibration",
        source_schema_digest=DIGEST,
    )
    features = SemanticFeatureVector(
        assertion_kind=SemanticAssertionKind.NORMATIVE,
        norm_strength=SemanticNormStrength.PREFERENCE,
        workflow_structure=SemanticWorkflowStructure.NONE,
        example_intent=SemanticExampleIntent.NONE,
        transition_intent=SemanticTransitionIntent.ADDITION,
    )
    receipt = SemanticInterpreterReceipt(
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        source_runtime_version="codex-cli 0.146.0",
        source_runtime_digest=DIGEST,
        prompt_digest="sha256:" + "b" * 64,
        output_schema_digest="sha256:" + "c" * 64,
        batch_input_digest="sha256:" + "d" * 64,
        output_digest="sha256:" + "e" * 64,
        external_session_digest="sha256:" + "f" * 64,
        external_turn_digest="sha256:" + "1" * 64,
        input_count=1,
        created_at=NOW,
    )
    signal = SemanticFeedbackSignal(
        signal_kind=FeedbackSignalKind.PREFERENCE,
        normalized_behavior="Lead with the result, followed by the details.",
        requested_route=ArtifactRoute.PREFERENCE,
        supporting_quote=text,
        support_start=0,
        support_end=len(text),
        durability=SemanticSignalDurability.DURABLE,
        clarity=SemanticSignalClarity.CLEAR,
        scope_hint=SemanticScopeHint.CURRENT_CONTEXT,
        semantic_features=features,
        route_candidates=(ArtifactRoute.PREFERENCE,),
        route_resolution=SemanticRouteResolution.RESOLVED,
    )
    interpretation = SemanticFeedbackInterpretation(
        observation_id=observation.observation_id,
        observation_digest=observation.content_digest,
        signals=(signal,),
        receipt=receipt,
    )
    detection = DetectedFeedback(
        candidate_id="candidate-calibration-observation-2",
        observation_digest=observation.content_digest,
        signal_kind=FeedbackSignalKind.PREFERENCE,
        normalized_behavior=signal.normalized_behavior,
        requested_route=ArtifactRoute.PREFERENCE,
        claim_key="claim-calibration-live",
        scope=scope,
        layer=AdaptationLayer.CURRENT_CONTEXT,
        disposition=AutomationDisposition.REVIEW_REQUIRED,
        reasons=("Semantic candidate is retained for review and is not active.",),
        detected_at=NOW,
        detector_id="codex-semantic-feedback",
        detector_version="1.1.0",
        detector_mode=FeedbackDetectorMode.REVIEW,
        interpreter_receipt_digest=receipt.content_digest,
        semantic_candidate_count=1,
    )
    evidence = build_stage_evidence(build_calibration_history(), 1).messages[1]
    record = bind_sensor_record(
        persona_id="calibration-alex",
        turn=2,
        evidence=evidence,
        observation=observation,
        interpretation=interpretation,
        detection=detection,
        approved=True,
        review_receipt_digest="sha256:" + "2" * 64,
    )
    assert record.claim_id == "claim-calibration-live"
    assert record.transition_intent is SemanticTransitionIntent.ADDITION
    assert record.interpretation_receipt_digest == receipt.content_digest
    with pytest.raises(ValueError, match="requires one exact active target"):
        PersonaSensorRecord.model_validate(
            {
                **record.model_dump(round_trip=True),
                "transition_intent": SemanticTransitionIntent.CORRECTION,
                "affected_claim_id": None,
            }
        )


def test_protocol_and_disposable_calibration_are_frozen_and_non_evidentiary() -> None:
    protocol = PersonaV21Protocol()
    assert protocol.total_session_maximum == 120
    assert protocol.learning_state_scoring == "deterministic_hidden_oracle"
    assert protocol.guidance_adjudication_rate_maximum == 0.25
    assert protocol.version_or_binary_drift_fails_closed is True
    report = run_disposable_calibration()
    assert report.passed is True
    assert report.provider_billed_calls == 0
    assert report.counts_toward_product_evidence is False
    assert len(report.checks) == 9


def test_v1_artifacts_remain_byte_identical_during_hardening() -> None:
    manifest = json.loads(
        (
            ROOT / "development_benchmark_persona_instrument" / "V1-IMMUTABILITY-MANIFEST.json"
        ).read_text(encoding="utf-8")
    )
    source = ROOT / "development_benchmark_persona_evaluation"
    assert manifest["v1_artifacts_immutable"] is True
    for name, expected in manifest["files"].items():
        actual = "sha256:" + hashlib.sha256((source / name).read_bytes()).hexdigest()
        assert actual == expected
