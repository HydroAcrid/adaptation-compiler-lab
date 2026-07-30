"""Ordinary-use Codex dogfood gate reporting tests."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime import (
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeTargetDeliveryAcknowledgement,
    build_codex_dogfood_gate_report,
    initial_runtime_state,
)
from adaptation_compiler_lab.domain import TaskRecordRef
from adaptation_compiler_lab.targets.base import sha256_text
from tests.unit.automatic_runtime.test_runtime import (
    NOW,
    _context,
    _observation,
    _runtime,
)


def test_gate_report_measures_false_learning_and_false_activation(
    tmp_path: Path,
) -> None:
    runtime, policy = _runtime(tmp_path)
    learning = runtime.learn(
        _observation(1, "I prefer purpose before commands"),
        state=initial_runtime_state(policy),
        processed_at=NOW + timedelta(minutes=2),
    )
    assessment = RuntimeLearningAssessment(
        assessment_id="assessment-1",
        subject_id="kevin",
        cycle_id=learning.cycle.cycle_id,
        cycle_digest=learning.cycle.content_digest,
        outcome=RuntimeLearningAssessmentOutcome.FALSE_POSITIVE,
        recorded_at=NOW + timedelta(minutes=2, seconds=1),
    )
    prepared = runtime.activate(
        activation_id="activation-1",
        task_ref=TaskRecordRef(record_id="task-1", record_version="1.0.0"),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Prepare the handoff.",
        activated_at=NOW + timedelta(minutes=2, seconds=2),
    )
    acknowledgement = RuntimeTargetDeliveryAcknowledgement(
        acknowledgement_id="acknowledgement-1",
        activation_id=prepared.activation.activation_id,
        subject_id="kevin",
        target_family="codex",
        activation_digest=prepared.activation.content_digest,
        external_session_digest=sha256_text("session-1"),
        external_turn_digest=sha256_text("turn-1"),
        result_digest=sha256_text("result-1"),
        status="completed",
        acknowledged_at=NOW + timedelta(minutes=2, seconds=3),
    )
    feedback = RuntimeActivationFeedback(
        feedback_id="feedback-1",
        subject_id="kevin",
        cycle_id=prepared.activation.activation_id,
        delivery_receipt_digest=prepared.activation.delivery_receipt_digest,
        outcome=RuntimeFeedbackOutcome.IRRELEVANT,
        relevant_artifact_ids=(),
        activated_artifact_ids=prepared.activation.active_artifact_ids,
        correction_key="purpose-order",
        recorded_at=NOW + timedelta(minutes=2, seconds=4),
    )

    report = build_codex_dogfood_gate_report(
        subject_id="kevin",
        learning_cycles=(learning.cycle,),
        learning_assessments=(assessment,),
        activations=(prepared.activation,),
        acknowledgements=(acknowledgement,),
        activation_feedback=(feedback,),
        generated_at=NOW + timedelta(minutes=2, seconds=5),
        goal_interaction_count=1,
        minimum_active_dates=1,
        minimum_activation_count=1,
    )

    assert report.evidence_ready is True
    assert report.false_learning_count == 1
    assert report.false_activation_count == 1
    assert report.correct_activation_count == 0
    assert report.irrelevant_count == 1
    assert report.remaining_interactions == 0


def test_gate_report_rejects_assessment_for_another_cycle(tmp_path: Path) -> None:
    runtime, policy = _runtime(tmp_path)
    learning = runtime.learn(
        _observation(1, "I prefer purpose before commands"),
        state=initial_runtime_state(policy),
        processed_at=NOW + timedelta(minutes=2),
    )
    assessment = RuntimeLearningAssessment(
        assessment_id="assessment-1",
        subject_id="kevin",
        cycle_id=learning.cycle.cycle_id,
        cycle_digest=sha256_text("another-cycle"),
        outcome=RuntimeLearningAssessmentOutcome.CORRECT,
        recorded_at=NOW + timedelta(minutes=2, seconds=1),
    )

    with pytest.raises(ValueError, match="assessment crossed"):
        build_codex_dogfood_gate_report(
            subject_id="kevin",
            learning_cycles=(learning.cycle,),
            learning_assessments=(assessment,),
            activations=(),
            acknowledgements=(),
            activation_feedback=(),
            generated_at=NOW + timedelta(minutes=2, seconds=2),
        )
