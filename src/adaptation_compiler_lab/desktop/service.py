"""Typed desktop service over the existing governed Codex dogfood runtime."""

from __future__ import annotations

import base64
import difflib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    FreshCodexTaskResult,
    _gateway_ledger,
    _gateway_project,
    _ledger,
    _load_config,
    _now,
    _raw_store,
    _verification_specs,
    execute_codex_feedback_poll,
    execute_governed_gateway_task,
    load_terminal_alpha_snapshot,
    renew_codex_dogfood_consent,
    resolve_codex_dogfood_review,
    revoke_active_codex_adaptation,
    save_codex_activation_feedback,
)
from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    ChangeApplicationReceipt,
    ChangeApplicationStatus,
    WorkspaceBaseline,
)
from adaptation_compiler_lab.automatic_runtime.models import RuntimeFeedbackOutcome
from adaptation_compiler_lab.automatic_runtime.product_dogfood import TerminalAlphaSnapshot
from adaptation_compiler_lab.automatic_runtime.workspace_gateway import (
    EncryptedChangeBundleStore,
    IndependentVerifier,
    RecoverableChangeApplier,
)
from adaptation_compiler_lab.connectors.pins import RuntimeConformanceError
from adaptation_compiler_lab.desktop.models import (
    ActionResult,
    ActivationFeedbackSummaryV1,
    AdaptationSummaryV1,
    ConsentStatus,
    DesktopAction,
    DesktopChangeReview,
    DesktopHealth,
    DesktopProject,
    DesktopSnapshot,
    DesktopTaskResult,
    RecentUndoSummaryV1,
    SuggestionSummaryV1,
)
from adaptation_compiler_lab.domain import ApprovalDecision, Scope
from adaptation_compiler_lab.modes import mode_by_id
from adaptation_compiler_lab.portability import ShareablePackageImportStore
from adaptation_compiler_lab.serialization import canonical_digest


@dataclass(frozen=True, slots=True)
class DesktopRuntimeProject:
    """Minimum governed project metadata needed by a presentation layer."""

    project_id: str
    registered_prospectively: bool
    task_runner_enabled: bool


@dataclass(frozen=True, slots=True)
class DesktopRuntimeConfiguration:
    """Raw-free configuration projection used by the desktop service."""

    consent_effective_at: datetime
    consent_expires_at: datetime
    retention_days: int
    projects: tuple[DesktopRuntimeProject, ...]


class DesktopBackend(Protocol):
    """Narrow seam that keeps presentation layers and tests out of persistence."""

    def config(self) -> DesktopRuntimeConfiguration: ...

    def snapshot(self, *, poll_now: bool = False) -> TerminalAlphaSnapshot: ...

    def poll(self) -> None: ...

    def decide_review(
        self,
        *,
        queue_id: str,
        proposal_digest: str,
        decision: ApprovalDecision,
        confirm_future_use: bool,
        refined_scope: Scope | None,
    ) -> None: ...

    def revoke(self, *, artifact_id: str) -> None: ...

    def renew_consent(self) -> None: ...

    def feedback(
        self,
        *,
        activation_id: str,
        delivery_receipt_digest: str,
        outcome: RuntimeFeedbackOutcome,
    ) -> None: ...

    def run_task(
        self, *, task: str, project_id: str, mode_id: str | None = None
    ) -> FreshCodexTaskResult: ...

    def change_review(self, *, session_id: str) -> DesktopChangeReview: ...

    def apply_changes(self, *, session_id: str, expected_head: str) -> None: ...

    def discard_changes(self, *, session_id: str) -> None: ...


