"""Typed desktop-service tests over synthetic raw-free runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import FreshCodexTaskResult
from adaptation_compiler_lab.automatic_runtime.models import RuntimeFeedbackOutcome
from adaptation_compiler_lab.automatic_runtime.product_dogfood import TerminalAlphaSnapshot
from adaptation_compiler_lab.connectors.pins import RuntimeConformanceError
from adaptation_compiler_lab.desktop.models import DesktopChangeReview
from adaptation_compiler_lab.desktop.service import (
    DesktopApplicationService,
    DesktopRuntimeConfiguration,
    DesktopRuntimeProject,
)
from adaptation_compiler_lab.domain import ApprovalDecision, Scope
from tests.unit.automatic_runtime.test_runtime import NOW
from tests.unit.automatic_runtime.test_terminal_alpha import _empty_snapshot


@dataclass
class FakeDesktopBackend:
    terminal: TerminalAlphaSnapshot
    expires_delta: timedelta = timedelta(days=20)
    decisions: list[tuple[str, str, ApprovalDecision, bool, Scope | None]] = field(
        default_factory=list
    )
    revoked: list[str] = field(default_factory=list)
    feedback_rows: list[tuple[str, RuntimeFeedbackOutcome]] = field(default_factory=list)
    poll_count: int = 0
    renewal_count: int = 0
    applied: list[tuple[str, str]] = field(default_factory=list)
    discarded: list[str] = field(default_factory=list)
    mode_ids: list[str | None] = field(default_factory=list)

    def config(self) -> DesktopRuntimeConfiguration:
        return DesktopRuntimeConfiguration(
            consent_effective_at=NOW - timedelta(days=10),
            consent_expires_at=NOW + self.expires_delta,
            retention_days=30,
            projects=tuple(
                DesktopRuntimeProject(
                    project_id=item,
                    registered_prospectively=True,
                    task_runner_enabled=True,
                )
                for item in self.terminal.configured_project_ids
            ),
        )

    def snapshot(self, *, poll_now: bool = False) -> TerminalAlphaSnapshot:
        if poll_now:
            self.poll_count += 1
        return self.terminal

    def poll(self) -> None:
        self.poll_count += 1

    def decide_review(
        self,
        *,
        queue_id: str,
        proposal_digest: str,
        decision: ApprovalDecision,
        confirm_future_use: bool,
        refined_scope: Scope | None,
    ) -> None:
        self.decisions.append(
            (queue_id, proposal_digest, decision, confirm_future_use, refined_scope)
        )

    def revoke(self, *, artifact_id: str) -> None:
        self.revoked.append(artifact_id)

    def renew_consent(self) -> None:
        self.renewal_count += 1

    def feedback(self, *, activation_id: str, outcome: RuntimeFeedbackOutcome) -> None:
        self.feedback_rows.append((activation_id, outcome))

    def run_task(
        self, *, task: str, project_id: str, mode_id: str | None = None
    ) -> FreshCodexTaskResult:
        assert task == "Do the bounded task."
        assert project_id == "green-meadow"
        self.mode_ids.append(mode_id)
        return FreshCodexTaskResult(
            activation_id="desktop-activation-1",
            material_utf8_bytes=144,
            status="completed",
            final_message="Done.",
        )

    def change_review(self, *, session_id: str) -> DesktopChangeReview:
        return DesktopChangeReview(
            session_id=session_id,
            expected_head="a" * 40,
            changed_files=("src/example.py",),
            diff_text="synthetic diff",
            binary_change_count=0,
        )

    def apply_changes(self, *, session_id: str, expected_head: str) -> None:
        self.applied.append((session_id, expected_head))

    def discard_changes(self, *, session_id: str) -> None:
        self.discarded.append(session_id)


def test_snapshot_is_raw_free_and_uses_calm_health(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    backend = FakeDesktopBackend(terminal)

    snapshot = DesktopApplicationService(
        backend,
        background_enabled=True,
        aggregate_reporting_enabled=False,
        clock=lambda: NOW,
    ).load()

    assert snapshot.product_name == "Adaptation Compiler"
    assert snapshot.health == "ready"
    assert snapshot.consent.days_remaining == 20
    assert snapshot.aggregate_reporting_enabled is False
    assert snapshot.raw_payloads_exposed is False
    assert tuple(item.project_id for item in snapshot.projects) == terminal.configured_project_ids


def test_expired_consent_fails_closed_in_snapshot(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    backend = FakeDesktopBackend(terminal, expires_delta=timedelta(seconds=-1))

    snapshot = DesktopApplicationService(backend, clock=lambda: NOW).load()

    assert snapshot.health == "consent_expired"
    assert snapshot.consent.renewal_required is True
    assert snapshot.consent.days_remaining == 0


def test_approval_forwards_exact_digest_and_future_use_confirmation(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    backend = FakeDesktopBackend(terminal)
    service = DesktopApplicationService(backend, background_enabled=True, clock=lambda: NOW)

    result = service.approve(
        queue_id="review-1",
        proposal_digest=f"sha256:{'a' * 64}",
    )

    assert result.ok is True
    assert backend.decisions == [
        (
            "review-1",
            f"sha256:{'a' * 64}",
            ApprovalDecision.APPROVED,
            True,
            None,
        )
    ]


def test_task_result_preserves_transient_message_but_action_is_raw_free(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    service = DesktopApplicationService(
        FakeDesktopBackend(terminal),
        background_enabled=True,
        clock=lambda: NOW,
    )

    action, task = service.run_task(task="Do the bounded task.", project_id="green-meadow")

    assert action.ok is True
    assert task is not None
    assert task.final_message == "Done."
    assert task.projection_utf8_bytes == 144
    assert "Done" not in action.message


def test_temporary_mode_is_forwarded_without_changing_the_normal_task_path(
    tmp_path: Path,
) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    backend = FakeDesktopBackend(terminal)
    service = DesktopApplicationService(backend, clock=lambda: NOW)

    action, task = service.run_task(
        task="Do the bounded task.",
        project_id="green-meadow",
        mode_id="frontend-studio",
    )

    assert action.ok is True
    assert task is not None
    assert backend.mode_ids == ["frontend-studio"]


def test_empty_task_is_rejected_before_backend_execution(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    service = DesktopApplicationService(FakeDesktopBackend(terminal), clock=lambda: NOW)

    action, task = service.run_task(task="  ", project_id="green-meadow")

    assert action.ok is False
    assert action.code == "invalid_task"
    assert task is None


def test_runtime_pin_drift_is_returned_as_a_safe_raw_free_failure(
    tmp_path: Path,
) -> None:
    terminal, _state = _empty_snapshot(tmp_path)

    class DriftBackend(FakeDesktopBackend):
        def run_task(
            self, *, task: str, project_id: str, mode_id: str | None = None
        ) -> FreshCodexTaskResult:
            del task, project_id, mode_id
            raise RuntimeConformanceError("private executable path and digest detail")

    service = DesktopApplicationService(DriftBackend(terminal), clock=lambda: NOW)

    action, task = service.run_task(task="Do the bounded task.", project_id="green-meadow")

    assert action.ok is False
    assert action.code == "runtimeconformance"
    assert "private executable" not in action.message
    assert task is None


def test_consent_renewal_is_an_explicit_backend_action(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    backend = FakeDesktopBackend(terminal)
    service = DesktopApplicationService(backend, clock=lambda: NOW)

    result = service.renew_consent()

    assert result.ok is True
    assert backend.renewal_count == 1


def test_apply_and_discard_forward_exact_review_identity(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    backend = FakeDesktopBackend(terminal)
    service = DesktopApplicationService(backend, clock=lambda: NOW)

    applied = service.apply_changes(
        session_id="desktop-activation-1",
        expected_head="a" * 40,
    )
    discarded = service.discard_changes(session_id="desktop-activation-2")

    assert applied.ok is True
    assert discarded.ok is True
    assert backend.applied == [("desktop-activation-1", "a" * 40)]
    assert backend.discarded == ["desktop-activation-2"]
