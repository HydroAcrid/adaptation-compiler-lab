"""Restart-safe orchestration ports for the automatic adaptation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeState,
    AutomationDisposition,
    InteractionObservation,
    PreparedRuntimeTask,
    RuntimeCycleReceipt,
    RuntimeNotice,
    RuntimeReviewQueueItem,
)
from adaptation_compiler_lab.automatic_runtime.service import (
    AutomaticAdaptationRuntime,
    AutomaticRuntimeError,
    AutomaticRuntimeResult,
)
from adaptation_compiler_lab.runtime import RuntimeProjectionContext
from adaptation_compiler_lab.serialization import canonical_digest


@dataclass(frozen=True, slots=True)
class RuntimeHostWorkItem:
    """Transient source item whose interaction and target text never enter the receipt ledger."""

    cursor: str
    observation: InteractionObservation
    context: RuntimeProjectionContext
    target_task: str
    processed_at: datetime

    def __post_init__(self) -> None:
        if not self.cursor.strip():
            raise ValueError("runtime host work-item cursor must not be empty")
        if not self.target_task.strip():
            raise ValueError("runtime host target task must not be empty")
        if self.processed_at.tzinfo is None or self.processed_at.utcoffset() is None:
            raise ValueError("runtime host processing time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RuntimeHostBatch:
    """One ordered, replayable page from a trusted local interaction source."""

    items: tuple[RuntimeHostWorkItem, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class RuntimeHostRunReceipt:
    """Non-sensitive summary returned only after every idempotent sink acknowledges the batch."""

    prior_cursor: str | None
    next_cursor: str | None
    item_count: int
    appended_count: int
    replayed_count: int
    delivery_count: int
    review_count: int
    notice_count: int


@runtime_checkable
class RuntimeInteractionSource(Protocol):
    """Read an ordered page and replay it until the caller persists the returned cursor."""

    def poll(self, *, after_cursor: str | None, limit: int) -> RuntimeHostBatch:
        """Return only interactions authorized for this local subject."""


@runtime_checkable
class RuntimeDeliverySink(Protocol):
    """Deliver exact task material idempotently by delivery receipt ID."""

    def deliver(self, task: PreparedRuntimeTask) -> None:
        """Accept an identical replay and reject changed content for an existing receipt ID."""


@runtime_checkable
class RuntimeReviewSink(Protocol):
    """Present raw-free review work idempotently by queue ID."""

    def enqueue(self, item: RuntimeReviewQueueItem) -> None:
        """Accept an identical replay and reject changed content for an existing queue ID."""


@runtime_checkable
class RuntimeNoticeSink(Protocol):
    """Publish small learning/undo notices idempotently by notice ID."""

    def publish(self, notice: RuntimeNotice) -> None:
        """Accept an identical replay and reject changed content for an existing notice ID."""


class AutomaticRuntimeHost:
    """Drive detection through delivery without widening the runtime's authority."""

    def __init__(
        self,
        *,
        runtime: AutomaticAdaptationRuntime,
        initial_state: AutomaticRuntimeState,
        ledger: AutomaticRuntimeLedger,
        source: RuntimeInteractionSource,
        delivery_sink: RuntimeDeliverySink,
        review_sink: RuntimeReviewSink,
        notice_sink: RuntimeNoticeSink,
    ) -> None:
        if initial_state.generation != 0:
            raise ValueError("automatic runtime host requires the exact initial state")
        self._runtime = runtime
        self._initial_state = initial_state
        self._ledger = ledger
        self._source = source
        self._delivery_sink = delivery_sink
        self._review_sink = review_sink
        self._notice_sink = notice_sink

    def run_once(
        self,
        *,
        after_cursor: str | None = None,
        limit: int = 25,
    ) -> RuntimeHostRunReceipt:
        """Process one replayable page and advance the cursor only after all sinks succeed."""

        if not 1 <= limit <= 100:
            raise ValueError("runtime host page limit must be between 1 and 100")
        self._ledger.initialize(self._initial_state)
        batch = self._source.poll(after_cursor=after_cursor, limit=limit)
        self._validate_batch(batch, after_cursor=after_cursor, limit=limit)

        appended = 0
        replayed = 0
        delivered = 0
        reviewed = 0
        noticed = 0
        for item in batch.items:
            prior = self._ledger.cycle_for_observation(item.observation.observation_id)
            if prior is None:
                result = self._process_new(item)
                appended += 1
                delivered += int(result.prepared_task is not None)
                reviewed += int(result.cycle.disposition is AutomationDisposition.REVIEW_REQUIRED)
                self._emit_new(result)
            else:
                self._replay(item, prior)
                replayed += 1
                delivered += int(prior.delivery_receipt_digest is not None)
                reviewed += int(prior.disposition is AutomationDisposition.REVIEW_REQUIRED)
            noticed += 1

        return RuntimeHostRunReceipt(
            prior_cursor=after_cursor,
            next_cursor=batch.next_cursor,
            item_count=len(batch.items),
            appended_count=appended,
            replayed_count=replayed,
            delivery_count=delivered,
            review_count=reviewed,
            notice_count=noticed,
        )

    def _process_new(self, item: RuntimeHostWorkItem) -> AutomaticRuntimeResult:
        state = self._ledger.current()
        if state is None:
            raise AutomaticRuntimeError("automatic runtime ledger failed to initialize")
        result = self._runtime.process(
            item.observation,
            state=state,
            context=item.context,
            target_task=item.target_task,
            processed_at=item.processed_at,
        )
        review_item = self._review_item(result)
        events = tuple(
            event for event in (result.release_event, result.activation_event) if event is not None
        )
        if not self._ledger.append(
            result.cycle,
            result.state,
            review_item=review_item,
            governance_events=events,
        ):
            raise AutomaticRuntimeError("new runtime observation unexpectedly already exists")
        return result

    def _emit_new(self, result: AutomaticRuntimeResult) -> None:
        if result.prepared_task is not None:
            self._delivery_sink.deliver(result.prepared_task)
        review_item = self._review_item(result)
        if review_item is not None:
            self._review_sink.enqueue(review_item)
        self._notice_sink.publish(result.cycle.notice)

    def _replay(self, item: RuntimeHostWorkItem, cycle: RuntimeCycleReceipt) -> None:
        if cycle.observation_digest != item.observation.content_digest:
            raise AutomaticRuntimeError(
                "replayed observation ID names different immutable interaction content"
            )
        if cycle.delivery_receipt_digest is not None:
            state = self._ledger.state_by_digest(cycle.resulting_state_digest)
            if state is None:
                raise AutomaticRuntimeError("replayed delivery state is unavailable")
            prepared = self._runtime.prepare_task(
                item.observation,
                state=state,
                context=item.context,
                target_task=item.target_task,
                delivered_at=cycle.created_at,
            )
            if canonical_digest(prepared.receipt) != cycle.delivery_receipt_digest:
                raise AutomaticRuntimeError("replayed target task changed after durable capture")
            self._delivery_sink.deliver(prepared)
        if cycle.disposition is AutomationDisposition.REVIEW_REQUIRED:
            review_item = self._ledger.review_item_for_cycle(cycle.cycle_id)
            if review_item is None:
                raise AutomaticRuntimeError("replayed review item is unavailable")
            self._review_sink.enqueue(review_item)
        self._notice_sink.publish(cycle.notice)

    @staticmethod
    def _review_item(result: AutomaticRuntimeResult) -> RuntimeReviewQueueItem | None:
        if result.cycle.disposition is not AutomationDisposition.REVIEW_REQUIRED:
            return None
        if result.captured is None or result.evaluation is None:
            raise AutomaticRuntimeError("review-required result lacks captured evaluation")
        return RuntimeReviewQueueItem(
            queue_id=f"review-{result.cycle.observation_id}",
            subject_id=result.cycle.subject_id,
            cycle_id=result.cycle.cycle_id,
            detection=result.detection,
            captured=result.captured,
            evaluation=result.evaluation,
            created_at=result.cycle.created_at,
        )

    @staticmethod
    def _validate_batch(
        batch: RuntimeHostBatch,
        *,
        after_cursor: str | None,
        limit: int,
    ) -> None:
        if len(batch.items) > limit:
            raise AutomaticRuntimeError("interaction source exceeded the requested page limit")
        cursors = tuple(item.cursor for item in batch.items)
        observation_ids = tuple(item.observation.observation_id for item in batch.items)
        if len(cursors) != len(set(cursors)) or len(observation_ids) != len(set(observation_ids)):
            raise AutomaticRuntimeError("interaction source returned duplicate work")
        expected_cursor = cursors[-1] if cursors else after_cursor
        if batch.next_cursor != expected_cursor:
            raise AutomaticRuntimeError("interaction source returned an incoherent cursor")
