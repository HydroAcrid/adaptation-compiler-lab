"""Pinned, bare, non-persistent, sandboxed Claude Code target execution."""

from __future__ import annotations

import json
import os
import shlex
import shutil
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
    TargetCommandAuditEntry,
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
    "CLAUDE_CODE_HOST_PLATFORM": "linux",
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
    "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1",
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
_COMMAND_EXECUTABLES: Final = frozenset({"python", "python3"})
_RUNTIME_ARTIFACTS: Final = (
    ".acl-runtime",
    ".bash_profile",
    ".bashrc",
    ".claude",
    ".idea",
    ".mcp.json",
)
_AMBIENT_READ_NAMES: Final = (
    ".claude",
    ".env",
    ".idea",
    ".mcp.json",
    "AGENTS.md",
    "CLAUDE.md",
)


@dataclass(frozen=True)
class ClaudeRuntimePaths:
    """External paths selected by the study operator; none are committed."""

    executable: Path
    bubblewrap: Path
    socat: Path
    sandbox_library_path: Path


@dataclass(frozen=True)
class _PreparedCommand:
    alias: str
    argv: tuple[str, ...]
    command_digest: str
    wrapper_path: Path


@dataclass(frozen=True)
class TargetFailureEvidence:
    """Raw post-execution evidence retained only for encrypted failure handling."""

    run_id: str
    runner_version: str
    model_id: str
    condition_digest: str
    command_digest: str
    started_at: datetime
    finished_at: datetime
    exit_code: int | None
    timed_out: bool
    stdout: str
    events: tuple[JsonObject, ...]
    stderr: str
    command_manifest_digest: str
    command_audit: tuple[TargetCommandAuditEntry, ...]
    config_destroyed: bool
    failure_code: str
    failure_subject_digest: str | None


class TargetExecutionError(RuntimeConformanceError):
    """The target runner could not preserve the frozen execution contract."""

    def __init__(
        self,
        message: str,
        *,
        evidence: TargetFailureEvidence | None = None,
        failure_code: str = "target_execution_error",
        failure_subject_digest: str | None = None,
        partial_command_audit: tuple[TargetCommandAuditEntry, ...] = (),
    ) -> None:
        super().__init__(message)
        self.evidence = evidence
        self.failure_code = failure_code
        self.failure_subject_digest = failure_subject_digest
        self.partial_command_audit = partial_command_audit


def _absolute_permission_rule(tool: str, path: Path, *, descendants: bool = False) -> str:
    suffix = "/**" if descendants else ""
    return f"{tool}(/{path.as_posix()}{suffix})"


def _tool_rules(workspace: Path, condition_file: Path) -> tuple[list[JsonValue], list[JsonValue]]:
    allow: list[JsonValue] = [
        _absolute_permission_rule("Read", workspace, descendants=True),
        _absolute_permission_rule("Edit", workspace, descendants=True),
    ]
    deny: list[JsonValue] = list(_REMOVED_TOOLS)
    deny.append(_absolute_permission_rule("Edit", condition_file))
    for name in _AMBIENT_READ_NAMES:
        path = workspace / name
        deny.append(_absolute_permission_rule("Read", path, descendants=path.suffix == ""))
        deny.append(_absolute_permission_rule("Edit", path, descendants=path.suffix == ""))
    runtime_path = workspace / ".acl-runtime"
    deny.append(_absolute_permission_rule("Read", runtime_path, descendants=True))
    deny.append(_absolute_permission_rule("Edit", runtime_path, descendants=True))
    return allow, deny


