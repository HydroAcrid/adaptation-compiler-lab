"""Restart-safe local watcher and raw-free Windows notification adapters."""

from __future__ import annotations

import base64
import os
import random
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Literal, Protocol

from adaptation_compiler_lab.automatic_runtime.gateway_ledger import GatewayLedger
from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    NotificationInboxEntry,
    RuntimeNotificationReceipt,
    RuntimeWatcherHeartbeat,
    RuntimeWatcherLease,
)
from adaptation_compiler_lab.automatic_runtime.models import (
    RuntimeNotice,
    RuntimeNoticeKind,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class WatcherError(ValueError):
    """Raised when watcher exclusivity or installation cannot be guaranteed."""


class PollOperation(Protocol):
    def __call__(self) -> object: ...


_PUBLIC_SUMMARIES: Final = {
    RuntimeNoticeKind.LEARNED: "Adaptation updated.",
    RuntimeNoticeKind.UPDATED: "Adaptation updated.",
    RuntimeNoticeKind.REMOVED: "Adaptation removed.",
    RuntimeNoticeKind.NEEDS_REVIEW: "Adaptation review available.",
    RuntimeNoticeKind.BLOCKED: "Adaptation runtime needs attention.",
}


class WindowsToastPublisher:
    """Publish only an allowlisted generic message through the Windows toast API."""

    _SCRIPT: Final = r"""
$ErrorActionPreference = 'Stop'
$null = [Windows.UI.Notifications.ToastNotificationManager,
  Windows.UI.Notifications, ContentType = WindowsRuntime]
$null = [Windows.UI.Notifications.ToastNotification,
  Windows.UI.Notifications, ContentType = WindowsRuntime]
$null = [Windows.Data.Xml.Dom.XmlDocument,
  Windows.Data.Xml.Dom, ContentType = WindowsRuntime]
$message = [Console]::In.ReadToEnd()
$escaped = [Security.SecurityElement]::Escape($message)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$template = "<toast><visual><binding template='ToastGeneric'>" +
  "<text>Adaptation Compiler Lab</text><text>$escaped</text>" +
  "</binding></visual></toast>"
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(
  'Adaptation Compiler Lab')
$notifier.Show($toast)
"""

    def __init__(self, executable: str = "powershell.exe") -> None:
        self._executable = executable

    def publish(self, summary: str) -> None:
        if summary not in set(_PUBLIC_SUMMARIES.values()):
            raise WatcherError("toast text is not on the raw-free allowlist")
        encoded = base64.b64encode(self._SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            result = subprocess.run(
                [
                    self._executable,
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded,
                ],
                input=summary,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise WatcherError("Windows toast delivery is unavailable") from error
        if result.returncode != 0:
            raise WatcherError("Windows toast delivery failed")


class DurableNotificationSink:
    """Deduplicate raw-free inbox entries and optionally mirror them to Windows toast."""

    def __init__(
        self,
        ledger: GatewayLedger,
        *,
        subject_id: str,
        toast: WindowsToastPublisher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ledger = ledger
        self._subject_id = subject_id
        self._toast = toast
        self._clock = clock or (lambda: datetime.now(UTC))

    def publish(self, notice: RuntimeNotice) -> None:
        summary = _PUBLIC_SUMMARIES.get(notice.kind)
        if summary is None:
            return
        now = self._clock()
        entry = NotificationInboxEntry(
            entry_id=f"inbox-{notice.notice_id}",
            subject_id=self._subject_id,
            notice_digest=canonical_digest(notice),
            kind=notice.kind.value,
            public_summary=summary,
            created_at=now,
        )
        inserted = self._ledger.append_inbox(entry)
        self._ledger.append_notification_receipt(
            RuntimeNotificationReceipt(
                receipt_id=f"notice-local-{notice.notice_id}",
                entry_id=entry.entry_id,
                channel="local_inbox",
                status="published",
                recorded_at=now,
            )
        )
        if self._toast is None or not inserted:
            return
        try:
            self._toast.publish(summary)
            status: Literal["published", "failed", "acknowledged"] = "published"
            failure_class = None
        except WatcherError as error:
            status = "failed"
            failure_class = type(error).__name__
        self._ledger.append_notification_receipt(
            RuntimeNotificationReceipt(
                receipt_id=f"notice-toast-{notice.notice_id}",
                entry_id=entry.entry_id,
                channel="windows_toast",
                status=status,
                failure_class=failure_class,
                recorded_at=now,
            )
        )


class FileWatcherLease:
    """One process lease with an explicit heartbeat and stale-owner recovery."""

    def __init__(self, state_root: Path, *, subject_id: str) -> None:
        self._path = state_root.expanduser().resolve() / "watcher-lease.json"
        self._subject_id = subject_id
        self.lease: RuntimeWatcherLease | None = None

    def acquire(self, *, now: datetime | None = None) -> RuntimeWatcherLease:
        observed = now or datetime.now(UTC)
        if self._path.exists():
            existing = self._read()
            if existing.expires_at > observed and self._pid_alive(existing.owner_pid):
                raise WatcherError("another runtime watcher owns the active lease")
            self._path.unlink()
        lease = RuntimeWatcherLease(
            lease_id=f"watcher-{self._subject_id}-{os.getpid()}-{int(observed.timestamp())}",
            subject_id=self._subject_id,
            owner_pid=os.getpid(),
            acquired_at=observed,
            expires_at=observed + timedelta(minutes=3),
        )
        descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical_json(lease) + "\n")
        self.lease = lease
        return lease

    def release(self) -> None:
        if self.lease is None:
            return
        try:
            if self._read().lease_id == self.lease.lease_id:
                self._path.unlink(missing_ok=True)
        finally:
            self.lease = None

    def renew(self, *, now: datetime | None = None) -> RuntimeWatcherLease:
        if self.lease is None:
            raise WatcherError("watcher lease is not held")
        existing = self._read()
        if existing.lease_id != self.lease.lease_id or existing.owner_pid != os.getpid():
            raise WatcherError("watcher lease ownership changed")
        observed = now or datetime.now(UTC)
        renewed = existing.model_copy(update={"expires_at": observed + timedelta(minutes=3)})
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(canonical_json(renewed) + "\n", encoding="utf-8")
        os.replace(temporary, self._path)
        self.lease = renewed
        return renewed

    def _read(self) -> RuntimeWatcherLease:
        try:
            return RuntimeWatcherLease.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise WatcherError("watcher lease file is invalid") from error

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


class AutomaticRuntimeWatcher:
    """Poll forever with durable health receipts and bounded exponential backoff."""

    def __init__(
        self,
        *,
        poll: PollOperation,
        ledger: GatewayLedger,
        lease: FileWatcherLease,
        state_root: Path,
        idle_seconds: float = 60.0,
        maximum_backoff_seconds: float = 900.0,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        if not 1 <= idle_seconds <= 300 or maximum_backoff_seconds < idle_seconds:
            raise ValueError("watcher cadence is outside the supported bounds")
        self._poll = poll
        self._ledger = ledger
        self._lease = lease
        self._stop_path = state_root.expanduser().resolve() / "watcher-stop"
        self._idle = idle_seconds
        self._maximum_backoff = maximum_backoff_seconds
        self._sleep = sleeper
        self._clock = clock or (lambda: datetime.now(UTC))
        self._random = random_source or random.Random()

    def run(self, *, maximum_polls: int | None = None) -> None:
        active = self._lease.acquire(now=self._clock())
        failures = 0
        sequence = 0
        polls = 0
        try:
            while not self._stop_path.exists():
                if maximum_polls is not None and polls >= maximum_polls:
                    break
                polls += 1
                sequence += 1
                try:
                    self._poll()
                    failures = 0
                    status: Literal["healthy", "backing_off", "stopping"] = "healthy"
                    failure_class = None
                    delay = self._idle
                except Exception as error:
                    failures += 1
                    status = "backing_off"
                    failure_class = type(error).__name__
                    ceiling = min(self._maximum_backoff, self._idle * (2**failures))
                    delay = ceiling * self._random.uniform(0.75, 1.0)
                observed = self._clock()
                self._lease.renew(now=observed)
                self._ledger.append_heartbeat(
                    RuntimeWatcherHeartbeat(
                        heartbeat_id=f"heartbeat-{active.lease_id}-{sequence}",
                        lease_id=active.lease_id,
                        sequence=sequence,
                        observed_at=observed,
                        status=status,
                        failure_class=failure_class,
                    )
                )
                if maximum_polls is None or polls < maximum_polls:
                    self._sleep_with_renewal(delay)
        finally:
            self._lease.release()
            self._stop_path.unlink(missing_ok=True)

    def request_stop(self) -> None:
        self._stop_path.touch(exist_ok=True)

    def _sleep_with_renewal(self, delay: float) -> None:
        remaining = delay
        while remaining > 0 and not self._stop_path.exists():
            interval = min(30.0, remaining)
            self._sleep(interval)
            remaining -= interval
            self._lease.renew(now=self._clock())


class WindowsTaskScheduler:
    """Explicitly install or remove a same-user login task without embedding secrets."""

    def __init__(self, executable: str = "schtasks.exe") -> None:
        self._executable = executable

    def install(self, *, task_name: str, action: str) -> None:
        result = subprocess.run(
            [
                self._executable,
                "/Create",
                "/F",
                "/SC",
                "ONLOGON",
                "/RL",
                "LIMITED",
                "/TN",
                task_name,
                "/TR",
                action,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise WatcherError("Windows watcher task installation failed")

    def uninstall(self, *, task_name: str) -> None:
        result = subprocess.run(
            [self._executable, "/Delete", "/F", "/TN", task_name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise WatcherError("Windows watcher task removal failed")
