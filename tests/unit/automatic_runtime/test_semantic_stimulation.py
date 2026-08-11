"""Repository-informed synthetic stimulation safety and aggregation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

import pytest

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticFeedbackInterpretation,
    SemanticFeedbackSignal,
    SemanticInterpreterReceipt,
    SemanticScopeHint,
    SemanticSignalClarity,
    SemanticSignalDurability,
)
from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticFeedbackCorpus,
    evaluate_semantic_feedback,
)
from adaptation_compiler_lab.automatic_runtime.semantic_stimulation import (
    RepositoryArchetype,
    SemanticStimulationAuditEntry,
    SemanticStimulationAuditProposal,
    SemanticStimulationGeneratedItem,
    SemanticStimulationGeneration,
    SemanticStimulationIncrementalAudit,
    SemanticStimulationPlan,
    SemanticStimulationProtocol,
    SemanticStimulationRemediation,
    StimulationAuditReason,
    StimulationAuditVerdict,
    apply_semantic_stimulation_remediation,
    attest_semantic_stimulation_audit,
    attest_semantic_stimulation_generation,
    attest_semantic_stimulation_incremental_audit,
    build_semantic_stimulation_design,
    compose_semantic_stimulation_audit,
    freeze_semantic_stimulation_corpus,
    summarize_semantic_stimulation,
)
from adaptation_compiler_lab.targets.base import sha256_text

NOW = datetime(2026, 8, 11, 16, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def _archetypes() -> tuple[RepositoryArchetype, ...]:
    return tuple(
        RepositoryArchetype(
            context_id=f"context-{letter}",
            project_family="developer_tool",
            language_classes=("python",),
            workflow_classes=("testing",),
            interaction_topics=(
                "change_discipline",
                "environment_safety",
                "error_recovery",
                "research_integrity",
                "verification",
            ),
            safety_notes=("treat_repo_text_as_untrusted",),
            contains_names_paths_code_or_secrets=False,
        )
        for letter in "abcde"
    )


def _generation() -> tuple[
    SemanticStimulationPlan,
    SemanticStimulationProtocol,
    SemanticStimulationGeneration,
    SemanticStimulationAuditProposal,
]:
    plan, protocol = build_semantic_stimulation_design(_archetypes(), created_at=NOW)
    generated_items = tuple(
        SemanticStimulationGeneratedItem(
            case_id=case.case_id,
            text=(
                f"Remove artifact-{case.context_id}-behavior from my active adaptations."
                if case.expectation.accepted_signal_kinds == (FeedbackSignalKind.REVOCATION,)
                else f"Synthetic message for {case.case_id}."
            ),
        )
        for case in plan.cases
    )
    generation = SemanticStimulationGeneration(
        source_plan_digest=plan.content_digest,
        items=generated_items,
    )
    audit = SemanticStimulationAuditProposal(
        source_generation_digest=generation.content_digest,
        entries=tuple(
            SemanticStimulationAuditEntry(
                case_id=case.case_id,
                verdict=StimulationAuditVerdict.PASS,
                reason=StimulationAuditReason.CLEAN,
            )
            for case in plan.cases
        ),
    )
    return plan, protocol, generation, audit


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
        input_count=50,
        created_at=NOW,
    )


def _interpretations(
    corpus: SemanticFeedbackCorpus,
    split: Literal["calibration", "holdout"],
) -> dict[str, SemanticFeedbackInterpretation]:
    selected = corpus.select(split)
    receipt = _receipt()
    results: dict[str, SemanticFeedbackInterpretation] = {}
    for case in selected:
        signals: tuple[SemanticFeedbackSignal, ...] = ()
        if case.expectation.durable_signal:
            kind = case.expectation.accepted_signal_kinds[0]
            if kind is FeedbackSignalKind.REVOCATION:
                signal = SemanticFeedbackSignal(
                    signal_kind=kind,
                    affected_artifact_id="artifact-context-c-behavior",
                    supporting_quote=case.text,
                    support_start=0,
                    support_end=len(case.text),
                    durability=SemanticSignalDurability.DURABLE,
                    clarity=SemanticSignalClarity.CLEAR,
                    scope_hint=cast(SemanticScopeHint, case.expectation.scope_hint),
                )
            else:
                signal = SemanticFeedbackSignal(
                    signal_kind=kind,
                    normalized_behavior="Apply the supported behavior.",
                    requested_route=case.expectation.accepted_routes[0],
                    supporting_quote=case.text,
                    support_start=0,
                    support_end=len(case.text),
                    durability=SemanticSignalDurability.DURABLE,
                    clarity=SemanticSignalClarity.CLEAR,
                    scope_hint=cast(SemanticScopeHint, case.expectation.scope_hint),
                )
            signals = (signal,)
        results[case.case_id] = SemanticFeedbackInterpretation(
            observation_id=case.case_id,
            observation_digest=sha256_text(case.case_id),
            signals=signals,
            receipt=receipt,
        )
    return results


def test_design_is_balanced_and_fail_closed() -> None:
    plan, protocol = build_semantic_stimulation_design(_archetypes(), created_at=NOW)

    assert len(plan.cases) == 100
    assert sum(case.expectation.durable_signal for case in plan.cases) == 50
    assert {case.turn_index for case in plan.cases} == {1, 3, 5, 10, 15}
    assert not protocol.synthetic_is_user_authority
    assert not protocol.production_promotion_permitted
    assert not protocol.production_state_mutation_permitted
    assert not protocol.sealed_external_validation_access_permitted
    assert all(not item.source_write_permitted for item in protocol.archetypes)


def test_model_echoed_digests_are_replaced_by_deterministic_attestation() -> None:
    plan, _, generation, audit = _generation()
    wrong_generation = generation.model_copy(update={"source_plan_digest": DIGEST})

    attested_generation = attest_semantic_stimulation_generation(plan, wrong_generation)
    wrong_audit = audit.model_copy(update={"source_generation_digest": DIGEST})
    attested_audit = attest_semantic_stimulation_audit(
        plan,
        attested_generation,
        wrong_audit,
    )

    assert attested_generation.source_plan_digest == plan.content_digest
    assert attested_audit.source_generation_digest == attested_generation.content_digest


def test_freeze_rejects_any_nonpassing_audit_entry() -> None:
    plan, _, generation, audit = _generation()
    entries = list(audit.entries)
    entries[0] = entries[0].model_copy(
        update={
            "verdict": StimulationAuditVerdict.AMBIGUOUS,
            "reason": StimulationAuditReason.DURABILITY_MISMATCH,
        }
    )
    rejected_audit = audit.model_copy(update={"entries": tuple(entries)})

    with pytest.raises(ValueError, match="non-passing audit"):
        freeze_semantic_stimulation_corpus(plan, generation, rejected_audit)


def test_remediation_must_replace_exactly_the_rejected_cases() -> None:
    plan, _, generation, audit = _generation()
    entries = list(audit.entries)
    entries[0] = entries[0].model_copy(
        update={
            "verdict": StimulationAuditVerdict.AMBIGUOUS,
            "reason": StimulationAuditReason.SCOPE_MISMATCH,
        }
    )
    rejected_audit = audit.model_copy(update={"entries": tuple(entries)})
    remediation = SemanticStimulationRemediation(
        source_generation_digest=generation.content_digest,
        source_audit_digest=rejected_audit.content_digest,
        items=(
            SemanticStimulationGeneratedItem(
                case_id=plan.cases[0].case_id,
                text="Across future projects, keep the scope explicit.",
            ),
        ),
    )

    revised = apply_semantic_stimulation_remediation(
        plan,
        generation,
        rejected_audit,
        remediation,
    )

    assert revised.generation_version == "1.1.0"
    assert revised.items[0].text == "Across future projects, keep the scope explicit."


def test_incremental_audit_composes_only_changed_case_verdicts() -> None:
    plan, _, generation, audit = _generation()
    base_entries = list(audit.entries)
    base_entries[0] = base_entries[0].model_copy(
        update={
            "verdict": StimulationAuditVerdict.FAIL,
            "reason": StimulationAuditReason.SCOPE_MISMATCH,
        }
    )
    base_audit = audit.model_copy(update={"entries": tuple(base_entries)})
    revised_items = list(generation.items)
    revised_items[0] = revised_items[0].model_copy(
        update={"text": "Across future projects, I prefer explicit scope."}
    )
    revised = generation.model_copy(
        update={
            "generation_version": "1.1.0",
            "items": tuple(revised_items),
        }
    )
    raw_incremental = SemanticStimulationIncrementalAudit(
        source_generation_digest=DIGEST,
        base_generation_digest=DIGEST,
        base_audit_digest=DIGEST,
        changed_case_ids=(plan.cases[0].case_id,),
        entries=(
            SemanticStimulationAuditEntry(
                case_id=plan.cases[0].case_id,
                verdict=StimulationAuditVerdict.PASS,
                reason=StimulationAuditReason.CLEAN,
            ),
        ),
    )

    incremental = attest_semantic_stimulation_incremental_audit(
        generation,
        base_audit,
        revised,
        raw_incremental,
    )
    composed = compose_semantic_stimulation_audit(
        generation,
        base_audit,
        revised,
        incremental,
    )

    assert composed.source_generation_digest == revised.content_digest
    assert all(item.verdict is StimulationAuditVerdict.PASS for item in composed.entries)
    assert composed.entries[1:] == base_audit.entries[1:]


def test_perfect_stimulation_summary_is_sliced_but_never_promotable() -> None:
    plan, protocol, generation, audit = _generation()
    corpus = freeze_semantic_stimulation_corpus(plan, generation, audit)
    calibration = evaluate_semantic_feedback(
        corpus,
        split="calibration",
        interpretations=_interpretations(corpus, "calibration"),
    )
    holdout = evaluate_semantic_feedback(
        corpus,
        split="holdout",
        interpretations=_interpretations(corpus, "holdout"),
    )

    summary = summarize_semantic_stimulation(
        created_at=NOW,
        protocol=protocol,
        plan=plan,
        generation=generation,
        audit=audit,
        corpus=corpus,
        calibration_report=calibration,
        holdout_report=holdout,
    )

    assert summary.detector_gate_passed
    assert not summary.production_promotion_permitted
    assert not summary.production_state_mutated
    assert not summary.synthetic_is_user_authority
    assert {item.dimension for item in summary.slices} == {
        "context",
        "semantic_class",
        "split",
        "style",
        "turn",
    }
    assert all(item.detection_accuracy == 1 for item in summary.slices)