@dataclass(slots=True)
class CodexDogfoodDesktopBackend:
    """Production backend that delegates to already-tested governed functions."""

    config_path: Path
    predecessor_config_path: Path | None = None

    def config(self) -> DesktopRuntimeConfiguration:
        value = _load_config(self.config_path)
        return DesktopRuntimeConfiguration(
            consent_effective_at=value.policy.effective_at,
            consent_expires_at=value.policy.expires_at,
            retention_days=value.policy.retention_days,
            projects=tuple(
                DesktopRuntimeProject(
                    project_id=item.project_id,
                    registered_prospectively=item.registration is not None,
                    task_runner_enabled=value.gateway_workspace_root is not None,
                )
                for item in value.projects
            ),
        )

    def snapshot(self, *, poll_now: bool = False) -> TerminalAlphaSnapshot:
        value, _pickup = load_terminal_alpha_snapshot(
            self.config_path,
            predecessor_config_path=self.predecessor_config_path,
            poll_now=poll_now,
        )
        return value

    def poll(self) -> None:
        execute_codex_feedback_poll(self.config_path)

    def decide_review(
        self,
        *,
        queue_id: str,
        proposal_digest: str,
        decision: ApprovalDecision,
        confirm_future_use: bool,
        refined_scope: Scope | None,
    ) -> None:
        resolve_codex_dogfood_review(
            self.config_path,
            queue_id=queue_id,
            proposal_digest=proposal_digest,
            decision=decision,
            confirm_future_use=confirm_future_use,
            **_scope_options(refined_scope),
        )

    def revoke(self, *, artifact_id: str) -> None:
        revoke_active_codex_adaptation(self.config_path, artifact_id=artifact_id)

    def renew_consent(self) -> None:
        renew_codex_dogfood_consent(self.config_path, confirm_renewal=True)

    def feedback(
        self,
        *,
        activation_id: str,
        delivery_receipt_digest: str,
        outcome: RuntimeFeedbackOutcome,
    ) -> None:
        config = _load_config(self.config_path)
        activation = _ledger(config).activation(activation_id)
        if activation is None or str(activation.delivery_receipt_digest) != delivery_receipt_digest:
            raise ValueError("activation delivery receipt changed")
        save_codex_activation_feedback(
            self.config_path,
            activation_id=activation_id,
            outcome=outcome,
        )

    def run_task(
        self, *, task: str, project_id: str, mode_id: str | None = None
    ) -> FreshCodexTaskResult:
        config = _load_config(self.config_path)
        project = next((item for item in config.projects if item.project_id == project_id), None)
        if project is None:
            raise ValueError("desktop task requires an exact registered project")
        if config.gateway_workspace_root is None:
            raise ValueError("desktop task runner requires the isolated writable gateway")
        imported_mode = None
        if mode_id is not None and mode_by_id(mode_id) is None:
            imported_mode = next(
                (
                    mode
                    for mode in ShareablePackageImportStore(
                        config.state_root / "shareable-imports"
                    ).accepted_modes()
                    if mode.mode_id == mode_id
                ),
                None,
            )
            if imported_mode is None:
                raise ValueError("desktop task requested an unavailable Mode")
        session_id = execute_governed_gateway_task(
            self.config_path,
            task=task,
            project_id=project_id,
            mode_id=mode_id,
            mode=imported_mode,
        )
        session = _gateway_ledger(config).session(session_id)
        return FreshCodexTaskResult(
            activation_id=session_id,
            material_utf8_bytes=(0 if session is None else session.projection_utf8_bytes),
            status="review_available",
            final_message="Changes are ready for explicit review before they reach your project.",
        )

    def change_review(self, *, session_id: str) -> DesktopChangeReview:
        config = _load_config(self.config_path)
        bundle = _gateway_ledger(config).change_bundle(session_id)
        if bundle is None:
            raise ValueError("gateway change bundle is unavailable")
        value = EncryptedChangeBundleStore(_raw_store(config)).load(bundle)
        baseline = WorkspaceBaseline.model_validate(value.get("baseline"), strict=True)
        raw_changes = value.get("changes")
        if not isinstance(raw_changes, list):
            raise ValueError("gateway change bundle is invalid")
        diffs: list[str] = []
        binary_count = 0
        for raw in raw_changes:
            if not isinstance(raw, dict):
                raise ValueError("gateway change entry is invalid")
            path = str(raw.get("path", ""))
            before = _decode_change_bytes(raw.get("before"))
            after = _decode_change_bytes(raw.get("after"))
            if b"\x00" in before or b"\x00" in after:
                binary_count += 1
                diffs.append(f"Binary change: {path}\n")
                continue
            try:
                before_text = before.decode("utf-8")
                after_text = after.decode("utf-8")
            except UnicodeDecodeError:
                binary_count += 1
                diffs.append(f"Binary change: {path}\n")
                continue
            diffs.append(
                "".join(
                    difflib.unified_diff(
                        before_text.splitlines(keepends=True),
                        after_text.splitlines(keepends=True),
                        fromfile=f"a/{path}",
                        tofile=f"b/{path}",
                    )
                )
            )
        return DesktopChangeReview(
            session_id=session_id,
            expected_head=baseline.commit_sha,
            changed_files=tuple(item.path for item in bundle.receipt.changes),
            diff_text="\n".join(diffs),
            binary_change_count=binary_count,
        )

    def apply_changes(self, *, session_id: str, expected_head: str) -> None:
        config = _load_config(self.config_path)
        ledger = _gateway_ledger(config)
        session = ledger.session(session_id)
        bundle = ledger.change_bundle(session_id)
        if session is None or bundle is None:
            raise ValueError("gateway session or change bundle is unavailable")
        if ledger.application(session_id) is not None:
            raise ValueError("gateway changes already have a decision")
        project = _gateway_project(config, session.project_id)
        receipt, verifications = RecoverableChangeApplier(
            EncryptedChangeBundleStore(_raw_store(config))
        ).apply(
            bundle,
            canonical_root=project.root,
            expected_head=expected_head,
            verification_specs=_verification_specs(project, "postflight"),
            verifier=IndependentVerifier(),
            verification_session_id=f"application-{session_id}",
            on_applied=ledger.append_application_outcome,
        )
        if receipt.status.value != "applied":
            ledger.append_application_outcome(receipt, verifications)
            raise ValueError("gateway change application was refused or rolled back")

    def discard_changes(self, *, session_id: str) -> None:
        config = _load_config(self.config_path)
        ledger = _gateway_ledger(config)
        bundle = ledger.change_bundle(session_id)
        if bundle is None:
            raise ValueError("gateway change bundle is unavailable")
        if ledger.application(session_id) is not None:
            raise ValueError("gateway changes already have a decision")
        value = EncryptedChangeBundleStore(_raw_store(config)).load(bundle)
        baseline = WorkspaceBaseline.model_validate(value.get("baseline"), strict=True)
        ledger.append_application_outcome(
            ChangeApplicationReceipt(
                receipt_id=f"apply-{session_id}",
                session_id=session_id,
                change_receipt_digest=bundle.receipt.content_digest,
                expected_head=baseline.commit_sha,
                status=ChangeApplicationStatus.DISCARDED,
                verification_receipt_digests=(),
                recorded_at=_now(),
            ),
            (),
        )


