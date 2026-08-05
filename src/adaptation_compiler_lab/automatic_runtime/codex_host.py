"""Restart-safe coordination for post-task Codex learning pickup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodInteractionSource,
)
from adaptation_compiler_lab.automatic_runtime.host import (
    RuntimeNoticeSink,
    RuntimeReviewSink,
)
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeState,
    AutomationDisposition,
    FeedbackDetectorMode,
    InteractionObservation,
    RuntimeLearningCycleReceipt,
    RuntimeReviewQueueItem,
    RuntimeSourceCheckpoint,
    SemanticFeedbackInterpretation,
)
from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    SemanticFeedbackInterpreter,
)
from adaptation_compiler_lab.automatic_runtime.service import (
    AutomaticAdaptationRuntime,
    AutomaticLearningResult,
    AutomaticRuntimeError,
)
from adaptation_compiler_lab.targets.base import sha256_text


@dataclass(frozen=True, slots=True)
class CodexDogfoodPickupReceipt:
    """Non-sensitive page summary returned after the durable cursor commits."""

    prior_cursor_digest: str | None
    next_cursor_digest: str
    item_count: int
    appended_count: int
    replayed_count: int
    review_count: int
    notice_count: int
    checkpoint_advanced: bool


class CodexDogfoodHost:
    """Learn from completed Codex messages without coupling release to delivery."""

    def __init__(
        self,
        *,
        runtime: AutomaticAdaptationRuntime,
        initial_state: AutomaticRuntimeState,
        ledger: AutomaticRuntimeLedger,
        source: CodexDogfoodInteractionSource,
        review_sink: RuntimeReviewSink,
        notice_sink: RuntimeNoticeSink,
        detector_mode: FeedbackDetectorMode = FeedbackDetectorMode.GRAMMAR,
        semantic_interpreter: SemanticFeedbackInterpreter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if initial_state.generation != 0:
            raise ValueError("Codex dogfood host requires the exact initial state")
        self._runtime = runtime
        self._initial_state = initial_state
        self._ledger = ledger
        self._source = source
        self._review_sink = review_sink
        self._notice_sink = notice_sink
        if (detector_mode is FeedbackDetectorMode.GRAMMAR) != (semantic_interpreter is None):
            raise ValueError(
                "semantic interpreter is required exactly when detector mode is semantic"
            )
        self._detector_mode = detector_mode
        self._semantic_interpreter = semantic_interpreter
        self._clock = clock or (lambda: datetime.now(UTC))

    def run_once(self, *, limit: int = 25) -> CodexDogfoodPickupReceipt:
        """Process one source page and commit its cursor only after sinks acknowledge."""

        self._ledger.initialize(self._initial_state)
        checkpoint = self._ledger.current_checkpoint(self._source.source_id)
        prior_cursor = None if checkpoint is None else checkpoint.cursor_value
        batch = self._source.poll(after_cursor=prior_cursor, limit=limit)
        priors = {
            item.observation.observation_id: self._ledger.learning_cycle_for_observation(
                item.observation.observation_id
            )
            for item in batch.items
        }
        new_observations = tuple(
            item.observation
            for item in batch.items
            if priors[item.observation.observation_id] is None
        )
        interpretations: dict[str, SemanticFeedbackInterpretation] = {}
        if self._semantic_interpreter is not None and new_observations:
            interpretations = dict(self._semantic_interpreter.interpret_batch(new_observations))
            expected = tuple(item.observation_id for item in new_observations)
            if tuple(interpretations) != expected:
                raise AutomaticRuntimeError(
                    "semantic interpreter returned an incomplete or reordered batch"
                )
        appended = 0
        replayed = 0
        reviews = 0
        notices = 0

        for item in batch.items:
            observation = item.observation
            prior = priors[observation.observation_id]
            if prior is None:
                result = self._learn_new(
                    observation=observation,
                    processed_at=item.processed_at,
                    semantic_interpretation=interpretations.get(observation.observation_id),
                )
                appended += 1
                review_item = self._review_item(result)
                if review_item is not None:
                    self._review_sink.enqueue(review_item)
                    reviews += 1
                self._notice_sink.publish(result.cycle.notice)
            else:
                review_item = None
                if prior.disposition is AutomationDisposition.REVIEW_REQUIRED:
                    review_item = self._ledger.learning_review_item_for_cycle(prior.cycle_id)
                    if review_item is None:
                        raise AutomaticRuntimeError("replayed Codex review item is unavailable")
                if (
                    prior.observation_digest != observation.content_digest
                    and review_item is not None
                ):
                    observation = self._normalize_legacy_review_replay(
                        observation=observation,
                        prior=prior,
                        review_item=review_item,
                    )
                if prior.observation_digest != observation.content_digest:
                    raise AutomaticRuntimeError(
                        "replayed Codex observation changed after durable pickup"
                    )
                if review_item is not None:
                    self._review_sink.enqueue(review_item)
                    reviews += 1
                self._notice_sink.publish(prior.notice)
                replayed += 1
            notices += 1

        next_value = batch.cursor.value
        prior_digest = None if checkpoint is None else str(checkpoint.cursor_digest)
        next_digest = str(sha256_text(next_value))
        advanced = prior_cursor != next_value
        if advanced:
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise AutomaticRuntimeError("Codex host checkpoint clock must be timezone-aware")
            sequence = 1 if checkpoint is None else checkpoint.sequence + 1
            committed = self._ledger.commit_checkpoint(
                RuntimeSourceCheckpoint(
                    checkpoint_id=f"codex-checkpoint-{sequence}",
                    subject_id=self._initial_state.subject_id,
                    source_id=self._source.source_id,
                    sequence=sequence,
                    prior_cursor_digest=(None if checkpoint is None else checkpoint.cursor_digest),
                    cursor_digest=sha256_text(next_value),
                    cursor_value=next_value,
                    committed_at=now,
                )
            )
            if not committed:
                raise AutomaticRuntimeError("new Codex checkpoint unexpectedly already exists")

        return CodexDogfoodPickupReceipt(
            prior_cursor_digest=prior_digest,
            next_cursor_digest=next_digest,
            item_count=len(batch.items),
            appended_count=appended,
            replayed_count=replayed,
            review_count=reviews,
            notice_count=notices,
            checkpoint_advanced=advanced,
        )

    def _learn_new(
        self,
        *,
        observation: InteractionObservation,
        processed_at: datetime,
        semantic_interpretation: SemanticFeedbackInterpretation | None,
    ) -> AutomaticLearningResult:
        state = self._ledger.current()
        if state is None:
            raise AutomaticRuntimeError("Codex dogfood ledger failed to initialize")
        result = self._runtime.learn(
            observation,
            state=state,
            processed_at=processed_at,
            detector_mode=self._detector_mode,
            semantic_interpretation=semantic_interpretation,
        )
        review_item = self._review_item(result)
        if not self._ledger.append_learning(
            result.cycle,
            result.state,
            review_item=review_item,
            release_event=result.release_event,
        ):
            raise AutomaticRuntimeError("new Codex observation unexpectedly already exists")
        return result

    @staticmethod
    def _normalize_legacy_review_replay(
        *,
        observation: InteractionObservation,
        prior: RuntimeLearningCycleReceipt,
        review_item: RuntimeReviewQueueItem,
    ) -> InteractionObservation:
        """Recover an interrupted review written before source timestamps were stable.

        The former pickup implementation used its poll time as ``observed_at``. Recovery is
        limited to an incomplete review whose signed capture proves that legacy shape, and every
        source/content binding must still match before only that timestamp is reconstructed.
        """

        captured = review_item.captured
        evidence = captured.evidence
        capture = captured.capture
        payload = evidence.payload
        legacy_time = evidence.observed_at
        legacy_shape = (
            capture.captured_at == legacy_time
            and captured.consent.issued_at == legacy_time
            and prior.created_at == legacy_time
        )
        payload_digest = sha256_text(observation.text)
        source_matches = (
            observation.observation_id == prior.observation_id
            and observation.subject_id == review_item.subject_id
            and evidence.task_ref == observation.task_ref
            and evidence.producer == observation.actor
            and evidence.source_class == observation.source_class
            and evidence.scope == observation.scope
            and capture.subject_id == observation.subject_id
            and capture.source_selector.source_system == observation.source_system
            and capture.source_selector.source_ids == (observation.task_ref.record_id,)
            and capture.source_version == observation.source_version
            and capture.source_schema_digest == observation.source_schema_digest
            and payload is not None
            and payload.content_digest == payload_digest
            and capture.payload_digest == payload_digest
        )
        if not legacy_shape or not source_matches:
            return observation
        restored = observation.model_copy(update={"observed_at": legacy_time})
        if restored.content_digest != prior.observation_digest:
            return observation
        return restored

    @staticmethod
    def _review_item(result: AutomaticLearningResult) -> RuntimeReviewQueueItem | None:
        if result.cycle.disposition is not AutomationDisposition.REVIEW_REQUIRED:
            return None
        if result.captured is None or result.evaluation is None:
            raise AutomaticRuntimeError("review-required learning lacks captured evaluation")
        return RuntimeReviewQueueItem(
            queue_id=f"learning-review-{result.cycle.observation_id}",
            subject_id=result.cycle.subject_id,
            cycle_id=result.cycle.cycle_id,
            detection=result.detection,
            captured=result.captured,
            evaluation=result.evaluation,
            created_at=result.cycle.created_at,
        )
