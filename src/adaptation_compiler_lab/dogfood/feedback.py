"""Append-only activation-feedback ledger and longitudinal metrics."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from adaptation_compiler_lab.dogfood.models import (
    ActivationFeedback,
    DogfoodFeedbackOutcome,
    DogfoodMetrics,
    LongitudinalDogfoodResult,
)
from adaptation_compiler_lab.persistence.errors import RecordConflictError
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class DogfoodFeedbackLedger:
    """Persist minimal feedback immutably in the initialized local SQLite ledger."""

    def __init__(self, path: Path, *, subject_id: str) -> None:
        self._path = path
        self._subject_id = subject_id

    def add(self, feedback: ActivationFeedback) -> bool:
        if feedback.subject_id != self._subject_id:
            raise ValueError("dogfood feedback crossed the ledger subject boundary")
        payload = canonical_json(feedback)
        digest = str(canonical_digest(feedback)).removeprefix("sha256:")
        with sqlite3.connect(self._path) as connection:
            existing = connection.execute(
                "SELECT canonical_json, content_sha256 FROM dogfood_feedback WHERE feedback_id = ?",
                (feedback.feedback_id,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == (payload, digest):
                    return False
                raise RecordConflictError(
                    "dogfood feedback ID already names different immutable content"
                )
            connection.execute(
                """
                INSERT INTO dogfood_feedback (
                    feedback_id, subject_id, stage, task_id, outcome,
                    recorded_at, canonical_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.feedback_id,
                    feedback.subject_id,
                    feedback.stage,
                    feedback.task_id,
                    feedback.outcome.value,
                    feedback.recorded_at.isoformat(),
                    payload,
                    digest,
                ),
            )
            connection.commit()
        return True

    def list(self) -> tuple[ActivationFeedback, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                "SELECT canonical_json, content_sha256 FROM dogfood_feedback "
                "WHERE subject_id = ? ORDER BY recorded_at, feedback_id",
                (self._subject_id,),
            ).fetchall()
        result: list[ActivationFeedback] = []
        for payload, digest in rows:
            feedback = ActivationFeedback.model_validate_json(payload)
            if canonical_json(feedback) != payload:
                raise ValueError("stored dogfood feedback is not canonical")
            if str(canonical_digest(feedback)).removeprefix("sha256:") != digest:
                raise ValueError("stored dogfood feedback digest mismatch")
            result.append(feedback)
        return tuple(result)


def summarize_feedback(
    feedback: tuple[ActivationFeedback, ...],
    dogfood: LongitudinalDogfoodResult,
) -> DogfoodMetrics:
    """Calculate activation, correction, size, latency, and maintenance measures."""

    pack_by_stage = {
        snapshot.stage: snapshot.rendered_pack.pack_digest for snapshot in dogfood.stages
    }
    seen_feedback_ids: set[str] = set()
    correction_counts: dict[str, int] = {}
    helped = hurt = irrelevant = 0
    correct = false = missed = 0
    for item in feedback:
        if item.feedback_id in seen_feedback_ids:
            raise ValueError("duplicate dogfood feedback ID")
        seen_feedback_ids.add(item.feedback_id)
        if item.pack_digest != pack_by_stage[item.stage]:
            raise ValueError("feedback does not bind the exact stage pack")
        helped += item.outcome is DogfoodFeedbackOutcome.HELPED
        hurt += item.outcome is DogfoodFeedbackOutcome.HURT
        irrelevant += item.outcome is DogfoodFeedbackOutcome.IRRELEVANT
        relevant = set(item.relevant_instruction_ids)
        activated = set(item.activated_instruction_ids)
        if activated == relevant:
            correct += 1
        if activated - relevant:
            false += 1
        if relevant - activated:
            missed += 1
        if item.correction_key is not None:
            correction_counts[item.correction_key] = (
                correction_counts.get(item.correction_key, 0) + 1
            )
    repeated = sum(max(0, count - 1) for count in correction_counts.values())
    measurements = tuple(stage.measurement for stage in dogfood.stages)
    return DogfoodMetrics(
        feedback_count=len(feedback),
        helped_count=helped,
        hurt_count=hurt,
        irrelevant_count=irrelevant,
        repeated_correction_count=repeated,
        correct_activation_count=correct,
        false_activation_count=false,
        missed_activation_count=missed,
        stage_pack_bytes=tuple(item.target_visible_bytes for item in measurements),  # type: ignore[arg-type]
        stage_update_latency_seconds=tuple(item.update_latency_seconds for item in measurements),  # type: ignore[arg-type]
        total_maintenance_seconds=sum(item.maintenance_seconds for item in measurements),
        total_maintenance_actions=sum(item.maintenance_actions for item in measurements),
    )
