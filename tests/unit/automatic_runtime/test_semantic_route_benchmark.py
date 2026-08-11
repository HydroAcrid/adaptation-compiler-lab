"""Blind route-discrimination design and safety tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

import pytest

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticFeedbackInterpretation,
    SemanticFeedbackSignal,
    SemanticInterpreterReceipt,
    SemanticSignalClarity,
    SemanticSignalDurability,
)
from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticFeedbackCorpus,
    evaluate_semantic_feedback,
)
from adaptation_compiler_lab.automatic_runtime.semantic_route_benchmark import (
    BlindRouteClass,
    BlindRouteReason,
    BlindRouteScope,
    SemanticRouteBlindAudit,
    SemanticRouteBlindEntry,
    SemanticRouteClass,
    SemanticRouteGeneratedItem,
    SemanticRouteGeneration,
    SemanticRoutePlan,
    SemanticRouteProtocol,
    attest_semantic_route_blind_audit,
    attest_semantic_route_generation,
    build_semantic_route_design,
    freeze_semantic_route_corpus,
    semantic_route_blind_audit_prompt,
    summarize_semantic_route_benchmark,
)
from adaptation_compiler_lab.domain import ArtifactRoute
from adaptation_compiler_lab.targets.base import sha256_text

NOW = datetime(2026, 8, 11, 18, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64

_SIGNAL_AND_ROUTE = {
    SemanticRouteClass.MEMORY: (FeedbackSignalKind.MEMORY, ArtifactRoute.MEMORY),
    SemanticRouteClass.POSITIVE_EXAMPLE: (
        FeedbackSignalKind.POSITIVE_EXAMPLE,
        ArtifactRoute.EXAMPLE,
    ),
    SemanticRouteClass.PREFERENCE: (
        FeedbackSignalKind.PREFERENCE,
        ArtifactRoute.PREFERENCE,
    ),
    SemanticRouteClass.PROCEDURE: (
        FeedbackSignalKind.PROCEDURE,
        ArtifactRoute.PROCEDURE,
    ),
    SemanticRouteClass.PROMPT_RULE: (
        FeedbackSignalKind.PROMPT_RULE,
        ArtifactRoute.PROMPT_RULE,
    ),
    SemanticRouteClass.REVOCATION: (FeedbackSignalKind.REVOCATION, None),
}

_REASONS = {
    SemanticRouteClass.MEMORY: BlindRouteReason.NON_NORMATIVE_FACT,
    SemanticRouteClass.POSITIVE_EXAMPLE: BlindRouteReason.ENDORSED_REUSE,
    SemanticRouteClass.PREFERENCE: BlindRouteReason.STABLE_CHOICE,
    SemanticRouteClass.PROCEDURE: BlindRouteReason.ORDERED_TRIGGER_WORKFLOW,
    SemanticRouteClass.PROMPT_RULE: BlindRouteReason.HARD_INVARIANT,
    SemanticRouteClass.REVOCATION: BlindRouteReason.EXACT_ARTIFACT_REMOVAL,
}


def _plan() -> tuple[SemanticRoutePlan, SemanticRouteProtocol]:
    return build_semantic_route_design(created_at=NOW)


def _generation(plan: SemanticRoutePlan) -> SemanticRouteGeneration:
    proposal = SemanticRouteGeneration(
        source_plan_digest=DIGEST,
        items=tuple(
            SemanticRouteGeneratedItem(
                case_id=case.case_id,
                text=f"Synthetic route message {index + 1}.",
            )
            for index, case in enumerate(plan.cases)
        ),
    )
    return attest_semantic_route_generation(plan, proposal)


def _audit(
    plan: SemanticRoutePlan,
    generation: SemanticRouteGeneration,
    auditor_id: str,
    *,
    one_character_id_error: bool = False,
) -> SemanticRouteBlindAudit:
    entries = [
        SemanticRouteBlindEntry(
            case_id=case.case_id,
            classification=BlindRouteClass(case.semantic_class.value),
            scope=BlindRouteScope(case.scope_hint.value),
            reason=_REASONS[case.semantic_class],
        )
        for case in plan.cases
    ]
    if one_character_id_error:
        entries[-1] = entries[-1].model_copy(update={"case_id": entries[-1].case_id + "x"})
    proposal = SemanticRouteBlindAudit(
        auditor_id="model-echo",
        source_generation_digest=DIGEST,
        entries=tuple(entries),
    )
    return attest_semantic_route_blind_audit(
        generation,
        proposal,
        auditor_id=auditor_id,
    )


def _receipt() -> SemanticInterpreterReceipt:
    return SemanticInterpreterReceipt(
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        source_runtime_version="codex-cli 0.146.0",
        source_runtime_digest=DIGEST,
        prompt_digest=DIGEST,
        output_schema_digest=DIGEST,
        batch_input_digest=DIGEST,
        output_digest=DIGEST,
        external_session_digest=DIGEST,
        external_turn_digest=DIGEST,
        input_count=60,
        created_at=NOW,
    )


def _interpretations(
    plan: SemanticRoutePlan,
    corpus: SemanticFeedbackCorpus,
    split: Literal["calibration", "holdout"],
    *,
    wrong_case_id: str | None = None,
) -> dict[str, SemanticFeedbackInterpretation]:
    cases_by_id = {item.case_id: item for item in plan.cases}
    receipt = _receipt()
    results: dict[str, SemanticFeedbackInterpretation] = {}
    for case in corpus.select(split):
        scenario = cases_by_id[case.case_id]
        signal_kind, route = _SIGNAL_AND_ROUTE[scenario.semantic_class]
        if case.case_id == wrong_case_id:
            signal_kind = FeedbackSignalKind.PREFERENCE
            route = ArtifactRoute.PREFERENCE
        if signal_kind is FeedbackSignalKind.REVOCATION:
            signal = SemanticFeedbackSignal(
                signal_kind=signal_kind,
                affected_artifact_id=cast(str, scenario.affected_artifact_id),
                supporting_quote=case.text,
                support_start=0,
                support_end=len(case.text),
                durability=SemanticSignalDurability.DURABLE,
                clarity=SemanticSignalClarity.CLEAR,
                scope_hint=scenario.scope_hint,
            )
        else:
            signal = SemanticFeedbackSignal(
                signal_kind=signal_kind,
                normalized_behavior="Apply the exact synthetic behavior.",
                requested_route=cast(ArtifactRoute, route),
                supporting_quote=case.text,
                support_start=0,
                support_end=len(case.text),
                durability=SemanticSignalDurability.DURABLE,
                clarity=SemanticSignalClarity.CLEAR,
                scope_hint=scenario.scope_hint,
            )
        results[case.case_id] = SemanticFeedbackInterpretation(
            observation_id=case.case_id,
            observation_digest=sha256_text(case.text),
            signals=(signal,),
            receipt=receipt,
        )
    return results


def test_design_is_balanced_opaque_and_fail_closed() -> None:
    plan, protocol = _plan()

    assert len(plan.cases) == 120
    assert len({item.case_id for item in plan.cases}) == 120
    assert all(item.semantic_class.value not in item.case_id for item in plan.cases)
    assert not protocol.blind_auditors_receive_labels
    assert not protocol.synthetic_is_user_authority
    assert not protocol.production_promotion_permitted
    assert not protocol.production_state_mutation_permitted
    assert not protocol.sealed_external_validation_access_permitted


def test_v2_preserves_v1_and_uses_fresh_non_disclosing_scenarios() -> None:
    v1, _ = _plan()
    v2, protocol = build_semantic_route_design(created_at=NOW, revision="v2")

    assert v1.content_digest == (
        "sha256:4116cfa8d8869cdcd55c12dacc183f8351849e0a3ff6a8084deff9abab709ad8"
    )
    assert v2.plan_version == "2.0.0"
    assert protocol.protocol_version == "2.0.0"
    assert {item.case_id for item in v1.cases}.isdisjoint(item.case_id for item in v2.cases)
    assert all("Project Cedar" not in item.generation_brief for item in v2.cases)
    assert all("must never" in item.generation_brief for item in v2.cases)


def test_v3_uses_fresh_exact_revocation_targets() -> None:
    v2, _ = build_semantic_route_design(created_at=NOW, revision="v2")
    v3, protocol = build_semantic_route_design(created_at=NOW, revision="v3")

    revocations = tuple(
        item for item in v3.cases if item.semantic_class is SemanticRouteClass.REVOCATION
    )
    assert v3.plan_version == "3.0.0"
    assert protocol.protocol_version == "3.0.0"
    assert {item.case_id for item in v2.cases}.isdisjoint(item.case_id for item in v3.cases)
    assert all(item.affected_artifact_id is not None for item in revocations)
    assert all(
        item.expectation.affected_artifact_id == item.affected_artifact_id for item in revocations
    )
    assert all("artifact-route" not in cast(str, item.affected_artifact_id) for item in revocations)


def test_v4_adds_durable_memory_and_explicit_active_revocation_contracts() -> None:
    v3, _ = build_semantic_route_design(created_at=NOW, revision="v3")
    v4, protocol = build_semantic_route_design(created_at=NOW, revision="v4")
    memories = tuple(item for item in v4.cases if item.semantic_class is SemanticRouteClass.MEMORY)
    revocations = tuple(
        item for item in v4.cases if item.semantic_class is SemanticRouteClass.REVOCATION
    )

    assert v4.plan_version == "4.0.0"
    assert protocol.protocol_version == "4.0.0"
    assert {item.case_id for item in v3.cases}.isdisjoint(item.case_id for item in v4.cases)
    assert all("Never use current" in item.generation_brief for item in memories)
    assert all("active adaptation artifact" in item.generation_brief for item in revocations)

    corpus = freeze_semantic_route_corpus(v4, _generation(v4))
    assert corpus.corpus_version == "6.0.0"


def test_generation_and_blind_audit_bindings_are_deterministic() -> None:
    plan, _ = _plan()
    generation = _generation(plan)
    audit = _audit(
        plan,
        generation,
        "blind-auditor-a",
        one_character_id_error=True,
    )

    assert generation.source_plan_digest == plan.content_digest
    assert audit.source_generation_digest == generation.content_digest
    assert audit.auditor_id == "blind-auditor-a"
    assert not audit.labels_visible
    assert tuple(item.case_id for item in audit.entries) == tuple(
        item.case_id for item in generation.items
    )


def test_blind_packet_contains_no_plan_labels_or_briefs() -> None:
    plan, _ = _plan()
    generation = _generation(plan)

    packet = semantic_route_blind_audit_prompt(generation, auditor_id="blind-auditor-a")

    assert plan.content_digest not in packet
    assert "generation_brief" not in packet
    assert "accepted_routes" not in packet
    assert "answer key" in packet


def test_blind_entry_rejects_incoherent_reason_or_scope() -> None:
    with pytest.raises(ValueError, match="reason"):
        SemanticRouteBlindEntry(
            case_id="route-deadbeefdeadbeef",
            classification=BlindRouteClass.PREFERENCE,
            scope=BlindRouteScope.PERMANENT_PROFILE,
            reason=BlindRouteReason.HARD_INVARIANT,
        )
    with pytest.raises(ValueError, match="scope"):
        SemanticRouteBlindEntry(
            case_id="route-deadbeefdeadbeef",
            classification=BlindRouteClass.AMBIGUOUS,
            scope=BlindRouteScope.PERMANENT_PROFILE,
            reason=BlindRouteReason.AMBIGUOUS,
        )


def test_freeze_creates_v4_corpus_without_audit_selection() -> None:
    plan, _ = _plan()
    generation = _generation(plan)

    corpus = freeze_semantic_route_corpus(plan, generation)

    assert corpus.corpus_version == "4.0.0"
    assert len(corpus.cases) == 120
    assert all(item.expectation.durable_signal for item in corpus.cases)


def test_perfect_blind_and_detector_results_pass_route_gate() -> None:
    plan, protocol = _plan()
    generation = _generation(plan)
    corpus = freeze_semantic_route_corpus(plan, generation)
    calibration = evaluate_semantic_feedback(
        corpus,
        split="calibration",
        interpretations=_interpretations(plan, corpus, "calibration"),
    )
    holdout = evaluate_semantic_feedback(
        corpus,
        split="holdout",
        interpretations=_interpretations(plan, corpus, "holdout"),
    )

    summary = summarize_semantic_route_benchmark(
        created_at=NOW,
        protocol=protocol,
        plan=plan,
        generation=generation,
        corpus=corpus,
        auditor_a=_audit(plan, generation, "blind-auditor-a"),
        auditor_b=_audit(plan, generation, "blind-auditor-b"),
        calibration_report=calibration,
        holdout_report=holdout,
    )

    assert summary.route_gate_passed
    assert not summary.production_promotion_authorized
    assert summary.blind_metrics.both_match_answer_key_count == 120
    assert all(item.route_accuracy == 1.0 for item in summary.class_metrics)


def test_one_holdout_class_below_threshold_keeps_gate_closed() -> None:
    plan, protocol = _plan()
    generation = _generation(plan)
    corpus = freeze_semantic_route_corpus(plan, generation)
    holdout_memory = [
        item.case_id
        for item in plan.cases
        if item.split == "holdout" and item.semantic_class is SemanticRouteClass.MEMORY
    ]
    interpretations = _interpretations(plan, corpus, "holdout")
    for case_id in holdout_memory[:3]:
        original = interpretations[case_id]
        quote = original.signals[0].supporting_quote
        wrong_signal = SemanticFeedbackSignal(
            signal_kind=FeedbackSignalKind.PREFERENCE,
            normalized_behavior="Apply the wrong synthetic route.",
            requested_route=ArtifactRoute.PREFERENCE,
            supporting_quote=quote,
            support_start=0,
            support_end=len(quote),
            durability=SemanticSignalDurability.DURABLE,
            clarity=SemanticSignalClarity.CLEAR,
            scope_hint=original.signals[0].scope_hint,
        )
        interpretations[case_id] = original.model_copy(update={"signals": (wrong_signal,)})
    holdout = evaluate_semantic_feedback(
        corpus,
        split="holdout",
        interpretations=interpretations,
    )
    calibration = evaluate_semantic_feedback(
        corpus,
        split="calibration",
        interpretations=_interpretations(plan, corpus, "calibration"),
    )

    summary = summarize_semantic_route_benchmark(
        created_at=NOW,
        protocol=protocol,
        plan=plan,
        generation=generation,
        corpus=corpus,
        auditor_a=_audit(plan, generation, "blind-auditor-a"),
        auditor_b=_audit(plan, generation, "blind-auditor-b"),
        calibration_report=calibration,
        holdout_report=holdout,
    )

    assert not summary.route_gate_passed


def test_v3_evaluation_requires_the_exact_revocation_target() -> None:
    plan, _ = build_semantic_route_design(created_at=NOW, revision="v3")
    generation = _generation(plan)
    corpus = freeze_semantic_route_corpus(plan, generation)
    interpretations = _interpretations(plan, corpus, "holdout")
    revocation = next(
        item
        for item in plan.cases
        if item.split == "holdout" and item.semantic_class is SemanticRouteClass.REVOCATION
    )
    original = interpretations[revocation.case_id]
    signal = original.signals[0]
    wrong_target = signal.model_copy(update={"affected_artifact_id": "artifact-wrong-target"})
    interpretations[revocation.case_id] = original.model_copy(update={"signals": (wrong_target,)})

    report = evaluate_semantic_feedback(
        corpus,
        split="holdout",
        interpretations=interpretations,
    )
    evaluation = next(
        item for item in report.case_evaluations if item.case_id == revocation.case_id
    )

    assert corpus.corpus_version == "5.0.0"
    assert not evaluation.route_correct
    assert evaluation.predicted_affected_artifact_ids == ("artifact-wrong-target",)
