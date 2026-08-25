"""Versioned raw-free stdio protocol for the Temper desktop engine."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any, Final, Literal, TextIO

from pydantic import Field

from adaptation_compiler_lab.desktop.models import DesktopSnapshot
from adaptation_compiler_lab.desktop.service import (
    CodexDogfoodDesktopBackend,
    DesktopApplicationService,
)
from adaptation_compiler_lab.domain import FrozenModel, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest

PROTOCOL_VERSION: Final[Literal["temper-engine-protocol/v1"]] = "temper-engine-protocol/v1"
MAX_FRAME_BYTES = 1_048_576


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

    def __init__(self, service: DesktopApplicationService | None) -> None:
        self._service = service

    def handle(self, request: EngineRequest) -> EngineResponse:
        if request.method == "system.handshake":
            handshake = EngineHandshake(
                engine_version=version("adaptation-compiler-lab"),
                snapshot_schema_digest=snapshot_schema_digest(),
                mutation_enabled=False,
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
        return self._error(request, "unknown_method", "The requested operation is not supported.")

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
        return EngineProtocolRouter(None)
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
    return EngineProtocolRouter(service)


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
