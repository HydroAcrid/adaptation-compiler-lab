from __future__ import annotations

import io
import json
from typing import Any, cast
from unittest.mock import MagicMock

from adaptation_compiler_lab.desktop.engine_protocol import (
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    EngineProtocolRouter,
    EngineRequest,
    serve,
    snapshot_schema_digest,
)
from adaptation_compiler_lab.desktop.models import ActionResult, DesktopTaskResult


def _request(method: str, *, request_id: str = "request-1") -> EngineRequest:
    return EngineRequest(
        protocol_version=PROTOCOL_VERSION,
        request_id=request_id,
        method=method,
    )


def test_handshake_is_available_before_local_configuration() -> None:
    response = EngineProtocolRouter(None).handle(_request("system.handshake"))

    assert response.ok is True
    assert response.result is not None
    assert response.result["configured"] is False
    assert response.result["mutation_enabled"] is False
    assert response.result["snapshot_schema_digest"] == snapshot_schema_digest()


def test_snapshot_fails_closed_before_local_configuration() -> None:
    response = EngineProtocolRouter(None).handle(_request("snapshot.get"))

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "not_configured"


def test_unknown_method_does_not_expose_an_arbitrary_dispatch_surface() -> None:
    response = EngineProtocolRouter(None).handle(_request("process.run"))

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "unknown_method"


def test_mode_catalog_is_raw_free_and_reports_valid_frontend_studio() -> None:
    response = EngineProtocolRouter(None).handle(_request("mode.list"))

    assert response.ok is True
    assert response.result is not None
    assert response.result["raw_payloads_exposed"] is False
    modes = response.result["modes"]
    assert isinstance(modes, tuple)
    assert modes[0]["mode_id"] == "frontend-studio"
    assert modes[0]["evaluation_valid"] is True
    assert modes[0]["requested_tools"] == []


def test_portability_never_operates_without_governed_local_configuration() -> None:
    preview = EngineProtocolRouter(None).handle(_request("portability.export.preview"))
    mutation = EngineProtocolRouter(None).handle(_request("portability.import.stage"))

    assert preview.ok is False
    assert preview.error is not None
    assert preview.error.code == "not_configured"
    assert mutation.ok is False
    assert mutation.error is not None
    assert mutation.error.code == "not_configured"


def test_mode_run_is_bound_to_snapshot_and_forwards_exact_mode_scope() -> None:
    digest = f"sha256:{'a' * 64}"
    service = MagicMock()
    snapshot = MagicMock()
    snapshot.content_digest = digest
    service.load.return_value = snapshot
    service.run_task.return_value = (
        ActionResult(action="run_task", ok=True, code="ok", message="Ready."),
        DesktopTaskResult(
            activation_id="mode-run-1",
            status="review_available",
            projection_utf8_bytes=1200,
        ),
    )
    router = EngineProtocolRouter(cast(Any, service))
    request = EngineRequest(
        protocol_version=PROTOCOL_VERSION,
        request_id="mode-request-1",
        method="mode.task.run",
        params={
            "mode_id": "frontend-studio",
            "project_id": "kairn",
            "task": "Refine the settings page",
        },
        expected_snapshot_digest=digest,
        idempotency_key="mode-click-1",
    )

    response = router.handle(request)

    assert response.ok is True
    assert response.result is not None
    assert response.result["review_available"] is False
    service.run_task.assert_called_once_with(
        task="Refine the settings page",
        project_id="kairn",
        mode_id="frontend-studio",
    )


def test_stdio_server_handles_malformed_and_valid_frames_without_crashing() -> None:
    valid = _request("system.handshake").model_dump_json()
    source = io.StringIO("not-json\n" + valid + "\n")
    sink = io.StringIO()

    assert serve(EngineProtocolRouter(None), source=source, sink=sink) == 0

    responses = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == "invalid_request"
    assert responses[1]["ok"] is True


def test_stdio_server_rejects_oversized_frames() -> None:
    source = io.StringIO("x" * (MAX_FRAME_BYTES + 1) + "\n")
    sink = io.StringIO()

    serve(EngineProtocolRouter(None), source=source, sink=sink)

    response = json.loads(sink.getvalue())
    assert response["error"]["code"] == "frame_too_large"
