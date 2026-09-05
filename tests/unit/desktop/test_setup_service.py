from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.desktop.models import (
    AgentConnectionV1,
    ExistingInstallationSummary,
)
from adaptation_compiler_lab.desktop.platform import PlatformPaths
from adaptation_compiler_lab.desktop.setup_service import DesktopSetupApplicationService


class FakeInspector:
    def inspect(self) -> tuple[AgentConnectionV1, AgentConnectionV1]:
        return (
            AgentConnectionV1(
                agent_id="codex",
                display_name="Codex",
                installation_state="installed",
                authentication_state="signed_in",
                conformance_state="compatible",
                version_label="codex-cli 0.153.1",
                status_summary="Ready to use with Temper.",
                learning_capability="Learns from eligible completed tasks.",
                delivery_capability="Fresh Temper-managed tasks only.",
                cost_posture="Saved ChatGPT authentication.",
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
                cost_posture="Future use is provider-billed.",
            ),
        )

    def codex_executable(self) -> Path | None:
        return Path("/synthetic/codex")


def test_first_run_snapshot_and_project_preview_are_raw_free(tmp_path: Path) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=UTC)
    project = tmp_path / "Green Meadow"
    project.mkdir()
    service = DesktopSetupApplicationService(
        paths=PlatformPaths(
            platform="development",
            state_root=tmp_path / "state",
            config_root=tmp_path / "config",
            historical_state_root=tmp_path / "old-state",
            historical_config_root=tmp_path / "old-config",
        ),
        inspector=FakeInspector(),  # type: ignore[arg-type]
        clock=lambda: now,
    )

    snapshot = service.snapshot()
    preview = service.preview_project(project)

    assert snapshot.configuration_state == "unconfigured"
    assert snapshot.learning_enabled is False
    assert snapshot.aggregate_reporting_enabled is False
    assert preview.display_name == "Green Meadow"
    assert preview.project_id == "green-meadow"
    assert preview.historical_tasks_eligible is False
    assert str(project) not in preview.model_dump_json()


def test_setup_requires_explicit_consent_before_any_native_work(tmp_path: Path) -> None:
    project = tmp_path / "Kairn"
    project.mkdir()
    service = DesktopSetupApplicationService(
        paths=PlatformPaths(
            platform="development",
            state_root=tmp_path / "state",
            config_root=tmp_path / "config",
            historical_state_root=tmp_path / "old-state",
            historical_config_root=tmp_path / "old-config",
        ),
        inspector=FakeInspector(),  # type: ignore[arg-type]
    )
    snapshot = service.snapshot()
    preview = service.preview_project(project)

    with pytest.raises(ValueError, match="consent"):
        service.initialize(
            preview_token=preview.preview_token,
            expected_setup_digest=str(snapshot.content_digest),
            consent_confirmed=False,
        )


def test_existing_runtime_adoption_preserves_identity_and_hides_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=UTC)
    config = tmp_path / "existing" / "config.json"
    config.parent.mkdir()
    config.write_text("{}", encoding="utf-8")
    service = DesktopSetupApplicationService(
        paths=PlatformPaths(
            platform="development",
            state_root=tmp_path / "state",
            config_root=tmp_path / "preferences",
            historical_state_root=tmp_path / "old-state",
            historical_config_root=tmp_path / "old-preferences",
        ),
        inspector=FakeInspector(),  # type: ignore[arg-type]
        clock=lambda: now,
    )
    summary = ExistingInstallationSummary(
        signer_fingerprint=f"sha256:{'a' * 64}",
        project_count=3,
        consent_expires_at=datetime(2026, 9, 20, tzinfo=UTC),
        secure_store_ready=True,
    )
    monkeypatch.setattr(service, "_summarize_config", lambda path: summary)
    setup_digest = str(service.snapshot().content_digest)

    token, preview = service.preview_existing(config)
    adopted = service.adopt_existing(
        preview_token=token,
        expected_setup_digest=setup_digest,
    )

    assert preview == summary
    assert adopted.signer_fingerprint == summary.signer_fingerprint
    assert service.preferences_store.load().runtime_config_path == config.resolve()
    assert str(config) not in preview.model_dump_json()
