"""Frozen-corpus evaluation for semantic feedback candidate generation.

The interpreter is a fallible sensor, so serving decisions depend on aggregate behavior over
natural positives and adversarial negatives rather than on one demonstration phrase.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticFeedbackInterpretation,
    SemanticScopeHint,
    SemanticSignalDurability,
)
from adaptation_compiler_lab.domain import (
    ArtifactRoute,
    FrozenModel,
    Identifier,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest

SemanticEvaluationSplit = Literal["calibration", "holdout"]


class SemanticFeedbackExpectation(FrozenModel):
    """Outcome dimensions that can be scored without matching generated prose."""

    durable_signal: bool
    accepted_signal_kinds: tuple[FeedbackSignalKind, ...] = ()
    accepted_routes: tuple[ArtifactRoute, ...] = ()
    scope_hint: SemanticScopeHint | None = None
    affected_artifact_id: Identifier | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )

    @field_validator("accepted_signal_kinds", "accepted_routes")
    @classmethod
    def expected_values_are_sorted_unique(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        rendered = tuple(str(item) for item in value)
        if not strings_are_sorted_unique(rendered):
            raise ValueError("semantic expectation values must be sorted and unique")
        return value

    @model_validator(mode="after")
    def positive_shape_is_complete(self) -> SemanticFeedbackExpectation:
        if self.durable_signal != bool(self.accepted_signal_kinds):
            raise ValueError("durable expectation must specify accepted signal kinds")
        revocation_only = self.accepted_signal_kinds == (FeedbackSignalKind.REVOCATION,)
        if revocation_only and self.accepted_routes:
            raise ValueError("revocation expectations cannot specify artifact routes")
        if self.durable_signal and not revocation_only and not self.accepted_routes:
            raise ValueError("non-revocation durable expectation must specify accepted routes")
        if not self.durable_signal and self.accepted_routes:
            raise ValueError("negative expectation cannot specify accepted routes")
        if FeedbackSignalKind.REVOCATION in self.accepted_signal_kinds and not revocation_only:
            raise ValueError("revocation cannot be combined with learning signal kinds")
        if not revocation_only and self.affected_artifact_id is not None:
            raise ValueError("only revocation expectations may name an affected artifact")
        if self.durable_signal != (self.scope_hint is not None):
            raise ValueError("durable expectation must specify a scope hint")
        return self


class SemanticFeedbackCase(FrozenModel):
    """One public synthetic message and its behavior-level expectation."""

    case_id: Identifier
    split: SemanticEvaluationSplit
    text: str = Field(min_length=1, max_length=2_000)
    tags: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    expectation: SemanticFeedbackExpectation

    @field_validator("tags")
    @classmethod
    def tags_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("semantic evaluation tags must be sorted and unique")
        return value


class SemanticFeedbackCorpus(FrozenModel):
    """Versioned public corpus with a frozen holdout split."""

    corpus_version: Literal[
        "1.0.0",
        "2.0.0",
        "3.0.0",
        "4.0.0",
        "5.0.0",
        "6.0.0",
    ] = "1.0.0"
    corpus_id: Identifier
    frozen_at: UtcDateTime
    cases: Annotated[tuple[SemanticFeedbackCase, ...], Field(min_length=40)]

    @field_validator("cases")
    @classmethod
    def cases_are_sorted_unique(
        cls,
        value: tuple[SemanticFeedbackCase, ...],
    ) -> tuple[SemanticFeedbackCase, ...]:
        ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(ids):
            raise ValueError("semantic cases must be sorted by unique case ID")
        return value

    @model_validator(mode="after")
    def split_has_breadth(self) -> SemanticFeedbackCorpus:
        for split in ("calibration", "holdout"):
            selected = tuple(item for item in self.cases if item.split == split)
            positives = tuple(item for item in selected if item.expectation.durable_signal)
            negatives = tuple(item for item in selected if not item.expectation.durable_signal)
            route_only = self.corpus_version in {"4.0.0", "5.0.0", "6.0.0"}
            if (
                len(selected) < 20
                or len(positives) < 10
                or (not route_only and len(negatives) < 10)
            ):
                composition = "10 positives" if route_only else "10 positives, and 10 negatives"
                raise ValueError(
                    f"semantic {split} split requires at least 20 cases, {composition}"
                )
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)

    def select(self, split: SemanticEvaluationSplit) -> tuple[SemanticFeedbackCase, ...]:
        return tuple(item for item in self.cases if item.split == split)


class SemanticExpectationAdjudicationEntry(FrozenModel):
    """Audited calibration-only correction to synthetic ground truth."""

    case_id: Identifier
    revised_expectation: SemanticFeedbackExpectation
    rationale: str = Field(min_length=1, max_length=1_000)


class SemanticCorpusAdjudication(FrozenModel):
    """Append-only correction layer; the frozen source corpus remains immutable."""

    adjudication_version: Literal["1.0.0"] = "1.0.0"
    adjudication_id: Identifier
    source_corpus_digest: Sha256Digest
    created_at: UtcDateTime
    entries: Annotated[
        tuple[SemanticExpectationAdjudicationEntry, ...],
        Field(min_length=1),
    ]

    @field_validator("entries")
    @classmethod
    def entries_are_sorted_unique(
        cls,
        value: tuple[SemanticExpectationAdjudicationEntry, ...],
    ) -> tuple[SemanticExpectationAdjudicationEntry, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("semantic adjudication entries must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticEvaluationThresholds(FrozenModel):
    """Conservative gate for unattended low-risk promotion."""

    minimum_precision: float = Field(default=0.98, ge=0, le=1)
    minimum_recall: float = Field(default=0.90, ge=0, le=1)
    minimum_route_accuracy: float = Field(default=0.95, ge=0, le=1)
    minimum_negative_specificity: float = Field(default=0.98, ge=0, le=1)


class SemanticEvaluationMetrics(FrozenModel):
    """Behavior-level confusion matrix plus routing and scoping quality."""

    case_count: int = Field(ge=1)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    negative_specificity: float = Field(ge=0, le=1)
    route_accuracy: float = Field(ge=0, le=1)
    scope_accuracy: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def matrix_accounts_for_every_case(self) -> SemanticEvaluationMetrics:
        if (
            self.true_positive + self.false_positive + self.true_negative + self.false_negative
            != self.case_count
        ):
            raise ValueError("semantic confusion matrix does not account for every case")
        return self


class SemanticCaseEvaluation(FrozenModel):
    """Raw-free per-case classification used to diagnose calibration failures."""

    case_id: Identifier
    expected_durable: bool
    predicted_durable: bool
    predicted_signal_kinds: tuple[FeedbackSignalKind, ...]
    predicted_routes: tuple[ArtifactRoute, ...]
    predicted_affected_artifact_ids: tuple[Identifier, ...] = Field(
        default=(),
        exclude_if=lambda value: not value,
    )
    predicted_scope_hints: tuple[SemanticScopeHint, ...]
    detection_correct: bool
    route_correct: bool
    scope_correct: bool

    @field_validator(
        "predicted_signal_kinds",
        "predicted_routes",
        "predicted_affected_artifact_ids",
        "predicted_scope_hints",
    )
    @classmethod
    def predictions_are_sorted_unique(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        rendered = tuple(str(item) for item in value)
        if not strings_are_sorted_unique(rendered):
            raise ValueError("semantic case predictions must be sorted and unique")
        return value


class SemanticEvaluationReport(FrozenModel):
    """Raw-free, digest-bound result suitable for a detector serving gate."""

    report_version: Literal["1.0.0", "1.1.0", "1.2.0"] = "1.2.0"
    source_corpus_digest: Sha256Digest
    effective_corpus_digest: Sha256Digest
    adjudication_digest: Sha256Digest | None = None
    split: SemanticEvaluationSplit
    interpreter_receipt_digest: Sha256Digest
    metrics: SemanticEvaluationMetrics
    case_evaluations: tuple[SemanticCaseEvaluation, ...]
    failed_case_ids: tuple[Identifier, ...]
    thresholds: SemanticEvaluationThresholds
    promotion_ready: bool

    @field_validator("failed_case_ids")
    @classmethod
    def failures_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("semantic failures must be sorted and unique")
        return value

    @field_validator("case_evaluations")
    @classmethod
    def case_evaluations_are_sorted_unique(
        cls,
        value: tuple[SemanticCaseEvaluation, ...],
    ) -> tuple[SemanticCaseEvaluation, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("semantic case evaluations must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_semantic_feedback_corpus(path: Path) -> SemanticFeedbackCorpus:
    """Load one strict frozen corpus."""

    return SemanticFeedbackCorpus.model_validate_json(
        path.read_text(encoding="utf-8"),
        strict=True,
    )


def load_semantic_corpus_adjudication(path: Path) -> SemanticCorpusAdjudication:
    """Load one strict calibration-only expectation correction."""

    return SemanticCorpusAdjudication.model_validate_json(
        path.read_text(encoding="utf-8"),
        strict=True,
    )


def apply_semantic_corpus_adjudication(
    corpus: SemanticFeedbackCorpus,
    adjudication: SemanticCorpusAdjudication,
) -> SemanticFeedbackCorpus:
    """Apply corrections without mutating or replacing the frozen source corpus."""

    if adjudication.source_corpus_digest != corpus.content_digest:
        raise ValueError("semantic adjudication does not bind the exact source corpus")
    by_id = {item.case_id: item for item in corpus.cases}
    replacements = {item.case_id: item for item in adjudication.entries}
    for case_id in replacements:
        case = by_id.get(case_id)
        if case is None:
            raise ValueError("semantic adjudication names an unknown case")
        if case.split != "calibration":
            raise ValueError("semantic adjudication cannot alter holdout ground truth")
    return corpus.model_copy(
        update={
            "cases": tuple(
                case.model_copy(
                    update={
                        "expectation": replacements[case.case_id].revised_expectation,
                    }
                )
                if case.case_id in replacements
                else case
                for case in corpus.cases
            )
        }
    )


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def evaluate_semantic_feedback(
    corpus: SemanticFeedbackCorpus,
    *,
    split: SemanticEvaluationSplit,
    interpretations: Mapping[str, SemanticFeedbackInterpretation],
    thresholds: SemanticEvaluationThresholds | None = None,
    source_corpus_digest: Sha256Digest | None = None,
    adjudication_digest: Sha256Digest | None = None,
) -> SemanticEvaluationReport:
    """Score durable detection separately from generated wording."""

    selected = corpus.select(split)
    expected_ids = tuple(item.case_id for item in selected)
    if tuple(interpretations) != expected_ids:
        raise ValueError("semantic evaluation results omitted, reordered, or invented cases")
    receipts = {item.receipt.content_digest for item in interpretations.values()}
    if len(receipts) != 1:
        raise ValueError("semantic evaluation split must be generated by one isolated batch")

    true_positive = false_positive = true_negative = false_negative = 0
    route_correct = scope_correct = positive_predictions = 0
    failures: set[str] = set()
    case_evaluations: list[SemanticCaseEvaluation] = []
    for case in selected:
        interpretation = interpretations[case.case_id]
        durable = tuple(
            signal
            for signal in interpretation.signals
            if signal.durability is not SemanticSignalDurability.TASK_ONLY
        )
        evaluation_corrections = tuple(
            signal
            for signal in interpretation.signals
            if signal.durability is SemanticSignalDurability.TASK_ONLY
            and signal.signal_kind is FeedbackSignalKind.CORRECTION
        )
        candidates = durable + evaluation_corrections
        predicted_positive = bool(candidates)
        expected_positive = case.expectation.durable_signal
        if expected_positive and predicted_positive:
            true_positive += 1
        elif expected_positive:
            false_negative += 1
            failures.add(case.case_id)
        elif predicted_positive:
            false_positive += 1
            failures.add(case.case_id)
        else:
            true_negative += 1

        if not predicted_positive:
            case_evaluations.append(
                SemanticCaseEvaluation(
                    case_id=case.case_id,
                    expected_durable=expected_positive,
                    predicted_durable=False,
                    predicted_signal_kinds=(),
                    predicted_routes=(),
                    predicted_scope_hints=(),
                    detection_correct=predicted_positive == expected_positive,
                    route_correct=not expected_positive,
                    scope_correct=not expected_positive,
                )
            )
            continue
        positive_predictions += 1
        route_match = any(
            signal.signal_kind in case.expectation.accepted_signal_kinds
            and (
                signal.requested_route in case.expectation.accepted_routes
                or (
                    signal.signal_kind is FeedbackSignalKind.REVOCATION
                    and not case.expectation.accepted_routes
                    and signal.requested_route is None
                    and (
                        case.expectation.affected_artifact_id is None
                        or signal.affected_artifact_id == case.expectation.affected_artifact_id
                    )
                )
                or (
                    signal.signal_kind is FeedbackSignalKind.CORRECTION
                    and FeedbackSignalKind.CORRECTION in case.expectation.accepted_signal_kinds
                    and signal.requested_route is not None
                )
            )
            for signal in candidates
        )
        scope_match = any(signal.scope_hint is case.expectation.scope_hint for signal in candidates)
        route_correct += int(route_match)
        scope_correct += int(scope_match)
        if not route_match:
            failures.add(case.case_id)
        if not scope_match:
            failures.add(case.case_id)
        case_evaluations.append(
            SemanticCaseEvaluation(
                case_id=case.case_id,
                expected_durable=expected_positive,
                predicted_durable=True,
                predicted_signal_kinds=tuple(
                    sorted({item.signal_kind for item in candidates}, key=lambda item: item.value)
                ),
                predicted_routes=tuple(
                    sorted(
                        {
                            item.requested_route
                            for item in candidates
                            if item.requested_route is not None
                        },
                        key=lambda item: item.value,
                    )
                ),
                predicted_affected_artifact_ids=tuple(
                    sorted(
                        {
                            item.affected_artifact_id
                            for item in candidates
                            if item.affected_artifact_id is not None
                        }
                    )
                ),
                predicted_scope_hints=tuple(
                    sorted({item.scope_hint for item in candidates}, key=lambda item: item.value)
                ),
                detection_correct=predicted_positive == expected_positive,
                route_correct=route_match,
                scope_correct=scope_match,
            )
        )

    metrics = SemanticEvaluationMetrics(
        case_count=len(selected),
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        precision=_ratio(true_positive, true_positive + false_positive),
        recall=_ratio(true_positive, true_positive + false_negative),
        negative_specificity=_ratio(true_negative, true_negative + false_positive),
        route_accuracy=_ratio(route_correct, positive_predictions),
        scope_accuracy=_ratio(scope_correct, positive_predictions),
    )
    gate = thresholds or SemanticEvaluationThresholds()
    ready = (
        metrics.precision >= gate.minimum_precision
        and metrics.recall >= gate.minimum_recall
        and metrics.route_accuracy >= gate.minimum_route_accuracy
        and metrics.negative_specificity >= gate.minimum_negative_specificity
    )
    return SemanticEvaluationReport(
        source_corpus_digest=source_corpus_digest or corpus.content_digest,
        effective_corpus_digest=corpus.content_digest,
        adjudication_digest=adjudication_digest,
        split=split,
        interpreter_receipt_digest=next(iter(receipts)),
        metrics=metrics,
        case_evaluations=tuple(case_evaluations),
        failed_case_ids=tuple(sorted(failures)),
        thresholds=gate,
        promotion_ready=ready,
    )


def repair_semantic_evaluation_failures(
    report: SemanticEvaluationReport,
) -> SemanticEvaluationReport:
    """Upgrade v1.0 reports whose failure index omitted scope-only mismatches."""

    failures = tuple(
        sorted(
            item.case_id
            for item in report.case_evaluations
            if not (item.detection_correct and item.route_correct and item.scope_correct)
        )
    )
    return report.model_copy(
        update={
            "report_version": "1.1.0",
            "failed_case_ids": failures,
        }
    )
