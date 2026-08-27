"""Privacy-default and atomic desktop-preference tests."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.desktop.preferences import (
    DesktopPreferences,
    LocalDesktopPreferencesStore,
)
from adaptation_compiler_lab.serialization import canonical_json


def test_missing_preferences_default_both_observation_modes_off(tmp_path: Path) -> None:
    store = LocalDesktopPreferencesStore(tmp_path)

    preferences = store.load()

    assert preferences.background_enabled is False
    assert preferences.aggregate_reporting_enabled is False
    assert preferences.decision_notifications_enabled is False
    assert preferences.launch_at_login_enabled is False
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


def test_v1_preferences_migrate_without_enabling_new_observation_modes(tmp_path: Path) -> None:
    old_root = tmp_path / "AdaptationCompiler"
    old_root.mkdir()
    runtime = tmp_path / "historical" / "runtime.json"
    (old_root / "desktop-preferences.json").write_text(
        canonical_json(
            {
                "preferences_version": "1.0.0",
                "background_enabled": True,
                "aggregate_reporting_enabled": False,
                "runtime_config_path": str(runtime),
                "predecessor_config_path": None,
            }
        ),
        encoding="utf-8",
    )
    store = LocalDesktopPreferencesStore(tmp_path / "Temper", legacy_roots=(old_root,))

    migrated = store.load()

    assert migrated.preferences_version == "1.1.0"
    assert migrated.background_enabled is True
    assert migrated.aggregate_reporting_enabled is False
    assert migrated.decision_notifications_enabled is False
    assert migrated.launch_at_login_enabled is False
    assert migrated.runtime_config_path == runtime
    assert store.path.exists() is False
