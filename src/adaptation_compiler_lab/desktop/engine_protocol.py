"""Versioned raw-free stdio protocol for the Temper desktop engine."""

from __future__ import annotations

import json
import os
import platform
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, Final, Literal, TextIO

from pydantic import Field

from adaptation_compiler_lab.automatic_runtime.models import RuntimeFeedbackOutcome
from adaptation_compiler_lab.desktop.models import (
    ActionResult,
    ActivationFeedbackSummaryV1,
    AdaptationSummaryV1,
    DesktopSnapshot,
    DiagnosticsSummaryV1,
    MutationReceiptV1,
    ProjectCandidatePreviewV1,
    RecentUndoSummaryV1,
    SetupCompletionReceiptV1,
    SetupSnapshotV1,
    SuggestionDecisionRequestV1,
    SuggestionSummaryV1,
)
from adaptation_compiler_lab.domain import (
    ApprovalDecision,
    FrozenModel,
    NonEmptyStr,
    Scope,
    Sha256Digest,
)
from adaptation_compiler_lab.instruction_environment.models import (
    InstructionChangePreviewV1,
    InstructionChangeReceiptV1,
    InstructionEnvironmentSummaryV1,
    InstructionGlobalPreviewV1,
    InstructionSourceSummaryV1,
    NativeTarget,
)
from adaptation_compiler_lab.modes import MODE_CATALOG, evaluate_mode_conformance
from adaptation_compiler_lab.portability import (
    EncryptedProfileEnvelope,
    PackageImportPreviewV1,
    PackageReviewDecisionReceiptV1,
    PackageReviewItemV1,
    PersonalModeOverlayV1,
    PortableProfilePackage,
    ShareablePackage,
)
from adaptation_compiler_lab.serialization import canonical_digest

if TYPE_CHECKING:
    from adaptation_compiler_lab.claude_delivery.connection import ClaudeConnectionService
    from adaptation_compiler_lab.desktop.portability_service import LocalProfilePortabilityService
    from adaptation_compiler_lab.desktop.service import DesktopApplicationService
    from adaptation_compiler_lab.desktop.setup_service import DesktopSetupApplicationService
    from adaptation_compiler_lab.instruction_environment.service import (
        InstructionEnvironmentService,
    )

PROTOCOL_VERSION: Final[Literal["temper-engine-protocol/v1"]] = "temper-engine-protocol/v1"
MAX_FRAME_BYTES = 1_048_576
PREVIEW_TTL_SECONDS = 15 * 60


class EngineRequest(FrozenModel):
    """One renderer-independent engine request."""

    protocol_version: Literal["temper-engine-protocol/v1"]
    request_id: NonEmptyStr
    method: NonEmptyStr
    params: Mapping[str, Any] = Field(default_factory=dict)
    expected_snapshot_digest: Sha256Digest | None = None
    idempotency_key: NonEmptyStr | None = None


class EngineError(FrozenModel):
    """Stable error safe to expose to the renderer."""

    code: NonEmptyStr
    message: NonEmptyStr
    retryable: bool = False


class EngineResponse(FrozenModel):
    """One response carrying either a raw-free result or a sanitized error."""

    protocol_version: Literal["temper-engine-protocol/v1"] = PROTOCOL_VERSION
    request_id: NonEmptyStr
    ok: bool
    result: Mapping[str, Any] | None = None
    error: EngineError | None = None
    snapshot_digest: Sha256Digest | None = None


class EngineHandshake(FrozenModel):
    """Immutable compatibility statement checked before any engine operation."""

    protocol_version: Literal["temper-engine-protocol/v1"] = PROTOCOL_VERSION
    engine_version: NonEmptyStr
    snapshot_schema_digest: Sha256Digest
    mutation_enabled: bool
    configured: bool
    setup_available: Literal[True] = True
    configuration_state: Literal["unconfigured", "configured"]
    platform: Literal["windows", "macos", "development"]
    architecture: NonEmptyStr


def snapshot_schema_digest() -> Sha256Digest:
    """Return a deterministic digest of the renderer-visible snapshot contract."""

    return canonical_digest(DesktopSnapshot.model_json_schema())


