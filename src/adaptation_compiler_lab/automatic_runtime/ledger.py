"""Append-only SQLite persistence for automatic-runtime states and cycle receipts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeState,
    AutomationDisposition,
    PreparedRuntimeActivation,
    RuntimeActivationFeedback,
    RuntimeCycleReceipt,
    RuntimeLearningAssessment,
    RuntimeLearningCycleReceipt,
    RuntimeReviewQueueItem,
    RuntimeSourceCheckpoint,
    RuntimeTargetDeliveryAcknowledgement,
    RuntimeTaskActivationReceipt,
)
from adaptation_compiler_lab.governance import GovernanceEvent
from adaptation_compiler_lab.governance.signing import verify_signed_governance
from adaptation_compiler_lab.persistence.errors import (
    HistoryConflictError,
    RecordConflictError,
)
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

    def append_learning(
        self,
        cycle: RuntimeLearningCycleReceipt,
        state: AutomaticRuntimeState,
        *,
        review_item: RuntimeReviewQueueItem | None = None,
        release_event: GovernanceEvent | None = None,
    ) -> bool:
        """Atomically append learning without claiming that a target task was delivered."""

        self._validate_state_subject(state)
        if cycle.subject_id != self._subject_id:
            raise ValueError("runtime learning cycle crossed the ledger subject boundary")
        if cycle.resulting_state_digest != state.content_digest:
            raise ValueError("learning cycle does not bind the supplied resulting state")
        self._validate_learning_review_item(cycle, review_item)
        self._validate_learning_event(cycle, state, release_event)
        payload = canonical_json(cycle)
        digest = str(cycle.content_digest).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_cycles
                WHERE cycle_id = ?
                """,
                (cycle.cycle_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (payload, digest):
                    connection.rollback()
                    return False
                connection.rollback()
                raise RecordConflictError(
                    "runtime learning cycle ID names different immutable content"
                )
            current_row = self._current_row(connection)
            if current_row is None:
                connection.rollback()
                raise HistoryConflictError("automatic runtime ledger is not initialized")
            current = self._decode_state(current_row[0], current_row[1])
            if cycle.prior_state_digest != current.content_digest:
                connection.rollback()
                raise HistoryConflictError("automatic runtime learning state head changed")
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
                raise HistoryConflictError("unchanged learning cycle supplied a different state")
            connection.execute(
                """
                INSERT INTO automatic_runtime_learning_cycles (
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
                    payload,
                    digest,
                ),
            )
            if review_item is not None:
                self._insert_learning_review_item(connection, review_item)
            if release_event is not None:
                self._insert_learning_event(connection, cycle.cycle_id, release_event)
            connection.commit()
        return True

    def append_activation(self, prepared: PreparedRuntimeActivation) -> bool:
        """Append one signed next-task activation before an external launch is attempted."""

        activation = prepared.activation
        event = prepared.activation_event
        if activation.subject_id != self._subject_id:
            raise ValueError("runtime activation crossed the ledger subject boundary")
        payload = canonical_json(activation)
        digest = str(activation.content_digest).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_task_activations
                WHERE activation_id = ?
                """,
                (activation.activation_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (payload, digest):
                    connection.rollback()
                    return False
                connection.rollback()
                raise RecordConflictError("runtime activation ID names different immutable content")
            state_row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_states
                WHERE subject_id = ? AND state_digest = ?
                """,
                (self._subject_id, str(activation.state_digest).removeprefix("sha256:")),
            ).fetchone()
            if state_row is None:
                connection.rollback()
                raise HistoryConflictError("runtime activation state is unavailable")
            state = self._decode_state(str(state_row[0]), str(state_row[1]))
            if state.release is None or not state.transitions:
                connection.rollback()
                raise HistoryConflictError("runtime activation state has no governed release")
            try:
                verify_signed_governance(
                    event,
                    state.transitions[-1].signer_identity,
                    effective_at=event.occurred_at,
                )
            except ValueError as error:
                connection.rollback()
                raise ValueError("runtime activation event signature is invalid") from error
            connection.execute(
                """
                INSERT INTO automatic_runtime_task_activations (
                    activation_id, subject_id, task_id, state_digest,
                    activated_at, canonical_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activation.activation_id,
                    activation.subject_id,
                    activation.task_ref.record_id,
                    str(activation.state_digest).removeprefix("sha256:"),
                    activation.activated_at.isoformat(),
                    payload,
                    digest,
                ),
            )
            self._insert_activation_event(connection, activation.activation_id, event)
            connection.commit()
        return True

    def commit_checkpoint(self, checkpoint: RuntimeSourceCheckpoint) -> bool:
        """Append a source cursor only after its complete page has been acknowledged."""

        if checkpoint.subject_id != self._subject_id:
            raise ValueError("runtime checkpoint crossed the ledger subject boundary")
        payload = canonical_json(checkpoint)
        digest = str(checkpoint.content_digest).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_source_checkpoints
                WHERE checkpoint_id = ?
                """,
                (checkpoint.checkpoint_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (payload, digest):
                    connection.rollback()
                    return False
                connection.rollback()
                raise RecordConflictError("runtime checkpoint ID names different immutable content")
            prior_row = connection.execute(
                """
                SELECT canonical_json
                FROM automatic_runtime_source_checkpoints
                WHERE subject_id = ? AND source_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (self._subject_id, checkpoint.source_id),
            ).fetchone()
            if prior_row is None:
                if checkpoint.sequence != 1 or checkpoint.prior_cursor_digest is not None:
                    connection.rollback()
                    raise HistoryConflictError("first source checkpoint must start at sequence one")
            else:
                prior = RuntimeSourceCheckpoint.model_validate_json(str(prior_row[0]))
                if (
                    checkpoint.sequence != prior.sequence + 1
                    or checkpoint.prior_cursor_digest != prior.cursor_digest
                ):
                    connection.rollback()
                    raise HistoryConflictError("runtime source checkpoint head changed")
            connection.execute(
                """
                INSERT INTO automatic_runtime_source_checkpoints (
                    checkpoint_id, subject_id, source_id, sequence,
                    committed_at, canonical_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.subject_id,
                    checkpoint.source_id,
                    checkpoint.sequence,
                    checkpoint.committed_at.isoformat(),
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return True

    def acknowledge_delivery(
        self,
        acknowledgement: RuntimeTargetDeliveryAcknowledgement,
    ) -> bool:
        """Append exactly one completed/failed target result for an activation."""

        if acknowledgement.subject_id != self._subject_id:
            raise ValueError("delivery acknowledgement crossed the ledger subject boundary")
        payload = canonical_json(acknowledgement)
        digest = str(acknowledgement.content_digest).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_target_delivery_acknowledgements
                WHERE acknowledgement_id = ? OR activation_id = ?
                """,
                (acknowledgement.acknowledgement_id, acknowledgement.activation_id),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (payload, digest):
                    connection.rollback()
                    return False
                connection.rollback()
                raise RecordConflictError(
                    "runtime delivery acknowledgement conflicts with immutable history"
                )
            activation_row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_task_activations
                WHERE subject_id = ? AND activation_id = ?
                """,
                (self._subject_id, acknowledgement.activation_id),
            ).fetchone()
            if activation_row is None:
                connection.rollback()
                raise HistoryConflictError("runtime delivery activation is unavailable")
            activation = RuntimeTaskActivationReceipt.model_validate_json(activation_row[0])
            if acknowledgement.activation_digest != activation.content_digest:
                connection.rollback()
                raise HistoryConflictError(
                    "delivery acknowledgement does not bind the exact activation"
                )
            connection.execute(
                """
                INSERT INTO automatic_runtime_target_delivery_acknowledgements (
                    acknowledgement_id, subject_id, activation_id, status,
                    acknowledged_at, canonical_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    acknowledgement.acknowledgement_id,
                    acknowledgement.subject_id,
                    acknowledgement.activation_id,
                    acknowledgement.status,
                    acknowledgement.acknowledged_at.isoformat(),
                    payload,
                    digest,
                ),
            )
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

    def learning_cycle_for_observation(
        self, observation_id: str
    ) -> RuntimeLearningCycleReceipt | None:
        """Return an exact prior pickup result so a source page can be replayed safely."""

        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_cycles
                WHERE subject_id = ? AND observation_id = ?
                """,
                (self._subject_id, observation_id),
            ).fetchone()
        if row is None:
            return None
        cycle = RuntimeLearningCycleReceipt.model_validate_json(row[0])
        if canonical_json(cycle) != row[0]:
            raise ValueError("stored runtime learning cycle is not canonical")
        if str(cycle.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored runtime learning cycle digest mismatch")
        return cycle

    def learning_cycles(self) -> tuple[RuntimeLearningCycleReceipt, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_cycles
                WHERE subject_id = ?
                ORDER BY created_at, cycle_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeLearningCycleReceipt] = []
        for payload, digest in rows:
            cycle = RuntimeLearningCycleReceipt.model_validate_json(payload)
            if canonical_json(cycle) != payload:
                raise ValueError("stored runtime learning cycle is not canonical")
            if str(cycle.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored runtime learning cycle digest mismatch")
            result.append(cycle)
        return tuple(result)

    def learning_cycle(self, cycle_id: str) -> RuntimeLearningCycleReceipt | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_cycles
                WHERE subject_id = ? AND cycle_id = ?
                """,
                (self._subject_id, cycle_id),
            ).fetchone()
        if row is None:
            return None
        cycle = RuntimeLearningCycleReceipt.model_validate_json(row[0])
        if canonical_json(cycle) != row[0]:
            raise ValueError("stored runtime learning cycle is not canonical")
        if str(cycle.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored runtime learning cycle digest mismatch")
        return cycle

    def activation(self, activation_id: str) -> RuntimeTaskActivationReceipt | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_task_activations
                WHERE subject_id = ? AND activation_id = ?
                """,
                (self._subject_id, activation_id),
            ).fetchone()
        if row is None:
            return None
        activation = RuntimeTaskActivationReceipt.model_validate_json(row[0])
        if canonical_json(activation) != row[0]:
            raise ValueError("stored runtime activation is not canonical")
        if str(activation.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored runtime activation digest mismatch")
        return activation

    def activations(self) -> tuple[RuntimeTaskActivationReceipt, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_task_activations
                WHERE subject_id = ?
                ORDER BY activated_at, activation_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeTaskActivationReceipt] = []
        for payload, digest in rows:
            activation = RuntimeTaskActivationReceipt.model_validate_json(payload)
            if canonical_json(activation) != payload:
                raise ValueError("stored runtime activation is not canonical")
            if str(activation.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored runtime activation digest mismatch")
            result.append(activation)
        return tuple(result)

    def delivery_acknowledgement(
        self, activation_id: str
    ) -> RuntimeTargetDeliveryAcknowledgement | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_target_delivery_acknowledgements
                WHERE subject_id = ? AND activation_id = ?
                """,
                (self._subject_id, activation_id),
            ).fetchone()
        if row is None:
            return None
        acknowledgement = RuntimeTargetDeliveryAcknowledgement.model_validate_json(row[0])
        if canonical_json(acknowledgement) != row[0]:
            raise ValueError("stored delivery acknowledgement is not canonical")
        if str(acknowledgement.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored delivery acknowledgement digest mismatch")
        return acknowledgement

    def delivery_acknowledgements(
        self,
    ) -> tuple[RuntimeTargetDeliveryAcknowledgement, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_target_delivery_acknowledgements
                WHERE subject_id = ?
                ORDER BY acknowledged_at, acknowledgement_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeTargetDeliveryAcknowledgement] = []
        for payload, digest in rows:
            acknowledgement = RuntimeTargetDeliveryAcknowledgement.model_validate_json(payload)
            if canonical_json(acknowledgement) != payload:
                raise ValueError("stored delivery acknowledgement is not canonical")
            if str(acknowledgement.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored delivery acknowledgement digest mismatch")
            result.append(acknowledgement)
        return tuple(result)

    def current_checkpoint(self, source_id: str) -> RuntimeSourceCheckpoint | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_source_checkpoints
                WHERE subject_id = ? AND source_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (self._subject_id, source_id),
            ).fetchone()
        if row is None:
            return None
        checkpoint = RuntimeSourceCheckpoint.model_validate_json(row[0])
        if canonical_json(checkpoint) != row[0]:
            raise ValueError("stored runtime checkpoint is not canonical")
        if str(checkpoint.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored runtime checkpoint digest mismatch")
        return checkpoint

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

    def learning_review_items(self) -> tuple[RuntimeReviewQueueItem, ...]:
        """Return review work produced by post-task Codex pickup."""

        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_review_queue
                WHERE subject_id = ?
                ORDER BY created_at, queue_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeReviewQueueItem] = []
        for payload, digest in rows:
            item = RuntimeReviewQueueItem.model_validate_json(payload)
            if canonical_json(item) != payload:
                raise ValueError("stored runtime learning review is not canonical")
            if str(item.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored runtime learning review digest mismatch")
            result.append(item)
        return tuple(result)

    def learning_review_item_for_cycle(self, cycle_id: str) -> RuntimeReviewQueueItem | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_review_queue
                WHERE subject_id = ? AND cycle_id = ?
                """,
                (self._subject_id, cycle_id),
            ).fetchone()
        if row is None:
            return None
        item = RuntimeReviewQueueItem.model_validate_json(row[0])
        if canonical_json(item) != row[0]:
            raise ValueError("stored runtime learning review is not canonical")
        if str(item.content_digest).removeprefix("sha256:") != row[1]:
            raise ValueError("stored runtime learning review digest mismatch")
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

    def add_learning_assessment(self, assessment: RuntimeLearningAssessment) -> bool:
        """Append one classification bound to an exact post-task learning cycle."""

        if assessment.subject_id != self._subject_id:
            raise ValueError("runtime learning assessment crossed the subject boundary")
        payload = canonical_json(assessment)
        digest = str(assessment.content_digest).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_assessments
                WHERE assessment_id = ? OR cycle_id = ?
                """,
                (assessment.assessment_id, assessment.cycle_id),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (payload, digest):
                    connection.rollback()
                    return False
                connection.rollback()
                raise RecordConflictError(
                    "runtime learning cycle already has another immutable assessment"
                )
            cycle_row = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_cycles
                WHERE subject_id = ? AND cycle_id = ?
                """,
                (self._subject_id, assessment.cycle_id),
            ).fetchone()
            if cycle_row is None:
                connection.rollback()
                raise HistoryConflictError("runtime learning assessment cycle is unavailable")
            cycle = RuntimeLearningCycleReceipt.model_validate_json(cycle_row[0])
            if canonical_json(cycle) != cycle_row[0]:
                connection.rollback()
                raise ValueError("stored runtime learning cycle is not canonical")
            if str(cycle.content_digest).removeprefix("sha256:") != cycle_row[1]:
                connection.rollback()
                raise ValueError("stored runtime learning cycle digest mismatch")
            if assessment.cycle_digest != cycle.content_digest:
                connection.rollback()
                raise HistoryConflictError(
                    "runtime learning assessment does not bind the exact cycle"
                )
            connection.execute(
                """
                INSERT INTO automatic_runtime_learning_assessments (
                    assessment_id, subject_id, cycle_id, outcome,
                    recorded_at, canonical_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assessment.assessment_id,
                    assessment.subject_id,
                    assessment.cycle_id,
                    assessment.outcome.value,
                    assessment.recorded_at.isoformat(),
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return True

    def learning_assessments(self) -> tuple[RuntimeLearningAssessment, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_learning_assessments
                WHERE subject_id = ?
                ORDER BY recorded_at, assessment_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeLearningAssessment] = []
        for payload, digest in rows:
            assessment = RuntimeLearningAssessment.model_validate_json(payload)
            if canonical_json(assessment) != payload:
                raise ValueError("stored runtime learning assessment is not canonical")
            if str(assessment.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored runtime learning assessment digest mismatch")
            result.append(assessment)
        return tuple(result)

    def add_feedback(self, feedback: RuntimeActivationFeedback) -> bool:
        """Append feedback only when it binds an exact legacy cycle or later activation."""

        if feedback.subject_id != self._subject_id:
            raise ValueError("automatic runtime feedback crossed the ledger subject boundary")
        payload = canonical_json(feedback)
        digest = str(feedback.content_digest).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            existing_legacy = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_feedback
                WHERE feedback_id = ?
                """,
                (feedback.feedback_id,),
            ).fetchone()
            existing_activation = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_activation_feedback
                WHERE feedback_id = ?
                """,
                (feedback.feedback_id,),
            ).fetchone()
            existing = existing_legacy or existing_activation
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
            if cycle_row is not None:
                cycle = RuntimeCycleReceipt.model_validate_json(cycle_row[0])
                expected_delivery = cycle.delivery_receipt_digest
                destination = "automatic_runtime_feedback"
            else:
                activation_row = connection.execute(
                    """
                    SELECT canonical_json
                    FROM automatic_runtime_task_activations
                    WHERE activation_id = ? AND subject_id = ?
                    """,
                    (feedback.cycle_id, self._subject_id),
                ).fetchone()
                if activation_row is None:
                    raise HistoryConflictError(
                        "runtime feedback cycle or activation is unavailable"
                    )
                activation = RuntimeTaskActivationReceipt.model_validate_json(activation_row[0])
                acknowledgement_row = connection.execute(
                    """
                    SELECT canonical_json
                    FROM automatic_runtime_target_delivery_acknowledgements
                    WHERE activation_id = ? AND subject_id = ?
                    """,
                    (feedback.cycle_id, self._subject_id),
                ).fetchone()
                if acknowledgement_row is None:
                    raise HistoryConflictError(
                        "runtime activation feedback requires a delivery acknowledgement"
                    )
                acknowledgement = RuntimeTargetDeliveryAcknowledgement.model_validate_json(
                    acknowledgement_row[0]
                )
                if acknowledgement.status != "completed":
                    raise HistoryConflictError(
                        "runtime feedback cannot rate a failed target delivery"
                    )
                if feedback.activated_artifact_ids != activation.active_artifact_ids:
                    raise HistoryConflictError(
                        "runtime feedback changed the exact activated artifact set"
                    )
                expected_delivery = activation.delivery_receipt_digest
                destination = "automatic_runtime_activation_feedback"
            if expected_delivery != feedback.delivery_receipt_digest:
                raise HistoryConflictError(
                    "runtime feedback does not bind the exact delivery receipt"
                )
            if destination == "automatic_runtime_feedback":
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
            else:
                connection.execute(
                    """
                    INSERT INTO automatic_runtime_activation_feedback (
                        feedback_id, subject_id, activation_id, outcome,
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
            legacy_rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_feedback
                WHERE subject_id = ?
                ORDER BY recorded_at, feedback_id
                """,
                (self._subject_id,),
            ).fetchall()
            activation_rows = connection.execute(
                """
                SELECT canonical_json, content_sha256
                FROM automatic_runtime_activation_feedback
                WHERE subject_id = ?
                ORDER BY recorded_at, feedback_id
                """,
                (self._subject_id,),
            ).fetchall()
        result: list[RuntimeActivationFeedback] = []
        for payload, digest in (*legacy_rows, *activation_rows):
            feedback = RuntimeActivationFeedback.model_validate_json(payload)
            if canonical_json(feedback) != payload:
                raise ValueError("stored automatic runtime feedback is not canonical")
            if str(feedback.content_digest).removeprefix("sha256:") != digest:
                raise ValueError("stored automatic runtime feedback digest mismatch")
            result.append(feedback)
        return tuple(sorted(result, key=lambda item: (item.recorded_at, item.feedback_id)))

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

    def _insert_learning_review_item(
        self,
        connection: sqlite3.Connection,
        item: RuntimeReviewQueueItem,
    ) -> None:
        payload = canonical_json(item)
        digest = str(item.content_digest).removeprefix("sha256:")
        connection.execute(
            """
            INSERT INTO automatic_runtime_learning_review_queue (
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

    def _insert_learning_event(
        self,
        connection: sqlite3.Connection,
        cycle_id: str,
        event: GovernanceEvent,
    ) -> None:
        payload = canonical_json(event)
        digest = str(canonical_digest(event)).removeprefix("sha256:")
        connection.execute(
            """
            INSERT INTO automatic_runtime_learning_governance_events (
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

    def _insert_activation_event(
        self,
        connection: sqlite3.Connection,
        activation_id: str,
        event: GovernanceEvent,
    ) -> None:
        payload = canonical_json(event)
        digest = str(canonical_digest(event)).removeprefix("sha256:")
        connection.execute(
            """
            INSERT INTO automatic_runtime_activation_governance_events (
                event_id, subject_id, activation_id, event_type, occurred_at,
                canonical_json, content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.subject_id,
                activation_id,
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

    def _validate_learning_review_item(
        self,
        cycle: RuntimeLearningCycleReceipt,
        item: RuntimeReviewQueueItem | None,
    ) -> None:
        required = cycle.disposition is AutomationDisposition.REVIEW_REQUIRED
        if required != (item is not None):
            raise ValueError("review-required learning needs exactly one durable review item")
        if item is None:
            return
        if item.subject_id != self._subject_id or item.cycle_id != cycle.cycle_id:
            raise ValueError("runtime learning review crossed its cycle or subject boundary")
        if (
            cycle.detected_feedback_digest != item.detection.content_digest
            or cycle.evaluation_receipt_digest != item.evaluation.content_digest
            or cycle.observation_digest != item.captured.observation_digest
        ):
            raise ValueError("runtime learning review does not bind the exact cycle")

    def _validate_learning_event(
        self,
        cycle: RuntimeLearningCycleReceipt,
        state: AutomaticRuntimeState,
        event: GovernanceEvent | None,
    ) -> None:
        actual = None if event is None else canonical_digest(event)
        if actual != cycle.release_event_digest:
            raise ValueError("runtime release event does not bind the exact learning cycle")
        if event is None:
            return
        if event.subject_id != self._subject_id or not state.transitions:
            raise ValueError("runtime release event crossed its subject or state boundary")
        try:
            verify_signed_governance(
                event,
                state.transitions[-1].signer_identity,
                effective_at=event.occurred_at,
            )
        except ValueError as error:
            raise ValueError("runtime release event signature is invalid") from error

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
