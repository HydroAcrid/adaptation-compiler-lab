"""Versioned raw-free stdio protocol for the Temper desktop engine."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from time import monotonic
from typing import Any, Final, Literal, TextIO

from pydantic import Field

from adaptation_compiler_lab.desktop.models import DesktopSnapshot
from adaptation_compiler_lab.desktop.portability_service import LocalProfilePortabilityService
from adaptation_compiler_lab.desktop.service import (
    CodexDogfoodDesktopBackend,
    DesktopApplicationService,
)
from adaptation_compiler_lab.domain import FrozenModel, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.modes import FRONTEND_STUDIO_MODE, evaluate_frontend_studio_mode
from adaptation_compiler_lab.portability import (
    EncryptedProfileEnvelope,
    PortableProfilePackage,
)
from adaptation_compiler_lab.serialization import canonical_digest

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


def snapshot_schema_digest() -> Sha256Digest:
    """Return a deterministic digest of the renderer-visible snapshot contract."""

    return canonical_digest(DesktopSnapshot.model_json_schema())


class EngineProtocolRouter:
    """Fail-closed dispatcher with no generic filesystem or process methods."""

    def __init__(
        self,
        service: DesktopApplicationService | None,
        portability: LocalProfilePortabilityService | None = None,
    ) -> None:
        self._service = service
        self._portability = portability
        self._export_previews: dict[str, tuple[float, PortableProfilePackage]] = {}
        self._import_previews: dict[str, tuple[float, EncryptedProfileEnvelope]] = {}
        self._mutation_results: dict[str, tuple[Sha256Digest, EngineResponse]] = {}

    def handle(self, request: EngineRequest) -> EngineResponse:
        if request.method == "system.handshake":
            handshake = EngineHandshake(
                engine_version=version("adaptation-compiler-lab"),
                snapshot_schema_digest=snapshot_schema_digest(),
                mutation_enabled=self._service is not None,
                configured=self._service is not None,
            )
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result=handshake.model_dump(mode="json"),
            )
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
        if request.method == "portability.export.preview":
            return self._preview_export(request)
        if request.method == "portability.export.create":
            return self._create_export(request)
        if request.method == "portability.import.preview":
            return self._preview_import(request)
        if request.method == "portability.import.stage":
            return self._stage_import(request)
        if request.method == "mode.task.run":
            return self._run_mode_task(request)
        if request.method == "mode.list":
            if request.params:
                return self._error(request, "invalid_params", "mode.list takes no parameters.")
            report = evaluate_frontend_studio_mode()
            return EngineResponse(
                request_id=request.request_id,
                ok=True,
                result={
                    "modes": (
                        {
                            "mode_id": FRONTEND_STUDIO_MODE.mode_id,
                            "mode_version": FRONTEND_STUDIO_MODE.mode_version,
                            "name": FRONTEND_STUDIO_MODE.name,
                            "summary": FRONTEND_STUDIO_MODE.summary,
                            "activation_default": FRONTEND_STUDIO_MODE.activation_default,
                            "applicable_task_classes": list(
                                FRONTEND_STUDIO_MODE.applicable_task_classes
                            ),
                            "compatible_target_families": list(
                                FRONTEND_STUDIO_MODE.compatible_target_families
                            ),
                            "requested_tools": list(FRONTEND_STUDIO_MODE.requested_tools),
                            "projection_utf8_bytes": report.projection_utf8_bytes,
                            "evaluation_valid": report.valid,
                            "evaluation_case_count": len(report.cases),
                            "mutates_permanent_core": False,
                        },
                    ),
                    "raw_payloads_exposed": False,
                },
            )
        return self._error(request, "unknown_method", "The requested operation is not supported.")

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
        if mode_id != FRONTEND_STUDIO_MODE.mode_id:
            return self._error(request, "mode_unavailable", "That Mode is unavailable.")
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
                "raw_payloads_exposed": False,
            },
            snapshot_digest=current.content_digest,
        )
        return self._remember_mutation(request, request_fingerprint, response)

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
    service = DesktopApplicationService(
        CodexDogfoodDesktopBackend(
            config_path.expanduser().resolve(),
            predecessor_config_path=(
                None
                if predecessor_config_path is None
                else predecessor_config_path.expanduser().resolve()
            ),
        )
    )
    return EngineProtocolRouter(
        service,
        LocalProfilePortabilityService(config_path.expanduser().resolve()),
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

    return (EngineRequest, EngineError, EngineResponse, EngineHandshake, DesktopSnapshot)


def _required_string(params: Mapping[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {key}")
    return value
