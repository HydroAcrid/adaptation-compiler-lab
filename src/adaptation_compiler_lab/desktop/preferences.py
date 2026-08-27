"""Local raw-free desktop preferences with privacy-preserving defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.domain import FrozenModel
from adaptation_compiler_lab.serialization import canonical_json


class _LegacyDesktopPreferencesV1(FrozenModel):
    preferences_version: Literal["1.0.0"] = "1.0.0"
    background_enabled: bool = False
    aggregate_reporting_enabled: bool = False
    runtime_config_path: Path | None = None
    predecessor_config_path: Path | None = None


class DesktopPreferences(FrozenModel):
    """Non-secret installation preferences with every observation switch default off."""

    preferences_version: Literal["1.1.0"] = "1.1.0"
    background_enabled: bool = False
    aggregate_reporting_enabled: bool = False
    decision_notifications_enabled: bool = False
    launch_at_login_enabled: bool = False
    runtime_config_path: Path | None = None
    predecessor_config_path: Path | None = None


class LocalDesktopPreferencesStore:
    """Atomic local preference store containing no raw evidence or credentials."""

    def __init__(self, state_root: Path, *, legacy_roots: tuple[Path, ...] = ()) -> None:
        self._root = state_root.expanduser().resolve()
        self._path = self._root / "desktop-preferences.json"
        self._legacy_paths = tuple(
            root.expanduser().resolve() / "desktop-preferences.json" for root in legacy_roots
        )

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> DesktopPreferences:
        source = self._path
        if not source.exists():
            source = next((path for path in self._legacy_paths if path.is_file()), source)
        if not source.exists():
            return DesktopPreferences()
        try:
            payload = source.read_text(encoding="utf-8")
            try:
                return DesktopPreferences.model_validate_json(payload, strict=True)
            except ValueError:
                legacy = _LegacyDesktopPreferencesV1.model_validate_json(payload, strict=True)
                return DesktopPreferences(
                    background_enabled=legacy.background_enabled,
                    aggregate_reporting_enabled=legacy.aggregate_reporting_enabled,
                    runtime_config_path=legacy.runtime_config_path,
                    predecessor_config_path=legacy.predecessor_config_path,
                )
        except (OSError, ValueError) as error:
            raise ValueError("desktop preferences are invalid") from error

    def save(self, preferences: DesktopPreferences) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._root.chmod(0o700)
        temporary = self._path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(canonical_json(preferences) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)
