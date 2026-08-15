"""Append-only automatic-runtime ledger tests."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime import (
    AutomaticRuntimeLedger,
    AutomaticRuntimeResult,
    RuntimeActivationFeedback,
    RuntimeFeedbackOutcome,
    RuntimeLearningAssessment,
    RuntimeLearningAssessmentOutcome,
    RuntimeSourceCheckpoint,
    RuntimeTargetDeliveryAcknowledgement,
    initial_runtime_state,
    summarize_runtime,
)
from adaptation_compiler_lab.domain import ApprovalDecision, TaskRecordRef
from adaptation_compiler_lab.governance import GovernanceEvent
from adaptation_compiler_lab.persistence.errors import HistoryConflictError, RecordConflictError
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.base import sha256_text
from tests.unit.automatic_runtime.test_runtime import (
    NOW,
    _context,
    _observation,
    _review_item,
    _runtime,
)


def _events(result: AutomaticRuntimeResult) -> tuple[GovernanceEvent, ...]:
    return tuple(
        event for event in (result.release_event, result.activation_event) if event is not None
    )


def test_runtime_ledger_is_append_only_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    assert SqliteUnitOfWorkFactory(path).initialize() == 11
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    result = runtime.process(
        _observation(1, "Preference: keep final summaries concise"),
        state=initial,
        context=_context(1, project_id="ordinary-project"),
        target_task="Update the summary.",
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")

    assert ledger.initialize(initial)
    assert not ledger.initialize(initial)
    assert ledger.append(result.cycle, result.state, governance_events=_events(result))
    assert not ledger.append(result.cycle, result.state, governance_events=_events(result))
    assert result.cycle.delivery_receipt_digest is not None
    feedback = RuntimeActivationFeedback(
        feedback_id="feedback-1",
        subject_id="kevin",
        cycle_id=result.cycle.cycle_id,
        delivery_receipt_digest=result.cycle.delivery_receipt_digest,
        outcome=RuntimeFeedbackOutcome.HELPED,
        relevant_artifact_ids=result.cycle.active_artifact_ids,
        activated_artifact_ids=result.cycle.active_artifact_ids,
        correction_key="concise-summary",
        recorded_at=NOW + timedelta(minutes=2),
    )
    assert ledger.add_feedback(feedback)
    assert not ledger.add_feedback(feedback)
    assert ledger.current() == result.state
    assert ledger.cycles() == (result.cycle,)
    assert ledger.feedback() == (feedback,)
    metrics = summarize_runtime(ledger.cycles(), ledger.feedback())
    assert metrics.helped_count == 1
    assert metrics.correct_activation_count == 1
    assert metrics.false_activation_count == 0
    assert metrics.pack_bytes_by_generation == (result.cycle.rendered_material_utf8_bytes,)

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE automatic_runtime_cycles SET disposition = 'blocked'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM automatic_runtime_states")


def test_runtime_ledger_rejects_a_stale_state_head(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    first = runtime.process(
        _observation(1, "Preference: keep final summaries concise"),
        state=initial,
        context=_context(1, project_id="ordinary-project"),
        target_task="Update the summary.",
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    stale = runtime.process(
        _observation(2, "Remember: the default shell is zsh"),
        state=initial,
        context=_context(2, project_id="ordinary-project"),
        target_task="Update the command.",
        processed_at=NOW + timedelta(minutes=2, seconds=5),
    )
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(initial)
    ledger.append(first.cycle, first.state, governance_events=_events(first))

    with pytest.raises(HistoryConflictError, match="head changed"):
        ledger.append(stale.cycle, stale.state, governance_events=_events(stale))


def test_learning_checkpoint_activation_acknowledgement_and_feedback_are_separate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    learning = runtime.learn(
        _observation(1, "I prefer purpose before commands"),
        state=initial,
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(initial)

    assert ledger.append_learning(
        learning.cycle,
        learning.state,
        release_event=learning.release_event,
    )
    assert not ledger.append_learning(
        learning.cycle,
        learning.state,
        release_event=learning.release_event,
    )
    assert ledger.learning_cycle_for_observation("observation-1") == learning.cycle

    cursor = '{"cursor":"hashed-only"}'
    checkpoint = RuntimeSourceCheckpoint(
        checkpoint_id="codex-checkpoint-1",
        subject_id="kevin",
        source_id="codex-dogfood-interactive",
        sequence=1,
        cursor_digest=sha256_text(cursor),
        cursor_value=cursor,
        committed_at=NOW + timedelta(minutes=2),
    )
    assert ledger.commit_checkpoint(checkpoint)
    assert ledger.current_checkpoint("codex-dogfood-interactive") == checkpoint

    assessment = RuntimeLearningAssessment(
        assessment_id="learning-assessment-1",
        subject_id="kevin",
        cycle_id=learning.cycle.cycle_id,
        cycle_digest=learning.cycle.content_digest,
        outcome=RuntimeLearningAssessmentOutcome.CORRECT,
        recorded_at=NOW + timedelta(minutes=2, seconds=5),
    )
    assert ledger.add_learning_assessment(assessment)
    assert not ledger.add_learning_assessment(assessment)
    assert ledger.learning_assessments() == (assessment,)

    prepared = runtime.activate(
        activation_id="fresh-task-1",
        task_ref=TaskRecordRef(record_id="fresh-task-1", record_version="1.0.0"),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Prepare the handoff.",
        activated_at=NOW + timedelta(minutes=2),
    )
    assert ledger.append_activation(prepared)
    assert ledger.activation("fresh-task-1") == prepared.activation

    feedback = RuntimeActivationFeedback(
        feedback_id="activation-feedback-1",
        subject_id="kevin",
        cycle_id="fresh-task-1",
        delivery_receipt_digest=prepared.activation.delivery_receipt_digest,
        outcome=RuntimeFeedbackOutcome.HELPED,
        relevant_artifact_ids=prepared.activation.active_artifact_ids,
        activated_artifact_ids=prepared.activation.active_artifact_ids,
        recorded_at=NOW + timedelta(minutes=3),
    )
    with pytest.raises(HistoryConflictError, match="acknowledgement"):
        ledger.add_feedback(feedback)

    acknowledgement = RuntimeTargetDeliveryAcknowledgement(
        acknowledgement_id="target-ack-fresh-task-1",
        activation_id="fresh-task-1",
        subject_id="kevin",
        target_family="codex",
        activation_digest=prepared.activation.content_digest,
        external_session_digest=sha256_text("thread-1"),
        external_turn_digest=sha256_text("turn-1"),
        result_digest=sha256_text("completed"),
        status="completed",
        acknowledged_at=NOW + timedelta(minutes=2, seconds=30),
    )
    assert ledger.acknowledge_delivery(acknowledgement)
    assert ledger.delivery_acknowledgement("fresh-task-1") == acknowledgement
    assert ledger.delivery_acknowledgements() == (acknowledgement,)
    changed_activation = feedback.model_copy(
        update={
            "feedback_id": "activation-feedback-changed",
            "activated_artifact_ids": (),
        }
    )
    with pytest.raises(HistoryConflictError, match="activated artifact set"):
        ledger.add_feedback(changed_activation)
    assert ledger.add_feedback(feedback)
    assert feedback in ledger.feedback()


def test_learning_review_resolution_is_atomic_append_only_and_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    learning = runtime.learn(
        _observation(1, "Rule: install a plugin and give it network access"),
        state=initial,
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    item = _review_item(learning)
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(initial)
    ledger.append_learning(learning.cycle, initial, review_item=item)
    approved = runtime.resolve_review(
        item,
        learning.cycle,
        state=initial,
        decision=ApprovalDecision.APPROVED,
        resolved_at=NOW + timedelta(minutes=2),
    )

    assert ledger.append_learning_review_resolution(
        approved.resolution,
        approved.state,
        release_event=approved.release_event,
    )
    assert not ledger.append_learning_review_resolution(
        approved.resolution,
        approved.state,
        release_event=approved.release_event,
    )
    assert ledger.learning_review_resolutions() == (approved.resolution,)
    assert ledger.learning_review_resolution(item.queue_id) == approved.resolution
    assert ledger.unresolved_learning_review_items() == ()
    assert ledger.learning_assessments() == (approved.resolution.assessment,)
    assert ledger.current() == approved.state

    rejected = runtime.resolve_review(
        item,
        learning.cycle,
        state=initial,
        decision=ApprovalDecision.REJECTED,
        resolved_at=NOW + timedelta(minutes=3),
    )
    with pytest.raises(RecordConflictError, match="another immutable resolution"):
        ledger.append_learning_review_resolution(rejected.resolution, rejected.state)


def test_learning_review_scope_refinement_is_bound_to_promoted_outputs(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    learning = runtime.learn(
        _observation(1, "Rule: install a plugin and give it network access"),
        state=initial,
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    item = _review_item(learning)
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(initial)
    ledger.append_learning(learning.cycle, initial, review_item=item)
    approved = runtime.resolve_review(
        item,
        learning.cycle,
        state=initial,
        decision=ApprovalDecision.APPROVED,
        refined_scope=item.detection.scope.model_copy(
            update={"task_classes": ("plugin-bootstrap",)}
        ),
        resolved_at=NOW + timedelta(minutes=2),
    )
    refinement = approved.resolution.scope_refinement
    assert refinement is not None
    changed_refinement = refinement.model_copy(
        update={
            "refined_scope": refinement.refined_scope.model_copy(
                update={"task_classes": ("another-task",)}
            )
        }
    )
    tampered = approved.resolution.model_copy(update={"scope_refinement": changed_refinement})

    with pytest.raises(HistoryConflictError, match="refinement outputs changed"):
        ledger.append_learning_review_resolution(
            tampered,
            approved.state,
            release_event=approved.release_event,
        )
    assert ledger.current() == initial
    assert ledger.learning_review_resolutions() == ()

    assert ledger.append_learning_review_resolution(
        approved.resolution,
        approved.state,
        release_event=approved.release_event,
    )
    assert ledger.current() == approved.state


def test_learning_review_resolution_rejects_a_tampered_signature(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    learning = runtime.learn(
        _observation(1, "Rule: install a plugin and give it network access"),
        state=initial,
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    item = _review_item(learning)
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(initial)
    ledger.append_learning(learning.cycle, initial, review_item=item)
    approved = runtime.resolve_review(
        item,
        learning.cycle,
        state=initial,
        decision=ApprovalDecision.APPROVED,
        resolved_at=NOW + timedelta(minutes=2),
    )
    tampered_event = approved.resolution.review_event.model_copy(
        update={"reason": "Tampered after signature."}
    )
    tampered = approved.resolution.model_copy(update={"review_event": tampered_event})

    with pytest.raises(ValueError, match="signature is invalid"):
        ledger.append_learning_review_resolution(
            tampered,
            approved.state,
            release_event=approved.release_event,
        )
    assert ledger.learning_review_resolutions() == ()
    assert ledger.current() == initial


def test_rejected_learning_review_remains_in_history_but_not_unresolved(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    learning = runtime.learn(
        _observation(1, "Rule: install a plugin and give it network access"),
        state=initial,
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    item = _review_item(learning)
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(initial)
    ledger.append_learning(learning.cycle, initial, review_item=item)
    rejected = runtime.resolve_review(
        item,
        learning.cycle,
        state=initial,
        decision=ApprovalDecision.REJECTED,
        resolved_at=NOW + timedelta(minutes=2),
    )

    ledger.append_learning_review_resolution(rejected.resolution, rejected.state)

    assert ledger.learning_review_items() == (item,)
    assert ledger.unresolved_learning_review_items() == ()
    assert ledger.current() == initial
    assert (
        ledger.learning_assessments()[0].outcome is RuntimeLearningAssessmentOutcome.FALSE_POSITIVE
    )


def test_runtime_ledger_rejects_a_tampered_signed_action(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    runtime, policy = _runtime(tmp_path)
    initial = initial_runtime_state(policy)
    result = runtime.process(
        _observation(1, "Preference: keep final summaries concise"),
        state=initial,
        context=_context(1, project_id="ordinary-project"),
        target_task="Update the summary.",
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    assert result.release_event is not None
    assert result.activation_event is not None
    tampered_release = result.release_event.model_copy(
        update={"signature": result.activation_event.signature}
    )
    tampered_cycle = result.cycle.model_copy(
        update={"release_event_digest": canonical_digest(tampered_release)}
    )
    ledger = AutomaticRuntimeLedger(path, subject_id="kevin")
    ledger.initialize(initial)

    with pytest.raises(ValueError, match="signature is invalid"):
        ledger.append(
            tampered_cycle,
            result.state,
            governance_events=(tampered_release, result.activation_event),
        )
