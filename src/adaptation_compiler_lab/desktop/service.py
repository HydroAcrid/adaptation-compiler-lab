"""Typed desktop service over the existing governed Codex dogfood runtime."""

from __future__ import annotations

import base64
import difflib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    FreshCodexTaskResult,
    _gateway_ledger,
    _gateway_project,
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
    ConsentStatus,
    DesktopAction,
    DesktopChangeReview,
    DesktopHealth,
    DesktopProject,
    DesktopSnapshot,
    DesktopTaskResult,
)
from adaptation_compiler_lab.domain import ApprovalDecision, Scope


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
    """Narrow seam that keeps QML, tests, and future adapters out of persistence."""

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

    def feedback(self, *, activation_id: str, outcome: RuntimeFeedbackOutcome) -> None: ...

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

    def feedback(self, *, activation_id: str, outcome: RuntimeFeedbackOutcome) -> None:
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
        session_id = execute_governed_gateway_task(
            self.config_path,
            task=task,
            project_id=project_id,
            mode_id=mode_id,
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
            "refine_task_class": None,
            "refine_environment_id": None,
            "refine_activation_condition": None,
            "refine_exclusion": None,
        }
    return {
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
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._backend = backend
        self._background_enabled = background_enabled
        self._reporting_enabled = aggregate_reporting_enabled
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
            terminal=terminal,
            projects=projects,
            generated_at=now,
        )

    def poll(self) -> ActionResult:
        return self._mutate("poll", self._backend.poll)

    def set_local_preferences(
        self,
        *,
        background_enabled: bool,
        aggregate_reporting_enabled: bool,
    ) -> DesktopSnapshot:
        self._background_enabled = background_enabled
        self._reporting_enabled = aggregate_reporting_enabled
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

    def revoke(self, *, artifact_id: str) -> ActionResult:
        return self._mutate("revoke", lambda: self._backend.revoke(artifact_id=artifact_id))

    def renew_consent(self) -> ActionResult:
        return self._mutate("renew", self._backend.renew_consent)

    def feedback(
        self,
        *,
        activation_id: str,
        outcome: RuntimeFeedbackOutcome,
    ) -> ActionResult:
        return self._mutate(
            "feedback",
            lambda: self._backend.feedback(activation_id=activation_id, outcome=outcome),
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
