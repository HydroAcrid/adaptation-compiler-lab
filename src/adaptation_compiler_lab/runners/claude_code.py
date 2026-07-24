"""Pinned, bare, non-persistent, sandboxed Claude Code target execution."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from adaptation_compiler_lab.connectors.models import (
    JsonObject,
    JsonValue,
    TargetRunRequest,
    TargetRunResult,
)
from adaptation_compiler_lab.connectors.pins import (
    RuntimeConformanceError,
    RuntimePinSet,
    VerifiedClaudeRuntime,
    sha256_bytes,
    sha256_file,
    verify_claude_runtime,
)

_BUILTIN_TOOLS: Final = ("Bash", "Edit", "Glob", "Grep", "Read", "Write")
_TRACE_ALLOWED_TOOLS: Final = frozenset({*_BUILTIN_TOOLS, "EndConversation"})
_NON_BASH_ALLOWED_TOOLS: Final = ("Edit", "Glob", "Grep", "Read", "Write")
_REMOVED_TOOLS: Final = (
    "Agent",
    "Artifact",
    "Computer",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "mcp__*",
)
_FORBIDDEN_PROVIDER_ENV: Final = (
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_USE_VERTEX",
)
_FIXED_ENV: Final = {
    "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
    "CLAUDE_CODE_DISABLE_ARTIFACT": "1",
    "CLAUDE_CODE_DISABLE_ATTACHMENTS": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
    "CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
    "CLAUDE_CODE_DISABLE_POLICY_SKILLS": "1",
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
    "CLAUDE_CODE_DISABLE_WORKFLOWS": "1",
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_UPDATES": "1",
    "DO_NOT_TRACK": "1",
    "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
    "PYTHONDONTWRITEBYTECODE": "1",
}
_GENERIC_STDIN_PROMPT: Final = (
    "Complete the coding task supplied on standard input. Follow only the injected condition "
    "material and the task itself."
)


class TargetExecutionError(RuntimeConformanceError):
    """The target runner could not preserve the frozen execution contract."""


@dataclass(frozen=True)
class ClaudeRuntimePaths:
    """External paths selected by the study operator; none are committed."""

    executable: Path
    bubblewrap: Path
    socat: Path
    sandbox_library_path: Path


def _settings(
    workspace: Path,
    allowed_bash_commands: tuple[str, ...],
) -> JsonObject:
    allow_rules: list[JsonValue] = list(_NON_BASH_ALLOWED_TOOLS)
    allow_rules.extend(f"Bash({command})" for command in allowed_bash_commands)
    sensitive_roots: list[JsonValue] = [
        "/home",
        "/mnt",
        "/root",
        "/proc",
        "/sys",
        "/dev",
        "/etc/ssh",
    ]
    return {
        "autoMemoryEnabled": False,
        "disableClaudeAiConnectors": True,
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": allow_rules,
            "ask": [],
            "deny": list(_REMOVED_TOOLS),
            "additionalDirectories": [],
        },
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": False,
            "allowUnsandboxedCommands": False,
            "excludedCommands": [],
            "filesystem": {
                "denyRead": sensitive_roots,
                "allowRead": [str(workspace)],
                "denyWrite": sensitive_roots,
                "allowWrite": [str(workspace)],
            },
            "network": {
                "allowedDomains": [],
                "deniedDomains": ["*"],
                "allowAllUnixSockets": False,
            },
        },
    }


def _iter_objects(value: JsonValue) -> Iterator[JsonObject]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_objects(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_objects(nested)


def _parse_stream(stdout: str) -> tuple[JsonObject, ...]:
    events: list[JsonObject] = []

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is forbidden: {value}")

    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line, parse_constant=reject_constant)
        except ValueError as exc:
            raise TargetExecutionError(
                f"Claude stream line {line_number} is not strict JSON"
            ) from exc
        if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
            raise TargetExecutionError(f"Claude stream line {line_number} is not an object")
        events.append(cast(JsonObject, payload))
    return tuple(events)


def _assert_trace_conformance(
    events: tuple[JsonObject, ...],
    *,
    model_id: str,
    timed_out: bool,
) -> None:
    if timed_out:
        return
    init_events = [
        event
        for event in events
        if event.get("type") == "system" and event.get("subtype") == "init"
    ]
    if len(init_events) != 1:
        raise TargetExecutionError("Claude trace must contain exactly one system/init event")
    init = init_events[0]
    if init.get("model") != model_id:
        raise TargetExecutionError("Claude initialized a model other than the frozen full ID")
    tools = init.get("tools")
    if not isinstance(tools, list) or any(not isinstance(item, str) for item in tools):
        raise TargetExecutionError("Claude system/init omitted its tool inventory")
    unknown_tools = set(cast(list[str], tools)) - _TRACE_ALLOWED_TOOLS
    if unknown_tools:
        raise TargetExecutionError(
            "Claude initialized forbidden tools: " + ", ".join(sorted(unknown_tools))
        )
    mcp_servers = init.get("mcp_servers", [])
    if mcp_servers not in ([], {}):
        raise TargetExecutionError("Claude initialized an MCP server")
    plugins = init.get("plugins", [])
    if plugins not in ([], {}):
        raise TargetExecutionError("Claude initialized a plugin")
    for event in events:
        for nested in _iter_objects(event):
            if nested.get("type") == "tool_use":
                name = nested.get("name")
                if not isinstance(name, str) or name not in _TRACE_ALLOWED_TOOLS:
                    raise TargetExecutionError("Claude trace contains a forbidden tool use")


class ClaudeCodeTargetRunner:
    """Invoke one frozen Claude Code binary with no ambient agent state."""

    def __init__(
        self,
        *,
        paths: ClaudeRuntimePaths,
        pins: RuntimePinSet,
        environment: Mapping[str, str] | None = None,
        api_key_file: Path | None = None,
    ) -> None:
        self._paths = paths
        self._pins = pins
        self._environment = dict(os.environ if environment is None else environment)
        self._api_key_file = api_key_file

    def _api_key(self) -> str:
        environment_key = self._environment.get("ANTHROPIC_API_KEY")
        if self._api_key_file is None:
            if not environment_key:
                raise TargetExecutionError("a dedicated Anthropic Console API key is required")
            return environment_key
        if environment_key:
            raise TargetExecutionError("Claude API key source is ambiguous")
        key_path = self._api_key_file.expanduser().resolve()
        if not key_path.is_file():
            raise TargetExecutionError("external Claude API key file is unavailable")
        if stat.S_IMODE(key_path.stat().st_mode) & 0o077:
            raise TargetExecutionError("external Claude API key file permissions are too broad")
        try:
            raw_key = key_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise TargetExecutionError("unable to read external Claude API key file") from exc
        key = raw_key.strip()
        if not key or any(character.isspace() for character in key):
            raise TargetExecutionError("external Claude API key file is malformed")
        return key

    def _verify_runtime(self) -> VerifiedClaudeRuntime:
        return verify_claude_runtime(
            executable=self._paths.executable,
            bubblewrap=self._paths.bubblewrap,
            socat=self._paths.socat,
            sandbox_library_path=self._paths.sandbox_library_path,
            pin=self._pins.claude_code,
            sandbox_pin=self._pins.sandbox,
        )

    def _environment_for_run(
        self,
        runtime: VerifiedClaudeRuntime,
        *,
        config_dir: Path,
    ) -> dict[str, str]:
        api_key = self._api_key()
        configured_base = self._environment.get("ANTHROPIC_BASE_URL")
        if configured_base not in (None, "", runtime.api_base_url):
            raise TargetExecutionError("alternate Anthropic base URLs are forbidden")
        present_provider_overrides = [
            name for name in _FORBIDDEN_PROVIDER_ENV if self._environment.get(name)
        ]
        if present_provider_overrides:
            raise TargetExecutionError("alternate Claude provider credentials are forbidden")
        environment = {
            key: value
            for key, value in self._environment.items()
            if key
            in {
                "HOME",
                "LANG",
                "LC_ALL",
                "LOGNAME",
                "PATH",
                "SHELL",
                "TERM",
                "TMPDIR",
                "USER",
            }
        }
        path_parts = [str(runtime.bubblewrap.parent), str(runtime.socat.parent)]
        inherited_path = environment.get("PATH")
        if inherited_path:
            path_parts.append(inherited_path)
        environment["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))
        environment["LD_LIBRARY_PATH"] = str(runtime.sandbox_library_path)
        environment["ANTHROPIC_API_KEY"] = api_key
        environment["ANTHROPIC_BASE_URL"] = runtime.api_base_url
        environment["ANTHROPIC_MODEL"] = runtime.model_id
        environment["CLAUDE_CONFIG_DIR"] = str(config_dir)
        environment.update(_FIXED_ENV)
        return environment

    def run(self, request: TargetRunRequest) -> TargetRunResult:
        runtime = self._verify_runtime()
        if request.model_id != runtime.model_id:
            raise TargetExecutionError("target request does not use the frozen model")
        workspace = request.workspace_root.expanduser().resolve()
        condition_file = request.condition_file.expanduser().resolve()
        if not workspace.is_dir():
            raise TargetExecutionError("target workspace is unavailable")
        if not condition_file.is_file() or not condition_file.is_relative_to(workspace):
            raise TargetExecutionError("condition file must be a regular file inside the workspace")
        if (
            self._api_key_file is not None
            and self._api_key_file.expanduser().resolve().is_relative_to(workspace)
        ):
            raise TargetExecutionError("Claude API key file cannot be inside the target workspace")
        if sha256_file(condition_file) != request.condition_digest:
            raise TargetExecutionError("condition file digest changed before execution")

        with tempfile.TemporaryDirectory(prefix="acl-claude-config-") as temporary:
            config_dir = Path(temporary)
            settings_path = config_dir / "settings.json"
            settings_payload = _settings(workspace, request.allowed_bash_commands)
            settings_path.write_text(
                json.dumps(
                    settings_payload,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            settings_path.chmod(0o600)
            environment = self._environment_for_run(runtime, config_dir=config_dir)
            allowed_tools = [*_NON_BASH_ALLOWED_TOOLS]
            allowed_tools.extend(f"Bash({command})" for command in request.allowed_bash_commands)
            command = [
                str(runtime.executable),
                "--bare",
                "--print",
                "--no-session-persistence",
                "--output-format",
                "stream-json",
                "--verbose",
                "--append-system-prompt-file",
                str(condition_file),
                "--tools",
                ",".join(_BUILTIN_TOOLS),
                "--allowedTools",
                *allowed_tools,
                "--disallowedTools",
                *_REMOVED_TOOLS,
                "--permission-mode",
                "dontAsk",
                "--strict-mcp-config",
                "--setting-sources",
                "",
                "--settings",
                str(settings_path),
                "--no-chrome",
                "--disable-slash-commands",
                "--model",
                runtime.model_id,
                "--max-turns",
                str(request.max_turns),
                "--max-budget-usd",
                f"{request.max_usd:.2f}",
                _GENERIC_STDIN_PROMPT,
            ]
            command_digest = sha256_bytes(
                json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
            started_at = datetime.now(UTC)
            timed_out = False
            exit_code: int | None
            stdout = ""
            stderr = ""
            try:
                process = subprocess.Popen(
                    command,
                    cwd=workspace,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    start_new_session=True,
                )
            except OSError as exc:
                raise TargetExecutionError("unable to start pinned Claude Code") from exc
            try:
                stdout, stderr = process.communicate(
                    input=request.prompt,
                    timeout=request.max_seconds,
                )
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    timeout_stdout, timeout_stderr = process.communicate(timeout=5.0)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    timeout_stdout, timeout_stderr = process.communicate(timeout=5.0)
                stdout += timeout_stdout
                stderr += timeout_stderr
                exit_code = None
            api_key = environment["ANTHROPIC_API_KEY"]
            if api_key in stdout or api_key in stderr:
                raise TargetExecutionError("Claude output exposed the API credential")
            events = _parse_stream(stdout)
            _assert_trace_conformance(
                events,
                model_id=runtime.model_id,
                timed_out=timed_out,
            )
            # Wall clocks can move backwards while a process is running (for example, an NTP
            # correction). Preserve the result contract without pretending elapsed-time
            # measurement comes from wall-clock ordering.
            finished_at = max(datetime.now(UTC), started_at)
        return TargetRunResult(
            run_id=request.run_id,
            runner_version=runtime.version,
            model_id=runtime.model_id,
            condition_digest=request.condition_digest,
            command_digest=command_digest,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            timed_out=timed_out,
            events=events,
            stderr=stderr,
            config_destroyed=not config_dir.exists(),
        )
