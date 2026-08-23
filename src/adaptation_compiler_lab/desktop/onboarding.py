"""Fail-closed first-run import for an existing governed local runtime."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _load_config,
    load_terminal_alpha_snapshot,
)
from adaptation_compiler_lab.connectors.pins import RuntimeConformanceError
from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore


class DesktopSetupController(QObject):
    """Validate and remember a local config without exposing its contents to QML."""

    stateChanged = Signal()
    configured = Signal(str)

    def __init__(
        self,
        store: LocalDesktopPreferencesStore,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._selected_path = ""
        self._predecessor_path = ""
        self._message = ""
        self._message_is_error = False

    @Property(str, notify=stateChanged)
    def selectedPath(self) -> str:
        return self._selected_path

    @Property(str, notify=stateChanged)
    def predecessorPath(self) -> str:
        return self._predecessor_path

    @Property(str, notify=stateChanged)
    def message(self) -> str:
        return self._message

    @Property(bool, notify=stateChanged)
    def messageIsError(self) -> bool:
        return self._message_is_error

    @Property(bool, notify=stateChanged)
    def canContinue(self) -> bool:
        return bool(self._selected_path) and not self._message_is_error

    @Slot(str)
    def inspectConfig(self, file_url: str) -> None:
        url = QUrl(file_url)
        if not url.isLocalFile():
            self._set_state("", "Choose a local runtime config file.", error=True)
            return
        path = Path(url.toLocalFile()).expanduser().resolve()
        try:
            config = _load_config(path)
        except (OSError, ValueError):
            self._set_state("", "That file is not a supported governed setup.", error=True)
            return
        self._set_state(
            str(path),
            f"Ready to use {len(config.projects)} registered project(s).",
            error=False,
        )

    @Slot(str)
    def inspectPredecessor(self, file_url: str) -> None:
        url = QUrl(file_url)
        if not url.isLocalFile():
            self._set_state(
                self._selected_path,
                "Choose a local predecessor config file.",
                error=True,
            )
            return
        path = Path(url.toLocalFile()).expanduser().resolve()
        try:
            _load_config(path)
        except (OSError, ValueError):
            self._set_state(
                self._selected_path,
                "That predecessor file is not a supported governed setup.",
                error=True,
            )
            return
        self._predecessor_path = str(path)
        self._set_state(
            self._selected_path,
            "Preserved predecessor selected. The exact lineage will be verified before saving.",
            error=False,
        )

    @Slot()
    def continueWithConfig(self) -> None:
        if not self.canContinue:
            self._set_state("", "Choose and verify a setup first.", error=True)
            return
        path = Path(self._selected_path)
        predecessor = None if not self._predecessor_path else Path(self._predecessor_path)
        try:
            _load_config(path)
            if predecessor is not None:
                _load_config(predecessor)
            load_terminal_alpha_snapshot(
                path,
                predecessor_config_path=predecessor,
                poll_now=False,
            )
            current = self._store.load()
            self._store.save(
                current.model_copy(
                    update={
                        "runtime_config_path": path,
                        "predecessor_config_path": predecessor,
                        "background_enabled": False,
                        "aggregate_reporting_enabled": False,
                    }
                )
            )
        except (OSError, ValueError, RuntimeConformanceError):
            self._set_state("", "The setup changed before it could be saved.", error=True)
            return
        self.configured.emit(str(path))

    def _set_state(self, path: str, message: str, *, error: bool) -> None:
        self._selected_path = path
        self._message = message
        self._message_is_error = error
        self.stateChanged.emit()
