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

    codex, claude = inspector.inspect()

    assert codex.conformance_state == "compatible"
    assert codex.authentication_state == "signed_in"
    assert "completed tasks" in codex.learning_capability
    assert "fresh Temper-managed" in codex.delivery_capability
    assert codex.available_actions == ("refresh", "use_for_setup")
    assert claude.installation_state == "not_installed"
    assert "Not integrated" in claude.learning_capability


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
