"""Native desktop entry point for Adaptation Compiler."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config
from adaptation_compiler_lab.desktop.controller import DesktopController
from adaptation_compiler_lab.desktop.lifecycle import DesktopLifecycleService
from adaptation_compiler_lab.desktop.onboarding import DesktopSetupController
from adaptation_compiler_lab.desktop.platform import (
    MacOSAutostartManager,
    WindowsAutostartManager,
    platform_paths,
)
from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore
from adaptation_compiler_lab.desktop.service import (
    CodexDogfoodDesktopBackend,
    DesktopApplicationService,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adaptation-compiler")
    parser.add_argument("--config", type=Path, help="Existing governed local runtime config.")
    parser.add_argument("--predecessor-config", type=Path)
    parser.add_argument("--background-enabled", action="store_true")
    parser.add_argument("--aggregate-reporting-enabled", action="store_true")
    parser.add_argument("--background", action="store_true", help=argparse.SUPPRESS)
    return parser


def _configured_path(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()
    stored = QSettings().value("runtime/configPath", "")
    return Path(stored).expanduser().resolve() if isinstance(stored, str) and stored else None


def _load_state_root(config_path: Path) -> Path:
    return _load_config(config_path).state_root


def main(argv: list[str] | None = None) -> int:
    """Start one local GUI process without reading secrets from environment variables."""

    arguments = _parser().parse_args(argv)
    QCoreApplication.setOrganizationName("Adaptation Compiler")
    QCoreApplication.setOrganizationDomain("local.adaptation-compiler")
    QCoreApplication.setApplicationName("Adaptation Compiler")
    paths = platform_paths()
    preference_store = LocalDesktopPreferencesStore(paths.state_root)
    preferences = preference_store.load()
    if arguments.config is not None:
        preferences = preferences.model_copy(
            update={
                "runtime_config_path": arguments.config.expanduser().resolve(),
                "predecessor_config_path": (
                    preferences.predecessor_config_path
                    if arguments.predecessor_config is None
                    else arguments.predecessor_config.expanduser().resolve()
                ),
                "background_enabled": (
                    preferences.background_enabled or arguments.background_enabled
                ),
                "aggregate_reporting_enabled": (
                    preferences.aggregate_reporting_enabled or arguments.aggregate_reporting_enabled
                ),
            }
        )
        preference_store.save(preferences)
    if arguments.background:
        config_path = preferences.runtime_config_path
        if config_path is None or not config_path.is_file():
            print("Background runtime config is unavailable.", file=sys.stderr)
            return 2
        from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
            execute_runtime_watcher,
        )

        execute_runtime_watcher(config_path)
        return 0
    application = QGuiApplication(sys.argv[:1])
    config_path = preferences.runtime_config_path or _configured_path(arguments.config)
    if config_path is None or not config_path.is_file():
        setup_controller = DesktopSetupController(preference_store)
        setup_engine = QQmlApplicationEngine()
        setup_engine.rootContext().setContextProperty("setupController", setup_controller)
        setup_qml = Path(__file__).with_name("qml") / "Onboarding.qml"
        setup_engine.load(QUrl.fromLocalFile(os.fspath(setup_qml)))
        if not setup_engine.rootObjects():
            return 1

        def close_after_setup(_path: str) -> None:
            application.quit()

        setup_controller.configured.connect(close_after_setup)
        return application.exec()
    QSettings().setValue("runtime/configPath", str(config_path))
    service = DesktopApplicationService(
        CodexDogfoodDesktopBackend(
            config_path,
            predecessor_config_path=preferences.predecessor_config_path,
        ),
        background_enabled=preferences.background_enabled,
        aggregate_reporting_enabled=preferences.aggregate_reporting_enabled,
    )
    autostart = (
        WindowsAutostartManager()
        if paths.platform == "windows"
        else MacOSAutostartManager()
        if paths.platform == "macos"
        else None
    )
    lifecycle = DesktopLifecycleService(
        preference_store,
        executable=Path(sys.executable),
        config_path=config_path,
        autostart=autostart,
        watcher_stop_path=_load_state_root(config_path) / "watcher-stop",
    )
    controller = DesktopController(service, lifecycle=lifecycle)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("desktopController", controller)
    qml_path = Path(__file__).with_name("qml") / "Main.qml"
    engine.load(QUrl.fromLocalFile(os.fspath(qml_path)))
    if not engine.rootObjects():
        return 1
    controller.refresh()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
