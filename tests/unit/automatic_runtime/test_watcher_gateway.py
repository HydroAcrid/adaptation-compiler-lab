from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.gateway_ledger import GatewayLedger
from adaptation_compiler_lab.automatic_runtime.models import RuntimeNotice, RuntimeNoticeKind
from adaptation_compiler_lab.automatic_runtime.watcher import (
    AutomaticRuntimeWatcher,
    DurableNotificationSink,
    FileWatcherLease,
)
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class FakeToast:
    def __init__(self) -> None:
        self.summaries: list[str] = []

    def publish(self, summary: str) -> None:
        self.summaries.append(summary)


def _ledger(tmp_path: Path) -> GatewayLedger:
    path = tmp_path / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    return GatewayLedger(path, subject_id="kevin")


def test_notice_is_generic_durable_and_idempotent(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    toast = FakeToast()
    sink = DurableNotificationSink(
        ledger,
        subject_id="kevin",
        toast=toast,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    notice = RuntimeNotice(
        notice_id="review-1",
        kind=RuntimeNoticeKind.NEEDS_REVIEW,
        summary="private raw preference must not appear",
        created_at=NOW,
    )

    sink.publish(notice)
    sink.publish(notice)

    assert toast.summaries == ["Adaptation review available."]
    assert ledger.inbox()[0].public_summary == "Adaptation review available."
    assert "private raw" not in str(ledger.inbox()[0])


def test_no_signal_notice_does_not_create_inbox_entry(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    sink = DurableNotificationSink(ledger, subject_id="kevin", clock=lambda: NOW)
    sink.publish(
        RuntimeNotice(
            notice_id="ignored-1",
            kind=RuntimeNoticeKind.IGNORED,
            summary="ignored",
            created_at=NOW,
        )
    )
    assert ledger.inbox() == ()


def test_watcher_retries_with_backoff_and_releases_lease(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    attempts = 0
    sleeps: list[float] = []

    def poll() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")

    watcher = AutomaticRuntimeWatcher(
        poll=poll,
        ledger=ledger,
        lease=FileWatcherLease(tmp_path, subject_id="kevin"),
        state_root=tmp_path,
        idle_seconds=1,
        maximum_backoff_seconds=4,
        sleeper=sleeps.append,
        clock=lambda: NOW,
    )
    watcher.run(maximum_polls=2)

    assert attempts == 2
    assert len(sleeps) == 1
    assert not (tmp_path / "watcher-lease.json").exists()
