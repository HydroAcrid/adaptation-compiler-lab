"""First-run desktop setup imports only an exact governed local configuration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QUrl

from adaptation_compiler_lab.desktop import onboarding
from adaptation_compiler_lab.desktop.onboarding import DesktopSetupController
from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore


def test_nonlocal_and_invalid_configs_fail_closed(tmp_path: Path) -> None:
    controller = DesktopSetupController(LocalDesktopPreferencesStore(tmp_path / "preferences"))

    controller.inspectConfig("https://example.com/config.json")

    assert controller.property("canContinue") is False
    assert controller.property("messageIsError") is True
    invalid = tmp_path / "config.json"
    invalid.write_text("{}", encoding="utf-8")
    controller.inspectConfig(QUrl.fromLocalFile(str(invalid)).toString())
    assert controller.property("canContinue") is False


def test_verified_config_is_saved_with_both_observation_modes_off(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        onboarding,
        "_load_config",
        lambda path: SimpleNamespace(projects=("one", "two")) if path == config else None,
    )
    monkeypatch.setattr(
        onboarding,
        "load_terminal_alpha_snapshot",
        lambda path, *, predecessor_config_path, poll_now: (
            path,
            predecessor_config_path,
            poll_now,
        ),
    )
    store = LocalDesktopPreferencesStore(tmp_path / "preferences")
    controller = DesktopSetupController(store)
    configured: list[str] = []
    controller.configured.connect(configured.append)

    controller.inspectConfig(QUrl.fromLocalFile(str(config)).toString())
    controller.continueWithConfig()

    preferences = store.load()
    assert controller.property("canContinue") is True
    assert configured == [str(config)]
    assert preferences.runtime_config_path == config
    assert preferences.background_enabled is False
    assert preferences.aggregate_reporting_enabled is False


def test_optional_predecessor_is_preserved_and_exact_lineage_is_validated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = tmp_path / "current.json"
    predecessor = tmp_path / "predecessor.json"
    current.write_text("{}", encoding="utf-8")
    predecessor.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        onboarding,
        "_load_config",
        lambda _path: SimpleNamespace(projects=("one",)),
    )
    lineage_calls: list[tuple[Path, Path | None, bool]] = []

    def verify_lineage(
        path: Path,
        *,
        predecessor_config_path: Path | None,
        poll_now: bool,
    ) -> tuple[object, object]:
        lineage_calls.append((path, predecessor_config_path, poll_now))
        return object(), object()

    monkeypatch.setattr(onboarding, "load_terminal_alpha_snapshot", verify_lineage)
    store = LocalDesktopPreferencesStore(tmp_path / "preferences")
    controller = DesktopSetupController(store)

    controller.inspectConfig(QUrl.fromLocalFile(str(current)).toString())
    controller.inspectPredecessor(QUrl.fromLocalFile(str(predecessor)).toString())
    controller.continueWithConfig()

    assert store.load().predecessor_config_path == predecessor
    assert lineage_calls == [(current, predecessor, False)]


def test_onboarding_qml_loads_offscreen(qtbot: object) -> None:
    del qtbot
    from PySide6.QtQml import QQmlApplicationEngine

    controller = DesktopSetupController(LocalDesktopPreferencesStore(Path.cwd() / ".unused"))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("setupController", controller)
    qml_path = (
        Path(__file__).parents[3]
        / "src"
        / "adaptation_compiler_lab"
        / "desktop"
        / "qml"
        / "Onboarding.qml"
    )

    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))

    assert len(engine.rootObjects()) == 1
    root = engine.rootObjects()[0]
    assert root.property("title") == "Set up Adaptation Compiler"
    root.setProperty("visible", False)
