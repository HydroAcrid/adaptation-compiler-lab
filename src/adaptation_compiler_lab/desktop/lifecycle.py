"""Transactional desktop opt-in lifecycle for background work and aggregate reporting."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.desktop.platform import AutostartManager
from adaptation_compiler_lab.desktop.preferences import (
    DesktopPreferences,
    LocalDesktopPreferencesStore,
)


class DesktopLifecycleService:
    """Apply native lifecycle changes before publishing their local preference state."""

    def __init__(
        self,
        store: LocalDesktopPreferencesStore,
        *,
        executable: Path,
        config_path: Path,
        autostart: AutostartManager | None,
        watcher_stop_path: Path,
    ) -> None:
        self._store = store
        self._executable = executable
        self._config_path = config_path
        self._autostart = autostart
        self._stop_path = watcher_stop_path

    def preferences(self) -> DesktopPreferences:
        return self._store.load()

    def set_background_enabled(self, enabled: bool) -> DesktopPreferences:
        current = self._store.load()
        if current.background_enabled is enabled:
            return current
        if self._autostart is None:
            raise ValueError("background startup is unavailable in this development build")
        if enabled:
            self._stop_path.unlink(missing_ok=True)
            self._autostart.install(
                executable=self._executable,
                config_path=self._config_path,
            )
        else:
            self._stop_path.parent.mkdir(parents=True, exist_ok=True)
            self._stop_path.touch(exist_ok=True)
            self._autostart.remove()
        updated = current.model_copy(update={"background_enabled": enabled})
        try:
            self._store.save(updated)
        except BaseException:
            if enabled:
                self._autostart.remove()
                self._stop_path.touch(exist_ok=True)
            else:
                self._stop_path.unlink(missing_ok=True)
                self._autostart.install(
                    executable=self._executable,
                    config_path=self._config_path,
                )
            raise
        return updated

    def set_reporting_enabled(self, enabled: bool) -> DesktopPreferences:
        current = self._store.load()
        updated = current.model_copy(update={"aggregate_reporting_enabled": enabled})
        self._store.save(updated)
        return updated
