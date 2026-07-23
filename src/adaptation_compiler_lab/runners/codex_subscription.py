"""Isolated ChatGPT-authenticated Codex CLI runner for Milestone 5.5."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunRequest,
)
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file

_EXPECTED_CLI_VERSION: Final = "codex-cli 0.145.0"
_EXPECTED_CLI_DIGEST: Final = (
    "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
)
_MODEL: Final = "gpt-5.6-terra"
_REASONING_EFFORT: Final = "high"
_DISABLED_FEATURES: Final = (
    "apps",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode_host",
    "computer_use",
    "fast_mode",
    "goals",
    "hooks",
    "image_generation",
    "in_app_browser",
    "memories",
    "mentions_v2",
    "multi_agent",
    "plugin_sharing",
    "plugins",
    "remote_plugin",
    "shell_snapshot",
    "skill_mcp_dependency_install",
    "skill_search",
    "tool_suggest",
    "workspace_dependencies",
)
_FORBIDDEN_ITEM_FRAGMENTS: Final = (
    "agent",
    "app",
    "browser",
    "computer",
    "image",
    "mcp",
    "memory",
    "plugin",
    "skill",
    "web_search",
)
_FORBIDDEN_ENV_NAMES: Final = frozenset(
    {
        "CODEX_API_KEY",
        "OPENAI_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "OPENAI_ACCESS_TOKEN",
    }
)


class CodexSubscriptionError(ValueError):
    """The subscription runner could not preserve its frozen execution contract."""


@dataclass(frozen=True, slots=True)
class CodexSubscriptionRawResult:
    """Raw result returned only to the encrypted development coordinator."""

    run_id: str
    command_digest: str
    environment_digest: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    exit_code: int | None
    timed_out: bool
    events: tuple[JsonObject, ...]
    trace_bytes: bytes
    stderr: str
    final_response: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    trace_conformant: bool
    trace_validation_error: str | None
    config_destroyed: bool
    session_files_persisted: bool
    api_key_environment_present: bool
    forbidden_ambient_surface_observed: bool


def _strict_json_events(trace: bytes) -> tuple[JsonObject, ...]:
    events: list[JsonObject] = []

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    try:
        text = trace.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CodexSubscriptionError("Codex JSONL trace is not UTF-8") from error
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line, parse_constant=reject_constant)
        except ValueError as error:
            raise CodexSubscriptionError(
                f"Codex trace line {line_number} is not strict JSON"
            ) from error
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise CodexSubscriptionError(f"Codex trace line {line_number} is not an object")
        events.append(cast(JsonObject, value))
    return tuple(events)


def _trace_summary(
    events: tuple[JsonObject, ...],
) -> tuple[str, tuple[int, int, int, int], bool]:
    starts = sum(event.get("type") == "thread.started" for event in events)
    turn_starts = sum(event.get("type") == "turn.started" for event in events)
    terminal = tuple(
        event for event in events if event.get("type") in {"turn.completed", "turn.failed"}
    )
    if starts != 1 or turn_starts != 1 or len(terminal) != 1:
        raise CodexSubscriptionError("Codex trace does not contain exactly one terminal exec turn")

    final_messages: list[str] = []
    forbidden = False
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if (
            isinstance(item_type, str)
            and item_type != "agent_message"
            and any(fragment in item_type.casefold() for fragment in _FORBIDDEN_ITEM_FRAGMENTS)
        ):
            forbidden = True
        if item_type == "agent_message" and isinstance(item.get("text"), str):
            final_messages.append(cast(str, item["text"]))
    final_response = final_messages[-1] if final_messages else ""

    usage_value = terminal[0].get("usage", {})
    usage = usage_value if isinstance(usage_value, dict) else {}

    def token(name: str) -> int:
        value = usage.get(name, 0)
        return value if isinstance(value, int) and value >= 0 else 0

    return (
        final_response,
        (
            token("input_tokens"),
            token("cached_input_tokens"),
            token("output_tokens"),
            token("reasoning_output_tokens"),
        ),
        forbidden,
    )


class CodexSubscriptionRunner:
    """Run one condition/task cell with copied saved ChatGPT auth and no ambient state."""

    def __init__(
        self,
        *,
        executable: Path,
        saved_auth_file: Path,
        max_seconds: int = 1200,
    ) -> None:
        self._executable = executable.expanduser().resolve()
        self._saved_auth_file = saved_auth_file.expanduser().resolve()
        self._max_seconds = max_seconds

    def _verify_binary(self) -> None:
        if not self._executable.is_file():
            raise CodexSubscriptionError("pinned Codex CLI is unavailable")
        if sha256_file(self._executable) != _EXPECTED_CLI_DIGEST:
            raise CodexSubscriptionError("pinned Codex CLI digest drifted")
        completed = subprocess.run(
            [str(self._executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if completed.returncode != 0 or completed.stdout.strip() != _EXPECTED_CLI_VERSION:
            raise CodexSubscriptionError("pinned Codex CLI version drifted")

    def _copy_auth(self, destination: Path) -> None:
        if not self._saved_auth_file.is_file():
            raise CodexSubscriptionError("saved ChatGPT authentication is unavailable")
        if stat.S_IMODE(self._saved_auth_file.stat().st_mode) & 0o077:
            raise CodexSubscriptionError("saved ChatGPT authentication permissions are too broad")
        target = destination / "auth.json"
        shutil.copyfile(self._saved_auth_file, target)
        target.chmod(0o600)

    @staticmethod
    def _environment(codex_home: Path) -> dict[str, str]:
        environment = {
            "CODEX_HOME": str(codex_home),
            "HOME": str(codex_home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "SHELL": "/bin/bash",
            "USER": "codex-development-runner",
        }
        if any(name in environment for name in _FORBIDDEN_ENV_NAMES):
            raise CodexSubscriptionError("API credentials entered the Codex run environment")
        return environment

    def verify_chatgpt_authentication(self) -> str:
        """Return the exact non-secret login-status line from an isolated auth-only home."""

        self._verify_binary()
        with tempfile.TemporaryDirectory(prefix="acl-codex-auth-check-") as temporary:
            codex_home = Path(temporary)
            self._copy_auth(codex_home)
            completed = subprocess.run(
                [str(self._executable), "login", "status"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=self._environment(codex_home),
                timeout=30,
            )
            combined = "\n".join((completed.stdout.strip(), completed.stderr.strip())).strip()
            if completed.returncode != 0 or combined != "Logged in using ChatGPT":
                raise CodexSubscriptionError("Codex authentication is not saved ChatGPT login")
            return combined

    def run(
        self,
        request: CodexDevelopmentRunRequest,
        *,
        workspace: Path,
    ) -> CodexSubscriptionRawResult:
        """Execute one ephemeral turn and return raw bytes for immediate encrypted storage."""

        self._verify_binary()
        resolved_workspace = workspace.expanduser().resolve()
        if not resolved_workspace.is_dir() or not (resolved_workspace / ".git").is_dir():
            raise CodexSubscriptionError("development workspace must be an isolated Git repository")
        if any(resolved_workspace.rglob("AGENTS.md")):
            raise CodexSubscriptionError("development workspace contains AGENTS.md")
        if any(resolved_workspace.rglob(".codex")):
            raise CodexSubscriptionError("development workspace contains project Codex state")
        observed_condition_digest = (
            "sha256:" + hashlib.sha256(request.condition_text.encode("utf-8")).hexdigest()
        )
        if observed_condition_digest != request.condition_digest:
            raise CodexSubscriptionError("condition material digest changed before Codex execution")

        developer_instructions = (
            f"{request.common_instructions.rstrip()}\n\n"
            "Condition material follows. Treat it as the only adaptation material for this run. "
            "Do not mention, identify, compare, or persist the condition.\n\n"
            f"{request.condition_text}"
        ).rstrip()
        feature_args = [value for name in _DISABLED_FEATURES for value in ("--disable", name)]
        shell_environment_set = (
            f'{{ PATH = "/usr/bin:/bin", HOME = {json.dumps(str(resolved_workspace))} }}'
        )
        command = [
            str(self._executable),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--json",
            "--color",
            "never",
            "--cd",
            str(resolved_workspace),
            "--model",
            _MODEL,
            "--sandbox",
            "workspace-write",
            "--config",
            f"model_reasoning_effort={json.dumps(_REASONING_EFFORT)}",
            "--config",
            'approval_policy="never"',
            "--config",
            'web_search="disabled"',
            "--config",
            'personality="none"',
            "--config",
            "agents.enabled=false",
            "--config",
            'shell_environment_policy.inherit="none"',
            "--config",
            f"shell_environment_policy.set={shell_environment_set}",
            "--config",
            f"developer_instructions={json.dumps(developer_instructions)}",
            *feature_args,
            request.task.prompt,
        ]
        command_digest = sha256_bytes(
            json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        environment_descriptor = {
            "api_key_environment_present": False,
            "approval_policy": "never",
            "cli_digest": _EXPECTED_CLI_DIGEST,
            "cli_version": _EXPECTED_CLI_VERSION,
            "disabled_features": list(_DISABLED_FEATURES),
            "ephemeral": True,
            "ignore_rules": True,
            "ignore_user_config": True,
            "isolated_codex_home": True,
            "model": _MODEL,
            "reasoning_effort": _REASONING_EFFORT,
            "sandbox": "workspace-write",
            "shell_environment_inherit": "none",
            "web_search": "disabled",
        }
        environment_digest = sha256_bytes(
            json.dumps(
                environment_descriptor,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )

        trace = b""
        stderr = ""
        timed_out = False
        exit_code: int | None
        session_files_persisted = False
        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()
        temporary_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="acl-codex-run-") as temporary:
            codex_home = Path(temporary)
            temporary_path = codex_home
            self._copy_auth(codex_home)
            environment = self._environment(codex_home)
            if any(name in environment for name in _FORBIDDEN_ENV_NAMES):
                raise CodexSubscriptionError("API credential environment reached Codex")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=resolved_workspace,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as error:
                raise CodexSubscriptionError("unable to start pinned Codex CLI") from error
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=self._max_seconds)
                trace = stdout_bytes
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    stdout_bytes, stderr_bytes = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout_bytes, stderr_bytes = process.communicate(timeout=5)
                trace = stdout_bytes
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                exit_code = None
            sessions = codex_home / "sessions"
            session_files_persisted = sessions.exists() and any(sessions.rglob("*"))
        duration_seconds = time.monotonic() - started_monotonic
        finished_at = max(datetime.now(UTC), started_at)
        config_destroyed = temporary_path is not None and not temporary_path.exists()

        trace_validation_error = None
        try:
            events = _strict_json_events(trace)
            final_response, usage, forbidden = _trace_summary(events)
        except CodexSubscriptionError as error:
            events = ()
            final_response = ""
            usage = (0, 0, 0, 0)
            forbidden = False
            trace_validation_error = str(error)
        trace_conformant = (
            not timed_out and exit_code == 0 and not forbidden and trace_validation_error is None
        )
        return CodexSubscriptionRawResult(
            run_id=request.run_id,
            command_digest=command_digest,
            environment_digest=environment_digest,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            exit_code=exit_code,
            timed_out=timed_out,
            events=events,
            trace_bytes=trace,
            stderr=stderr,
            final_response=final_response,
            input_tokens=usage[0],
            cached_input_tokens=usage[1],
            output_tokens=usage[2],
            reasoning_output_tokens=usage[3],
            trace_conformant=trace_conformant,
            trace_validation_error=trace_validation_error,
            config_destroyed=config_destroyed,
            session_files_persisted=session_files_persisted,
            api_key_environment_present=False,
            forbidden_ambient_surface_observed=forbidden,
        )
