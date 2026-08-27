"""Qt controller that projects typed desktop state into raw-free QML properties."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from PySide6.QtCore import Property, QObject, QThread, Signal, Slot

from adaptation_compiler_lab.automatic_runtime.models import RuntimeFeedbackOutcome
from adaptation_compiler_lab.connectors.pins import RuntimeConformanceError
from adaptation_compiler_lab.desktop.lifecycle import DesktopLifecycleService
from adaptation_compiler_lab.desktop.models import ActionResult, DesktopSnapshot, DesktopTaskResult
from adaptation_compiler_lab.desktop.service import DesktopApplicationService

_STATUS_LABELS: Final = {
    "ready": ("You're all set", "Adaptation Compiler is ready for your next task."),
    "needs_attention": ("A quick review is waiting", "Nothing changes until you decide."),
    "paused": ("Background learning is paused", "You can still review existing adaptations."),
    "consent_expired": ("Renewal needed", "Learning is paused until you renew consent."),
}


def _scope_label(scope: Any) -> str:
    if scope.project_ids:
        return "Project: " + ", ".join(scope.project_ids)
    if scope.task_classes:
        return "Tasks like: " + ", ".join(scope.task_classes)
    if scope.target_families == ("codex",):
        return "Your Codex sessions"
    return "Your registered AI sessions"


class _TaskWorker(QObject):
    completed = Signal(object, object)

    def __init__(
        self,
        operation: Callable[[], tuple[ActionResult, DesktopTaskResult | None]],
    ) -> None:
        super().__init__()
        self._operation = operation

    @Slot()
    def run(self) -> None:
        action, result = self._operation()
        self.completed.emit(action, result)


class DesktopController(QObject):
    """One-controller QML boundary; all durable actions remain in the application service."""

    stateChanged = Signal()
    messageChanged = Signal()
    taskChanged = Signal()

    def __init__(
        self,
        service: DesktopApplicationService,
        *,
        lifecycle: DesktopLifecycleService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._lifecycle = lifecycle
        self._snapshot: DesktopSnapshot | None = None
        self._busy = False
        self._message = ""
        self._message_is_error = False
        self._task_result = ""
        self._change_review: dict[str, object] = {}
        self._task_thread: QThread | None = None
        self._task_worker: _TaskWorker | None = None

    @Property(bool, notify=stateChanged)
    def ready(self) -> bool:
        return self._snapshot is not None

    @Property(bool, notify=stateChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=stateChanged)
    def health(self) -> str:
        return self._health()

    def _health(self) -> str:
        return "needs_attention" if self._snapshot is None else self._snapshot.health

    @Property(str, notify=stateChanged)
    def statusTitle(self) -> str:
        return _STATUS_LABELS[self._health()][0]

    @Property(str, notify=stateChanged)
    def statusDetail(self) -> str:
        return _STATUS_LABELS[self._health()][1]

    @Property(int, notify=stateChanged)
    def suggestionCount(self) -> int:
        if self._snapshot is None:
            return 0
        return self._snapshot.terminal.review_mode.metrics.pending_review_count

    @Property(int, notify=stateChanged)
    def adaptationCount(self) -> int:
        return 0 if self._snapshot is None else len(self._snapshot.terminal.active_adaptations)

    @Property(int, notify=stateChanged)
    def feedbackCount(self) -> int:
        if self._snapshot is None:
            return 0
        return self._snapshot.terminal.review_mode.metrics.pending_feedback_count

    @Property(int, notify=stateChanged)
    def consentDaysRemaining(self) -> int:
        return 0 if self._snapshot is None else self._snapshot.consent.days_remaining

    @Property(bool, notify=stateChanged)
    def backgroundEnabled(self) -> bool:
        return False if self._snapshot is None else self._snapshot.background_enabled

    @Property(bool, notify=stateChanged)
    def reportingEnabled(self) -> bool:
        return False if self._snapshot is None else self._snapshot.aggregate_reporting_enabled

    @Property(list, notify=stateChanged)
    def projects(self) -> list[dict[str, object]]:
        if self._snapshot is None:
            return []
        return [
            {
                "id": item.project_id,
                "name": item.display_name,
                "prospective": item.registered_prospectively,
                "taskRunnerEnabled": item.task_runner_enabled,
            }
            for item in self._snapshot.projects
        ]

    @Property(list, notify=stateChanged)
    def suggestions(self) -> list[dict[str, object]]:
        if self._snapshot is None:
            return []
        return [
            {
                "number": item.review_number,
                "queueId": item.queue_id,
                "digest": str(item.proposal_digest),
                "behavior": (
                    f"Stop using adaptation {item.affected_artifact_id}"
                    if item.behavior is None
                    else item.behavior
                ),
                "scope": _scope_label(item.scope),
                "why": "; ".join(item.reasons),
                "route": "revocation" if item.route is None else item.route.value,
                "evidence": item.evidence_ref.record_id,
            }
            for item in self._snapshot.terminal.review_mode.proposals
        ]

    @Property(list, notify=stateChanged)
    def adaptations(self) -> list[dict[str, object]]:
        if self._snapshot is None:
            return []
        return [
            {
                "id": item.artifact_id,
                "intent": item.intent,
                "behavior": "\n".join(item.required_behaviors),
                "scope": _scope_label(item.scope),
                "type": item.artifact_type,
                "evidenceCount": item.evidence_count,
            }
            for item in self._snapshot.terminal.active_adaptations
        ]

    @Property(list, notify=stateChanged)
    def pendingFeedback(self) -> list[dict[str, object]]:
        if self._snapshot is None:
            return []
        return [
            {
                "activationId": item.activation_id,
                "taskId": item.task_ref_id,
                "projectionBytes": item.projection_utf8_bytes,
                "artifactCount": len(item.active_artifact_ids),
            }
            for item in self._snapshot.terminal.review_mode.activation_feedback
        ]

    @Property(str, notify=messageChanged)
    def message(self) -> str:
        return self._message

    @Property(bool, notify=messageChanged)
    def messageIsError(self) -> bool:
        return self._message_is_error

    @Property(str, notify=taskChanged)
    def taskResult(self) -> str:
        return self._task_result

    @Property(dict, notify=taskChanged)
    def changeReview(self) -> dict[str, object]:
        return self._change_review

    @Slot()
    def refresh(self) -> None:
        self._set_busy(True)
        try:
            self._snapshot = self._service.load()
            self._set_message("", error=False)
        except (OSError, ValueError, RuntimeConformanceError):
            self._set_message(
                "Adaptation Compiler could not load this installation safely.",
                error=True,
            )
        finally:
            self._set_busy(False)
            self.stateChanged.emit()

    @Slot()
    def poll(self) -> None:
        self._handle(self._service.poll())

    @Slot(str, str)
    def approve(self, queue_id: str, digest: str) -> None:
        self._handle(self._service.approve(queue_id=queue_id, proposal_digest=digest))

    @Slot(str, str)
    def reject(self, queue_id: str, digest: str) -> None:
        self._handle(self._service.reject(queue_id=queue_id, proposal_digest=digest))

    @Slot(str)
    def revoke(self, artifact_id: str) -> None:
        snapshot = self._service.load()
        artifact = next(
            (item for item in snapshot.adaptations if item.artifact_id == artifact_id),
            None,
        )
        if artifact is None:
            self._set_message("That adaptation is no longer active.", error=True)
            return
        self._handle(
            self._service.revoke(
                artifact_id=artifact_id,
                artifact_digest=str(artifact.artifact_digest),
            )
        )

    @Slot(str, str)
    def recordFeedback(self, activation_id: str, outcome: str) -> None:
        try:
            typed_outcome = RuntimeFeedbackOutcome(outcome)
        except ValueError:
            self._set_message("That feedback option is not supported.", error=True)
            return
        snapshot = self._service.load()
        activation = next(
            (item for item in snapshot.activation_feedback if item.activation_id == activation_id),
            None,
        )
        if activation is None:
            self._set_message("That activation is no longer waiting for feedback.", error=True)
            return
        self._handle(
            self._service.feedback(
                activation_id=activation_id,
                delivery_receipt_digest=str(activation.delivery_receipt_digest),
                outcome=typed_outcome,
            )
        )

    @Slot(str, str)
    def runTask(self, task: str, workspace: str) -> None:
        if self._task_thread is not None:
            self._set_message("A governed task is already running.", error=True)
            return
        self._set_busy(True)
        self._task_result = ""
        self._change_review = {}
        self.taskChanged.emit()
        thread = QThread(self)
        worker = _TaskWorker(lambda: self._service.run_task(task=task, project_id=workspace))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._finish_task)
        worker.completed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_task_worker)
        self._task_thread = thread
        self._task_worker = worker
        thread.start()

    @Slot(bool)
    def setBackgroundEnabled(self, enabled: bool) -> None:
        if self._lifecycle is None:
            self._set_message("Background startup is unavailable in this build.", error=True)
            return
        try:
            preferences = self._lifecycle.set_background_enabled(enabled)
            self._snapshot = self._service.set_local_preferences(
                background_enabled=preferences.background_enabled,
                aggregate_reporting_enabled=preferences.aggregate_reporting_enabled,
            )
        except (OSError, ValueError):
            self._set_message("Background startup could not be changed safely.", error=True)
            return
        self._set_message("Background learning preference updated.", error=False)
        self.stateChanged.emit()

    @Slot(bool)
    def setReportingEnabled(self, enabled: bool) -> None:
        if self._lifecycle is None:
            self._set_message("Aggregate reporting is unavailable in this build.", error=True)
            return
        try:
            preferences = self._lifecycle.set_reporting_enabled(enabled)
            self._snapshot = self._service.set_local_preferences(
                background_enabled=preferences.background_enabled,
                aggregate_reporting_enabled=preferences.aggregate_reporting_enabled,
            )
        except (OSError, ValueError):
            self._set_message("Aggregate reporting could not be changed safely.", error=True)
            return
        self._set_message("Aggregate reporting preference updated.", error=False)
        self.stateChanged.emit()

    @Slot()
    def renewConsent(self) -> None:
        self._handle(self._service.renew_consent())

    @Slot(str, str)
    def applyChanges(self, session_id: str, expected_head: str) -> None:
        result = self._service.apply_changes(
            session_id=session_id,
            expected_head=expected_head,
        )
        self._set_message(result.message, error=not result.ok)
        if result.ok:
            self._change_review = {}
            self.taskChanged.emit()
            self.refresh()

    @Slot(str)
    def discardChanges(self, session_id: str) -> None:
        result = self._service.discard_changes(session_id=session_id)
        self._set_message(result.message, error=not result.ok)
        if result.ok:
            self._change_review = {}
            self.taskChanged.emit()
            self.refresh()

    @Slot(object, object)
    def _finish_task(self, action: ActionResult, result: DesktopTaskResult | None) -> None:
        self._set_message(action.message, error=not action.ok)
        if result is not None:
            self._task_result = (
                result.final_message or "The task completed without a final message."
            )
            review = result.change_review
            self._change_review = (
                {}
                if review is None
                else {
                    "sessionId": review.session_id,
                    "expectedHead": review.expected_head,
                    "changedFiles": list(review.changed_files),
                    "diff": review.diff_text,
                    "binaryCount": review.binary_change_count,
                }
            )
            self.taskChanged.emit()
        self._set_busy(False)
        if action.ok:
            self.refresh()

    @Slot()
    def _clear_task_worker(self) -> None:
        self._task_thread = None
        self._task_worker = None

    def _handle(self, result: ActionResult) -> None:
        self._set_message(result.message, error=not result.ok)
        if result.ok:
            self.refresh()

    def _set_busy(self, value: bool) -> None:
        if self._busy == value:
            return
        self._busy = value
        self.stateChanged.emit()

    def _set_message(self, value: str, *, error: bool) -> None:
        self._message = value
        self._message_is_error = error
        self.messageChanged.emit()