def _settings(
    workspace: Path,
    condition_file: Path,
    commands_dir: Path,
    prepared_commands: tuple[_PreparedCommand, ...],
) -> JsonObject:
    allow_rules, deny_rules = _tool_rules(workspace, condition_file)
    allow_rules.extend(f"Bash({command.alias})" for command in prepared_commands)
    runtime_root = workspace / ".acl-runtime"
    ambient_paths = [str(workspace / name) for name in _AMBIENT_READ_NAMES]
    system_read_paths: list[JsonValue] = [
        "/bin",
        "/dev/null",
        "/dev/urandom",
        "/etc/ld.so.cache",
        "/lib",
        "/lib64",
        "/usr",
        str(commands_dir),
        str(workspace),
    ]
    denied_credentials: list[JsonValue] = [
        {"name": name, "mode": "deny"}
        for name in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "NPM_TOKEN",
            "OPENAI_API_KEY",
        )
    ]
    return {
        "autoMemoryEnabled": False,
        "disableClaudeAiConnectors": True,
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": allow_rules,
            "ask": [],
            "deny": deny_rules,
            "additionalDirectories": [],
        },
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": False,
            "allowUnsandboxedCommands": False,
            # Claude Code's WSL sandbox derives an absent Windows managed-settings path on this
            # pinned runtime. Only the generated aliases bypass that wrapper. Each alias
            # immediately enters the separately pinned Bubblewrap boundary built below.
            "excludedCommands": [command.alias for command in prepared_commands],
            "filesystem": {
                "denyRead": ["/", *ambient_paths],
                "allowRead": system_read_paths,
                "denyWrite": [
                    "/",
                    *ambient_paths,
                    str(condition_file),
                    str(commands_dir),
                    str(runtime_root),
                ],
                "allowWrite": [
                    "/dev/null",
                    "/dev/urandom",
                    str(runtime_root / "home"),
                    str(runtime_root / "tmp"),
                    str(workspace),
                ],
            },
            "credentials": {
                "files": [
                    {"path": "/home", "mode": "deny"},
                    {"path": "/mnt", "mode": "deny"},
                    {"path": "/root", "mode": "deny"},
                ],
                "envVars": denied_credentials,
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


def _approved_argv(command: str) -> tuple[str, ...]:
    try:
        argv = tuple(shlex.split(command, posix=True))
    except ValueError as exc:
        raise TargetExecutionError("approved command has invalid shell quoting") from exc
    if not argv:
        raise TargetExecutionError("approved command cannot be empty")
    if argv[0] not in _COMMAND_EXECUTABLES:
        raise TargetExecutionError("approved command executable is not supported")
    if len(argv) < 3 or argv[1:3] != ("-m", "unittest"):
        raise TargetExecutionError("only Python unittest commands may be approved")
    if any(item in {"-c", "--locals"} for item in argv[3:]):
        raise TargetExecutionError("approved unittest command includes a forbidden option")
    return argv


def _wrapper_payload(
    *,
    bubblewrap: Path,
    executable: Path,
    arguments: tuple[str, ...],
    runtime_root: Path,
    workspace: Path,
    request: TargetRunRequest,
) -> str:
    memory_kb = request.command_memory_mb * 1024
    file_blocks = request.command_file_size_mb * 1024
    sandbox_command = shlex.join(
        (
            str(bubblewrap),
            "--unshare-all",
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
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/runtime",
            "--bind",
            str(runtime_root / "home"),
            "/runtime/home",
            "--bind",
            str(runtime_root / "tmp"),
            "/runtime/tmp",
            "--bind",
            str(workspace),
            "/workspace",
            "--chdir",
            "/workspace",
            "--clearenv",
            "--setenv",
            "HOME",
            "/runtime/home",
            "--setenv",
            "TMPDIR",
            "/runtime/tmp",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "LC_ALL",
            "C.UTF-8",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "ACL_BOUNDED_TEST",
            "1",
            "--",
            str(executable),
            *arguments,
        )
    )
    return (
        "#!/usr/bin/bash\n"
        "set -euo pipefail\n"
        f"ulimit -t {request.command_cpu_seconds}\n"
        f"ulimit -v {memory_kb}\n"
        f"ulimit -f {file_blocks}\n"
        f"ulimit -u {request.command_process_limit}\n"
        f"ulimit -n {request.command_open_files_limit}\n"
        "exec /usr/bin/timeout --signal=TERM --kill-after=5 "
        f"{request.command_timeout_seconds} {sandbox_command}\n"
    )


def _prepare_commands(
    *,
    bubblewrap: Path,
    config_dir: Path,
    workspace: Path,
    request: TargetRunRequest,
) -> tuple[Path, tuple[_PreparedCommand, ...], str]:
    commands_dir = config_dir / "bounded-commands"
    commands_dir.mkdir(mode=0o700)
    runtime_root = workspace / ".acl-runtime"
    (runtime_root / "home").mkdir(parents=True, mode=0o700)
    (runtime_root / "tmp").mkdir(mode=0o700)
    prepared: list[_PreparedCommand] = []
    manifest: list[JsonObject] = []
    system_path = "/usr/bin:/bin"
    aliases: set[str] = set()
    for index, command in enumerate(request.allowed_bash_commands, start=1):
        argv = _approved_argv(command)
        resolved = shutil.which(argv[0], path=system_path)
        if resolved is None:
            raise TargetExecutionError("approved command executable is unavailable")
        executable = Path(resolved).resolve()
        if not executable.is_relative_to(Path("/usr")) and not executable.is_relative_to(
            Path("/bin")
        ):
            raise TargetExecutionError("approved command executable resolved outside system paths")
        unittest_arguments = tuple(item for item in argv[3:] if item != "-v")
        if not unittest_arguments:
            alias = "acl-test-full"
        elif len(request.allowed_bash_commands) == 2:
            alias = "acl-test-focused"
        else:
            alias = f"acl-test-focused-{index:02d}"
        if alias in aliases:
            raise TargetExecutionError("approved commands produced a duplicate bounded alias")
        aliases.add(alias)
        command_digest = sha256_bytes(
            json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        wrapper_path = commands_dir / alias
        wrapper_path.write_text(
            _wrapper_payload(
                bubblewrap=bubblewrap,
                executable=executable,
                arguments=argv[1:],
                runtime_root=runtime_root,
                workspace=workspace,
                request=request,
            ),
            encoding="utf-8",
        )
        wrapper_path.chmod(0o500)
        prepared.append(
            _PreparedCommand(
                alias=alias,
                argv=argv,
                command_digest=command_digest,
                wrapper_path=wrapper_path,
            )
        )
        manifest.append(
            {
                "alias": alias,
                "approved_command_digest": command_digest,
                "command_timeout_seconds": request.command_timeout_seconds,
                "command_cpu_seconds": request.command_cpu_seconds,
                "command_memory_mb": request.command_memory_mb,
                "command_file_size_mb": request.command_file_size_mb,
                "command_process_limit": request.command_process_limit,
                "command_open_files_limit": request.command_open_files_limit,
                "sandbox_backend_digest": sha256_file(bubblewrap),
                "sandbox_network": "unshared",
                "sandbox_host_filesystem": "not_mounted",
            }
        )
    manifest_digest = sha256_bytes(
        json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return commands_dir, tuple(prepared), manifest_digest


def _command_instructions(prepared_commands: tuple[_PreparedCommand, ...]) -> str:
    if not prepared_commands:
        return (
            "\n\nExecution boundary: no shell command is approved. Use Read, Glob, and Grep for "
            "inspection and Edit or Write for file changes."
        )
    lines = [
        "",
        "",
        "Execution boundary: use Read, Glob, and Grep for inspection and Edit or Write for file "
        "changes. The only approved shell commands are the exact bounded aliases below. Invoke an "
        "alias exactly as shown, without arguments, chaining, redirection, substitution, a path "
        "prefix, or a replacement Python command. Do not use Bash for file discovery, navigation, "
        "or inspection. Do not inspect .acl-condition.md or .acl-runtime; the condition is already "
        "injected and runner state is not task input:",
    ]
    for command in prepared_commands:
        purpose = (
            "run the full visible suite"
            if command.alias == "acl-test-full"
            else ("run the focused regression")
        )
        lines.append(f"- `{command.alias}` — {purpose}.")
    lines.append("A command alias has a fixed timeout and resource ceiling and is audit logged.")
    return "\n".join(lines)


def _compatibility_command(
    *,
    bubblewrap: Path,
    claude_command: list[str],
    workspace: Path,
) -> list[str]:
    """Mask WSL's Windows mount while retaining Claude's inner security sandbox."""

    return [
        str(bubblewrap),
        "--bind",
        "/",
        "/",
        "--tmpfs",
        "/mnt",
        "--dir",
        "/mnt/c",
        "--dir",
        "/mnt/c/Program Files",
        "--dir",
        "/mnt/c/Program Files/ClaudeCode",
        "--die-with-parent",
        "--new-session",
        "--chdir",
        str(workspace),
        "--",
        *claude_command,
    ]


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


def serialize_target_trace(events: tuple[JsonObject, ...]) -> bytes:
    """Serialize an ordered target-event sequence without treating it as a mapping."""

    return json.dumps(
        events,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _assert_trace_conformance(
    events: tuple[JsonObject, ...],
    *,
    model_id: str,
    timed_out: bool,
    workspace: Path,
    condition_file: Path,
    prepared_commands: tuple[_PreparedCommand, ...],
    command_timeout_seconds: int,
) -> tuple[TargetCommandAuditEntry, ...]:
    if not timed_out:
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
    prepared_by_alias = {command.alias: command for command in prepared_commands}
    audit: list[TargetCommandAuditEntry] = []
    reserved_paths = {
        (workspace / name).resolve() for name in (*_RUNTIME_ARTIFACTS, *_AMBIENT_READ_NAMES)
    }
    reserved_paths.add(condition_file)

    def assert_workspace_path(value: object, *, write: bool) -> None:
        if value is None:
            return
        if not isinstance(value, str) or not value:
            raise TargetExecutionError("Claude file tool supplied a malformed path")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(workspace):
            raise TargetExecutionError(
                "Claude file tool attempted host-file access",
                failure_code="host_file_access",
                failure_subject_digest=sha256_bytes(str(resolved).encode("utf-8")),
            )
        if any(
            resolved == reserved or resolved.is_relative_to(reserved) for reserved in reserved_paths
        ):
            operation = "modify" if write else "read"
            raise TargetExecutionError(
                f"Claude attempted to {operation} a reserved runner path",
                failure_code=f"reserved_runner_path_{operation}",
                failure_subject_digest=sha256_bytes(str(resolved).encode("utf-8")),
            )

    for event in events:
        for nested in _iter_objects(event):
            if nested.get("type") == "tool_use":
                name = nested.get("name")
                if not isinstance(name, str) or name not in _TRACE_ALLOWED_TOOLS:
                    raise TargetExecutionError("Claude trace contains a forbidden tool use")
                tool_input = nested.get("input", {})
                if not isinstance(tool_input, dict):
                    raise TargetExecutionError("Claude tool use has malformed input")
                if name == "Bash":
                    raw_command = tool_input.get("command")
                    if not isinstance(raw_command, str):
                        raise TargetExecutionError("Claude Bash tool omitted its command")
                    prepared = prepared_by_alias.get(raw_command)
                    if prepared is None:
                        raise TargetExecutionError(
                            "Claude attempted a Bash command outside the bounded manifest",
                            failure_code="out_of_manifest_bash_command",
                            failure_subject_digest=sha256_bytes(raw_command.encode("utf-8")),
                            partial_command_audit=tuple(audit),
                        )
                    disable_sandbox = tool_input.get("dangerouslyDisableSandbox")
                    if disable_sandbox not in (None, False):
                        raise TargetExecutionError("Claude attempted to disable the Bash sandbox")
                    timeout_value = tool_input.get("timeout")
                    if timeout_value is not None and (
                        not isinstance(timeout_value, int)
                        or isinstance(timeout_value, bool)
                        or timeout_value < 1
                        or timeout_value > command_timeout_seconds * 1000
                    ):
                        raise TargetExecutionError("Claude requested an invalid command timeout")
                    audit.append(
                        TargetCommandAuditEntry(
                            sequence=len(audit) + 1,
                            alias=prepared.alias,
                            approved_command_digest=prepared.command_digest,
                            requested_timeout_ms=timeout_value,
                        )
                    )
                elif name in {"Read", "Glob", "Grep"}:
                    assert_workspace_path(
                        tool_input.get("file_path", tool_input.get("path")),
                        write=False,
                    )
                elif name in {"Edit", "Write"}:
                    assert_workspace_path(
                        tool_input.get("file_path", tool_input.get("path")),
                        write=True,
                    )
    return tuple(audit)


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
        commands_dir: Path,
        managed_settings_dir: Path,
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
        path_parts = [
            str(commands_dir),
            str(runtime.bubblewrap.parent),
            str(runtime.socat.parent),
            "/usr/bin",
            "/bin",
        ]
        environment["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))
        environment["LD_LIBRARY_PATH"] = str(runtime.sandbox_library_path)
        environment["ANTHROPIC_API_KEY"] = api_key
        environment["ANTHROPIC_BASE_URL"] = runtime.api_base_url
        environment["ANTHROPIC_MODEL"] = runtime.model_id
        environment["CLAUDE_CONFIG_DIR"] = str(config_dir)
        environment["CLAUDE_CODE_MANAGED_SETTINGS_PATH"] = str(managed_settings_dir)
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
        existing_runtime_artifacts = [
            name for name in _RUNTIME_ARTIFACTS if (workspace / name).exists()
        ]
        if existing_runtime_artifacts:
            raise TargetExecutionError(
                "target workspace contains reserved runner artifacts: "
                + ", ".join(existing_runtime_artifacts)
            )

        try:
            with tempfile.TemporaryDirectory(prefix="acl-claude-config-") as temporary:
                config_dir = Path(temporary)
                commands_dir, prepared_commands, command_manifest_digest = _prepare_commands(
                    bubblewrap=runtime.bubblewrap,
                    config_dir=config_dir,
                    workspace=workspace,
                    request=request,
                )
                settings_path = config_dir / "settings.json"
                settings_payload = _settings(
                    workspace,
                    condition_file,
                    commands_dir,
                    prepared_commands,
                )
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
                managed_settings_path = config_dir / "managed-settings.json"
                managed_settings_payload = {
                    **settings_payload,
                    "bwrapPath": str(runtime.bubblewrap),
                }
                managed_settings_path.write_text(
                    json.dumps(
                        managed_settings_payload,
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )
                managed_settings_path.chmod(0o600)
                environment = self._environment_for_run(
                    runtime,
                    config_dir=config_dir,
                    commands_dir=commands_dir,
                    managed_settings_dir=config_dir,
                )
                allow_rules, _ = _tool_rules(workspace, condition_file)
                allowed_tools = [cast(str, rule) for rule in allow_rules]
                allowed_tools.extend(f"Bash({prepared.alias})" for prepared in prepared_commands)
                claude_command = [
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
                command = _compatibility_command(
                    bubblewrap=runtime.bubblewrap,
                    claude_command=claude_command,
                    workspace=workspace,
                )
                command_digest = sha256_bytes(
                    json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                )
                started_at = datetime.now(UTC)
                timed_out = False
                exit_code: int | None
                stdout = ""
                stderr = ""
                events: tuple[JsonObject, ...] = ()
                command_audit: tuple[TargetCommandAuditEntry, ...] = ()
                trace_error: TargetExecutionError | None = None
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
                target_prompt = request.prompt + _command_instructions(prepared_commands)
                try:
                    stdout, stderr = process.communicate(
                        input=target_prompt,
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
                # Wall clocks can move backwards while a process is running (for example, an NTP
                # correction). Preserve the result contract without pretending elapsed-time
                # measurement comes from wall-clock ordering.
                finished_at = max(datetime.now(UTC), started_at)
                try:
                    command_audit = _assert_trace_conformance(
                        events,
                        model_id=runtime.model_id,
                        timed_out=timed_out,
                        workspace=workspace,
                        condition_file=condition_file,
                        prepared_commands=prepared_commands,
                        command_timeout_seconds=request.command_timeout_seconds,
                    )
                except TargetExecutionError as exc:
                    trace_error = exc
                    command_audit = exc.partial_command_audit
        finally:
            for name in _RUNTIME_ARTIFACTS:
                path = workspace / name
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                elif path.exists() or path.is_symlink():
                    path.unlink()
        if trace_error is not None:
            evidence = TargetFailureEvidence(
                run_id=request.run_id,
                runner_version=runtime.version,
                model_id=runtime.model_id,
                condition_digest=request.condition_digest,
                command_digest=command_digest,
                started_at=started_at,
                finished_at=finished_at,
                exit_code=exit_code,
                timed_out=timed_out,
                stdout=stdout,
                events=events,
                stderr=stderr,
                command_manifest_digest=command_manifest_digest,
                command_audit=command_audit,
                config_destroyed=not config_dir.exists(),
                failure_code=trace_error.failure_code,
                failure_subject_digest=trace_error.failure_subject_digest,
            )
            raise TargetExecutionError(
                str(trace_error),
                evidence=evidence,
                failure_code=trace_error.failure_code,
                failure_subject_digest=trace_error.failure_subject_digest,
                partial_command_audit=command_audit,
            ) from trace_error
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
            command_manifest_digest=command_manifest_digest,
            command_audit=command_audit,
            config_destroyed=not config_dir.exists(),
        )
