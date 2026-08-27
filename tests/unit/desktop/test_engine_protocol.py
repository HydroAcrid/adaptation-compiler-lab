from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
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
from adaptation_compiler_lab.desktop.models import (
    ActionResult,
    AgentConnectionV1,
    DesktopTaskResult,
    ExistingInstallationSummary,
    ProjectCandidatePreviewV1,
    SecureStoreStatus,
    SetupCompletionReceiptV1,
    SetupSnapshotV1,
)


def test_unconfigured_engine_import_does_not_load_managed_runtime_service() -> None:
    script = """
import sys
from adaptation_compiler_lab.desktop.engine_protocol import build_router
assert build_router(None) is not None
assert 'adaptation_compiler_lab.desktop.service' not in sys.modules
assert 'adaptation_compiler_lab.automatic_runtime.dogfood_cli' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


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
    assert response.result["setup_available"] is True
    assert response.result["configuration_state"] == "unconfigured"
    assert response.result["snapshot_schema_digest"] == snapshot_schema_digest()


def test_snapshot_fails_closed_before_local_configuration() -> None:
    response = EngineProtocolRouter(None).handle(_request("snapshot.get"))

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "not_configured"


class FakeSetupService:
    def __init__(self) -> None:
        now = datetime(2026, 8, 27, 12, tzinfo=UTC)
        self.snapshot_value = SetupSnapshotV1(
            configuration_state="unconfigured",
            secure_store=SecureStoreStatus(
                platform="windows",
                protector="windows-dpapi-current-user",
                status="not_created",
            ),
            connections=(
                AgentConnectionV1(
                    agent_id="codex",
                    display_name="Codex",
                    installation_state="installed",
                    authentication_state="signed_in",
                    conformance_state="compatible",
                    status_summary="Ready.",
                    learning_capability="Prospective completed tasks.",
                    delivery_capability="Fresh managed tasks.",
                    cost_posture="ChatGPT authentication.",
                    available_actions=("refresh", "use_for_setup"),
                ),
                AgentConnectionV1(
                    agent_id="claude",
                    display_name="Claude Code",
                    installation_state="not_installed",
                    authentication_state="unknown",
                    conformance_state="not_applicable",
                    status_summary="Not installed.",
                    learning_capability="Not integrated.",
                    delivery_capability="Not integrated.",
                    cost_posture="Provider-billed if added later.",
                ),
            ),
        )
        self.preview = ProjectCandidatePreviewV1(
            preview_token="preview-1",
            project_id="kairn",
            display_name="Kairn",
            capture_after_epoch_seconds=int(now.timestamp()),
            expires_at=now + timedelta(minutes=15),
        )

    def snapshot(self) -> SetupSnapshotV1:
        return self.snapshot_value

    def preview_project(self, root: Path) -> ProjectCandidatePreviewV1:
        assert root.name == "kairn"
        return self.preview

    def preview_existing(self, config_path: Path) -> tuple[str, ExistingInstallationSummary]:
        assert config_path.name == "config.json"
        return "existing-preview-1", self.existing_summary()

    def adopt_existing(
        self,
        *,
        preview_token: str,
        expected_setup_digest: str,
    ) -> ExistingInstallationSummary:
        assert preview_token == "existing-preview-1"
        assert expected_setup_digest == str(self.snapshot_value.content_digest)
        return self.existing_summary()

    @staticmethod
    def existing_summary() -> ExistingInstallationSummary:
        return ExistingInstallationSummary(
            signer_fingerprint=f"sha256:{'c' * 64}",
            project_count=2,
            consent_expires_at=datetime(2026, 9, 20, tzinfo=UTC),
            secure_store_ready=True,
        )

    def initialize(
        self,
        *,
        preview_token: str,
        expected_setup_digest: str,
        consent_confirmed: bool,
    ) -> SetupCompletionReceiptV1:
        assert preview_token == self.preview.preview_token
        assert expected_setup_digest == str(self.snapshot_value.content_digest)
        assert consent_confirmed is True
        return SetupCompletionReceiptV1(
            subject_id="temper-owner",
            signer_fingerprint=f"sha256:{'b' * 64}",
            project_id="kairn",
            capture_after_epoch_seconds=self.preview.capture_after_epoch_seconds,
            consent_expires_at=self.preview.expires_at,
        )


def test_setup_status_preview_and_bound_initialization_are_allowlisted(tmp_path: Path) -> None:
    setup = FakeSetupService()
    router = EngineProtocolRouter(None, setup_factory=lambda: cast(Any, setup))
    project = tmp_path / "kairn"
    project.mkdir()

    status = router.handle(_request("setup.status"))
    preview = router.handle(
        EngineRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id="preview-request",
            method="setup.project.preview",
            params={"path": str(project)},
        )
    )
    initialized = router.handle(
        EngineRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id="setup-request",
            method="setup.initialize",
            params={"preview_token": "preview-1", "consent_confirmed": True},
            expected_snapshot_digest=setup.snapshot_value.content_digest,
            idempotency_key="setup-click-1",
        )
    )

    assert status.ok is True
    assert status.snapshot_digest == setup.snapshot_value.content_digest
    assert preview.ok is True
    assert preview.result is not None
    assert preview.result["historical_tasks_eligible"] is False
    assert initialized.ok is True
    assert initialized.result is not None
    assert initialized.result["learning_enabled"] is False


def test_existing_installation_adoption_is_previewed_and_digest_bound(tmp_path: Path) -> None:
    setup = FakeSetupService()
    router = EngineProtocolRouter(None, setup_factory=lambda: cast(Any, setup))
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")

    preview = router.handle(
        EngineRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id="existing-preview-request",
            method="setup.existing.preview",
            params={"path": str(config)},
        )
    )
    adopted = router.handle(
        EngineRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id="existing-adopt-request",
            method="setup.existing.adopt",
            params={"preview_token": "existing-preview-1"},
            expected_snapshot_digest=setup.snapshot_value.content_digest,
            idempotency_key="existing-adopt-click-1",
        )
    )

    assert preview.ok is True
    assert preview.result is not None
    assert preview.result["raw_payloads_exposed"] is False
    assert adopted.ok is True
    assert adopted.result is not None
    assert adopted.result["restart_required"] is True


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
