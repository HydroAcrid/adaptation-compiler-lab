"""Privacy-default and atomic desktop-preference tests."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.desktop.preferences import (
    DesktopPreferences,
    LocalDesktopPreferencesStore,
)


def test_missing_preferences_default_both_observation_modes_off(tmp_path: Path) -> None:
    store = LocalDesktopPreferencesStore(tmp_path)

    preferences = store.load()

    assert preferences.background_enabled is False
    assert preferences.aggregate_reporting_enabled is False
    assert store.path.exists() is False


def test_preferences_round_trip_contains_no_raw_payload_fields(tmp_path: Path) -> None:
    store = LocalDesktopPreferencesStore(tmp_path)
    preferences = DesktopPreferences(
        background_enabled=True,
        aggregate_reporting_enabled=True,
        runtime_config_path=tmp_path / "runtime.json",
    )

    store.save(preferences)

    assert store.load() == preferences
    payload = store.path.read_text(encoding="utf-8")
    assert "prompt" not in payload
    assert "evidence" not in payload
    assert "output" not in payload