class EngineProtocolRouter:
    """Fail-closed dispatcher with no generic filesystem or process methods."""

    def __init__(
        self,
        service: DesktopApplicationService | None,
        portability: LocalProfilePortabilityService | None = None,
        setup_factory: Callable[[], DesktopSetupApplicationService] | None = None,
        instruction_factory: Callable[[], InstructionEnvironmentService] | None = None,
        claude_hook_handler: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
        claude_connection: ClaudeConnectionService | None = None,
        claude_projection_refresher: Callable[[], object] | None = None,
    ) -> None:
        self._service = service
        self._portability = portability
        self._setup_factory = setup_factory
        self._instruction_factory = instruction_factory
        self._claude_hook_handler = claude_hook_handler
        self._claude_connection = claude_connection
        self._claude_projection_refresher = claude_projection_refresher
        self._setup: DesktopSetupApplicationService | None = None
        self._instruction_environment: InstructionEnvironmentService | None = None
        self._export_previews: dict[str, tuple[float, PortableProfilePackage]] = {}
        self._import_previews: dict[str, tuple[float, EncryptedProfileEnvelope]] = {}
        self._package_export_previews: dict[str, tuple[float, ShareablePackage]] = {}
        self._package_import_previews: dict[
            str, tuple[float, ShareablePackage, PackageImportPreviewV1]
        ] = {}
        self._mutation_results: dict[str, tuple[Sha256Digest, EngineResponse]] = {}

    def handle(self, request: EngineRequest) -> EngineResponse:
        if request.method == "system.handshake":
            handshake = EngineHandshake(
                engine_version=version("adaptation-compiler-lab"),
                snapshot_schema_digest=snapshot_schema_digest(),
                mutation_enabled=self._service is not None,
                configured=self._service is not None,
                configuration_state=("configured" if self._service is not None else "unconfigured"),
                platform=_host_platform(),
                architecture=platform.machine() or "unknown",
            )
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result=handshake.model_dump(mode="json"),
            )
        if request.method == "claude.hook.handle":
            return self._handle_claude_hook(request)
        if request.method == "claude.runtime.refresh":
            return self._refresh_claude_runtime(request)
        if request.method in {"setup.status", "connection.inspect"}:
            if request.params:
                return self._error(
                    request,
                    "invalid_params",
                    f"{request.method} takes no parameters.",
                )
            try:
                setup_snapshot = self._connection_snapshot(self._setup_service().snapshot())
            except (OSError, ValueError):
                return self._error(
                    request,
                    "setup_unavailable",
                    "Temper could not safely inspect this installation.",
                    retryable=True,
                )
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result=setup_snapshot.model_dump(mode="json"),
                snapshot_digest=setup_snapshot.content_digest,
            )
        if request.method == "connection.claude.preview":
            return self._preview_claude_connection(request)
        if request.method == "connection.claude.apply":
            return self._apply_claude_connection(request)
        if request.method == "setup.existing.preview":
            try:
                if set(request.params) != {"path"}:
                    raise ValueError
                token, summary = self._setup_service().preview_existing(
                    Path(_required_string(request.params, "path"))
                )
            except (OSError, ValueError):
                return self._error(
                    request,
                    "existing_installation_invalid",
                    "Temper could not safely preview that existing installation.",
                )
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result={
                    "preview_token": token,
                    "installation": summary.model_dump(mode="json"),
                    "raw_payloads_exposed": False,
                },
            )
        if request.method == "setup.existing.adopt":
            return self._adopt_existing(request)
        if request.method in {"setup.project.preview", "project.registration.preview"}:
            try:
                if set(request.params) != {"path"}:
                    raise ValueError
                preview = self._setup_service().preview_project(
                    Path(_required_string(request.params, "path"))
                )
            except (OSError, ValueError):
                return self._error(
                    request,
                    "project_invalid",
                    "Temper could not safely preview that project.",
                )
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result=preview.model_dump(mode="json"),
            )
        if request.method == "setup.initialize":
            return self._initialize_setup(request)
        if request.method == "project.register":
            checked = self._mutation_request(request)
            if isinstance(checked, EngineResponse):
                return checked
            _snapshot_digest, fingerprint = checked
            try:
                if set(request.params) != {"preview_token"}:
                    raise ValueError
                preview = self._setup_service().register_project(
                    preview_token=_required_string(request.params, "preview_token")
                )
                if self._service is None:
                    raise ValueError
                current = self._service.load()
                self._instruction_environment = None
            except (OSError, ValueError):
                return self._error(
                    request,
                    "project_registration_refused",
                    "Temper could not safely register that project.",
                )
            response = EngineResponse(
                request_id=request.request_id,
                ok=True,
                result={
                    "project_id": preview.project_id,
                    "display_name": preview.display_name,
                    "capture_after_epoch_seconds": preview.capture_after_epoch_seconds,
                    "historical_tasks_eligible": False,
                    "raw_payloads_exposed": False,
                },
                snapshot_digest=current.content_digest,
            )
            return self._remember_mutation(request, fingerprint, response)
        if request.method == "instruction_environment.get":
            return self._instruction_environment_get(request)
        if request.method == "instruction_environment.refresh":
            return self._instruction_environment_refresh(request)
        if request.method == "instruction_environment.analyze":
            return self._instruction_environment_analyze(request)
        if request.method == "instruction_environment.reconcile":
            return self._instruction_environment_reconcile(request)
        if request.method == "instruction_environment.adoption.preview":
            return self._instruction_adoption_preview(request)
        if request.method == "instruction_environment.global.preview":
            return self._instruction_global_preview(request)
        if request.method == "instruction_environment.global.enable":
            return self._instruction_global_enable(request)
        if request.method == "instruction_environment.global.disable":
            return self._instruction_global_disable(request)
        if request.method == "instruction_environment.change.preview":
            return self._instruction_change_preview(request)
        if request.method == "instruction_environment.change.apply":
            return self._instruction_change_apply(request)
        if request.method == "instruction_environment.change.rollback":
            return self._instruction_change_rollback(request)
        if request.method == "snapshot.get":
            if self._service is None:
                return self._error(
                    request,
                    "not_configured",
                    "Temper needs a governed local setup before it can load live state.",
                )
            if request.params:
                return self._error(request, "invalid_params", "snapshot.get takes no parameters.")
            try:
                snapshot = self._service.load()
            except (OSError, ValueError):
                return self._error(
                    request,
                    "snapshot_unavailable",
                    "Temper could not safely read the governed local state.",
                    retryable=True,
                )
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result=snapshot.model_dump(mode="json"),
                snapshot_digest=snapshot.content_digest,
            )
        if request.method == "learning.poll":
            return self._run_simple_mutation(request, (), "learning", self._service_poll)
        if request.method == "review.decide":
            return self._decide_review(request)
        if request.method == "adaptation.revoke":
            return self._revoke_adaptation(request)
        if request.method == "adaptation.undo":
            return self._undo_adaptation(request)
        if request.method == "feedback.record":
            return self._record_feedback(request)
        if request.method == "consent.renew":
            return self._renew_consent(request)
        if request.method == "preferences.update":
            return self._update_preferences(request)
        if request.method == "portability.export.preview":
            return self._preview_export(request)
        if request.method == "portability.export.create":
            return self._create_export(request)
        if request.method == "portability.import.preview":
            return self._preview_import(request)
        if request.method == "portability.import.stage":
            return self._stage_import(request)
        if request.method == "package.export.preview":
            return self._preview_package_export(request)
        if request.method == "package.export.create":
            return self._create_package_export(request)
        if request.method == "package.import.preview":
            return self._preview_package_import(request)
        if request.method == "package.import.stage":
            return self._stage_package_import(request)
        if request.method == "package.review.list":
            return self._list_package_reviews(request)
        if request.method == "package.review.decide":
            return self._decide_package_review(request)
        if request.method == "mode.task.run":
            return self._run_mode_task(request)
        if request.method == "task.run":
            return self._run_task(request)
        if request.method == "task.apply":
            return self._apply_task(request)
        if request.method == "task.discard":
            return self._discard_task(request)
        if request.method == "diagnostics.get":
            return self._diagnostics(request)
        if request.method == "mode.list":
            if request.params:
                return self._error(request, "invalid_params", "mode.list takes no parameters.")
            modes = list(MODE_CATALOG)
            overlays: tuple[PersonalModeOverlayV1, ...] = ()
            if self._portability is not None:
                try:
                    modes.extend(self._portability.accepted_imported_modes())
                    overlays = self._portability.accepted_personal_overlays()
                except (OSError, ValueError):
                    return self._error(
                        request,
                        "mode_catalog_unavailable",
                        "Temper could not safely verify the local Mode catalog.",
                    )
            if len({mode.mode_id for mode in modes}) != len(modes):
                return self._error(
                    request,
                    "mode_catalog_conflict",
                    "An imported Mode conflicts with the local catalog.",
                )
            catalog = tuple((mode, evaluate_mode_conformance(mode)) for mode in modes)
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result={
                    "modes": tuple(
                        {
                            "mode_id": mode.mode_id,
                            "mode_version": mode.mode_version,
                            "name": mode.name,
                            "summary": mode.summary,
                            "publisher": mode.publisher,
                            "source_license": mode.source_license,
                            "activation_default": mode.activation_default,
                            "task_lease_hours": mode.task_lease_hours,
                            "supports_personal_overlay": mode.supports_personal_overlay,
                            "applicable_task_classes": list(mode.applicable_task_classes),
                            "compatible_target_families": list(mode.compatible_target_families),
                            "requested_tools": list(mode.requested_tools),
                            "required_capabilities": list(mode.required_capabilities),
                            "evaluation_status": mode.evaluation_status.value,
                            "effectiveness_evaluated": (
                                mode.evaluation_status.value == "product_evaluated"
                            ),
                            "projection_utf8_bytes": report.projection_utf8_bytes,
                            "evaluation_valid": report.valid,
                            "evaluation_case_count": len(report.cases),
                            "mutates_permanent_core": False,
                            "auto_activates": False,
                            "source_kind": mode.source_kind,
                            "personalized": any(
                                overlay.base_mode_id == mode.mode_id
                                and overlay.base_mode_version == mode.mode_version
                                and overlay.base_mode_digest == mode.content_digest
                                for overlay in overlays
                            ),
                        }
                        for mode, report in catalog
                    ),
                    "raw_payloads_exposed": False,
                },
            )
        return self._error(request, "unknown_method", "The requested operation is not supported.")

    def _handle_claude_hook(self, request: EngineRequest) -> EngineResponse:
        try:
            if set(request.params) != {"payload"}:
                raise ValueError
            payload = request.params["payload"]
            if not isinstance(payload, Mapping):
                raise ValueError
            output = (
                None if self._claude_hook_handler is None else self._claude_hook_handler(payload)
            )
            if output is not None and not isinstance(output, Mapping):
                raise ValueError
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "claude_hook_unavailable",
                "Temper could not safely handle this Claude event.",
                retryable=True,
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "available": self._claude_hook_handler is not None,
                "output": output,
                "raw_payloads_exposed": False,
            },
        )

    def _refresh_claude_runtime(self, request: EngineRequest) -> EngineResponse:
        if request.params:
            return self._error(
                request,
                "invalid_params",
                "claude.runtime.refresh takes no parameters.",
            )
        if self._claude_projection_refresher is None:
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result={
                    "available": False,
                    "prepared_projection_count": 0,
                    "raw_payloads_exposed": False,
                },
            )
        try:
            leases = self._claude_projection_refresher()
            prepared = len(leases) if isinstance(leases, Sequence) else 0
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "claude_runtime_refresh_refused",
                "Temper could not safely refresh Claude delivery.",
                retryable=True,
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "available": True,
                "prepared_projection_count": prepared,
                "raw_payloads_exposed": False,
            },
        )

    def _connection_snapshot(self, snapshot: SetupSnapshotV1) -> SetupSnapshotV1:
        if self._claude_connection is None:
            unavailable_connections = tuple(
                item.model_copy(
                    update={
                        "integration_state": "unavailable",
                        "available_actions": ("refresh",),
                        "status_summary": (
                            "Claude Code was detected, but this Temper runtime cannot connect it."
                            if item.agent_id == "claude" and item.installation_state == "installed"
                            else item.status_summary
                        ),
                    }
                )
                if item.agent_id == "claude"
                else item
                for item in snapshot.connections
            )
            return snapshot.model_copy(update={"connections": unavailable_connections})
        status = self._claude_connection.status()
        mutable_connections = list(snapshot.connections)
        claude_index = next(
            (index for index, item in enumerate(mutable_connections) if item.agent_id == "claude"),
            None,
        )
        if claude_index is None:
            return snapshot
        claude = mutable_connections[claude_index]
        if status.state == "connected":
            runtime_ready = (
                claude.installation_state == "installed"
                and claude.authentication_state == "signed_in"
                and claude.conformance_state == "compatible"
                and self._claude_hook_handler is not None
            )
            mutable_connections[claude_index] = claude.model_copy(
                update={
                    "integration_state": "connected" if runtime_ready else "attention",
                    "status_summary": (
                        status.status_summary
                        if runtime_ready
                        else "Claude changed after connection; delivery is paused."
                    ),
                    "learning_capability": (
                        "Captures authorized user prompts from registered projects."
                        if runtime_ready
                        else "Learning is paused until the Claude connection is repaired."
                    ),
                    "delivery_capability": (
                        "Delivers only a signed cached projection in registered projects."
                        if runtime_ready
                        else "Delivery is paused until the Claude connection is repaired."
                    ),
                    "available_actions": ("refresh", "disconnect"),
                }
            )
        elif status.state == "attention":
            mutable_connections[claude_index] = claude.model_copy(
                update={
                    "integration_state": "attention",
                    "status_summary": status.status_summary,
                    "learning_capability": (
                        "Learning is paused until this connection is removed or repaired."
                    ),
                    "delivery_capability": (
                        "Delivery is paused until this connection is removed or repaired."
                    ),
                    "available_actions": ("refresh", "disconnect"),
                }
            )
        return snapshot.model_copy(update={"connections": tuple(mutable_connections)})

    def _preview_claude_connection(self, request: EngineRequest) -> EngineResponse:
        if self._service is None or self._claude_connection is None:
            return self._error(
                request,
                "claude_connection_unavailable",
                "Claude connection is unavailable in this Temper installation.",
            )
        try:
            if set(request.params) != {"operation"}:
                raise ValueError
            operation = _required_string(request.params, "operation")
            if operation not in {"connect", "disconnect"}:
                raise ValueError
            snapshot = self._connection_snapshot(self._setup_service().snapshot())
            claude = next(item for item in snapshot.connections if item.agent_id == "claude")
            expected_action = "connect" if operation == "connect" else "disconnect"
            if expected_action not in claude.available_actions:
                return self._error(
                    request,
                    "claude_connection_unavailable",
                    "Claude is not in a state where Temper can make that change.",
                )
            selected_operation: Literal["connect", "disconnect"] = (
                "connect" if operation == "connect" else "disconnect"
            )
            preview = self._claude_connection.preview(operation=selected_operation)
        except (OSError, StopIteration, TypeError, ValueError):
            return self._error(
                request,
                "claude_connection_preview_refused",
                "Temper could not safely preview that Claude connection change.",
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=preview.model_dump(mode="json"),
        )

    def _apply_claude_connection(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, fingerprint = checked
        if self._claude_connection is None or request.idempotency_key is None:
            return self._error(
                request,
                "claude_connection_unavailable",
                "Claude connection is unavailable in this Temper installation.",
            )
        try:
            if set(request.params) != {
                "preview_token",
                "expected_before_digest",
                "consent_confirmed",
            }:
                raise ValueError
            consent_confirmed = request.params.get("consent_confirmed")
            if not isinstance(consent_confirmed, bool):
                raise ValueError
            receipt = self._claude_connection.apply(
                preview_token=_required_string(request.params, "preview_token"),
                expected_before_digest=_required_string(request.params, "expected_before_digest"),
                consent_confirmed=consent_confirmed,
                idempotency_key=request.idempotency_key,
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "claude_connection_change_refused",
                "Temper could not safely apply that Claude connection change.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "receipt_id": receipt.receipt_id,
                "operation": receipt.operation,
                "connection_digest": receipt.content_digest,
                "expires_at": receipt.expires_at.isoformat(),
                "project_count": len(receipt.projects),
                "restart_required": True,
                "provider_call_required": False,
                "raw_payloads_exposed": False,
            },
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, fingerprint, response)

    def _instruction_environment_get(self, request: EngineRequest) -> EngineResponse:
        if self._service is None:
            return self._not_configured(request)
        try:
            instruction_service = self._instruction_service()
            if not request.params:
                summaries = instruction_service.summaries()
            else:
                if set(request.params) != {"project_id", "target"}:
                    raise ValueError
                summaries = (
                    instruction_service.summary(
                        project_id=_required_string(request.params, "project_id"),
                        target=NativeTarget(_required_string(request.params, "target")),
                    ),
                )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "instruction_environment_unavailable",
                "Temper could not safely inspect existing agent instructions.",
                retryable=True,
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "environments": [item.model_dump(mode="json") for item in summaries],
                "raw_payloads_exposed": False,
            },
        )

    def _instruction_environment_refresh(self, request: EngineRequest) -> EngineResponse:
        if self._service is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"project_id", "target"}:
                raise ValueError
            project_id = _required_string(request.params, "project_id")
            target = NativeTarget(_required_string(request.params, "target"))
            instruction_service = self._instruction_service()
            instruction_service.refresh(project_id=project_id, target=target)
            summary = instruction_service.summary(project_id=project_id, target=target)
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "instruction_environment_refresh_failed",
                "Temper could not safely refresh existing agent instructions.",
                retryable=True,
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=summary.model_dump(mode="json"),
        )

    def _instruction_environment_analyze(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, fingerprint = checked
        try:
            if set(request.params) != {"project_id", "target"}:
                raise ValueError
            project_id = _required_string(request.params, "project_id")
            target = NativeTarget(_required_string(request.params, "target"))
            instruction_service = self._instruction_service()
            instruction_service.analyze(project_id=project_id, target=target)
            summary = instruction_service.summary(project_id=project_id, target=target)
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "instruction_analysis_unavailable",
                "Temper could not complete isolated semantic setup analysis.",
                retryable=True,
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=summary.model_dump(mode="json"),
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, fingerprint, response)

    def _instruction_environment_reconcile(self, request: EngineRequest) -> EngineResponse:
        if self._service is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"project_id", "target"}:
                raise ValueError
            plan = self._instruction_service().reconciliation(
                project_id=_required_string(request.params, "project_id"),
                target=NativeTarget(_required_string(request.params, "target")),
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "instruction_reconciliation_unavailable",
                "Temper could not safely reconcile this agent's current memory and instructions.",
                retryable=True,
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=plan.model_dump(mode="json"),
        )

    def _instruction_adoption_preview(self, request: EngineRequest) -> EngineResponse:
        if self._service is None:
            return self._not_configured(request)
        if request.expected_snapshot_digest is None:
            return self._error(
                request,
                "snapshot_binding_required",
                "Review the current Temper state before adopting observed native context.",
            )
        try:
            if set(request.params) != {"project_id", "target", "native_clause_id"}:
                raise ValueError
            current = self._service.load()
            if current.content_digest != request.expected_snapshot_digest:
                return self._error(
                    request,
                    "stale_snapshot",
                    "Temper changed; review the current state before adopting native context.",
                )
            preview = self._instruction_service().preview_adoption(
                project_id=_required_string(request.params, "project_id"),
                target=NativeTarget(_required_string(request.params, "target")),
                native_clause_id=_required_string(request.params, "native_clause_id"),
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "native_adoption_preview_refused",
                "Temper could not safely preview that observed native behavior.",
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=preview.model_dump(mode="json"),
            snapshot_digest=request.expected_snapshot_digest,
        )

    def _instruction_global_preview(self, request: EngineRequest) -> EngineResponse:
        if self._service is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"path", "target"}:
                raise ValueError
            preview = self._instruction_service().preview_global(
                target=NativeTarget(_required_string(request.params, "target")),
                root=Path(_required_string(request.params, "path")),
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "personal_instruction_preview_refused",
                "Temper could not safely preview that personal agent setup.",
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=preview.model_dump(mode="json"),
        )

    def _instruction_global_enable(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, fingerprint = checked
        try:
            if (
                set(request.params) != {"preview_token", "target"}
                or request.idempotency_key is None
            ):
                raise ValueError
            summaries = self._instruction_service().enable_global(
                preview_token=_required_string(request.params, "preview_token"),
                target=NativeTarget(_required_string(request.params, "target")),
                idempotency_key=request.idempotency_key,
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "personal_instruction_enable_refused",
                "Temper could not safely enable personal agent inspection.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "environments": [item.model_dump(mode="json") for item in summaries],
                "raw_payloads_exposed": False,
            },
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, fingerprint, response)

    def _instruction_global_disable(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, fingerprint = checked
        try:
            if set(request.params) != {"target"} or request.idempotency_key is None:
                raise ValueError
            summaries = self._instruction_service().disable_global(
                target=NativeTarget(_required_string(request.params, "target")),
                idempotency_key=request.idempotency_key,
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "personal_instruction_disable_refused",
                "Temper could not safely disable personal agent inspection.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "environments": [item.model_dump(mode="json") for item in summaries],
                "raw_payloads_exposed": False,
            },
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, fingerprint, response)

    def _instruction_change_preview(self, request: EngineRequest) -> EngineResponse:
        if self._service is None:
            return self._not_configured(request)
        if request.expected_snapshot_digest is None:
            return self._error(
                request,
                "snapshot_binding_required",
                "Review the current Temper state before previewing this edit.",
            )
        try:
            if set(request.params) != {
                "project_id",
                "target",
                "source_id",
                "expected_environment_digest",
                "instruction_text",
            }:
                raise ValueError
            current = self._service.load()
            if current.content_digest != request.expected_snapshot_digest:
                return self._error(
                    request,
                    "stale_snapshot",
                    "Temper changed; review the current state before editing instructions.",
                )
            raw_text = request.params.get("instruction_text")
            if raw_text is not None and not isinstance(raw_text, str):
                raise ValueError
            preview = self._instruction_service().preview_change(
                project_id=_required_string(request.params, "project_id"),
                target=NativeTarget(_required_string(request.params, "target")),
                source_id=_required_string(request.params, "source_id"),
                expected_environment_digest=_required_string(
                    request.params, "expected_environment_digest"
                ),
                instruction_text=raw_text,
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "native_instruction_preview_refused",
                "Temper could not safely preview that native instruction edit.",
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=preview.model_dump(mode="json"),
            snapshot_digest=request.expected_snapshot_digest,
        )

    def _instruction_change_apply(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, fingerprint = checked
        try:
            if (
                set(request.params) != {"preview_token", "target", "expected_environment_digest"}
                or request.idempotency_key is None
            ):
                raise ValueError
            receipt = self._instruction_service().apply_change(
                preview_token=_required_string(request.params, "preview_token"),
                target=NativeTarget(_required_string(request.params, "target")),
                expected_environment_digest=_required_string(
                    request.params, "expected_environment_digest"
                ),
                idempotency_key=request.idempotency_key,
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "native_instruction_write_refused",
                "Existing instructions changed or could not be updated safely.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=receipt.model_dump(mode="json"),
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, fingerprint, response)

    def _instruction_change_rollback(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, fingerprint = checked
        try:
            if (
                set(request.params) != {"receipt_id", "target", "expected_environment_digest"}
                or request.idempotency_key is None
            ):
                raise ValueError
            receipt = self._instruction_service().rollback_change(
                receipt_id=_required_string(request.params, "receipt_id"),
                target=NativeTarget(_required_string(request.params, "target")),
                expected_environment_digest=_required_string(
                    request.params, "expected_environment_digest"
                ),
                idempotency_key=request.idempotency_key,
            )
        except (OSError, TypeError, ValueError):
            return self._error(
                request,
                "native_instruction_rollback_refused",
                "Temper could not safely restore that native instruction source.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=receipt.model_dump(mode="json"),
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, fingerprint, response)

    def _instruction_service(self) -> InstructionEnvironmentService:
        if self._instruction_environment is None:
            if self._instruction_factory is None:
                raise ValueError("instruction environment service is unavailable")
            self._instruction_environment = self._instruction_factory()
        return self._instruction_environment

    def _service_poll(self) -> ActionResult:
        if self._service is None:
            raise ValueError
        return self._service.poll()

    def _run_simple_mutation(
        self,
        request: EngineRequest,
        allowed_params: tuple[str, ...],
        target_id: str,
        operation: Callable[[], ActionResult],
    ) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if set(request.params) != set(allowed_params):
            return self._error(request, "invalid_params", "The mutation request was invalid.")
        action = operation()
        return self._action_response(request, fingerprint, target_id, action)

    def _decide_review(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            allowed = {"queue_id", "proposal_digest", "decision"}
            decision_name = _required_string(request.params, "decision")
            if decision_name == "keep_project":
                allowed.add("project_id")
            elif decision_name == "keep_narrowed":
                allowed.add("refined_scope")
            if set(request.params) != allowed:
                raise ValueError
            decision_payload = dict(request.params)
            if "refined_scope" in decision_payload:
                decision_payload["refined_scope"] = Scope.model_validate(
                    decision_payload["refined_scope"], strict=False
                )
            decision = SuggestionDecisionRequestV1.model_validate(decision_payload)
            if decision.decision in {
                "keep_suggested",
                "keep_project",
                "keep_narrowed",
                "approve_revocation",
            }:
                refined_scope = decision.refined_scope
                if decision.decision == "keep_project":
                    current = next(
                        (
                            item
                            for item in self._service.load().suggestions
                            if item.queue_id == decision.queue_id
                            and item.proposal_digest == decision.proposal_digest
                        ),
                        None,
                    )
                    if current is None:
                        raise ValueError
                    refined_scope = current.suggested_scope.model_copy(
                        update={"project_ids": (str(decision.project_id),)}
                    )
                action = self._service.approve(
                    queue_id=decision.queue_id,
                    proposal_digest=str(decision.proposal_digest),
                    scope=refined_scope,
                )
            else:
                action = self._service.reject(
                    queue_id=decision.queue_id,
                    proposal_digest=str(decision.proposal_digest),
                )
        except (TypeError, ValueError):
            return self._error(request, "invalid_params", "The review decision was invalid.")
        return self._action_response(request, fingerprint, decision.queue_id, action)

    def _revoke_adaptation(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"artifact_id", "artifact_digest"}:
                raise ValueError
            artifact_id = _required_string(request.params, "artifact_id")
            artifact_digest = _required_string(request.params, "artifact_digest")
        except ValueError:
            return self._error(request, "invalid_params", "The revocation request was invalid.")
        action = self._service.revoke(
            artifact_id=artifact_id,
            artifact_digest=artifact_digest,
        )
        return self._action_response(request, fingerprint, artifact_id, action)

    def _undo_adaptation(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"notice_id", "notice_digest", "artifact_id"}:
                raise ValueError
            notice_id = _required_string(request.params, "notice_id")
            notice_digest = _required_string(request.params, "notice_digest")
            artifact_id = _required_string(request.params, "artifact_id")
        except ValueError:
            return self._error(request, "invalid_params", "The undo request was invalid.")
        action = self._service.undo(
            notice_id=notice_id,
            notice_digest=notice_digest,
            artifact_id=artifact_id,
        )
        return self._action_response(request, fingerprint, notice_id, action)

    def _record_feedback(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {
                "activation_id",
                "delivery_receipt_digest",
                "outcome",
            }:
                raise ValueError
            activation_id = _required_string(request.params, "activation_id")
            delivery_digest = _required_string(request.params, "delivery_receipt_digest")
            outcome = RuntimeFeedbackOutcome(_required_string(request.params, "outcome"))
        except ValueError:
            return self._error(request, "invalid_params", "The feedback request was invalid.")
        action = self._service.feedback(
            activation_id=activation_id,
            delivery_receipt_digest=delivery_digest,
            outcome=outcome,
        )
        return self._action_response(request, fingerprint, activation_id, action)

    def _renew_consent(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"current_expires_at"}:
                raise ValueError
            expires_at = _required_string(request.params, "current_expires_at")
            if self._service.load().consent.expires_at.isoformat() != expires_at:
                raise ValueError
        except ValueError:
            return self._error(request, "invalid_params", "The consent renewal was invalid.")
        return self._action_response(
            request,
            fingerprint,
            "local-consent",
            self._service.renew_consent(),
        )

    def _update_preferences(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        allowed = {
            "background_enabled",
            "aggregate_reporting_enabled",
            "decision_notifications_enabled",
            "launch_at_login_enabled",
        }
        if not set(request.params) <= allowed or not {
            "background_enabled",
            "aggregate_reporting_enabled",
        } <= set(request.params):
            return self._error(request, "invalid_params", "The preference request was invalid.")
        background = request.params.get("background_enabled")
        reporting = request.params.get("aggregate_reporting_enabled")
        notifications = request.params.get("decision_notifications_enabled")
        launch = request.params.get("launch_at_login_enabled")
        if (
            not isinstance(background, bool)
            or not isinstance(reporting, bool)
            or (notifications is not None and not isinstance(notifications, bool))
            or (launch is not None and not isinstance(launch, bool))
        ):
            return self._error(request, "invalid_params", "The preference request was invalid.")
        try:
            current = self._service.set_local_preferences(
                background_enabled=background,
                aggregate_reporting_enabled=reporting,
                decision_notifications_enabled=notifications,
                launch_at_login_enabled=launch,
            )
        except (OSError, ValueError):
            return self._error(request, "preferences_failed", "Temper could not save settings.")
        action = ActionResult(
            action="preferences",
            ok=True,
            code="ok",
            message="Your settings were saved.",
            snapshot_digest=current.content_digest,
        )
        return self._action_response(request, fingerprint, "local-preferences", action)

    def _action_response(
        self,
        request: EngineRequest,
        fingerprint: Sha256Digest,
        target_id: str,
        action: ActionResult,
    ) -> EngineResponse:
        if not action.ok or action.snapshot_digest is None:
            return self._error(request, action.code, action.message)
        receipt = MutationReceiptV1(
            action=action.action,
            target_id=target_id,
            code=action.code,
            message=action.message,
            resulting_snapshot_digest=action.snapshot_digest,
        )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=receipt.model_dump(mode="json"),
            snapshot_digest=action.snapshot_digest,
        )
        return self._remember_mutation(request, fingerprint, response)

    def _initialize_setup(self, request: EngineRequest) -> EngineResponse:
        if request.expected_snapshot_digest is None or request.idempotency_key is None:
            return self._error(
                request,
                "mutation_binding_required",
                "Review the current setup before trying again.",
            )
        fingerprint = canonical_digest(
            {
                "method": request.method,
                "params": request.params,
                "expected_snapshot_digest": request.expected_snapshot_digest,
            }
        )
        cached = self._mutation_results.get(request.idempotency_key)
        if cached is not None:
            if cached[0] != fingerprint:
                return self._error(
                    request,
                    "idempotency_conflict",
                    "This setup action identifier was already used for something else.",
                )
            return cached[1].model_copy(update={"request_id": request.request_id})
        try:
            if set(request.params) != {"preview_token", "consent_confirmed"}:
                raise ValueError
            consent_confirmed = request.params.get("consent_confirmed")
            if not isinstance(consent_confirmed, bool):
                raise ValueError
            receipt = self._setup_service().initialize(
                preview_token=_required_string(request.params, "preview_token"),
                expected_setup_digest=str(request.expected_snapshot_digest),
                consent_confirmed=consent_confirmed,
            )
        except (OSError, ValueError):
            return self._error(
                request,
                "setup_refused",
                "Temper could not safely complete this setup.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=receipt.model_dump(mode="json"),
        )
        return self._remember_mutation(request, fingerprint, response)

    def _adopt_existing(self, request: EngineRequest) -> EngineResponse:
        checked = self._setup_mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        try:
            if set(request.params) != {"preview_token"}:
                raise ValueError
            summary = self._setup_service().adopt_existing(
                preview_token=_required_string(request.params, "preview_token"),
                expected_setup_digest=str(request.expected_snapshot_digest),
            )
        except (OSError, ValueError):
            return self._error(
                request,
                "existing_installation_adoption_refused",
                "Temper could not safely adopt that existing installation.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "installation": summary.model_dump(mode="json"),
                "restart_required": True,
                "raw_payloads_exposed": False,
            },
        )
        return self._remember_mutation(request, fingerprint, response)

    def _setup_mutation_request(
        self, request: EngineRequest
    ) -> tuple[Sha256Digest, Sha256Digest] | EngineResponse:
        if request.expected_snapshot_digest is None or request.idempotency_key is None:
            return self._error(
                request,
                "mutation_binding_required",
                "Review the current setup before trying again.",
            )
        fingerprint = canonical_digest(
            {
                "method": request.method,
                "params": request.params,
                "expected_snapshot_digest": request.expected_snapshot_digest,
            }
        )
        cached = self._mutation_results.get(request.idempotency_key)
        if cached is not None:
            if cached[0] != fingerprint:
                return self._error(
                    request,
                    "idempotency_conflict",
                    "This setup action identifier was already used for something else.",
                )
            return cached[1].model_copy(update={"request_id": request.request_id})
        try:
            snapshot = self._setup_service().snapshot()
        except (OSError, ValueError):
            return self._error(
                request,
                "setup_unavailable",
                "Temper could not safely inspect this installation.",
                retryable=True,
            )
        if snapshot.content_digest != request.expected_snapshot_digest:
            return self._error(
                request,
                "stale_snapshot",
                "Temper changed since this preview; review the current setup and try again.",
            )
        return snapshot.content_digest, fingerprint

    def _setup_service(self) -> DesktopSetupApplicationService:
        if self._setup is not None:
            return self._setup
        if self._setup_factory is None:
            from adaptation_compiler_lab.desktop.setup_service import (
                DesktopSetupApplicationService,
            )

            self._setup = DesktopSetupApplicationService()
        else:
            self._setup = self._setup_factory()
        return self._setup

    def _preview_export(self, request: EngineRequest) -> EngineResponse:
        if request.params:
            return self._error(
                request, "invalid_params", "portability.export.preview takes no parameters."
            )
        if self._portability is None:
            return self._not_configured(request)
        self._purge_previews()
        try:
            package = self._portability.build_export()
            preview = self._portability.preview_export(package)
        except (OSError, ValueError):
            return self._error(
                request,
                "export_unavailable",
                "Temper could not safely prepare this Core for export.",
            )
        token = uuid.uuid4().hex
        self._export_previews[token] = (monotonic(), package)
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={"export_token": token, **preview.model_dump(mode="json")},
        )

    def _create_export(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, request_fingerprint = checked
        if self._portability is None:
            return self._not_configured(request)
        try:
            token = _required_string(request.params, "export_token")
            passphrase = _required_string(request.params, "passphrase")
            destination = Path(_required_string(request.params, "destination"))
        except ValueError:
            return self._error(request, "invalid_params", "The export request was invalid.")
        self._purge_previews()
        held = self._export_previews.get(token)
        if held is None:
            return self._error(
                request, "preview_expired", "The export preview expired; review it again."
            )
        try:
            preview = self._portability.write_export(
                held[1], passphrase=passphrase, destination=destination
            )
        except FileExistsError:
            return self._error(
                request,
                "destination_exists",
                "Temper will not overwrite an existing profile file.",
            )
        except (OSError, ValueError):
            return self._error(
                request, "export_failed", "Temper could not safely write the profile."
            )
        del self._export_previews[token]
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "status": "exported",
                "package_digest": preview.package_digest,
                "item_count": preview.item_count,
                "raw_payloads_exposed": False,
            },
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

    def _preview_import(self, request: EngineRequest) -> EngineResponse:
        if self._portability is None:
            return self._not_configured(request)
        try:
            source = Path(_required_string(request.params, "source"))
            passphrase = _required_string(request.params, "passphrase")
            if set(request.params) != {"source", "passphrase"}:
                raise ValueError
            envelope = self._portability.read_import(source)
            preview = self._portability.preview_import(envelope, passphrase=passphrase)
        except (OSError, ValueError):
            return self._error(
                request,
                "import_invalid",
                "Temper could not verify this profile or its passphrase.",
            )
        self._purge_previews()
        token = uuid.uuid4().hex
        self._import_previews[token] = (monotonic(), envelope)
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={"import_token": token, **preview.model_dump(mode="json")},
        )

    def _stage_import(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, request_fingerprint = checked
        if self._portability is None or request.idempotency_key is None:
            return self._not_configured(request)
        try:
            token = _required_string(request.params, "import_token")
            passphrase = _required_string(request.params, "passphrase")
            package_digest = _required_string(request.params, "package_digest")
            if set(request.params) != {"import_token", "passphrase", "package_digest"}:
                raise ValueError
        except ValueError:
            return self._error(request, "invalid_params", "The import request was invalid.")
        self._purge_previews()
        held = self._import_previews.get(token)
        if held is None:
            return self._error(
                request, "preview_expired", "The import preview expired; review it again."
            )
        try:
            receipt = self._portability.stage_import(
                held[1],
                passphrase=passphrase,
                expected_package_digest=package_digest,
                idempotency_key=request.idempotency_key,
            )
        except (OSError, ValueError):
            return self._error(
                request, "import_failed", "Temper could not safely stage this profile."
            )
        del self._import_previews[token]
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "status": receipt.status,
                "receipt_id": receipt.receipt_id,
                "package_digest": receipt.package_digest,
                "item_count": len(receipt.imported_item_ids),
                "activates_artifacts": False,
                "raw_payloads_exposed": False,
            },
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

    def _preview_package_export(self, request: EngineRequest) -> EngineResponse:
        if self._portability is None:
            return self._not_configured(request)
        try:
            package_type = _required_string(request.params, "package_type")
            if package_type == "behavior_pack":
                if set(request.params) != {"package_type"}:
                    raise ValueError
                package: ShareablePackage = self._portability.build_shareable_behavior_export()
            elif package_type == "capability_mode":
                if set(request.params) != {"package_type", "mode_id"}:
                    raise ValueError
                package = self._portability.build_shareable_mode_export(
                    _required_string(request.params, "mode_id")
                )
            else:
                raise ValueError
            preview = self._portability.preview_shareable_export(package)
        except (OSError, ValueError):
            return self._error(
                request,
                "package_export_unavailable",
                "Temper could not safely prepare that shareable package.",
            )
        self._purge_previews()
        token = uuid.uuid4().hex
        self._package_export_previews[token] = (monotonic(), package)
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={"export_token": token, **preview.model_dump(mode="json")},
        )

    def _create_package_export(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, request_fingerprint = checked
        if self._portability is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"export_token", "destination"}:
                raise ValueError
            token = _required_string(request.params, "export_token")
            destination = Path(_required_string(request.params, "destination"))
        except ValueError:
            return self._error(request, "invalid_params", "The package export was invalid.")
        self._purge_previews()
        held = self._package_export_previews.get(token)
        if held is None:
            return self._error(
                request, "preview_expired", "The package preview expired; review it again."
            )
        try:
            written = self._portability.write_shareable_export(held[1], destination)
        except FileExistsError:
            return self._error(
                request,
                "destination_exists",
                "Temper will not overwrite an existing package file.",
            )
        except (OSError, ValueError):
            return self._error(
                request,
                "package_export_failed",
                "Temper could not safely write the package.",
            )
        del self._package_export_previews[token]
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "status": "exported",
                "package_digest": held[1].content_digest,
                "file_name": written.name,
                "raw_payloads_exposed": False,
            },
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

    def _preview_package_import(self, request: EngineRequest) -> EngineResponse:
        if self._portability is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"source"}:
                raise ValueError
            package = self._portability.read_shareable_import(
                Path(_required_string(request.params, "source"))
            )
            preview = self._portability.preview_shareable_import(package)
        except (OSError, ValueError):
            return self._error(
                request,
                "package_import_invalid",
                "Temper could not verify that shareable package.",
            )
        self._purge_previews()
        token = uuid.uuid4().hex
        self._package_import_previews[token] = (monotonic(), package, preview)
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={"import_token": token, **preview.model_dump(mode="json")},
        )

    def _stage_package_import(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        snapshot_digest, request_fingerprint = checked
        if self._portability is None or request.idempotency_key is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {"import_token", "package_digest"}:
                raise ValueError
            token = _required_string(request.params, "import_token")
            package_digest = _required_string(request.params, "package_digest")
        except ValueError:
            return self._error(request, "invalid_params", "The package import was invalid.")
        self._purge_previews()
        held = self._package_import_previews.get(token)
        if held is None:
            return self._error(
                request, "preview_expired", "The package preview expired; review it again."
            )
        if held[1].content_digest != package_digest:
            return self._error(
                request,
                "stale_package",
                "The package changed after preview; choose it again.",
            )
        try:
            receipt = self._portability.stage_shareable_import(
                held[1],
                held[2],
                idempotency_key=request.idempotency_key,
            )
        except (OSError, ValueError):
            return self._error(
                request,
                "package_import_failed",
                "Temper could not safely stage that package.",
            )
        del self._package_import_previews[token]
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "status": receipt.status,
                "receipt_id": receipt.receipt_id,
                "package_digest": receipt.package_digest,
                "item_count": held[2].item_count,
                "activates_artifacts": False,
                "raw_payloads_exposed": False,
            },
            snapshot_digest=snapshot_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

    def _list_package_reviews(self, request: EngineRequest) -> EngineResponse:
        if request.params:
            return self._error(
                request, "invalid_params", "package.review.list takes no parameters."
            )
        if self._portability is None:
            return self._not_configured(request)
        try:
            items = self._portability.package_review_items()
        except (OSError, ValueError):
            return self._error(
                request,
                "package_review_unavailable",
                "Temper could not safely read imported package reviews.",
                retryable=True,
            )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "items": tuple(
                    {
                        **item.model_dump(mode="json"),
                        "review_digest": item.content_digest,
                    }
                    for item in items
                ),
                "pending_count": len(items),
                "raw_payloads_exposed": False,
            },
        )

    def _decide_package_review(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, request_fingerprint = checked
        if self._portability is None or self._service is None or request.idempotency_key is None:
            return self._not_configured(request)
        try:
            if set(request.params) != {
                "review_id",
                "review_digest",
                "decision",
                "mapped_project_ids",
            }:
                raise ValueError
            decision = ApprovalDecision(_required_string(request.params, "decision"))
            raw_projects = request.params.get("mapped_project_ids")
            if not isinstance(raw_projects, list) or any(
                not isinstance(value, str) or not value.strip() for value in raw_projects
            ):
                raise ValueError
            projects = tuple(sorted(set(raw_projects)))
            if len(projects) != len(raw_projects):
                raise ValueError
            receipt = self._portability.decide_package_review(
                review_id=_required_string(request.params, "review_id"),
                review_digest=_required_string(request.params, "review_digest"),
                decision=decision,
                mapped_project_ids=projects,
                idempotency_key=request.idempotency_key,
            )
            current = self._service.load()
        except (OSError, ValueError):
            return self._error(
                request,
                "package_review_refused",
                "Temper could not safely apply that package decision.",
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "receipt_id": receipt.receipt_id,
                "review_id": receipt.review_id,
                "decision": receipt.decision,
                "status": receipt.resulting_status,
                "runtime_adoption_digest": receipt.runtime_adoption_digest,
                "origin_granted_authority": False,
                "raw_payloads_exposed": False,
            },
            snapshot_digest=current.content_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

    def _run_mode_task(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, request_fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            mode_id = _required_string(request.params, "mode_id")
            project_id = _required_string(request.params, "project_id")
            task = _required_string(request.params, "task")
            if set(request.params) != {"mode_id", "project_id", "task"}:
                raise ValueError
            if len(task.encode("utf-8")) > 32_000:
                raise ValueError
        except ValueError:
            return self._error(request, "invalid_params", "The managed task request was invalid.")
        action, task_result = self._service.run_task(
            task=task,
            project_id=project_id,
            mode_id=mode_id,
        )
        if not action.ok or task_result is None:
            return self._error(request, action.code, action.message)
        try:
            current = self._service.load()
        except (OSError, ValueError):
            return self._error(
                request, "snapshot_unavailable", "Temper could not verify the resulting state."
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "activation_id": task_result.activation_id,
                "status": task_result.status,
                "projection_utf8_bytes": task_result.projection_utf8_bytes,
                "review_available": task_result.change_review is not None,
                "final_message": task_result.final_message,
                "change_review": (
                    None
                    if task_result.change_review is None
                    else task_result.change_review.model_dump(mode="json")
                ),
                "raw_payloads_exposed": False,
            },
            snapshot_digest=current.content_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

    def _run_task(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, request_fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            project_id = _required_string(request.params, "project_id")
            task = _required_string(request.params, "task")
            if set(request.params) != {"project_id", "task"} or len(task.encode("utf-8")) > 32_000:
                raise ValueError
        except ValueError:
            return self._error(request, "invalid_params", "The managed task request was invalid.")
        action, task_result = self._service.run_task(task=task, project_id=project_id)
        if not action.ok or task_result is None:
            return self._error(request, action.code, action.message)
        try:
            current = self._service.load()
        except (OSError, ValueError):
            return self._error(
                request, "snapshot_unavailable", "Temper could not verify the resulting state."
            )
        response = EngineResponse(
            request_id=request.request_id,
            ok=True,
            result={
                **task_result.model_dump(mode="json"),
                "review_available": task_result.change_review is not None,
                "raw_payloads_exposed": False,
            },
            snapshot_digest=current.content_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

    def _apply_task(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            session_id = _required_string(request.params, "session_id")
            expected_head = _required_string(request.params, "expected_head")
            if set(request.params) != {"session_id", "expected_head"}:
                raise ValueError
        except ValueError:
            return self._error(request, "invalid_params", "The task application was invalid.")
        return self._action_response(
            request,
            fingerprint,
            session_id,
            self._service.apply_changes(session_id=session_id, expected_head=expected_head),
        )

    def _discard_task(self, request: EngineRequest) -> EngineResponse:
        checked = self._mutation_request(request)
        if isinstance(checked, EngineResponse):
            return checked
        _snapshot_digest, fingerprint = checked
        if self._service is None:
            return self._not_configured(request)
        try:
            session_id = _required_string(request.params, "session_id")
            if set(request.params) != {"session_id"}:
                raise ValueError
        except ValueError:
            return self._error(request, "invalid_params", "The task discard was invalid.")
        return self._action_response(
            request,
            fingerprint,
            session_id,
            self._service.discard_changes(session_id=session_id),
        )

    def _diagnostics(self, request: EngineRequest) -> EngineResponse:
        if request.params:
            return self._error(request, "invalid_params", "diagnostics.get takes no parameters.")
        if self._service is None:
            return self._not_configured(request)
        try:
            snapshot = self._service.load()
        except (OSError, ValueError):
            return self._error(request, "diagnostics_unavailable", "Diagnostics are unavailable.")
        summary = DiagnosticsSummaryV1(
            snapshot_version=snapshot.snapshot_version,
            project_count=len(snapshot.projects),
            pending_review_count=len(snapshot.suggestions),
            active_adaptation_count=len(snapshot.adaptations),
            pending_feedback_count=len(snapshot.activation_feedback),
            consent_current=not snapshot.consent.renewal_required,
            secure_store_ready=snapshot.terminal.review_mode.credential_enrolled,
        )
        return EngineResponse(
            request_id=request.request_id,
            ok=True,
            result=summary.model_dump(mode="json"),
            snapshot_digest=snapshot.content_digest,
        )

    def _mutation_request(
        self, request: EngineRequest
    ) -> tuple[Sha256Digest, Sha256Digest] | EngineResponse:
        if self._service is None:
            return self._not_configured(request)
        if request.expected_snapshot_digest is None or request.idempotency_key is None:
            return self._error(
                request,
                "mutation_binding_required",
                "Refresh Temper before trying this action again.",
            )
        fingerprint = canonical_digest(
            {
                "method": request.method,
                "params": {
                    key: value for key, value in request.params.items() if key != "passphrase"
                },
                "expected_snapshot_digest": request.expected_snapshot_digest,
            }
        )
        cached = self._mutation_results.get(request.idempotency_key)
        if cached is not None:
            if cached[0] != fingerprint:
                return self._error(
                    request,
                    "idempotency_conflict",
                    "This action identifier was already used for something else.",
                )
            return cached[1].model_copy(update={"request_id": request.request_id})
        try:
            snapshot = self._service.load()
        except (OSError, ValueError):
            return self._error(
                request, "snapshot_unavailable", "Temper could not verify current state."
            )
        if snapshot.content_digest != request.expected_snapshot_digest:
            return self._error(
                request,
                "stale_snapshot",
                "Temper changed since this preview; review the current state and try again.",
            )
        return snapshot.content_digest, fingerprint

    def _remember_mutation(
        self,
        request: EngineRequest,
        fingerprint: Sha256Digest,
        response: EngineResponse,
    ) -> EngineResponse:
        if request.idempotency_key is not None:
            self._mutation_results[request.idempotency_key] = (fingerprint, response)
        return response

    def _purge_previews(self) -> None:
        cutoff = monotonic() - PREVIEW_TTL_SECONDS
        self._export_previews = {
            key: value for key, value in self._export_previews.items() if value[0] >= cutoff
        }
        self._import_previews = {
            key: value for key, value in self._import_previews.items() if value[0] >= cutoff
        }
        self._package_export_previews = {
            key: value for key, value in self._package_export_previews.items() if value[0] >= cutoff
        }
        self._package_import_previews = {
            key: value for key, value in self._package_import_previews.items() if value[0] >= cutoff
        }

    def _not_configured(self, request: EngineRequest) -> EngineResponse:
        return self._error(
            request,
            "not_configured",
            "Temper needs a governed local setup before it can do that.",
        )

    @staticmethod
    def _error(
        request: EngineRequest,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> EngineResponse:
        return EngineResponse(
            request_id=request.request_id,
            ok=False,
            error=EngineError(code=code, message=message, retryable=retryable),
        )


def build_router(
    config_path: Path | None,
    *,
    predecessor_config_path: Path | None = None,
) -> EngineProtocolRouter:
    """Construct the protocol over the existing typed desktop application service."""

    if config_path is None:
        return EngineProtocolRouter(None, None)
    from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
        _context,
        _ledger,
        _load_config,
        _now,
        _raw_store,
        _registration_signer,
    )
    from adaptation_compiler_lab.claude_delivery import (
        ClaudeConnectionService,
        ClaudeHookLedger,
        ClaudeHookRuntimeHandler,
        ClaudeHookSettingsService,
        LocalClaudeHookRuntimePort,
    )
    from adaptation_compiler_lab.desktop.platform import platform_paths, product_preferences_store
    from adaptation_compiler_lab.desktop.portability_service import LocalProfilePortabilityService
    from adaptation_compiler_lab.desktop.preferences import (
        DesktopPreferences,
    )
    from adaptation_compiler_lab.desktop.service import (
        CodexDogfoodDesktopBackend,
        DesktopApplicationService,
    )
    from adaptation_compiler_lab.instruction_environment.codex_semantic import (
        ConfiguredCodexInstructionRelationAnalyzer,
        ConfiguredCodexInstructionSemanticAnalyzer,
        instruction_relation_analyzer_digest,
        instruction_semantic_analyzer_digest,
    )
    from adaptation_compiler_lab.instruction_environment.service import (
        InstructionEnvironmentService,
    )
    from adaptation_compiler_lab.runtime import (
        CanonicalRuntimeProjection,
        RuntimeProjectionContext,
        build_runtime_projection,
    )
    from adaptation_compiler_lab.targets.models import ScopeDimension

    preferences_store = product_preferences_store(platform_paths())
    try:
        preferences = preferences_store.load()
    except (OSError, ValueError):
        preferences = DesktopPreferences()

    def save_preferences(
        background_enabled: bool,
        reporting_enabled: bool,
        notifications_enabled: bool,
        launch_at_login_enabled: bool,
    ) -> None:
        preferences_store.save(
            preferences_store.load().model_copy(
                update={
                    "background_enabled": background_enabled,
                    "aggregate_reporting_enabled": reporting_enabled,
                    "decision_notifications_enabled": notifications_enabled,
                    "launch_at_login_enabled": launch_at_login_enabled,
                }
            )
        )

    service = DesktopApplicationService(
        CodexDogfoodDesktopBackend(
            config_path.expanduser().resolve(),
            predecessor_config_path=(
                None
                if predecessor_config_path is None
                else predecessor_config_path.expanduser().resolve()
            ),
        ),
        background_enabled=preferences.background_enabled,
        aggregate_reporting_enabled=preferences.aggregate_reporting_enabled,
        decision_notifications_enabled=preferences.decision_notifications_enabled,
        launch_at_login_enabled=preferences.launch_at_login_enabled,
        preference_writer=save_preferences,
    )

    def instruction_factory() -> InstructionEnvironmentService:
        config = _load_config(config_path)
        try:
            raw_store = _raw_store(config)
            signer = _registration_signer(config)
        except (OSError, ValueError):
            raw_store = None
            signer = None

        def projection_provider(
            project_id: str, target: NativeTarget
        ) -> CanonicalRuntimeProjection | None:
            state = _ledger(config).current()
            if state is None or state.release is None:
                return None
            project = next(
                (item for item in config.projects if item.project_id == project_id),
                None,
            )
            if project is None:
                return None
            if target is NativeTarget.CODEX:
                context = _context(config, project, evaluated_at=_now())
            elif target is NativeTarget.CLAUDE:
                context = RuntimeProjectionContext(
                    known_dimensions=(
                        ScopeDimension.PROJECT_IDS,
                        ScopeDimension.SUBJECT_IDS,
                        ScopeDimension.TARGET_FAMILIES,
                    ),
                    target_profile_id="claude-code",
                    subject_id=config.subject_id,
                    project_id=project.project_id,
                    target_family="claude-code",
                    evaluated_at=_now(),
                )
            else:
                return None
            return build_runtime_projection(state.release.governed_release, context)

        return InstructionEnvironmentService(
            projects={item.project_id: item.root for item in config.projects},
            state_root=config.state_root,
            raw_store=raw_store,
            signer=signer,
            semantic_analyzer=ConfiguredCodexInstructionSemanticAnalyzer(config_path),
            analyzer_digest=instruction_semantic_analyzer_digest(
                model=config.semantic_model,
                reasoning_effort=config.semantic_reasoning_effort,
            ),
            relation_analyzer=ConfiguredCodexInstructionRelationAnalyzer(config_path),
            relation_analyzer_digest=instruction_relation_analyzer_digest(
                model=config.semantic_model,
                reasoning_effort=config.semantic_reasoning_effort,
            ),
            projection_provider=projection_provider,
        )

    instruction_instance: InstructionEnvironmentService | None = None

    def shared_instruction_service() -> InstructionEnvironmentService:
        nonlocal instruction_instance
        if instruction_instance is None:
            instruction_instance = instruction_factory()
        return instruction_instance

    claude_connection = None
    claude_hook_handler = None
    claude_projection_refresher = None
    helper_value = os.environ.get("TEMPER_HOOK_HELPER_BINARY")
    settings_value = os.environ.get("TEMPER_CLAUDE_SETTINGS_PATH")
    if helper_value and settings_value:
        try:
            config = _load_config(config_path)
            raw_store = _raw_store(config)
            signer = _registration_signer(config)
            project_digests = {
                project.project_id: (
                    project.registration.content_digest
                    if project.registration is not None
                    else canonical_digest(
                        {
                            "capture_after_epoch_seconds": (
                                project.capture_after_epoch_seconds
                                if project.capture_after_epoch_seconds is not None
                                else config.capture_after_epoch_seconds
                            ),
                            "project_id": project.project_id,
                            "scope": project.scope,
                        }
                    )
                )
                for project in config.projects
            }
            hook_settings = ClaudeHookSettingsService(
                raw_store=raw_store,
                signer=signer,
                now=_now,
                state_root=config.state_root,
            )
            claude_connection = ClaudeConnectionService(
                subject_id=config.subject_id,
                projects=project_digests,
                settings=hook_settings,
                settings_path=Path(settings_value),
                helper_path=Path(helper_value),
                signer=signer,
                signer_identity=config.signer_identity,
                state_root=config.state_root,
                now=_now,
            )
            if claude_connection.status().state == "connected":

                def claude_projection_provider(
                    project_id: str, evaluated_at: datetime
                ) -> CanonicalRuntimeProjection | None:
                    state = _ledger(config).current()
                    if state is None or state.release is None:
                        return None
                    project = next(
                        (item for item in config.projects if item.project_id == project_id),
                        None,
                    )
                    if project is None:
                        return None
                    return build_runtime_projection(
                        state.release.governed_release,
                        RuntimeProjectionContext(
                            known_dimensions=(
                                ScopeDimension.PROJECT_IDS,
                                ScopeDimension.SUBJECT_IDS,
                                ScopeDimension.TARGET_FAMILIES,
                            ),
                            target_profile_id="claude-code",
                            subject_id=config.subject_id,
                            project_id=project.project_id,
                            target_family="claude-code",
                            evaluated_at=evaluated_at,
                        ),
                    )

                runtime = LocalClaudeHookRuntimePort(
                    projects={project.project_id: project.root for project in config.projects},
                    signer=signer,
                    signer_identity=config.signer_identity,
                    raw_store=raw_store,
                    ledger=ClaudeHookLedger(
                        config.state_root / "claude-delivery" / "hook-ledger.jsonl",
                        signer=signer,
                        signer_identity=config.signer_identity,
                    ),
                    instruction_environment=shared_instruction_service(),
                    authorization_provider=(
                        lambda project_id, effective_at: claude_connection.authorization(
                            project_id, effective_at=effective_at
                        )
                    ),
                    projection_provider=claude_projection_provider,
                    clock=_now,
                )
                runtime.prepare_all()
                claude_hook_handler = ClaudeHookRuntimeHandler(
                    runtime,
                    signer=signer,
                    signer_identity=config.signer_identity,
                    clock=_now,
                )
                claude_projection_refresher = runtime.prepare_all
        except (OSError, ValueError):
            claude_hook_handler = None
            claude_projection_refresher = None

    return EngineProtocolRouter(
        service,
        LocalProfilePortabilityService(config_path.expanduser().resolve()),
        instruction_factory=shared_instruction_service,
        claude_hook_handler=claude_hook_handler,
        claude_connection=claude_connection,
        claude_projection_refresher=claude_projection_refresher,
    )


def serve(
    router: EngineProtocolRouter,
    *,
    source: TextIO = sys.stdin,
    sink: TextIO = sys.stdout,
) -> int:
    """Serve bounded newline-delimited frames until stdin closes."""

    for raw_line in source:
        request_id = "invalid-request"
        encoded = raw_line.encode("utf-8")
        if len(encoded) > MAX_FRAME_BYTES:
            response = EngineResponse(
                request_id=request_id,
                ok=False,
                error=EngineError(code="frame_too_large", message="The request was too large."),
            )
        else:
            try:
                payload = json.loads(raw_line)
                if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
                    request_id = payload["request_id"]
                request = EngineRequest.model_validate(payload, strict=True)
                response = router.handle(request)
            except (json.JSONDecodeError, ValueError, TypeError):
                response = EngineResponse(
                    request_id=request_id,
                    ok=False,
                    error=EngineError(code="invalid_request", message="The request was invalid."),
                )
        sink.write(response.model_dump_json() + "\n")
        sink.flush()
    return 0


def protocol_schema_models() -> Sequence[type[FrozenModel]]:
    """Return public models used to generate cross-language golden vectors."""

    return (
        EngineRequest,
        EngineError,
        EngineResponse,
        EngineHandshake,
        DesktopSnapshot,
        SetupSnapshotV1,
        ProjectCandidatePreviewV1,
        SetupCompletionReceiptV1,
        SuggestionSummaryV1,
        SuggestionDecisionRequestV1,
        AdaptationSummaryV1,
        ActivationFeedbackSummaryV1,
        RecentUndoSummaryV1,
        MutationReceiptV1,
        PackageReviewItemV1,
        PackageReviewDecisionReceiptV1,
        InstructionSourceSummaryV1,
        InstructionEnvironmentSummaryV1,
        InstructionGlobalPreviewV1,
        InstructionChangePreviewV1,
        InstructionChangeReceiptV1,
    )


def _required_string(params: Mapping[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {key}")
    return value


def _host_platform() -> Literal["windows", "macos", "development"]:
    host = platform.system()
    if host == "Windows":
        return "windows"
    if host == "Darwin":
        return "macos"
    return "development"
