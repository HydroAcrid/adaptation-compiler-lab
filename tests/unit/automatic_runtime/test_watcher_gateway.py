from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.gateway_ledger import GatewayLedger
from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    ChangeApplicationReceipt,
    ChangeApplicationStatus,
    GatewaySession,
    GatewaySessionStatus,
    VerificationReceipt,
)
from adaptation_compiler_lab.automatic_runtime.models import RuntimeNotice, RuntimeNoticeKind
from adaptation_compiler_lab.automatic_runtime.watcher import (
    AutomaticRuntimeWatcher,
    DurableNotificationSink,
    FileWatcherLease,
)
from adaptation_compiler_lab.persistence.errors import RecordConflictError
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


def test_application_outcome_is_atomic_and_queryable(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    digest = f"sha256:{'a' * 64}"
    ledger.append_session(
        GatewaySession(
            session_id="session-1",
            subject_id="kevin",
            project_id="project-1",
            activation_id="activation-1",
            release_digest=digest,
            projection_digest=digest,
            baseline_digest=digest,
            model="test-model",
            reasoning_effort="low",
            projection_utf8_bytes=10,
            encrypted_trace_digest=digest,
            started_at=NOW,
            completed_at=NOW,
            status=GatewaySessionStatus.COMPLETED,
        )
    )
    existing = VerificationReceipt(
        receipt_id="verify-conflict",
        session_id="application-session-1",
        command_id="conflicting-check",
        argv_digest=digest,
        exit_code=0,
        timed_out=False,
        output_digest=digest,
        output_bytes=0,
        started_at=NOW,
        completed_at=NOW,
    )
    ledger.append_verification(existing)
    unique = existing.model_copy(
        update={
            "receipt_id": "verify-unique",
            "command_id": "unique-check",
        }
    )
    conflicting = existing.model_copy(update={"exit_code": 1})
    application = ChangeApplicationReceipt(
        receipt_id="apply-session-1",
        session_id="session-1",
        change_receipt_digest=digest,
        expected_head="0" * 40,
        status=ChangeApplicationStatus.APPLIED,
        verification_receipt_digests=(digest,),
        recorded_at=NOW,
    )

    with pytest.raises(RecordConflictError):
        ledger.append_application_outcome(application, (unique, conflicting))

    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_verification_receipts WHERE receipt_id = 'verify-unique'"
        ).fetchone() == (0,)
    assert ledger.application("session-1") is None

    ledger.append_application_outcome(application, (unique,))

    assert ledger.application("session-1") == application
