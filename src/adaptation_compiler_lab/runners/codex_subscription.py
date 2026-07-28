"""Isolated ChatGPT-authenticated Codex CLI runner for Milestone 5.5."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
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
_EXPECTED_BWRAP_DIGEST: Final = (
    "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
)
_OUTER_RUNTIME_ROOT: Final = Path("/opt/acl-codex-target")
_OUTER_CODEX: Final = _OUTER_RUNTIME_ROOT / "codex"
_OUTER_BWRAP: Final = _OUTER_RUNTIME_ROOT / "bwrap"
_OUTER_CODEX_HOME: Final = Path("/codex-home")
_OUTER_WORKSPACE: Final = Path("/workspace")
_WSL_RESOLV_CONF: Final = Path("/mnt/wsl/resolv.conf")
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
class CodexExecutionContract:
    """Versioned execution settings; defaults preserve the completed v1 development gate."""

    cli_version: str
    cli_digest: str
    model: str
    reasoning_effort: str
    service_mode: str
    max_seconds: int

    def __post_init__(self) -> None:
        if not self.cli_version or not self.cli_digest.startswith("sha256:"):
            raise ValueError("Codex execution contract requires an exact CLI identity")
        if not self.model or self.reasoning_effort not in {
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("Codex execution contract contains unsupported model settings")
        if self.service_mode != "standard":
            raise ValueError("subscription development runs require Standard service mode")
        if self.max_seconds < 1 or self.max_seconds > 1200:
            raise ValueError("Codex execution timeout must be between 1 and 1200 seconds")


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
    model_reroute_observed: bool
    model: str
    reasoning_effort: str
    service_mode: str


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
) -> tuple[str, tuple[int, int, int, int], bool, bool]:
    starts = sum(event.get("type") == "thread.started" for event in events)
    turn_starts = sum(event.get("type") == "turn.started" for event in events)
    terminal = tuple(
        event for event in events if event.get("type") in {"turn.completed", "turn.failed"}
    )
    if starts != 1 or turn_starts != 1 or len(terminal) != 1:
        raise CodexSubscriptionError("Codex trace does not contain exactly one terminal exec turn")

    final_messages: list[str] = []
    forbidden = False
    rerouted = False
    for event in events:
        event_type = event.get("type")
        if isinstance(event_type, str) and "rerout" in event_type.casefold():
            rerouted = True
        if "fromModel" in event or "toModel" in event:
            rerouted = True
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
        rerouted,
    )


class CodexSubscriptionRunner:
    """Run one condition/task cell with copied saved ChatGPT auth and no ambient state."""

    def __init__(
        self,
        *,
        executable: Path,
        saved_auth_file: Path,
        max_seconds: int = 1200,
        contract: CodexExecutionContract | None = None,
        bubblewrap: Path | None = None,
    ) -> None:
        self._executable = executable.expanduser().resolve()
        self._saved_auth_file = saved_auth_file.expanduser().resolve()
        self._contract = contract or CodexExecutionContract(
            cli_version=_EXPECTED_CLI_VERSION,
            cli_digest=_EXPECTED_CLI_DIGEST,
            model=_MODEL,
            reasoning_effort=_REASONING_EFFORT,
            service_mode="standard",
            max_seconds=max_seconds,
        )
        self._bubblewrap = bubblewrap.expanduser().resolve() if bubblewrap else None

    def _verify_binary(self) -> None:
        if not self._executable.is_file():
            raise CodexSubscriptionError("pinned Codex CLI is unavailable")
        if sha256_file(self._executable) != self._contract.cli_digest:
            raise CodexSubscriptionError("pinned Codex CLI digest drifted")
        completed = subprocess.run(
            [str(self._executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        if completed.returncode != 0 or completed.stdout.strip() != self._contract.cli_version:
            raise CodexSubscriptionError("pinned Codex CLI version drifted")

    def _verify_outer_sandbox(self) -> None:
        if self._bubblewrap is None:
            return
        if not self._bubblewrap.is_file():
            raise CodexSubscriptionError("pinned target bubblewrap is unavailable")
        if sha256_file(self._bubblewrap) != _EXPECTED_BWRAP_DIGEST:
            raise CodexSubscriptionError("pinned target bubblewrap digest drifted")
        if not _WSL_RESOLV_CONF.is_file():
            raise CodexSubscriptionError("exact WSL resolver target is unavailable")
        completed = subprocess.run(
            [
                str(self._bubblewrap),
                "--unshare-all",
                "--share-net",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--symlink",
                "usr/sbin",
                "/sbin",
                "--ro-bind",
                "/etc",
                "/etc",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--dir",
                "/mnt",
                "--dir",
                str(_WSL_RESOLV_CONF.parent),
                "--ro-bind",
                str(_WSL_RESOLV_CONF),
                str(_WSL_RESOLV_CONF),
                "--dir",
                "/opt",
                "--dir",
                str(_OUTER_RUNTIME_ROOT),
                "--ro-bind",
                str(self._bubblewrap),
                str(_OUTER_BWRAP),
                "--",
                str(_OUTER_BWRAP),
                "--unshare-all",
                "--share-net",
                "--die-with-parent",
                "--new-session",
                "--ro-bind",
                "/usr",
                "/usr",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--symlink",
                "usr/sbin",
                "/sbin",
                "--ro-bind",
                "/etc",
                "/etc",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--dir",
                "/mnt",
                "--dir",
                str(_WSL_RESOLV_CONF.parent),
                "--ro-bind",
                str(_WSL_RESOLV_CONF),
                str(_WSL_RESOLV_CONF),
                "--",
                "/usr/bin/getent",
                "hosts",
                "chatgpt.com",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if completed.returncode != 0:
            raise CodexSubscriptionError("pinned target outer sandbox or resolver is unavailable")

    def _copy_auth(self, destination: Path) -> None:
        if not self._saved_auth_file.is_file():
            raise CodexSubscriptionError("saved ChatGPT authentication is unavailable")
        if stat.S_IMODE(self._saved_auth_file.stat().st_mode) & 0o077:
            raise CodexSubscriptionError("saved ChatGPT authentication permissions are too broad")
        target = destination / "auth.json"
        shutil.copyfile(self._saved_auth_file, target)
        target.chmod(0o600)

    @staticmethod
    def _write_profile(destination: Path, developer_instructions: str) -> str:
        profile = destination / "development.config.toml"
        payload = (
            f"developer_instructions = {json.dumps(developer_instructions, ensure_ascii=False)}\n"
        ).encode()
        descriptor = os.open(profile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        profile.chmod(0o600)
        return sha256_bytes(payload)

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
            lines = tuple(
                line.strip()
                for stream in (completed.stdout, completed.stderr)
                for line in stream.splitlines()
                if line.strip()
            )
            status = "Logged in using ChatGPT"
            allowed_warning = "WARNING: proceeding, even though we could not create PATH aliases:"
            unexpected = tuple(
                line for line in lines if line != status and not line.startswith(allowed_warning)
            )
            if completed.returncode != 0 or lines.count(status) != 1 or unexpected:
                raise CodexSubscriptionError("Codex authentication is not saved ChatGPT login")
            return status

    def verify_target_preconditions(self) -> JsonObject:
        """Verify auth, model identity, and the optional outer target sandbox."""

        self._verify_outer_sandbox()
        return {
            "authentication": self.verify_chatgpt_authentication(),
            "model_catalog": self.verify_model_availability(),
            "outer_sandbox": (
                {
                    "digest": sha256_file(self._bubblewrap),
                    "workspace_policy": "read-only-except-registered-source-file",
                }
                if self._bubblewrap
                else None
            ),
        }

    @staticmethod
    def _rpc_response(
        process: subprocess.Popen[str],
        *,
        request_id: int,
        timeout_seconds: float,
    ) -> JsonObject:
        if process.stdout is None:
            raise CodexSubscriptionError("Codex model-catalog probe has no output stream")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_seconds
        try:
            while time.monotonic() < deadline:
                ready = selector.select(timeout=max(0.0, deadline - time.monotonic()))
                if not ready:
                    break
                line = process.stdout.readline()
                if not line:
                    break
                try:
                    value = json.loads(line)
                except ValueError as error:
                    raise CodexSubscriptionError(
                        "Codex model-catalog probe returned invalid JSON"
                    ) from error
                if not isinstance(value, dict):
                    raise CodexSubscriptionError("Codex model-catalog response is not an object")
                if value.get("id") != request_id:
                    continue
                if "error" in value:
                    raise CodexSubscriptionError("Codex model-catalog request failed")
                result = value.get("result")
                if not isinstance(result, dict):
                    raise CodexSubscriptionError("Codex model-catalog result is not an object")
                return cast(JsonObject, result)
        finally:
            selector.close()
        raise CodexSubscriptionError("Codex model-catalog request timed out")

    @staticmethod
    def _rpc_write(process: subprocess.Popen[str], payload: JsonObject) -> None:
        if process.stdin is None:
            raise CodexSubscriptionError("Codex model-catalog probe has no input stream")
        process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def verify_model_availability(self) -> JsonObject:
        """Fail closed unless the isolated live catalog exposes the exact model and effort."""

        self._verify_binary()
        with tempfile.TemporaryDirectory(prefix="acl-codex-model-check-") as temporary:
            codex_home = Path(temporary)
            self._copy_auth(codex_home)
            try:
                process = subprocess.Popen(
                    [
                        str(self._executable),
                        "app-server",
                        "--stdio",
                        "--strict-config",
                        "--disable",
                        "plugins",
                        "--disable",
                        "memories",
                        "--disable",
                        "multi_agent",
                        "--disable",
                        "fast_mode",
                    ],
                    env=self._environment(codex_home),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    start_new_session=True,
                )
            except OSError as error:
                raise CodexSubscriptionError("unable to start Codex model-catalog probe") from error
            try:
                self._rpc_write(
                    process,
                    {
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "clientInfo": {
                                "name": "adaptation-compiler-lab",
                                "title": "Adaptation Compiler Lab",
                                "version": "0.1.0",
                            },
                            "capabilities": {"experimentalApi": False},
                        },
                    },
                )
                self._rpc_response(process, request_id=1, timeout_seconds=30)
                self._rpc_write(process, {"method": "initialized", "params": {}})
                cursor: str | None = None
                request_id = 2
                matching: JsonObject | None = None
                while True:
                    self._rpc_write(
                        process,
                        {
                            "id": request_id,
                            "method": "model/list",
                            "params": {
                                "cursor": cursor,
                                "includeHidden": False,
                                "limit": 100,
                            },
                        },
                    )
                    response = self._rpc_response(
                        process,
                        request_id=request_id,
                        timeout_seconds=30,
                    )
                    data = response.get("data")
                    if not isinstance(data, list):
                        raise CodexSubscriptionError("Codex model catalog has invalid data")
                    for value in data:
                        if (
                            isinstance(value, dict)
                            and value.get("model") == self._contract.model
                            and value.get("id") == self._contract.model
                            and value.get("hidden") is False
                        ):
                            matching = value
                    next_cursor = response.get("nextCursor")
                    if next_cursor is None:
                        break
                    if not isinstance(next_cursor, str) or not next_cursor:
                        raise CodexSubscriptionError("Codex model catalog has invalid pagination")
                    cursor = next_cursor
                    request_id += 1
                if matching is None:
                    raise CodexSubscriptionError("explicit Codex model is unavailable")
                efforts = matching.get("supportedReasoningEfforts")
                if not isinstance(efforts, list) or self._contract.reasoning_effort not in {
                    value.get("reasoningEffort") for value in efforts if isinstance(value, dict)
                }:
                    raise CodexSubscriptionError("explicit Codex reasoning effort is unavailable")
                return {
                    "hidden": False,
                    "model": self._contract.model,
                    "reasoning_effort": self._contract.reasoning_effort,
                    "service_mode": self._contract.service_mode,
                }
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

    def _outer_sandbox_command(
        self,
        *,
        inner_command: list[str],
        codex_home: Path,
        workspace: Path,
        allowed_change_paths: tuple[str, ...],
    ) -> list[str]:
        if self._bubblewrap is None:
            return inner_command
        writable_files = tuple(
            sorted(
                {
                    (
                        (workspace / value).resolve(),
                        _OUTER_WORKSPACE / value,
                    )
                    for value in allowed_change_paths
                }
            )
        )
        if not writable_files:
            raise CodexSubscriptionError("outer target sandbox requires an allowed file")
        if any(
            not host_path.is_file()
            or not host_path.is_relative_to(workspace)
            or not sandbox_path.is_relative_to(_OUTER_WORKSPACE)
            for host_path, sandbox_path in writable_files
        ):
            raise CodexSubscriptionError("outer target writable file is unsafe")
        writable_args = [
            value
            for host_path, sandbox_path in writable_files
            for value in ("--bind", str(host_path), str(sandbox_path))
        ]
        return [
            str(self._bubblewrap),
            "--unshare-all",
            "--share-net",
            "--die-with-parent",
            "--new-session",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--symlink",
            "usr/sbin",
            "/sbin",
            "--ro-bind",
            "/etc",
            "/etc",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/mnt",
            "--dir",
            str(_WSL_RESOLV_CONF.parent),
            "--ro-bind",
            str(_WSL_RESOLV_CONF),
            str(_WSL_RESOLV_CONF),
            "--dir",
            "/opt",
            "--dir",
            str(_OUTER_RUNTIME_ROOT),
            "--dir",
            str(_OUTER_CODEX_HOME),
            "--dir",
            str(_OUTER_WORKSPACE),
            "--ro-bind",
            str(self._executable),
            str(_OUTER_CODEX),
            "--ro-bind",
            str(self._bubblewrap),
            str(_OUTER_BWRAP),
            "--bind",
            str(codex_home),
            str(_OUTER_CODEX_HOME),
            "--ro-bind",
            str(workspace),
            str(_OUTER_WORKSPACE),
            *writable_args,
            "--chdir",
            str(_OUTER_WORKSPACE),
            "--",
            *inner_command,
        ]

    def run(
        self,
        request: CodexDevelopmentRunRequest,
        *,
        workspace: Path,
    ) -> CodexSubscriptionRawResult:
        """Execute one ephemeral turn and return raw bytes for immediate encrypted storage."""

        self._verify_binary()
        self._verify_outer_sandbox()
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
        execution_workspace = _OUTER_WORKSPACE if self._bubblewrap else resolved_workspace
        execution_path = (
            f"{_OUTER_RUNTIME_ROOT}:/usr/bin:/bin" if self._bubblewrap else "/usr/bin:/bin"
        )
        shell_environment_set = (
            f"{{ PATH = {json.dumps(execution_path)}, "
            f"HOME = {json.dumps(str(execution_workspace))}, "
            'PYTHONDONTWRITEBYTECODE = "1" }'
        )
        inner_command = [
            str(_OUTER_CODEX if self._bubblewrap else self._executable),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--profile",
            "development",
            "--json",
            "--color",
            "never",
            "--cd",
            str(execution_workspace),
            "--model",
            self._contract.model,
            "--sandbox",
            "workspace-write",
            "--config",
            f"model_reasoning_effort={json.dumps(self._contract.reasoning_effort)}",
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
            *feature_args,
            "-",
        ]
        developer_profile_digest = sha256_bytes(
            (
                f"developer_instructions = "
                f"{json.dumps(developer_instructions, ensure_ascii=False)}\n"
            ).encode()
        )
        command_digest = sha256_bytes(
            json.dumps(
                {
                    "argv": inner_command,
                    "developer_profile_digest": developer_profile_digest,
                    "outer_sandbox_digest": (
                        sha256_file(self._bubblewrap) if self._bubblewrap else None
                    ),
                    "outer_writable_paths": list(request.task.allowed_change_paths),
                    "prompt_digest": sha256_bytes(request.task.prompt.encode("utf-8")),
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        environment_descriptor = {
            "api_key_environment_present": False,
            "approval_policy": "never",
            "cli_digest": self._contract.cli_digest,
            "cli_version": self._contract.cli_version,
            "disabled_features": list(_DISABLED_FEATURES),
            "ephemeral": True,
            "ignore_rules": True,
            "ignore_user_config": True,
            "isolated_codex_home": True,
            "model": self._contract.model,
            "nested_sandbox_binary_digest": (
                sha256_file(self._bubblewrap) if self._bubblewrap else None
            ),
            "nested_sandbox_binary_path": (str(_OUTER_BWRAP) if self._bubblewrap else None),
            "outer_minimal_mount_namespace": self._bubblewrap is not None,
            "outer_workspace_read_only_except_allowed_files": (self._bubblewrap is not None),
            "reasoning_effort": self._contract.reasoning_effort,
            "sandbox": "workspace-write",
            "service_mode": self._contract.service_mode,
            "shell_environment_inherit": "none",
            "shell_python_bytecode": "disabled",
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
            observed_profile_digest = self._write_profile(
                codex_home,
                developer_instructions,
            )
            if observed_profile_digest != developer_profile_digest:
                raise CodexSubscriptionError("isolated Codex profile digest changed")
            environment = self._environment(_OUTER_CODEX_HOME if self._bubblewrap else codex_home)
            if self._bubblewrap:
                environment["PATH"] = execution_path
            if any(name in environment for name in _FORBIDDEN_ENV_NAMES):
                raise CodexSubscriptionError("API credential environment reached Codex")
            try:
                command = self._outer_sandbox_command(
                    inner_command=inner_command,
                    codex_home=codex_home,
                    workspace=resolved_workspace,
                    allowed_change_paths=request.task.allowed_change_paths,
                )
                process = subprocess.Popen(
                    command,
                    cwd=resolved_workspace,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as error:
                raise CodexSubscriptionError("unable to start pinned Codex CLI") from error
            try:
                stdout_bytes, stderr_bytes = process.communicate(
                    input=request.task.prompt.encode("utf-8"),
                    timeout=self._contract.max_seconds,
                )
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
            final_response, usage, forbidden, rerouted = _trace_summary(events)
        except CodexSubscriptionError as error:
            events = ()
            final_response = ""
            usage = (0, 0, 0, 0)
            forbidden = False
            rerouted = False
            trace_validation_error = str(error)
        trace_conformant = (
            not timed_out
            and exit_code == 0
            and not forbidden
            and not rerouted
            and trace_validation_error is None
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
            model_reroute_observed=rerouted,
            model=self._contract.model,
            reasoning_effort=self._contract.reasoning_effort,
            service_mode=self._contract.service_mode,
        )
