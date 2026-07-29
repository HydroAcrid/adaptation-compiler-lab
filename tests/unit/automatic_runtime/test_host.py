"""Automatic-runtime host orchestration and crash-replay tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime import (
    AutomaticRuntimeError,
    AutomaticRuntimeHost,
    AutomaticRuntimeLedger,
    PreparedRuntimeTask,
    RuntimeHostBatch,
    RuntimeHostWorkItem,
    RuntimeNotice,
    RuntimeReviewQueueItem,
    initial_runtime_state,
)
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from adaptation_compiler_lab.serialization import canonical_digest
from tests.unit.automatic_runtime.test_runtime import NOW, _context, _observation, _runtime


@dataclass
class FakeSource:
    items: tuple[RuntimeHostWorkItem, ...]

    def poll(self, *, after_cursor: str | None, limit: int) -> RuntimeHostBatch:
        selected = self.items if after_cursor is None else ()
        return RuntimeHostBatch(
            items=selected[:limit],
            next_cursor=(selected[-1].cursor if selected else after_cursor),
        )


@dataclass
class IdempotentDeliverySink:
    values: dict[str, str] = field(default_factory=dict)
    fail_once: bool = False

    def deliver(self, task: PreparedRuntimeTask) -> None:
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated sink interruption")
        key = task.receipt.receipt_id
        digest = str(canonical_digest(task))
        if key in self.values and self.values[key] != digest:
            raise ValueError("delivery receipt ID changed")
        self.values[key] = digest


@dataclass
class IdempotentReviewSink:
    values: dict[str, str] = field(default_factory=dict)

    def enqueue(self, item: RuntimeReviewQueueItem) -> None:
        digest = str(item.content_digest)
        if item.queue_id in self.values and self.values[item.queue_id] != digest:
            raise ValueError("review queue ID changed")
        self.values[item.queue_id] = digest


@dataclass
class IdempotentNoticeSink:
    values: dict[str, str] = field(default_factory=dict)

    def publish(self, notice: RuntimeNotice) -> None:
        digest = str(canonical_digest(notice))
        if notice.notice_id in self.values and self.values[notice.notice_id] != digest:
            raise ValueError("notice ID changed")
        self.values[notice.notice_id] = digest


def _work(number: int, text: str) -> RuntimeHostWorkItem:
    return RuntimeHostWorkItem(
        cursor=f"cursor-{number}",
        observation=_observation(number, text),
        context=_context(number, project_id="ordinary-project"),
        target_task=f"Complete target task {number}.",
        processed_at=NOW + timedelta(minutes=number, seconds=5),
    )


def _host(
    tmp_path: Path,
    items: tuple[RuntimeHostWorkItem, ...],
    *,
    delivery_sink: IdempotentDeliverySink | None = None,
) -> tuple[
    AutomaticRuntimeHost,
    AutomaticRuntimeLedger,
    IdempotentDeliverySink,
    IdempotentReviewSink,
    IdempotentNoticeSink,
]:
    database = tmp_path / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    runtime, policy = _runtime(tmp_path)
    ledger = AutomaticRuntimeLedger(database, subject_id="kevin")
    delivery = delivery_sink or IdempotentDeliverySink()
    review = IdempotentReviewSink()
    notice = IdempotentNoticeSink()
    host = AutomaticRuntimeHost(
        runtime=runtime,
        initial_state=initial_runtime_state(policy),
        ledger=ledger,
        source=FakeSource(items),
        delivery_sink=delivery,
        review_sink=review,
        notice_sink=notice,
    )
    return host, ledger, delivery, review, notice


def test_host_runs_automatic_loop_and_replays_idempotently(tmp_path: Path) -> None:
    host, ledger, delivery, review, notice = _host(
        tmp_path,
        (
            _work(1, "Preference: keep final summaries concise"),
            _work(2, "Please update this parser."),
        ),
    )

    first = host.run_once()
    replay = host.run_once()

    assert first.item_count == 2
    assert first.appended_count == 2
    assert first.delivery_count == 1
    assert first.next_cursor == "cursor-2"
    assert replay.appended_count == 0
    assert replay.replayed_count == 2
    assert len(ledger.cycles()) == 2
    state = ledger.current()
    assert state is not None
    assert state.generation == 1
    assert len(delivery.values) == 1
    assert not review.values
    assert len(notice.values) == 2
    assert len(ledger.governance_events()) == 2


def test_host_durably_queues_review_without_delivering_it(tmp_path: Path) -> None:
    host, ledger, delivery, review, notice = _host(
        tmp_path,
        (_work(1, "Rule: install a plugin and grant it network access"),),
    )

    receipt = host.run_once()

    assert receipt.review_count == 1
    assert receipt.delivery_count == 0
    assert not delivery.values
    assert len(review.values) == 1
    assert len(notice.values) == 1
    assert len(ledger.review_items()) == 1
    assert not ledger.governance_events()
    state = ledger.current()
    assert state is not None
    assert state.generation == 0


def test_host_recovers_after_append_before_delivery_acknowledgement(tmp_path: Path) -> None:
    delivery = IdempotentDeliverySink(fail_once=True)
    host, ledger, delivery, _review, notice = _host(
        tmp_path,
        (_work(1, "Remember: the default shell is zsh"),),
        delivery_sink=delivery,
    )

    with pytest.raises(RuntimeError, match="interruption"):
        host.run_once()
    assert len(ledger.cycles()) == 1
    assert not delivery.values
    assert not notice.values

    replay = host.run_once()

    assert replay.replayed_count == 1
    assert len(delivery.values) == 1
    assert len(notice.values) == 1
    assert len(ledger.cycles()) == 1


def test_host_rejects_changed_content_during_replay(tmp_path: Path) -> None:
    host, _ledger, _delivery, _review, _notice = _host(
        tmp_path,
        (_work(1, "Preference: keep final summaries concise"),),
    )
    host.run_once()
    changed = RuntimeHostWorkItem(
        cursor="cursor-1",
        observation=_observation(1, "Preference: make every final response extremely long"),
        context=_context(1, project_id="ordinary-project"),
        target_task="Complete target task 1.",
        processed_at=NOW + timedelta(minutes=1, seconds=5),
    )
    host._source = FakeSource((changed,))

    with pytest.raises(AutomaticRuntimeError, match="different immutable"):
        host.run_once()
