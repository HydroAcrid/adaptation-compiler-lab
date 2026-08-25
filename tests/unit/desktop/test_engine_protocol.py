from __future__ import annotations

import io
import json

from adaptation_compiler_lab.desktop.engine_protocol import (
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    EngineProtocolRouter,
    EngineRequest,
    serve,
    snapshot_schema_digest,
)


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
