"""Small native-platform adapters for paths and opt-in same-user autostart."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore

HostPlatform = Literal["windows", "macos", "development"]


class PlatformIntegrationError(ValueError):
    """Raised when a native integration cannot be installed exactly."""


@dataclass(frozen=True, slots=True)
class PlatformPaths:
    platform: HostPlatform
    state_root: Path
    config_root: Path
    historical_state_root: Path
    historical_config_root: Path


def platform_paths(
    *,
    platform_name: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> PlatformPaths:
    """Return product-owned roots without consulting repository or WSL paths."""

    selected = sys.platform if platform_name is None else platform_name
    variables = os.environ if environ is None else environ
    user_home = Path.home() if home is None else home
    if selected == "win32":
        local = variables.get("LOCALAPPDATA")
        roaming = variables.get("APPDATA")
        if not local or not roaming:
            raise PlatformIntegrationError("Windows application-data roots are unavailable")
        return PlatformPaths(
            platform="windows",
            state_root=Path(local) / "Temper",
            config_root=Path(roaming) / "Temper",
            historical_state_root=Path(local) / "AdaptationCompiler",
            historical_config_root=Path(roaming) / "AdaptationCompiler",
        )
    if selected == "darwin":
        support = user_home / "Library" / "Application Support" / "Temper"
        historical = user_home / "Library" / "Application Support" / "Adaptation Compiler"
        return PlatformPaths(
            platform="macos",
            state_root=support,
            config_root=support,
            historical_state_root=historical,
            historical_config_root=historical,
        )
    development = user_home / ".local" / "state" / "temper"
    return PlatformPaths(
        platform="development",
        state_root=development,
        config_root=user_home / ".config" / "temper",
        historical_state_root=user_home / ".local" / "state" / "adaptation-compiler",
        historical_config_root=user_home / ".config" / "adaptation-compiler",
    )


def product_preferences_store(paths: PlatformPaths) -> LocalDesktopPreferencesStore:
    """Use Temper-branded preferences while reading the historical product path once."""

    from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore

    return LocalDesktopPreferencesStore(
        paths.config_root,
        legacy_roots=(paths.historical_config_root, paths.historical_state_root),
    )


class AutostartManager(Protocol):
    def install(self, *, executable: Path, config_path: Path) -> None: ...

    def remove(self) -> None: ...


class WindowsAutostartManager:
    """Install a same-user limited Task Scheduler entry for the signed executable."""

    def __init__(self, *, task_name: str = "Adaptation Compiler", command: str = "schtasks.exe"):
        self._task_name = task_name
        self._command = command

    def install(self, *, executable: Path, config_path: Path) -> None:
        binary = _required_file(executable, label="desktop executable")
        config = _required_file(config_path, label="runtime config")
        action = f'"{binary}" --background --config "{config}"'
        self._run(
            [
                self._command,
                "/Create",
                "/F",
                "/SC",
                "ONLOGON",
                "/RL",
                "LIMITED",
                "/TN",
                self._task_name,
                "/TR",
                action,
            ]
        )

    def remove(self) -> None:
        self._run([self._command, "/Delete", "/F", "/TN", self._task_name])

    @staticmethod
    def _run(arguments: list[str]) -> None:
        try:
            result = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PlatformIntegrationError("Windows autostart is unavailable") from error
        if result.returncode != 0:
            raise PlatformIntegrationError("Windows autostart refused the requested change")


class MacOSAutostartManager:
    """Install one per-user LaunchAgent with an argument array and no embedded secret."""

    def __init__(
        self,
        *,
        launch_agents_root: Path | None = None,
        label: str = "local.adaptation-compiler.background",
        command: str = "/bin/launchctl",
        user_id: int | None = None,
    ) -> None:
        self._root = launch_agents_root or Path.home() / "Library" / "LaunchAgents"
        self._label = label
        self._command = command
        self._uid = os.getuid() if user_id is None else user_id
        self._path = self._root / f"{label}.plist"

    def install(self, *, executable: Path, config_path: Path) -> None:
        binary = _required_file(executable, label="desktop executable")
        config = _required_file(config_path, label="runtime config")
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": self._label,
            "ProgramArguments": [str(binary), "--background", "--config", str(config)],
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Background",
        }
        temporary = self._path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            plistlib.dump(payload, stream, sort_keys=True)
        temporary.chmod(0o600)
        os.replace(temporary, self._path)
        self._run("bootstrap", f"gui/{self._uid}", str(self._path))

    def remove(self) -> None:
        if not self._path.exists():
            return
        self._run("bootout", f"gui/{self._uid}", str(self._path))
        self._path.unlink(missing_ok=True)

    def _run(self, *arguments: str) -> None:
        try:
            result = subprocess.run(
                [self._command, *arguments],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PlatformIntegrationError("macOS autostart is unavailable") from error
        if result.returncode != 0:
            raise PlatformIntegrationError("macOS autostart refused the requested change")


def _required_file(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise PlatformIntegrationError(f"{label} is unavailable")
    return resolved
