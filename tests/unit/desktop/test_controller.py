"""Offscreen Qt/QML tests for the raw-free desktop presentation boundary."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine

from adaptation_compiler_lab.desktop.controller import DesktopController
from adaptation_compiler_lab.desktop.service import DesktopApplicationService
from tests.unit.automatic_runtime.test_runtime import NOW
from tests.unit.automatic_runtime.test_terminal_alpha import _empty_snapshot
from tests.unit.desktop.test_service import FakeDesktopBackend


def test_controller_projects_only_normalized_raw_free_fields(tmp_path: Path) -> None:
    terminal, _state = _empty_snapshot(tmp_path)
    controller = DesktopController(
        DesktopApplicationService(
            FakeDesktopBackend(terminal),
            background_enabled=True,
            clock=lambda: NOW,
        )
    )

    controller.refresh()

    assert controller.property("ready") is True
    assert controller.property("statusTitle") == "You're all set"
    serialized = repr(
        (
            controller.property("projects"),
            controller.property("suggestions"),
            controller.property("adaptations"),
            controller.property("message"),
        )
    )
    assert "supporting_quote" not in serialized
    assert "locator" not in serialized
    assert "raw_payload" not in serialized


def test_main_qml_loads_offscreen_with_typed_controller(qtbot: object, tmp_path: Path) -> None:
    del qtbot
    terminal, _state = _empty_snapshot(tmp_path)
    controller = DesktopController(
        DesktopApplicationService(
            FakeDesktopBackend(terminal),
            background_enabled=True,
            clock=lambda: NOW,
        )
    )
    controller.refresh()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("desktopController", controller)
    qml_path = (
        Path(__file__).parents[3]
        / "src"
        / "adaptation_compiler_lab"
        / "desktop"
        / "qml"
        / "Main.qml"
    )

    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))

    assert len(engine.rootObjects()) == 1
    root = engine.rootObjects()[0]
    assert root.property("title") == "Adaptation Compiler"
    root.setProperty("visible", False)
