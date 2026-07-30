"""Frozen semantic-feedback corpus and promotion-gate tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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
    SemanticFeedbackCase,
    apply_semantic_corpus_adjudication,
    evaluate_semantic_feedback,
    load_semantic_corpus_adjudication,
    load_semantic_feedback_corpus,
)
from adaptation_compiler_lab.domain import ArtifactRoute
from adaptation_compiler_lab.targets.base import sha256_text

ROOT = Path(__file__).resolve().parents[3]
CORPUS_PATH = ROOT / "development_benchmark_semantic_feedback" / "CORPUS-v1.json"
DIGEST_PATH = ROOT / "development_benchmark_semantic_feedback" / "CORPUS-v1.sha256"
CORPUS_V2_PATH = ROOT / "development_benchmark_semantic_feedback" / "CORPUS-v2.json"
ADJUDICATION_V2_PATH = (
    ROOT / "development_benchmark_semantic_feedback" / "CALIBRATION_ADJUDICATION-v2.json"
)
NOW = datetime(2026, 7, 30, 18, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


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
        input_count=24,
        created_at=NOW,
    )


def _positive_signal(case: SemanticFeedbackCase) -> SemanticFeedbackSignal:
    expectation = case.expectation
    return SemanticFeedbackSignal(
        signal_kind=expectation.accepted_signal_kinds[0],
        normalized_behavior="Apply the supported behavior.",
        requested_route=expectation.accepted_routes[0],
        supporting_quote=case.text,
        support_start=0,
        support_end=len(case.text),
        durability=SemanticSignalDurability.DURABLE,
        clarity=SemanticSignalClarity.CLEAR,
        scope_hint=expectation.scope_hint or SemanticScopeHint.PERMANENT_PROFILE,
    )


def _interpretation(
    case: SemanticFeedbackCase,
    receipt: SemanticInterpreterReceipt,
) -> SemanticFeedbackInterpretation:
    return SemanticFeedbackInterpretation(
        observation_id=case.case_id,
        observation_digest=sha256_text(case.case_id),
        signals=((_positive_signal(case),) if case.expectation.durable_signal else ()),
        receipt=receipt,
    )


def test_frozen_semantic_corpus_has_broad_balanced_splits() -> None:
    corpus = load_semantic_feedback_corpus(CORPUS_PATH)

    assert len(corpus.cases) == 48
    assert len(corpus.select("calibration")) == 24
    assert len(corpus.select("holdout")) == 24
    assert DIGEST_PATH.read_text(encoding="utf-8").strip() == corpus.content_digest
    tags = {tag for case in corpus.cases for tag in case.tags}
    assert {
        "acronym",
        "bad_grammar",
        "fragment",
        "hypothetical",
        "immediate_task_only",
        "prompt_injection_quote",
        "quoted_third_party",
        "slang",
        "task_request",
    } <= tags


def test_perfect_semantic_holdout_is_promotion_ready() -> None:
    corpus = load_semantic_feedback_corpus(CORPUS_PATH)
    receipt = _receipt()
    interpretations = {
        case.case_id: _interpretation(case, receipt) for case in corpus.select("holdout")
    }

    report = evaluate_semantic_feedback(
        corpus,
        split="holdout",
        interpretations=interpretations,
    )

    assert report.promotion_ready
    assert report.metrics.precision == 1
    assert report.metrics.recall == 1
    assert report.metrics.negative_specificity == 1
    assert not report.failed_case_ids


def test_calibration_adjudication_preserves_source_and_cannot_relabel_holdout() -> None:
    corpus = load_semantic_feedback_corpus(CORPUS_V2_PATH)
    adjudication = load_semantic_corpus_adjudication(ADJUDICATION_V2_PATH)

    effective = apply_semantic_corpus_adjudication(corpus, adjudication)

    assert effective.content_digest != corpus.content_digest
    assert next(
        case for case in effective.cases if case.case_id == "v2c019"
    ).expectation.durable_signal
    invalid = adjudication.model_copy(
        update={"entries": (adjudication.entries[0].model_copy(update={"case_id": "v2h001"}),)}
    )
    with pytest.raises(ValueError, match="cannot alter holdout"):
        apply_semantic_corpus_adjudication(corpus, invalid)


def test_one_false_positive_blocks_calibrated_promotion() -> None:
    corpus = load_semantic_feedback_corpus(CORPUS_PATH)
    receipt = _receipt()
    interpretations = {
        case.case_id: _interpretation(case, receipt) for case in corpus.select("holdout")
    }
    negative = next(
        case for case in corpus.select("holdout") if not case.expectation.durable_signal
    )
    interpretations[negative.case_id] = SemanticFeedbackInterpretation(
        observation_id=negative.case_id,
        observation_digest=sha256_text(negative.case_id),
        signals=(
            SemanticFeedbackSignal(
                signal_kind=FeedbackSignalKind.PREFERENCE,
                normalized_behavior="Apply an unsupported preference.",
                requested_route=ArtifactRoute.PREFERENCE,
                supporting_quote=negative.text,
                support_start=0,
                support_end=len(negative.text),
                durability=SemanticSignalDurability.DURABLE,
                clarity=SemanticSignalClarity.CLEAR,
                scope_hint=SemanticScopeHint.PERMANENT_PROFILE,
            ),
        ),
        receipt=receipt,
    )

    report = evaluate_semantic_feedback(
        corpus,
        split="holdout",
        interpretations=interpretations,
    )

    assert not report.promotion_ready
    assert report.metrics.false_positive == 1
    assert report.failed_case_ids == (negative.case_id,)