def _scope_options(scope: Scope | None) -> dict[str, list[str] | None]:
    if scope is None:
        return {
            "refine_project_id": None,
            "refine_task_class": None,
            "refine_environment_id": None,
            "refine_activation_condition": None,
            "refine_exclusion": None,
        }
    return {
        "refine_project_id": list(scope.project_ids),
        "refine_task_class": list(scope.task_classes),
        "refine_environment_id": list(scope.environment_ids),
        "refine_activation_condition": list(scope.activation_conditions),
        "refine_exclusion": list(scope.exclusions),
    }


def _decode_change_bytes(value: object) -> bytes:
    if value is None:
        return b""
    if not isinstance(value, str):
        raise ValueError("gateway change bytes are invalid")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise ValueError("gateway change bytes are invalid") from error


class DesktopApplicationService:
    """Consumer-safe desktop API with exact governed mutations and fail-closed status."""

    def __init__(
        self,
        backend: DesktopBackend,
        *,
        background_enabled: bool = False,
        aggregate_reporting_enabled: bool = False,
        decision_notifications_enabled: bool = False,
        launch_at_login_enabled: bool = False,
        preference_writer: Callable[[bool, bool, bool, bool], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._background_enabled = background_enabled
        self._reporting_enabled = aggregate_reporting_enabled
        self._decision_notifications_enabled = decision_notifications_enabled
        self._launch_at_login_enabled = launch_at_login_enabled
        self._preference_writer = preference_writer
        self._clock = clock or (lambda: datetime.now(UTC))

    def load(self, *, poll_now: bool = False) -> DesktopSnapshot:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("desktop clock must be timezone-aware")
        config = self._backend.config()
        terminal = self._backend.snapshot(poll_now=poll_now)
        expires_at = config.consent_expires_at
        renewal_required = expires_at <= now
        remaining_seconds = max(0.0, (expires_at - now).total_seconds())
        days_remaining = min(30, int((remaining_seconds + 86_399) // 86_400))
        health: DesktopHealth
        if renewal_required:
            health = "consent_expired"
        elif not terminal.review_mode.credential_enrolled:
            health = "needs_attention"
        elif not self._background_enabled:
            health = "paused"
        elif (
            terminal.review_mode.metrics.pending_review_count
            or terminal.review_mode.metrics.pending_feedback_count
        ):
            health = "needs_attention"
        else:
            health = "ready"
        projects = tuple(
            DesktopProject(
                project_id=item.project_id,
                display_name=item.project_id.replace("-", " ").title(),
                registered_prospectively=item.registered_prospectively,
                task_runner_enabled=item.task_runner_enabled,
            )
            for item in config.projects
        )
        suggestions = tuple(
            SuggestionSummaryV1(
                review_number=item.review_number,
                queue_id=item.queue_id,
                proposal_digest=item.proposal_digest,
                signal_kind=item.signal_kind,
                proposed_behavior=item.behavior,
                affected_artifact_id=item.affected_artifact_id,
                route=item.route,
                layer=item.layer,
                suggested_scope=item.scope,
                reason_summary=item.reasons,
                evidence_digest=item.evidence_ref.content_digest,
                consent_digest=item.consent_ref.content_digest,
                capture_digest=item.capture_ref.content_digest,
                available_actions=(
                    ("approve_revocation", "reject_revocation")
                    if item.signal_kind.value == "revocation"
                    else ("keep_suggested", "keep_project", "keep_narrowed", "ignore")
                ),
                created_at=item.created_at,
            )
            for item in terminal.review_mode.proposals
        )
        adaptations = tuple(
            AdaptationSummaryV1(
                artifact_id=item.artifact_id,
                artifact_version=item.artifact_version,
                artifact_digest=canonical_digest(item),
                artifact_type=item.artifact_type,
                layer=item.layer,
                intent=item.intent,
                required_behaviors=item.required_behaviors,
                scope=item.scope,
                evidence_count=item.evidence_count,
                review_at=item.review_at,
                expires_at=item.expires_at,
            )
            for item in terminal.active_adaptations
        )
        activation_feedback = tuple(
            ActivationFeedbackSummaryV1(
                activation_id=item.activation_id,
                delivery_receipt_digest=item.delivery_receipt_digest,
                active_artifact_ids=item.active_artifact_ids,
                projection_utf8_bytes=item.projection_utf8_bytes,
                activated_at=item.activated_at,
                completed_at=item.completed_at,
            )
            for item in terminal.review_mode.activation_feedback
        )
        active_ids = {item.artifact_id for item in adaptations}
        recent_undos = tuple(
            RecentUndoSummaryV1(
                notice_id=notice.notice_id,
                notice_digest=canonical_digest(notice),
                artifact_id=notice.undo_artifact_id,
                summary=notice.summary,
                created_at=notice.created_at,
                expires_at=notice.created_at + timedelta(hours=24),
            )
            for notice in terminal.review_mode.recent_notices
            if notice.undo_artifact_id is not None
            and notice.undo_artifact_id in active_ids
            and notice.created_at <= now <= notice.created_at + timedelta(hours=24)
        )
        return DesktopSnapshot(
            health=health,
            consent=ConsentStatus(
                effective_at=config.consent_effective_at,
                expires_at=expires_at,
                retention_days=config.retention_days,
                days_remaining=days_remaining,
                renewal_required=renewal_required,
            ),
            background_enabled=self._background_enabled,
            aggregate_reporting_enabled=self._reporting_enabled,
            decision_notifications_enabled=self._decision_notifications_enabled,
            launch_at_login_enabled=self._launch_at_login_enabled,
            terminal=terminal,
            projects=projects,
            suggestions=suggestions,
            adaptations=adaptations,
            activation_feedback=activation_feedback,
            recent_undos=recent_undos,
            generated_at=now,
        )

    def poll(self) -> ActionResult:
        snapshot = self.load()
        if not snapshot.background_enabled:
            return self._failure("poll", "learning_paused", "Turn on learning before polling.")
        if snapshot.consent.renewal_required:
            return self._failure("poll", "consent_expired", "Renew consent before polling.")
        return self._mutate("poll", self._backend.poll)

    def set_local_preferences(
        self,
        *,
        background_enabled: bool,
        aggregate_reporting_enabled: bool,
        decision_notifications_enabled: bool | None = None,
        launch_at_login_enabled: bool | None = None,
    ) -> DesktopSnapshot:
        notifications = (
            self._decision_notifications_enabled
            if decision_notifications_enabled is None
            else decision_notifications_enabled
        )
        launch = (
            self._launch_at_login_enabled
            if launch_at_login_enabled is None
            else launch_at_login_enabled
        )
        if self._preference_writer is not None:
            self._preference_writer(
                background_enabled,
                aggregate_reporting_enabled,
                notifications,
                launch,
            )
        self._background_enabled = background_enabled
        self._reporting_enabled = aggregate_reporting_enabled
        self._decision_notifications_enabled = notifications
        self._launch_at_login_enabled = launch
        return self.load()

    def approve(
        self,
        *,
        queue_id: str,
        proposal_digest: str,
        scope: Scope | None = None,
    ) -> ActionResult:
        return self._mutate(
            "approve",
            lambda: self._backend.decide_review(
                queue_id=queue_id,
                proposal_digest=proposal_digest,
                decision=ApprovalDecision.APPROVED,
                confirm_future_use=True,
                refined_scope=scope,
            ),
        )

    def reject(self, *, queue_id: str, proposal_digest: str) -> ActionResult:
        return self._mutate(
            "reject",
            lambda: self._backend.decide_review(
                queue_id=queue_id,
                proposal_digest=proposal_digest,
                decision=ApprovalDecision.REJECTED,
                confirm_future_use=False,
                refined_scope=None,
            ),
        )

    def revoke(self, *, artifact_id: str, artifact_digest: str) -> ActionResult:
        current = next(
            (item for item in self.load().adaptations if item.artifact_id == artifact_id),
            None,
        )
        if current is None or str(current.artifact_digest) != artifact_digest:
            return self._failure(
                "revoke", "artifact_changed", "This adaptation changed; review it again."
            )
        return self._mutate("revoke", lambda: self._backend.revoke(artifact_id=artifact_id))

    def undo(
        self,
        *,
        notice_id: str,
        notice_digest: str,
        artifact_id: str,
    ) -> ActionResult:
        current = next(
            (
                item
                for item in self.load().recent_undos
                if item.notice_id == notice_id and item.artifact_id == artifact_id
            ),
            None,
        )
        if current is None or str(current.notice_digest) != notice_digest:
            return self._failure("undo", "undo_expired", "This undo is no longer available.")
        return self._mutate("undo", lambda: self._backend.revoke(artifact_id=artifact_id))

    def renew_consent(self) -> ActionResult:
        return self._mutate("renew", self._backend.renew_consent)

    def feedback(
        self,
        *,
        activation_id: str,
        delivery_receipt_digest: str,
        outcome: RuntimeFeedbackOutcome,
    ) -> ActionResult:
        current = next(
            (
                item
                for item in self.load().activation_feedback
                if item.activation_id == activation_id
            ),
            None,
        )
        if current is None or str(current.delivery_receipt_digest) != delivery_receipt_digest:
            return self._failure(
                "feedback", "activation_changed", "This activation changed; review it again."
            )
        return self._mutate(
            "feedback",
            lambda: self._backend.feedback(
                activation_id=activation_id,
                delivery_receipt_digest=delivery_receipt_digest,
                outcome=outcome,
            ),
        )

    def run_task(
        self,
        *,
        task: str,
        project_id: str,
        mode_id: str | None = None,
    ) -> tuple[ActionResult, DesktopTaskResult | None]:
        if not task.strip():
            return self._failure("run_task", "invalid_task", "Enter a task before running."), None
        try:
            result = (
                self._backend.run_task(task=task, project_id=project_id)
                if mode_id is None
                else self._backend.run_task(task=task, project_id=project_id, mode_id=mode_id)
            )
            review = (
                None
                if result.status != "review_available"
                else self._backend.change_review(session_id=result.activation_id)
            )
        except (OSError, ValueError, RuntimeConformanceError) as error:
            return self._safe_exception("run_task", error), None
        task_result = DesktopTaskResult(
            activation_id=result.activation_id,
            status=result.status,
            projection_utf8_bytes=result.material_utf8_bytes,
            final_message=result.final_message,
            change_review=review,
        )
        message = (
            "Changes are ready for review; your project is unchanged."
            if result.status == "review_available"
            else "Task completed in a fresh governed session."
        )
        action = self._success("run_task", message)
        return action, task_result

    def apply_changes(self, *, session_id: str, expected_head: str) -> ActionResult:
        return self._mutate(
            "apply_changes",
            lambda: self._backend.apply_changes(
                session_id=session_id,
                expected_head=expected_head,
            ),
        )

    def discard_changes(self, *, session_id: str) -> ActionResult:
        return self._mutate(
            "discard_changes",
            lambda: self._backend.discard_changes(session_id=session_id),
        )

    def _mutate(self, action: DesktopAction, operation: Callable[[], None]) -> ActionResult:
        try:
            operation()
        except (OSError, ValueError, RuntimeConformanceError) as error:
            return self._safe_exception(action, error)
        return self._success(action, "Your change was saved.")

    def _success(self, action: DesktopAction, message: str) -> ActionResult:
        snapshot = self.load()
        return ActionResult(
            action=action,
            ok=True,
            code="ok",
            message=message,
            snapshot_digest=snapshot.content_digest,
        )

    @staticmethod
    def _failure(action: DesktopAction, code: str, message: str) -> ActionResult:
        return ActionResult(action=action, ok=False, code=code, message=message)

    @classmethod
    def _safe_exception(cls, action: DesktopAction, error: Exception) -> ActionResult:
        code = type(error).__name__.replace("Error", "").lower() or "operation_failed"
        safe_messages = {
            "automaticruntime": "The governed runtime refused this operation.",
            "credentialstore": "Local credentials are unavailable.",
            "runtimeconformance": "The installed Codex version does not match the release pin.",
        }
        return cls._failure(
            action,
            code,
            safe_messages.get(code, "The operation could not be completed safely."),
        )
