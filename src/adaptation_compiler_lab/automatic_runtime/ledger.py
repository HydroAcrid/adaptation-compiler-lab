"""Append-only SQLite persistence for automatic-runtime states and cycle receipts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeState,
    AutomationDisposition,
    RuntimeActivationFeedback,
    RuntimeCycleReceipt,
    RuntimeReviewQueueItem,
)
from adaptation_compiler_lab.governance import GovernanceEvent
from adaptation_compiler_lab.governance.signing import verify_signed_governance
from adaptation_compiler_lab.persistence.errors import HistoryConflictError, RecordConflictError
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class AutomaticRuntimeLedger:
    """Persist raw-free state snapshots with compare-and-swap cycle sequencing."""

    def __init__(self, path: Path, *, subject_id: str) -> None:
        if not subject_id:
            raise ValueError("automatic runtime ledger requires a subject")
        self._path = path
        self._subject_id = subject_id

    def initialize(self, state: AutomaticRuntimeState) -> bool:
        """Store generation zero once, or verify the existing exact initial state."""

        self._validate_state_subject(state)
        if state.generation != 0:
            raise ValueError("automatic runtime initialization requires generation zero")
        with sqlite3.connect(self._path) as connection:
            initial = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_states
                WHERE subject_id = ? AND generation = 0
                """,
                (self._subject_id,),
            ).fetchone()
            if initial is not None:
                existing = self._decode_state(str(initial[0]), str(initial[1]))
                if existing == state:
                    return False
                raise HistoryConflictError("automatic runtime already has another initial state")
            if self._current_row(connection) is not None:
                raise HistoryConflictError("automatic runtime initial state is unavailable")
            self._insert_state(connection, state)
            connection.commit()
        return True

    def append(
        self,
        cycle: RuntimeCycleReceipt,
        state: AutomaticRuntimeState,
        *,
        review_item: RuntimeReviewQueueItem | None = None,
        governance_events: tuple[GovernanceEvent, ...] = (),
    ) -> bool:
        """Atomically append one cycle and its changed state after an exact head comparison."""

        self._validate_state_subject(state)
        if cycle.subject_id != self._subject_id:
            raise ValueError("automatic runtime cycle crossed the ledger subject boundary")
        if cycle.resulting_state_digest != state.content_digest:
            raise ValueError("cycle does not bind the supplied resulting state")
        self._validate_review_item(cycle, review_item)
        self._validate_governance_events(cycle, state, governance_events)
        cycle_json = canonical_json(cycle)
        cycle_digest = str(canonical_digest(cycle)).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_cycles
                WHERE cycle_id = ?
                """,
                (cycle.cycle_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (cycle_json, cycle_digest):
                    connection.rollback()
                    return False
                connection.rollback()
                raise RecordConflictError(
                    "automatic runtime cycle ID names different immutable content"
                )
            current_row = self._current_row(connection)
            if current_row is None:
                connection.rollback()
                raise HistoryConflictError("automatic runtime ledger is not initialized")
            current = self._decode_state(current_row[0], current_row[1])
            if cycle.prior_state_digest != current.content_digest:
                connection.rollback()
                raise HistoryConflictError("automatic runtime state head changed")
            changed = cycle.resulting_state_digest != cycle.prior_state_digest
            if changed:
                if state.generation != current.generation + 1:
                    connection.rollback()
                    raise HistoryConflictError(
                        "changed runtime state must advance exactly one generation"
                    )
                self._insert_state(connection, state)
            elif state != current:
                connection.rollback()
                raise HistoryConflictError("unchanged cycle supplied a different state")
            connection.execute(
                """
                INSERT INTO automatic_runtime_cycles (
                    cycle_id, subject_id, observation_id, disposition,
                    prior_state_digest, resulting_state_digest, created_at,
                    canonical_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle.cycle_id,
                    cycle.subject_id,
                    cycle.observation_id,
                    cycle.disposition.value,
                    str(cycle.prior_state_digest).removeprefix("sha256:"),
                    str(cycle.resulting_state_digest).removeprefix("sha256:"),
                    cycle.created_at.isoformat(),
                    cycle_json,
                    cycle_digest,
                ),
            )
            if review_item is not None:
                self._insert_review_item(connection, review_item)
            for event in governance_events:
                self._insert_governance_event(connection, cycle.cycle_id, event)
            connection.commit()
        return True

    def current(self) -> AutomaticRuntimeState | None:
        with sqlite3.connect(self._path) as connection:
            row = self._current_row(connection)
        return None if row is None else self._decode_state(row[0], row[1])

    def cycles(self) -> tuple[RuntimeCycleReceipt, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_cycles
                WHERE subject_id = ?
                ORDER BY created_at, cycle_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeCycleReceipt] = []
        for payload, digest in rows:
            cycle = RuntimeCycleReceipt.model_validate_json(payload)
            if canonical_json(cycle) != payload:
                raise ValueError("stored automatic runtime cycle is not canonical")
            if str(canonical_digest(cycle)).removeprefix("sha256:") != digest:
                raise ValueError("stored automatic runtime cycle digest mismatch")
            result.append(cycle)
        return tuple(result)

    def cycle_for_observation(self, observation_id: str) -> RuntimeCycleReceipt | None:
        """Return the exact prior result used to replay an interrupted host delivery."""

        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_cycles
                WHERE subject_id = ? AND observation_id = ?
                """,
                (self._subject_id, observation_id),
            ).fetchone()
        if row is None:
            return None
        cycle = RuntimeCycleReceipt.model_validate_json(row[0])
        if canonical_json(cycle) != row[0]:
            raise ValueError("stored automatic runtime cycle is not canonical")
        if str(cycle.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored automatic runtime cycle digest mismatch")
        return cycle

    def state_by_digest(self, digest: str) -> AutomaticRuntimeState | None:
        """Load an immutable historical state by its canonical digest."""

        normalized = digest.removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_states
                WHERE state_digest = ? AND subject_id = ?
                """,
                (normalized, self._subject_id),
            ).fetchone()
        return None if row is None else self._decode_state(str(row[0]), str(row[1]))

    def review_items(self) -> tuple[RuntimeReviewQueueItem, ...]:
        """Return durable raw-free review work in append order."""

        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_review_queue
                WHERE subject_id = ?
                ORDER BY created_at, queue_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeReviewQueueItem] = []
        for payload, digest in rows:
            item = RuntimeReviewQueueItem.model_validate_json(payload)
            if canonical_json(item) != payload:
                raise ValueError("stored automatic runtime review item is not canonical")
            if str(item.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored automatic runtime review item digest mismatch")
            result.append(item)
        return tuple(result)

    def review_item_for_cycle(self, cycle_id: str) -> RuntimeReviewQueueItem | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_review_queue
                WHERE subject_id = ? AND cycle_id = ?
                """,
                (self._subject_id, cycle_id),
            ).fetchone()
        if row is None:
            return None
        item = RuntimeReviewQueueItem.model_validate_json(row[0])
        if canonical_json(item) != row[0]:
            raise ValueError("stored automatic runtime review item is not canonical")
        if str(item.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored automatic runtime review item digest mismatch")
        return item

    def governance_events(self) -> tuple[GovernanceEvent, ...]:
        """Return signed release and activation actions in append order."""

        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_governance_events
                WHERE subject_id = ?
                ORDER BY occurred_at, event_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[GovernanceEvent] = []
        for payload, digest in rows:
            event = GovernanceEvent.model_validate_json(payload)
            if canonical_json(event) != payload:
                raise ValueError("stored automatic runtime governance event is not canonical")
            if str(canonical_digest(event)).removeprefix("sha256:") != digest:
                raise ValueError("stored automatic runtime governance event digest mismatch")
            result.append(event)
        return tuple(result)

    def add_feedback(self, feedback: RuntimeActivationFeedback) -> bool:
        """Append feedback only when it binds an exact delivered cycle."""

        if feedback.subject_id != self._subject_id:
            raise ValueError("automatic runtime feedback crossed the ledger subject boundary")
        payload = canonical_json(feedback)
        digest = str(feedback.content_digest).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            existing = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_feedback
                WHERE feedback_id = ?
                """,
                (feedback.feedback_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (payload, digest):
                    return False
                raise RecordConflictError(
                    "automatic runtime feedback ID names different immutable content"
                )
            cycle_row = connection.execute(
                """
                SELECT canonical_json
                FROM automatic_runtime_cycles
                WHERE cycle_id = ? AND subject_id = ?
                """,
                (feedback.cycle_id, self._subject_id),
            ).fetchone()
            if cycle_row is None:
                raise HistoryConflictError("runtime feedback cycle is unavailable")
            cycle = RuntimeCycleReceipt.model_validate_json(cycle_row[0])
            if cycle.delivery_receipt_digest != feedback.delivery_receipt_digest:
                raise HistoryConflictError(
                    "runtime feedback does not bind the exact delivery receipt"
                )
            connection.execute(
                """
                INSERT INTO automatic_runtime_feedback (
                    feedback_id, subject_id, cycle_id, outcome,
                    recorded_at, canonical_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.feedback_id,
                    feedback.subject_id,
                    feedback.cycle_id,
                    feedback.outcome.value,
                    feedback.recorded_at.isoformat(),
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return True

    def feedback(self) -> tuple[RuntimeActivationFeedback, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_feedback
                WHERE subject_id = ?
                ORDER BY recorded_at, feedback_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeActivationFeedback] = []
        for payload, digest in rows:
            feedback = RuntimeActivationFeedback.model_validate_json(payload)
            if canonical_json(feedback) != payload:
                raise ValueError("stored automatic runtime feedback is not canonical")
            if str(feedback.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored automatic runtime feedback digest mismatch")
            result.append(feedback)
        return tuple(result)

    def _insert_state(
        self,
        connection: sqlite3.Connection,
        state: AutomaticRuntimeState,
    ) -> None:
        payload = canonical_json(state)
        digest = str(state.content_digest).removeprefix("sha256:")
        connection.execute(
            """
            INSERT INTO automatic_runtime_states (
                state_digest, subject_id, generation, created_at,
                canonical_json, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                digest,
                state.subject_id,
                state.generation,
                (
                    state.transitions[-1].activated_at.isoformat()
                    if state.transitions
                    else state.release.governed_release.lifecycle_history[
                        -1
                    ].activated_at.isoformat()
                    if state.release is not None
                    else "1970-01-01T00:00:00+00:00"
                ),
                payload,
                digest,
            ),
        )

    def _insert_review_item(
        self,
        connection: sqlite3.Connection,
        item: RuntimeReviewQueueItem,
    ) -> None:
        payload = canonical_json(item)
        digest = str(item.content_digest).removeprefix("sha256:")
        connection.execute(
            """
            INSERT INTO automatic_runtime_review_queue (
                queue_id, subject_id, cycle_id, created_at, canonical_json, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.queue_id,
                item.subject_id,
                item.cycle_id,
                item.created_at.isoformat(),
                payload,
                digest,
            ),
        )

    def _insert_governance_event(
        self,
        connection: sqlite3.Connection,
        cycle_id: str,
        event: GovernanceEvent,
    ) -> None:
        payload = canonical_json(event)
        digest = str(canonical_digest(event)).removeprefix("sha256:")
        connection.execute(
            """
            INSERT INTO automatic_runtime_governance_events (
                event_id, subject_id, cycle_id, event_type, occurred_at,
                canonical_json, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.subject_id,
                cycle_id,
                event.event_type.value,
                event.occurred_at.isoformat(),
                payload,
                digest,
            ),
        )

    def _current_row(self, connection: sqlite3.Connection) -> tuple[str, str] | None:
        row = connection.execute(
            """
            SELECT canonical_json, content_sha256
            FROM automatic_runtime_states
            WHERE subject_id = ?
            ORDER BY generation DESC
            LIMIT 1
            """,
            (self._subject_id,),
        ).fetchone()
        return None if row is None else (str(row[0]), str(row[1]))

    def _decode_state(self, payload: str, digest: str) -> AutomaticRuntimeState:
        state = AutomaticRuntimeState.model_validate_json(payload)
        self._validate_state_subject(state)
        if canonical_json(state) != payload:
            raise ValueError("stored automatic runtime state is not canonical")
        if str(state.content_digest).removeprefix("sha256:") != digest:
            raise ValueError("stored automatic runtime state digest mismatch")
        return state

    def _validate_state_subject(self, state: AutomaticRuntimeState) -> None:
        if state.subject_id != self._subject_id:
            raise ValueError("automatic runtime state crossed the ledger subject boundary")

    def _validate_review_item(
        self,
        cycle: RuntimeCycleReceipt,
        item: RuntimeReviewQueueItem | None,
    ) -> None:
        required = cycle.disposition is AutomationDisposition.REVIEW_REQUIRED
        if required != (item is not None):
            raise ValueError("review-required cycles need exactly one durable review item")
        if item is None:
            return
        if item.subject_id != self._subject_id or item.cycle_id != cycle.cycle_id:
            raise ValueError("runtime review item crossed its cycle or subject boundary")
        if (
            cycle.detected_feedback_digest != item.detection.content_digest
            or cycle.evaluation_receipt_digest != item.evaluation.content_digest
            or cycle.observation_digest != item.captured.observation_digest
        ):
            raise ValueError("runtime review item does not bind the exact cycle")

    def _validate_governance_events(
        self,
        cycle: RuntimeCycleReceipt,
        state: AutomaticRuntimeState,
        events: tuple[GovernanceEvent, ...],
    ) -> None:
        expected = tuple(
            digest
            for digest in (cycle.release_event_digest, cycle.activation_event_digest)
            if digest is not None
        )
        actual = tuple(canonical_digest(event) for event in events)
        if actual != expected:
            raise ValueError("runtime governance events do not bind the exact cycle")
        if any(event.subject_id != self._subject_id for event in events):
            raise ValueError("runtime governance event crossed the ledger subject boundary")
        if events:
            if not state.transitions:
                raise ValueError("runtime governance events require one signed transition")
            identity = state.transitions[-1].signer_identity
            try:
                for event in events:
                    verify_signed_governance(
                        event,
                        identity,
                        effective_at=event.occurred_at,
                    )
            except ValueError as error:
                raise ValueError("runtime governance event signature is invalid") from error
