"""Local raw-free desktop preferences with privacy-preserving defaults."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.domain import FrozenModel
from adaptation_compiler_lab.serialization import canonical_json


class DesktopPreferences(FrozenModel):
    """Non-secret installation preferences; both observation switches default off."""

    preferences_version: Literal["1.0.0"] = "1.0.0"
    background_enabled: bool = False
    aggregate_reporting_enabled: bool = False
    runtime_config_path: Path | None = None
    predecessor_config_path: Path | None = None


class LocalDesktopPreferencesStore:
    """Atomic local preference store containing no raw evidence or credentials."""

    def __init__(self, state_root: Path) -> None:
        self._root = state_root.expanduser().resolve()
        self._path = self._root / "desktop-preferences.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> DesktopPreferences:
        if not self._path.exists():
            return DesktopPreferences()
        try:
            return DesktopPreferences.model_validate_json(
                self._path.read_text(encoding="utf-8"),
                strict=True,
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
