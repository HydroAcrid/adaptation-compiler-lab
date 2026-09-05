from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.desktop import connections
from adaptation_compiler_lab.desktop.connections import AgentConnectionInspector


class FakeRunner:
    def run(self, argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        if tuple(argv[1:]) == ("--version",):
            return subprocess.CompletedProcess(argv, 0, "codex-cli 0.150.0-alpha.8\n", "")
        if tuple(argv[1:]) == ("login", "status"):
            return subprocess.CompletedProcess(argv, 0, "Logged in using ChatGPT\n", "")
        raise AssertionError(f"unexpected probe: {argv!r}")


class ClaudeRunner:
    def run(self, argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        if tuple(argv[1:]) == ("--version",):
            return subprocess.CompletedProcess(argv, 0, "2.1.218 (Claude Code)\n", "")
        if tuple(argv[1:]) == ("auth", "status"):
            return subprocess.CompletedProcess(argv, 0, "Logged in\n", "")
        if tuple(argv[1:]) == ("--help",):
            return subprocess.CompletedProcess(argv, 0, "synthetic help\n", "")
        raise AssertionError(f"unexpected probe: {argv!r}")


class CopilotRunner:
    def run(self, argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        if tuple(argv[1:]) == ("--version",):
            return subprocess.CompletedProcess(argv, 0, "GitHub Copilot CLI 1.0.54\n", "")
        raise AssertionError(f"unexpected probe: {argv!r}")


def test_codex_connection_reports_separate_truthful_capabilities(
    tmp_path: Path, monkeypatch: Any
) -> None:
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"synthetic")
    executable.chmod(0o700)
    monkeypatch.setattr(connections, "verify_codex_runtime", lambda *_args, **_kwargs: None)
    inspector = AgentConnectionInspector(
        runner=FakeRunner(),
        environ={"PATH": str(tmp_path), "OPENAI_API_KEY": "must-not-be-used"},
        platform_name="win32",
    )

    codex, claude, copilot = inspector.inspect()

    assert codex.conformance_state == "compatible"
    assert codex.authentication_state == "signed_in"
    assert "completed tasks" in codex.learning_capability
    assert "fresh Temper-managed" in codex.delivery_capability
    assert codex.available_actions == ("refresh", "use_for_setup")
    assert codex.integration_state == "connected"
    assert claude.installation_state == "not_installed"
    assert "Not integrated" in claude.learning_capability
    assert copilot.installation_state == "not_installed"
    assert "repository instructions" in copilot.learning_capability


def test_ready_claude_is_available_for_explicit_local_connection(
    tmp_path: Path, monkeypatch: Any
) -> None:
    executable = tmp_path / "claude.exe"
    executable.write_bytes(b"synthetic")
    executable.chmod(0o700)
    monkeypatch.setattr(
        AgentConnectionInspector,
        "_claude_conformant",
        lambda _self, _path: True,
    )
    inspector = AgentConnectionInspector(
        runner=ClaudeRunner(),
        environ={"PATH": str(tmp_path), "CLAUDE_API_KEY": "must-not-be-used"},
        platform_name="win32",
    )

    claude = inspector.inspect_claude()

    assert claude.authentication_state == "signed_in"
    assert claude.conformance_state == "compatible"
    assert claude.integration_state == "available"
    assert claude.available_actions == ("refresh", "connect")
    assert "local and free" in claude.cost_posture


def test_version_drift_never_appears_connected(tmp_path: Path) -> None:
    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"drifted")
    executable.chmod(0o700)
    inspector = AgentConnectionInspector(
        runner=FakeRunner(),
        environ={"PATH": str(tmp_path)},
        platform_name="win32",
    )

    codex = inspector.inspect_codex()

    assert codex.conformance_state == "update_required"
    assert codex.available_actions == ("refresh",)
    assert "updated connector" in codex.status_summary


def test_copilot_detection_does_not_imply_authentication_or_delivery(tmp_path: Path) -> None:
    executable = tmp_path / "copilot.exe"
    executable.write_bytes(b"synthetic")
    executable.chmod(0o700)
    inspector = AgentConnectionInspector(
        runner=FakeRunner(),
        environ={"PATH": str(tmp_path)},
        platform_name="win32",
    )

    copilot = inspector.inspect_copilot()

    assert copilot.installation_state == "installed"
    assert copilot.authentication_state == "unknown"
    assert copilot.conformance_state == "update_required"
    assert copilot.integration_state == "unavailable"
    assert copilot.available_actions == ("refresh",)


def test_current_copilot_cli_reports_hook_as_available_but_not_connected(tmp_path: Path) -> None:
    executable = tmp_path / "copilot.exe"
    executable.write_bytes(b"synthetic")
    executable.chmod(0o700)
    inspector = AgentConnectionInspector(
        runner=CopilotRunner(),
        environ={"PATH": str(tmp_path)},
        platform_name="win32",
    )

    copilot = inspector.inspect_copilot()

    assert copilot.conformance_state == "compatible"
    assert copilot.authentication_state == "unknown"
    assert copilot.integration_state == "available"
    assert "not connected" in copilot.status_summary
    assert "local hook" in copilot.delivery_capability
    assert copilot.available_actions == ("refresh", "connect")
