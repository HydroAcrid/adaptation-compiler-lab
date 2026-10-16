"""Bounded local agent inspection for truthful desktop connection states."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_RUNTIME_LOCK,
    RuntimeConformanceError,
    load_dogfood_runtime_pins,
    load_runtime_pins,
    select_product_codex_runtime_lock,
    sha256_file,
    verify_codex_runtime,
)
from adaptation_compiler_lab.desktop.models import (
    AgentConnectionV1,
    ConnectionAuthenticationState,
)


class ProbeRunner(Protocol):
    """Small seam for deterministic command-probe tests."""

    def run(self, argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]: ...


class LocalProbeRunner:
    """Run one exact argv without a shell or inherited API-key credentials."""

    def run(self, argv: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "CODEX_API_KEY", "OPENAI_API_KEY"}
        }
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=environment,
        )


class AgentConnectionInspector:
    """Inspect only fixed local agent commands and expose no private paths."""

    def __init__(
        self,
        *,
        runner: ProbeRunner | None = None,
        environ: Mapping[str, str] | None = None,
        platform_name: str | None = None,
        codex_pin_path: Path | None = None,
        claude_pin_path: Path | None = None,
    ) -> None:
        self._runner = runner or LocalProbeRunner()
        self._environ = os.environ if environ is None else environ
        self._platform = sys.platform if platform_name is None else platform_name
        self._codex_pin_path = codex_pin_path
        self._claude_pin_path = claude_pin_path or DEFAULT_RUNTIME_LOCK

    def inspect(self) -> tuple[AgentConnectionV1, AgentConnectionV1, AgentConnectionV1]:
        return self.inspect_codex(), self.inspect_claude(), self.inspect_copilot()

    def inspect_codex(self) -> AgentConnectionV1:
        executable = self._find_executable("codex")
        if executable is None:
            return AgentConnectionV1(
                agent_id="codex",
                display_name="Codex",
                installation_state="not_installed",
                authentication_state="unknown",
                conformance_state="unverified",
                integration_state="unavailable",
                status_summary="Codex was not found in a supported location.",
                learning_capability="Unavailable until a compatible Codex installation is found.",
                delivery_capability="Unavailable until a compatible Codex installation is found.",
                cost_posture="Uses saved ChatGPT authentication; API keys are not supported.",
            )
        version = self._version(executable)
        authentication = self._codex_authentication(executable)
        conformant = False
        try:
            if self._codex_pin_path is None:
                select_product_codex_runtime_lock(executable, self._platform)
            else:
                pin = load_dogfood_runtime_pins(self._codex_pin_path).codex
                verify_codex_runtime(executable, pin)
            conformant = True
        except (OSError, RuntimeConformanceError):
            pass
        return AgentConnectionV1(
            agent_id="codex",
            display_name="Codex",
            installation_state="installed",
            authentication_state=authentication,
            conformance_state="compatible" if conformant else "update_required",
            integration_state=(
                "connected" if conformant and authentication == "signed_in" else "unavailable"
            ),
            version_label=version,
            status_summary=(
                "Ready to use with Temper."
                if conformant and authentication == "signed_in"
                else "Temper needs a compatible, ChatGPT-authenticated Codex installation."
                if conformant
                else "Temper needs an updated connector for this Codex version."
            ),
            learning_capability=(
                "Learns from eligible completed tasks created after project registration."
                if conformant and authentication == "signed_in"
                else "Learning is unavailable until the connection is ready."
            ),
            delivery_capability=(
                "Approved suggestions go to fresh Temper-managed tasks. Authorized style defaults "
                "can also reach ordinary Codex chats through native instructions "
                "or scoped MCP context."
                if conformant and authentication == "signed_in"
                else "Delivery is unavailable until the connection is ready."
            ),
            cost_posture="Uses saved ChatGPT authentication; API keys are never consumed.",
            available_actions=(
                ("refresh", "use_for_setup")
                if conformant and authentication == "signed_in"
                else ("refresh",)
            ),
        )

    def inspect_claude(self) -> AgentConnectionV1:
        executable = self._find_executable("claude")
        if executable is None:
            return AgentConnectionV1(
                agent_id="claude",
                display_name="Claude Code",
                installation_state="not_installed",
                authentication_state="unknown",
                conformance_state="not_applicable",
                integration_state="unavailable",
                status_summary="Claude Code is not installed. Temper does not install it.",
                learning_capability="Not integrated in this Temper build.",
                delivery_capability="Not integrated in this Temper build.",
                cost_posture="Future Claude use would be billed by Anthropic.",
            )
        version = self._version(executable)
        authentication = self._claude_authentication(executable)
        conformant = self._claude_conformant(executable)
        ready = conformant and authentication == "signed_in"
        return AgentConnectionV1(
            agent_id="claude",
            display_name="Claude Code",
            installation_state="installed",
            authentication_state=authentication,
            conformance_state="compatible" if conformant else "update_required",
            integration_state="available" if ready else "unavailable",
            version_label=version,
            status_summary=(
                "Ready for you to review the local Temper connection."
                if ready
                else "Sign in to the pinned Claude Code installation before connecting."
                if conformant
                else "Temper needs an updated connector for this Claude Code version."
            ),
            learning_capability=(
                "Can capture authorized user prompts from registered projects after connection."
                if ready
                else "Learning is unavailable until the connection is ready."
            ),
            delivery_capability=(
                "Can deliver only a signed cached projection in registered projects."
                if ready
                else "Delivery is unavailable until the connection is ready."
            ),
            cost_posture=(
                "Connecting is local and free; ordinary Claude Code use is billed by Anthropic."
            ),
            available_actions=("refresh", "connect") if ready else ("refresh",),
        )

    def inspect_copilot(self) -> AgentConnectionV1:
        """Inspect the documented Copilot CLI only; IDE/cloud surfaces are file-based."""

        executable = self._find_executable("copilot")
        if executable is None:
            return AgentConnectionV1(
                agent_id="copilot",
                display_name="GitHub Copilot",
                installation_state="not_installed",
                authentication_state="unknown",
                conformance_state="not_applicable",
                integration_state="unavailable",
                status_summary="GitHub Copilot CLI is not installed. Temper does not install it.",
                learning_capability=(
                    "Supported repository instructions can still be inspected per project."
                ),
                delivery_capability=(
                    "Other Copilot surfaces use confirmed repository-instruction previews only."
                ),
                cost_posture="Temper does not initiate or bill Copilot provider use.",
            )
        version = self._version(executable)
        conformant = version is not None and "1.0.54" in version
        return AgentConnectionV1(
            agent_id="copilot",
            display_name="GitHub Copilot",
            installation_state="installed",
            authentication_state="unknown",
            conformance_state="compatible" if conformant else "update_required",
            integration_state="available" if conformant else "unavailable",
            version_label=version,
            status_summary=(
                "Compatible Copilot CLI found; direct Temper delivery is not connected yet."
                if conformant
                else "Temper needs an updated connector for this Copilot CLI version."
            ),
            learning_capability=(
                "Repository instructions are understood; ordinary Copilot capture is not connected."
            ),
            delivery_capability=(
                "Copilot CLI supports a local hook; other surfaces use confirmed file previews."
                if conformant
                else "Only existing repository instructions can be inspected."
            ),
            cost_posture="Connection work is local; Copilot usage follows the user's GitHub plan.",
            available_actions=("refresh", "connect") if conformant else ("refresh",),
        )

    def _claude_conformant(self, executable: Path) -> bool:
        try:
            pin = load_runtime_pins(self._claude_pin_path).claude_code.executable
            if sha256_file(executable) != pin.executable_sha256:
                return False
            version = self._runner.run(
                (str(executable), *pin.version_args),
                timeout=5.0,
            )
            if version.returncode != 0 or version.stdout.strip() != pin.version_stdout:
                return False
            help_result = self._runner.run((str(executable), "--help"), timeout=8.0)
            return help_result.returncode == 0 and all(
                flag in help_result.stdout for flag in pin.required_help_flags
            )
        except (OSError, RuntimeConformanceError, subprocess.TimeoutExpired):
            return False

    def codex_executable(self) -> Path | None:
        """Return the internally inspected candidate; never serialize this value."""

        return self._find_executable("codex")

    def _find_executable(self, name: str) -> Path | None:
        command = f"{name}.exe" if self._platform == "win32" else name
        path_value = self._environ.get("PATH")
        located = shutil.which(command, path=path_value)
        candidates: list[Path] = []
        if located:
            candidates.append(Path(located))
        if self._platform == "win32":
            local_app_data = self._environ.get("LOCALAPPDATA")
            if local_app_data and name == "codex":
                root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
                if root.is_dir():
                    candidates.extend(sorted(root.glob("*/codex.exe"), reverse=True))
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve(strict=True)
            except OSError:
                continue
            if resolved.is_file():
                return resolved
        return None

    def _version(self, executable: Path) -> str | None:
        try:
            completed = self._runner.run((str(executable), "--version"), timeout=5.0)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        value = completed.stdout.strip().splitlines()
        return value[0][:120] if value else None

    def _codex_authentication(self, executable: Path) -> ConnectionAuthenticationState:
        try:
            completed = self._runner.run(
                (str(executable), "login", "status"),
                timeout=8.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        output = f"{completed.stdout}\n{completed.stderr}".casefold()
        if completed.returncode == 0 and "chatgpt" in output and "logged in" in output:
            return "signed_in"
        return "signed_out" if completed.returncode != 0 else "unknown"

    def _claude_authentication(self, executable: Path) -> ConnectionAuthenticationState:
        try:
            completed = self._runner.run(
                (str(executable), "auth", "status"),
                timeout=8.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        if completed.returncode != 0:
            return "signed_out"
        output = f"{completed.stdout}\n{completed.stderr}".casefold()
        return "signed_in" if "logged" in output or "authenticated" in output else "unknown"
