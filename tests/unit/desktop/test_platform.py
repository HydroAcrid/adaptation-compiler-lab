"""Deterministic platform-path and same-user autostart tests."""

from __future__ import annotations

import plistlib
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from adaptation_compiler_lab.desktop import platform as native


def test_windows_and_macos_paths_never_depend_on_repository_root(tmp_path: Path) -> None:
    windows = native.platform_paths(
        platform_name="win32",
        environ={
            "LOCALAPPDATA": str(tmp_path / "Local"),
            "APPDATA": str(tmp_path / "Roaming"),
        },
        home=tmp_path,
    )
    macos = native.platform_paths(platform_name="darwin", environ={}, home=tmp_path)

    assert windows.state_root == tmp_path / "Local" / "AdaptationCompiler"
    assert windows.config_root == tmp_path / "Roaming" / "AdaptationCompiler"
    assert macos.state_root == (
        tmp_path / "Library" / "Application Support" / "Adaptation Compiler"
    )
    assert "projects" not in str(windows.state_root)
    assert "projects" not in str(macos.state_root)


def test_windows_autostart_uses_limited_same_user_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "AdaptationCompiler.exe"
    config = tmp_path / "runtime.json"
    executable.touch()
    config.touch()
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs: object) -> CompletedProcess[str]:
        calls.append(arguments)
        return CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr("adaptation_compiler_lab.desktop.platform.subprocess.run", fake_run)

    native.WindowsAutostartManager().install(executable=executable, config_path=config)

    arguments = calls[0]
    assert "/RL" in arguments
    assert arguments[arguments.index("/RL") + 1] == "LIMITED"
    assert "--background" in arguments[arguments.index("/TR") + 1]
    assert not any("key" in item.lower() for item in arguments)


def test_macos_autostart_writes_argument_array_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "Adaptation Compiler"
    config = tmp_path / "runtime.json"
    executable.touch()
    config.touch()

    def fake_run(arguments: list[str], **_kwargs: object) -> CompletedProcess[str]:
        return CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr("adaptation_compiler_lab.desktop.platform.subprocess.run", fake_run)
    launch_root = tmp_path / "LaunchAgents"
    manager = native.MacOSAutostartManager(
        launch_agents_root=launch_root,
        command="launchctl",
        user_id=501,
    )

    manager.install(executable=executable, config_path=config)

    plist_path = launch_root / "local.adaptation-compiler.background.plist"
    with plist_path.open("rb") as stream:
        payload = plistlib.load(stream)
    assert payload["ProgramArguments"] == [
        str(executable.resolve()),
        "--background",
        "--config",
        str(config.resolve()),
    ]
    serialized = plist_path.read_text(encoding="utf-8").lower()
    assert "api_key" not in serialized
    assert "token" not in serialized
    assert "credential" not in serialized
