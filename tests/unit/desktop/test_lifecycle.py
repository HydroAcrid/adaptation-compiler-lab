"""Transactional opt-in lifecycle tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from adaptation_compiler_lab.desktop.lifecycle import DesktopLifecycleService
from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore


@dataclass
class FakeAutostart:
    installed: list[tuple[Path, Path]] = field(default_factory=list)
    remove_count: int = 0

    def install(self, *, executable: Path, config_path: Path) -> None:
        self.installed.append((executable, config_path))

    def remove(self) -> None:
        self.remove_count += 1


def _lifecycle(tmp_path: Path, autostart: FakeAutostart | None) -> DesktopLifecycleService:
    executable = tmp_path / "AdaptationCompiler"
    config = tmp_path / "runtime.json"
    executable.touch()
    config.touch()
    return DesktopLifecycleService(
        LocalDesktopPreferencesStore(tmp_path / "preferences"),
        executable=executable,
        config_path=config,
        autostart=autostart,
        watcher_stop_path=tmp_path / "runtime" / "watcher-stop",
    )


def test_background_opt_in_installs_before_persisting_and_pause_requests_stop(
    tmp_path: Path,
) -> None:
    autostart = FakeAutostart()
    lifecycle = _lifecycle(tmp_path, autostart)

    enabled = lifecycle.set_background_enabled(True)
    disabled = lifecycle.set_background_enabled(False)

    assert enabled.background_enabled is True
    assert disabled.background_enabled is False
    assert len(autostart.installed) == 1
    assert autostart.remove_count == 1
    assert (tmp_path / "runtime" / "watcher-stop").exists()


def test_background_opt_in_fails_closed_without_native_manager(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path, None)

    with pytest.raises(ValueError, match="unavailable"):
        lifecycle.set_background_enabled(True)

    assert lifecycle.preferences().background_enabled is False


def test_reporting_is_independent_from_background_opt_in(tmp_path: Path) -> None:
    lifecycle = _lifecycle(tmp_path, FakeAutostart())

    updated = lifecycle.set_reporting_enabled(True)

    assert updated.aggregate_reporting_enabled is True
    assert updated.background_enabled is False
