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
    initial_runtime_state,
    summarize_runtime,
)
from adaptation_compiler_lab.governance import GovernanceEvent
from adaptation_compiler_lab.persistence.errors import HistoryConflictError
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.serialization import canonical_digest
from tests.unit.automatic_runtime.test_runtime import NOW, _context, _observation, _runtime


def _events(result: AutomaticRuntimeResult) -> tuple[GovernanceEvent, ...]:
    return tuple(
        event for event in (result.release_event, result.activation_event) if event is not None
    )


def test_runtime_ledger_is_append_only_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    assert SqliteUnitOfWorkFactory(path).initialize() == 7
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
