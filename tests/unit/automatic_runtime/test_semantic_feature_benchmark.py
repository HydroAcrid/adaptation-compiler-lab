from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticCaseEvaluation,
    SemanticEvaluationMetrics,
    SemanticEvaluationReport,
    SemanticEvaluationThresholds,
    SemanticFeedbackCorpus,
    load_semantic_feedback_corpus,
)
from adaptation_compiler_lab.automatic_runtime.semantic_feature_benchmark import (
    SemanticArchitectureBinding,
    SemanticFeatureBlindAudit,
    SemanticFeatureBlindEntry,
    SemanticFeatureClass,
    SemanticFeatureGeneratedItem,
    SemanticFeatureGeneration,
    SemanticFeaturePlan,
    SemanticFeatureProtocol,
    SemanticFeatureRemediation,
    apply_semantic_feature_remediation,
    attest_semantic_feature_audit,
    attest_semantic_feature_generation,
    build_semantic_feature_design,
    freeze_semantic_feature_corpus,
    revise_semantic_feature_audit_protocol,
    summarize_semantic_feature_benchmark,
)

ROOT = Path(__file__).resolve().parents[3]
CALIBRATION = ROOT / "development_benchmark_semantic_routes_v4" / "CORPUS-v6.json"
NOW = datetime(2026, 8, 12, 22, 45, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def _design() -> tuple[SemanticFeedbackCorpus, SemanticFeaturePlan, SemanticFeatureProtocol]:
    calibration = load_semantic_feedback_corpus(CALIBRATION)
    bindings = tuple(
        SemanticArchitectureBinding(component=name, digest=DIGEST)
        for name in ("detector", "evaluation", "interpreter", "models", "router")
    )
    plan, protocol = build_semantic_feature_design(
        created_at=NOW,
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=bindings,
    )
    return calibration, plan, protocol


def _generation(plan: SemanticFeaturePlan) -> SemanticFeatureGeneration:
    items = []
    for scenario in plan.scenarios:
        target = scenario.expectation.affected_artifact_id
        suffix = "" if target is None else f" Remove {target}."
        items.append(
            SemanticFeatureGeneratedItem(
                case_id=scenario.case_id,
                message=f"Natural user statement {scenario.case_id}.{suffix}",
            )
        )
    proposal = SemanticFeatureGeneration(plan_digest=DIGEST, items=tuple(items))
    return attest_semantic_feature_generation(plan, proposal)


def test_feature_design_is_balanced_and_binds_the_architecture() -> None:
    _calibration, plan, protocol = _design()

    assert len(plan.scenarios) == 64
    assert protocol.plan_digest == plan.content_digest
    assert len(protocol.architecture_bindings) == 5
    for semantic_class in SemanticFeatureClass:
        assert (
            len(tuple(item for item in plan.scenarios if item.semantic_class is semantic_class))
            == 8
        )


def test_v2_supersedes_v1_and_changes_the_fresh_inventory() -> None:
    calibration, plan, protocol = _design()
    bindings = protocol.architecture_bindings

    revised_plan, revised_protocol = build_semantic_feature_design(
        created_at=NOW,
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=bindings,
        revision="v2",
        prior_plan_digest=plan.content_digest,
        prior_protocol_digest=protocol.content_digest,
    )

    assert revised_plan.plan_version == "2.0.0"
    assert revised_plan.supersedes_plan_digest == plan.content_digest
    assert revised_protocol.supersedes_protocol_digest == protocol.content_digest
    assert {item.case_id for item in revised_plan.scenarios}.isdisjoint(
        item.case_id for item in plan.scenarios
    )
    assert "fictional project" not in " ".join(item.brief for item in revised_plan.scenarios)


def test_generation_attestation_and_corpus_freeze_preserve_fresh_holdout() -> None:
    calibration, plan, _protocol = _design()
    generation = _generation(plan)

    corpus = freeze_semantic_feature_corpus(
        calibration,
        plan,
        generation,
        frozen_at=NOW,
    )

    assert corpus.corpus_version == "7.0.0"
    assert len(corpus.select("calibration")) == 60
    assert len(corpus.select("holdout")) == 64
    assert {item.case_id for item in corpus.select("holdout")} == {
        item.case_id for item in plan.scenarios
    }


def test_generation_rejects_construction_disclosure_and_missing_revocation_target() -> None:
    _calibration, plan, _protocol = _design()
    generation = _generation(plan)
    first = generation.items[0].model_copy(update={"message": "This synthetic benchmark case."})
    disclosed = generation.model_copy(update={"items": (first, *generation.items[1:])})
    with pytest.raises(ValueError, match="construction framing"):
        attest_semantic_feature_generation(plan, disclosed)

    revocation = next(
        item for item in plan.scenarios if item.semantic_class is SemanticFeatureClass.REVOCATION
    )
    index = tuple(item.case_id for item in generation.items).index(revocation.case_id)
    missing = generation.items[index].model_copy(update={"message": "Please remove the old item."})
    items = list(generation.items)
    items[index] = missing
    with pytest.raises(ValueError, match="exact artifact target"):
        attest_semantic_feature_generation(
            plan,
            generation.model_copy(update={"items": tuple(items)}),
        )


def test_remediation_can_change_only_framing_violations() -> None:
    _calibration, plan, _protocol = _design()
    generation = _generation(plan)
    by_id = {item.case_id: item for item in plan.scenarios}
    original = next(
        item
        for item in generation.items
        if by_id[item.case_id].expectation.affected_artifact_id is None
    )
    index = generation.items.index(original)
    damaged = original.model_copy(update={"message": "This synthetic benchmark statement."})
    source_items = list(generation.items)
    source_items[index] = damaged
    source = generation.model_copy(update={"items": tuple(source_items)})
    repaired = original.model_copy(update={"message": "An ordinary user statement."})
    proposal = SemanticFeatureRemediation(
        plan_digest=plan.content_digest,
        source_generation_digest=source.content_digest,
        items=(repaired,),
    )

    result = apply_semantic_feature_remediation(plan, source, proposal)

    assert result.items[index] == repaired
    assert tuple(item for offset, item in enumerate(result.items) if offset != index) == tuple(
        item for offset, item in enumerate(generation.items) if offset != index
    )
    unauthorized_item = generation.items[0 if index != 0 else 1]
    unauthorized = proposal.model_copy(update={"items": (unauthorized_item,)})
    with pytest.raises(ValueError, match="unauthorized"):
        apply_semantic_feature_remediation(plan, source, unauthorized)


def test_perfect_blind_and_sensor_result_passes_only_the_development_gate() -> None:
    calibration, plan, protocol = _design()
    generation = _generation(plan)
    corpus = freeze_semantic_feature_corpus(
        calibration,
        plan,
        generation,
        frozen_at=NOW,
    )
    entries = tuple(
        SemanticFeatureBlindEntry(
            case_id=item.case_id,
            classification=item.semantic_class,
            scope_hint=item.scope_hint,
        )
        for item in plan.scenarios
    )
    auditor_a = attest_semantic_feature_audit(
        generation,
        SemanticFeatureBlindAudit(
            auditor_id="blind-a",
            generation_digest=DIGEST,
            entries=entries,
        ),
        auditor_id="blind-a",
    )
    auditor_b = attest_semantic_feature_audit(
        generation,
        SemanticFeatureBlindAudit(
            auditor_id="blind-b",
            generation_digest=DIGEST,
            entries=entries,
        ),
        auditor_id="blind-b",
    )
    evaluations = tuple(
        SemanticCaseEvaluation(
            case_id=item.case_id,
            expected_durable=True,
            predicted_durable=True,
            predicted_signal_count=(
                2 if item.semantic_class is SemanticFeatureClass.AMBIGUOUS else 1
            ),
            predicted_signal_kinds=item.expectation.accepted_signal_kinds,
            predicted_routes=item.expectation.accepted_routes,
            predicted_affected_artifact_ids=(
                ()
                if item.expectation.affected_artifact_id is None
                else (item.expectation.affected_artifact_id,)
            ),
            predicted_route_candidates=item.expected_route_candidates,
            predicted_route_resolutions=(item.expected_resolution,),
            predicted_scope_hints=(item.scope_hint,),
            detection_correct=True,
            route_correct=True,
            scope_correct=True,
        )
        for item in plan.scenarios
    )
    report = SemanticEvaluationReport(
        source_corpus_digest=corpus.content_digest,
        effective_corpus_digest=corpus.content_digest,
        split="holdout",
        interpreter_receipt_digest=DIGEST,
        metrics=SemanticEvaluationMetrics(
            case_count=64,
            true_positive=64,
            false_positive=0,
            true_negative=0,
            false_negative=0,
            precision=1,
            recall=1,
            negative_specificity=1,
            route_accuracy=1,
            scope_accuracy=1,
        ),
        case_evaluations=evaluations,
        failed_case_ids=(),
        thresholds=SemanticEvaluationThresholds(),
        promotion_ready=True,
    )

    summary = summarize_semantic_feature_benchmark(
        created_at=NOW,
        protocol=protocol,
        plan=plan,
        generation=generation,
        corpus=corpus,
        auditor_a=auditor_a,
        auditor_b=auditor_b,
        report=report,
    )

    assert summary.development_gate_passed
    assert summary.production_mode == "review"
    assert not summary.automatic_promotion_authorized
    assert summary.sensor_class_accuracy == 1
    assert all(item.sensor_accuracy == 1 for item in summary.class_metrics)


def test_blind_audit_cannot_reorder_cases() -> None:
    _calibration, plan, _protocol = _design()
    entries = tuple(
        SemanticFeatureBlindEntry(
            case_id=item.case_id,
            classification=item.semantic_class,
            scope_hint=item.scope_hint,
        )
        for item in reversed(plan.scenarios)
    )
    with pytest.raises(ValueError, match="sorted"):
        SemanticFeatureBlindAudit(
            auditor_id="blind-a",
            generation_digest=DIGEST,
            entries=entries,
        )


def test_v3_uses_new_topics_and_explicit_multi_signal_ambiguity() -> None:
    calibration, plan, protocol = _design()
    revised_plan, revised_protocol = build_semantic_feature_design(
        created_at=NOW,
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=protocol.architecture_bindings,
        revision="v3",
        prior_plan_digest=plan.content_digest,
        prior_protocol_digest=protocol.content_digest,
    )

    assert revised_plan.plan_version == "3.0.0"
    assert revised_protocol.protocol_version == "3.0.0"
    assert {item.topic for item in revised_plan.scenarios}.isdisjoint(
        item.topic for item in plan.scenarios
    )
    ambiguous = tuple(
        item
        for item in revised_plan.scenarios
        if item.semantic_class is SemanticFeatureClass.AMBIGUOUS
    )
    assert all("two separate sentences" in item.brief for item in ambiguous)


def test_v4_requires_explicit_scope_and_uses_a_fresh_inventory() -> None:
    calibration, plan, protocol = _design()
    revised_plan, revised_protocol = build_semantic_feature_design(
        created_at=NOW,
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=protocol.architecture_bindings,
        revision="v4",
        prior_plan_digest=plan.content_digest,
        prior_protocol_digest=protocol.content_digest,
    )

    assert revised_plan.plan_version == "4.0.0"
    assert revised_protocol.protocol_version == "4.0.0"
    assert {item.topic for item in revised_plan.scenarios}.isdisjoint(
        item.topic for item in plan.scenarios
    )
    for scenario in revised_plan.scenarios:
        if scenario.scope_hint.value == "current_context":
            assert scenario.context_name is not None
            assert scenario.context_name in scenario.brief
        else:
            assert scenario.context_name is None
            assert "across all future projects" in scenario.brief


def test_v4_generation_attestation_rejects_implicit_scope() -> None:
    calibration, plan, protocol = _design()
    revised_plan, _revised_protocol = build_semantic_feature_design(
        created_at=NOW,
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=protocol.architecture_bindings,
        revision="v4",
        prior_plan_digest=plan.content_digest,
        prior_protocol_digest=protocol.content_digest,
    )
    items = tuple(
        SemanticFeatureGeneratedItem(
            case_id=scenario.case_id,
            message=(
                f"For {scenario.context_name}, keep this durable behavior."
                if scenario.context_name is not None
                else "Across all future projects, keep this durable behavior."
            )
            + f" Reference {scenario.case_id}."
            + (
                " Remove " + str(scenario.expectation.affected_artifact_id) + "."
                if scenario.expectation.affected_artifact_id is not None
                else ""
            ),
        )
        for scenario in revised_plan.scenarios
    )
    generation = SemanticFeatureGeneration(
        generation_version="4.0.0",
        plan_digest=DIGEST,
        items=items,
    )
    assert attest_semantic_feature_generation(revised_plan, generation).plan_digest == (
        revised_plan.content_digest
    )

    permanent_index = next(
        index
        for index, scenario in enumerate(revised_plan.scenarios)
        if scenario.context_name is None and scenario.expectation.affected_artifact_id is None
    )
    damaged_items = list(generation.items)
    damaged_items[permanent_index] = damaged_items[permanent_index].model_copy(
        update={"message": "Generally, keep this durable behavior."}
    )
    with pytest.raises(ValueError, match="explicit permanent scope"):
        attest_semantic_feature_generation(
            revised_plan,
            generation.model_copy(update={"items": tuple(damaged_items)}),
        )


def test_v5_separates_ambiguous_topics_and_freezes_audit_contract() -> None:
    calibration, plan, protocol = _design()
    revised_plan, revised_protocol = build_semantic_feature_design(
        created_at=NOW,
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=(
            SemanticArchitectureBinding(component="benchmark", digest=DIGEST),
            *protocol.architecture_bindings,
        ),
        revision="v5",
        prior_plan_digest=plan.content_digest,
        prior_protocol_digest=protocol.content_digest,
    )

    assert revised_plan.plan_version == "5.0.0"
    assert revised_protocol.protocol_version == "5.0.0"
    assert revised_protocol.architecture_bindings[0].component == "benchmark"
    ambiguous = tuple(
        item
        for item in revised_plan.scenarios
        if item.semantic_class is SemanticFeatureClass.AMBIGUOUS
    )
    assert all(item.secondary_topic is not None for item in ambiguous)
    assert all(item.secondary_topic != item.topic for item in ambiguous)
    assert all("two unrelated durable sentences" in item.brief for item in ambiguous)


def test_indexed_blind_audit_is_bound_back_to_exact_case_ids() -> None:
    _calibration, plan, _protocol = _design()
    generation = _generation(plan)
    indexed = SemanticFeatureBlindAudit(
        auditor_id="blind-indexed",
        generation_digest=DIGEST,
        entries=tuple(
            SemanticFeatureBlindEntry(
                case_index=index,
                classification=scenario.semantic_class,
                scope_hint=scenario.scope_hint,
            )
            for index, scenario in enumerate(plan.scenarios)
        ),
    )

    result = attest_semantic_feature_audit(
        generation,
        indexed,
        auditor_id="blind-indexed",
    )

    assert tuple(item.case_id for item in result.entries) == tuple(
        item.case_id for item in generation.items
    )
    assert all(item.case_index is None for item in result.entries)


def test_audit_transport_revision_preserves_the_frozen_v5_plan() -> None:
    calibration, plan, protocol = _design()
    v5_plan, v5_protocol = build_semantic_feature_design(
        created_at=NOW,
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=(
            SemanticArchitectureBinding(component="benchmark", digest=DIGEST),
            *protocol.architecture_bindings,
        ),
        revision="v5",
        prior_plan_digest=plan.content_digest,
        prior_protocol_digest=protocol.content_digest,
    )

    revised = revise_semantic_feature_audit_protocol(
        created_at=NOW,
        plan=v5_plan,
        prior_protocol=v5_protocol,
        architecture_bindings=v5_protocol.architecture_bindings,
    )

    assert revised.protocol_version == "5.1.0"
    assert revised.plan_digest == v5_plan.content_digest
    assert revised.supersedes_protocol_digest == v5_protocol.content_digest


def test_committed_feature_benchmark_history_remains_readable() -> None:
    for revision in ("v2", "v3", "v4"):
        directory = ROOT / f"development_benchmark_semantic_features_{revision}"
        plan = SemanticFeaturePlan.model_validate_json(
            (directory / f"PLAN-{revision}.json").read_text(encoding="utf-8"),
            strict=True,
        )
        protocol = SemanticFeatureProtocol.model_validate_json(
            (directory / f"PROTOCOL-{revision}.json").read_text(encoding="utf-8"),
            strict=True,
        )
        generation = SemanticFeatureGeneration.model_validate_json(
            (directory / f"GENERATION-{revision}.json").read_text(encoding="utf-8"),
            strict=True,
        )
        assert protocol.plan_digest == plan.content_digest
        assert generation.plan_digest == plan.content_digest
        for label in ("A", "B"):
            audit = SemanticFeatureBlindAudit.model_validate_json(
                (directory / f"BLIND_AUDIT-{label}-{revision}.json").read_text(encoding="utf-8"),
                strict=True,
            )
            assert audit.generation_digest == generation.content_digest

    directory = ROOT / "development_benchmark_semantic_features_v5"
    plan = SemanticFeaturePlan.model_validate_json(
        (directory / "PLAN-v5.json").read_text(encoding="utf-8"), strict=True
    )
    protocol = SemanticFeatureProtocol.model_validate_json(
        (directory / "PROTOCOL-v5.1.json").read_text(encoding="utf-8"), strict=True
    )
    generation = SemanticFeatureGeneration.model_validate_json(
        (directory / "GENERATION-v5.json").read_text(encoding="utf-8"), strict=True
    )
    assert protocol.plan_digest == plan.content_digest
    assert generation.plan_digest == plan.content_digest
    for label in ("A", "B"):
        audit = SemanticFeatureBlindAudit.model_validate_json(
            (directory / "audit_transport_v2" / f"BLIND_AUDIT-{label}-v5.json").read_text(
                encoding="utf-8"
            ),
            strict=True,
        )
        assert audit.generation_digest == generation.content_digest
