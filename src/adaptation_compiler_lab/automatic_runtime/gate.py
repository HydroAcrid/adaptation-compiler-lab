"""Deterministic readiness report for the ordinary-use Codex dogfood gate."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    AutomationDisposition,
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeLearningCycleReceipt,
    RuntimeTargetDeliveryAcknowledgement,
    RuntimeTaskActivationReceipt,
)
from adaptation_compiler_lab.domain import FrozenModel, Identifier, UtcDateTime
from adaptation_compiler_lab.serialization import canonical_digest


class CodexDogfoodGateReport(FrozenModel):
    """Raw-free longitudinal measures and deterministic evidence-readiness state."""

    report_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    generated_at: UtcDateTime
    goal_interaction_count: int = Field(ge=1)
    minimum_active_dates: int = Field(ge=1)
    minimum_activation_count: int = Field(ge=1)
    eligible_interaction_count: int = Field(ge=0)
    active_date_count: int = Field(ge=0)
    assessed_interaction_count: int = Field(ge=0)
    correct_learning_count: int = Field(ge=0)
    false_learning_count: int = Field(ge=0)
    missed_learning_count: int = Field(ge=0)
    promoted_count: int = Field(ge=0)
    revoked_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    no_explicit_signal_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    activation_count: int = Field(ge=0)
    completed_activation_count: int = Field(ge=0)
    failed_activation_count: int = Field(ge=0)
    unresolved_activation_count: int = Field(ge=0)
    rated_activation_count: int = Field(ge=0)
    helped_count: int = Field(ge=0)
    hurt_count: int = Field(ge=0)
    irrelevant_count: int = Field(ge=0)
    correct_activation_count: int = Field(ge=0)
    false_activation_count: int = Field(ge=0)
    missed_activation_count: int = Field(ge=0)
    repeated_correction_count: int = Field(ge=0)
    pack_bytes_by_activation: tuple[int, ...]
    update_latency_seconds: tuple[float, ...]
    automatic_actions: int = Field(ge=0)
    manual_review_touches: int = Field(ge=0)
    remaining_interactions: int = Field(ge=0)
    evidence_ready: bool

    @model_validator(mode="after")
    def totals_and_readiness_are_exact(self) -> Self:
        if (
            self.correct_learning_count + self.false_learning_count + self.missed_learning_count
            != self.assessed_interaction_count
        ):
            raise ValueError("dogfood learning-assessment totals are inconsistent")
        if (
            self.completed_activation_count
            + self.failed_activation_count
            + self.unresolved_activation_count
            != self.activation_count
        ):
            raise ValueError("dogfood activation totals are inconsistent")
        if (
            self.helped_count + self.hurt_count + self.irrelevant_count
            != self.rated_activation_count
        ):
            raise ValueError("dogfood activation-feedback totals are inconsistent")
        expected_remaining = max(
            0,
            self.goal_interaction_count - self.eligible_interaction_count,
        )
        if self.remaining_interactions != expected_remaining:
            raise ValueError("dogfood remaining-interaction count is inconsistent")
        expected_ready = (
            self.eligible_interaction_count >= self.goal_interaction_count
            and self.active_date_count >= self.minimum_active_dates
            and self.activation_count >= self.minimum_activation_count
            and self.assessed_interaction_count == self.eligible_interaction_count
            and self.unresolved_activation_count == 0
            and self.rated_activation_count == self.completed_activation_count
        )
        if self.evidence_ready is not expected_ready:
            raise ValueError("dogfood evidence-ready state is inconsistent")
        return self

    @property
    def content_digest(self) -> str:
        return str(canonical_digest(self))


def build_codex_dogfood_gate_report(
    *,
    subject_id: Identifier,
    learning_cycles: tuple[RuntimeLearningCycleReceipt, ...],
    learning_assessments: tuple[RuntimeLearningAssessment, ...],
    activations: tuple[RuntimeTaskActivationReceipt, ...],
    acknowledgements: tuple[RuntimeTargetDeliveryAcknowledgement, ...],
    activation_feedback: tuple[RuntimeActivationFeedback, ...],
    generated_at: datetime,
    goal_interaction_count: int = 20,
    minimum_active_dates: int = 3,
    minimum_activation_count: int = 6,
) -> CodexDogfoodGateReport:
    """Build a raw-free report while rejecting incomplete or crossed lineage."""

    cycle_by_id = {item.cycle_id: item for item in learning_cycles}
    if len(cycle_by_id) != len(learning_cycles):
        raise ValueError("dogfood report received duplicate learning cycles")
    assessment_by_cycle: dict[str, RuntimeLearningAssessment] = {}
    for assessment in learning_assessments:
        cycle = cycle_by_id.get(assessment.cycle_id)
        if (
            cycle is None
            or assessment.subject_id != subject_id
            or assessment.cycle_digest != cycle.content_digest
        ):
            raise ValueError("dogfood assessment crossed or changed its learning cycle")
        if assessment.cycle_id in assessment_by_cycle:
            raise ValueError("dogfood report received duplicate learning assessments")
        assessment_by_cycle[assessment.cycle_id] = assessment

    activation_by_id = {item.activation_id: item for item in activations}
    if len(activation_by_id) != len(activations):
        raise ValueError("dogfood report received duplicate activations")
    acknowledgement_by_activation: dict[str, RuntimeTargetDeliveryAcknowledgement] = {}
    for acknowledgement in acknowledgements:
        activation = activation_by_id.get(acknowledgement.activation_id)
        if (
            activation is None
            or acknowledgement.subject_id != subject_id
            or acknowledgement.activation_digest != activation.content_digest
        ):
            raise ValueError("dogfood acknowledgement crossed or changed its activation")
        if acknowledgement.activation_id in acknowledgement_by_activation:
            raise ValueError("dogfood report received duplicate acknowledgements")
        acknowledgement_by_activation[acknowledgement.activation_id] = acknowledgement

    feedback_by_activation: dict[str, RuntimeActivationFeedback] = {}
    correction_counts: dict[str, int] = {}
    for feedback in activation_feedback:
        activation = activation_by_id.get(feedback.cycle_id)
        feedback_acknowledgement = acknowledgement_by_activation.get(feedback.cycle_id)
        if activation is None:
            continue
        if (
            feedback_acknowledgement is None
            or feedback_acknowledgement.status != "completed"
            or feedback.subject_id != subject_id
            or feedback.delivery_receipt_digest != activation.delivery_receipt_digest
            or feedback.activated_artifact_ids != activation.active_artifact_ids
        ):
            raise ValueError("dogfood feedback crossed or changed its completed activation")
        if feedback.cycle_id in feedback_by_activation:
            raise ValueError("dogfood report received duplicate activation feedback")
        feedback_by_activation[feedback.cycle_id] = feedback
        if feedback.correction_key is not None:
            correction_counts[feedback.correction_key] = (
                correction_counts.get(feedback.correction_key, 0) + 1
            )

    dispositions = tuple(item.disposition for item in learning_cycles)
    completed = tuple(item for item in acknowledgements if item.status == "completed")
    failed = tuple(item for item in acknowledgements if item.status == "failed")
    feedback_values = tuple(feedback_by_activation.values())
    correct_activation = false_activation = missed_activation = 0
    for feedback in feedback_values:
        relevant = set(feedback.relevant_artifact_ids)
        activated = set(feedback.activated_artifact_ids)
        correct_activation += activated == relevant
        false_activation += bool(activated - relevant)
        missed_activation += bool(relevant - activated)
    assessment_values = tuple(assessment_by_cycle.values())
    evidence_ready = (
        len(learning_cycles) >= goal_interaction_count
        and len({item.created_at.date() for item in learning_cycles}) >= minimum_active_dates
        and len(activations) >= minimum_activation_count
        and len(assessment_values) == len(learning_cycles)
        and len(acknowledgements) == len(activations)
        and len(feedback_values) == len(completed)
    )
    return CodexDogfoodGateReport(
        subject_id=subject_id,
        generated_at=generated_at,
        goal_interaction_count=goal_interaction_count,
        minimum_active_dates=minimum_active_dates,
        minimum_activation_count=minimum_activation_count,
        eligible_interaction_count=len(learning_cycles),
        active_date_count=len({item.created_at.date() for item in learning_cycles}),
        assessed_interaction_count=len(assessment_values),
        correct_learning_count=sum(
            item.outcome is RuntimeLearningAssessmentOutcome.CORRECT for item in assessment_values
        ),
        false_learning_count=sum(
            item.outcome is RuntimeLearningAssessmentOutcome.FALSE_POSITIVE
            for item in assessment_values
        ),
        missed_learning_count=sum(
            item.outcome is RuntimeLearningAssessmentOutcome.MISSED for item in assessment_values
        ),
        promoted_count=dispositions.count(AutomationDisposition.PROMOTED),
        revoked_count=dispositions.count(AutomationDisposition.REVOKED),
        review_required_count=dispositions.count(AutomationDisposition.REVIEW_REQUIRED),
        blocked_count=dispositions.count(AutomationDisposition.BLOCKED),
        no_explicit_signal_count=dispositions.count(AutomationDisposition.NO_EXPLICIT_SIGNAL),
        duplicate_count=dispositions.count(AutomationDisposition.DUPLICATE),
        activation_count=len(activations),
        completed_activation_count=len(completed),
        failed_activation_count=len(failed),
        unresolved_activation_count=len(activations) - len(acknowledgements),
        rated_activation_count=len(feedback_values),
        helped_count=sum(item.outcome is RuntimeFeedbackOutcome.HELPED for item in feedback_values),
        hurt_count=sum(item.outcome is RuntimeFeedbackOutcome.HURT for item in feedback_values),
        irrelevant_count=sum(
            item.outcome is RuntimeFeedbackOutcome.IRRELEVANT for item in feedback_values
        ),
        correct_activation_count=correct_activation,
        false_activation_count=false_activation,
        missed_activation_count=missed_activation,
        repeated_correction_count=sum(max(0, count - 1) for count in correction_counts.values()),
        pack_bytes_by_activation=tuple(item.material_utf8_bytes for item in activations),
        update_latency_seconds=tuple(
            item.update_latency_seconds
            for item in learning_cycles
            if item.disposition in {AutomationDisposition.PROMOTED, AutomationDisposition.REVOKED}
        ),
        automatic_actions=sum(item.automatic_actions for item in learning_cycles),
        manual_review_touches=sum(item.manual_review_touches for item in learning_cycles),
        remaining_interactions=max(0, goal_interaction_count - len(learning_cycles)),
        evidence_ready=evidence_ready,
    )
