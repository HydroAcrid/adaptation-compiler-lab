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
    TargetDeniedCommandAuditEntry,
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
_OUTER_RUNTIME_ROOT: Final = Path("/opt/acl-runtime")
_OUTER_CLAUDE: Final = _OUTER_RUNTIME_ROOT / "claude"
_OUTER_BWRAP: Final = _OUTER_RUNTIME_ROOT / "bwrap"
_OUTER_SOCAT: Final = _OUTER_RUNTIME_ROOT / "socat"
_OUTER_SANDBOX_LIB: Final = _OUTER_RUNTIME_ROOT / "lib"
_WSL_RESOLV_CONF: Final = Path("/mnt/wsl/resolv.conf")


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
class _BashPolicyAuditEntry:
    arguments: tuple[str, ...]
    decision: str


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
    bash_policy_audit_digest: str
    command_audit: tuple[TargetCommandAuditEntry, ...]
    denied_command_audit: tuple[TargetDeniedCommandAuditEntry, ...]
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
        "Glob",
        "Grep",
        _absolute_permission_rule("Read", workspace, descendants=True),
        _absolute_permission_rule("Edit", workspace, descendants=True),
        _absolute_permission_rule("Write", workspace, descendants=True),
    ]
    deny: list[JsonValue] = list(_REMOVED_TOOLS)
    deny.append(_absolute_permission_rule("Edit", condition_file))
    deny.append(_absolute_permission_rule("Write", condition_file))
    for name in _AMBIENT_READ_NAMES:
        path = workspace / name
        deny.append(_absolute_permission_rule("Read", path, descendants=path.suffix == ""))
        deny.append(_absolute_permission_rule("Edit", path, descendants=path.suffix == ""))
        deny.append(_absolute_permission_rule("Write", path, descendants=path.suffix == ""))
    runtime_path = workspace / ".acl-runtime"
    deny.append(_absolute_permission_rule("Read", runtime_path, descendants=True))
    deny.append(_absolute_permission_rule("Edit", runtime_path, descendants=True))
    deny.append(_absolute_permission_rule("Write", runtime_path, descendants=True))
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
        str(_OUTER_RUNTIME_ROOT),
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
            "excludedCommands": [],
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


def _write_bash_policy_shell(
    path: Path,
    *,
    prepared_commands: tuple[_PreparedCommand, ...],
    audit_path: Path,
) -> None:
    """Create the shell boundary that can execute only exact generated aliases."""

    allowed = json.dumps(
        {
            command.alias: str(command.wrapper_path)
            for command in sorted(prepared_commands, key=lambda item: item.alias)
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = (
        "#!/usr/bin/python3\n"
        "import json\n"
        "import os\n"
        "import re\n"
        "import sys\n"
        f"ALLOWED = {allowed}\n"
        f"AUDIT_PATH = {str(audit_path)!r}\n"
        "arguments = sys.argv[1:]\n"
        "joined = '\\n'.join(arguments)\n"
        "matched_aliases = sorted(\n"
        "    alias for alias in ALLOWED\n"
        "    if re.search(\n"
        "        r'(?<![A-Za-z0-9_.-])' + re.escape(alias) + "
        "r'(?![A-Za-z0-9_.-])',\n"
        "        joined,\n"
        "    )\n"
        ")\n"
        "decision = 'allow' if len(matched_aliases) == 1 else 'deny'\n"
        "entry = json.dumps({\n"
        "    'arguments': arguments,\n"
        "    'decision': decision,\n"
        "}, sort_keys=True, separators=(',', ':')) + '\\n'\n"
        "descriptor = os.open(AUDIT_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)\n"
        "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:\n"
        "    stream.write(entry)\n"
        "    stream.flush()\n"
        "    os.fsync(stream.fileno())\n"
        "if decision == 'deny':\n"
        "    sys.stderr.write('Blocked by the bounded Bash policy.\\n')\n"
        "    raise SystemExit(126)\n"
        "command = matched_aliases[0]\n"
        "wrapper = ALLOWED[command]\n"
        "os.execve(wrapper, [command], os.environ)\n"
    )
    path.write_text(payload, encoding="utf-8")
    path.chmod(0o500)


def _read_bash_policy_audit(path: Path) -> tuple[tuple[_BashPolicyAuditEntry, ...], str]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        payload = b""
    entries: list[_BashPolicyAuditEntry] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TargetExecutionError(f"Bash policy audit line {line_number} is invalid") from exc
        if (
            not isinstance(value, dict)
            or set(value) != {"arguments", "decision"}
            or value.get("decision") not in {"allow", "deny"}
            or not isinstance(value.get("arguments"), list)
            or not all(isinstance(item, str) for item in value["arguments"])
        ):
            raise TargetExecutionError("Bash policy audit entry is malformed")
        entries.append(
            _BashPolicyAuditEntry(
                arguments=tuple(cast(list[str], value["arguments"])),
                decision=cast(str, value["decision"]),
            )
        )
    return tuple(entries), sha256_bytes(payload)


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
    executable: Path,
    arguments: tuple[str, ...],
    runtime_root: Path,
    request: TargetRunRequest,
) -> str:
    environment_json = json.dumps(
        {
            "ACL_BOUNDED_TEST": "1",
            "HOME": str(runtime_root / "home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(runtime_root / "tmp"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    command_json = json.dumps(
        (
            "/usr/bin/timeout",
            "--signal=TERM",
            "--kill-after=5",
            str(request.command_timeout_seconds),
            str(executable),
            *arguments,
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "#!/usr/bin/python3\n"
        "import glob\n"
        "import json\n"
        "import os\n"
        "import resource\n"
        f"environment = json.loads({environment_json!r})\n"
        f"command = json.loads({command_json!r})\n"
        f"resource.setrlimit(resource.RLIMIT_CPU, ({request.command_cpu_seconds}, "
        "resource.getrlimit(resource.RLIMIT_CPU)[1]))\n"
        f"resource.setrlimit(resource.RLIMIT_AS, ({request.command_memory_mb * 1024 * 1024}, "
        "resource.getrlimit(resource.RLIMIT_AS)[1]))\n"
        f"resource.setrlimit(resource.RLIMIT_FSIZE, "
        f"({request.command_file_size_mb * 1024 * 1024}, "
        "resource.getrlimit(resource.RLIMIT_FSIZE)[1]))\n"
        "ambient_tasks = len(glob.glob('/proc/[0-9]*/task/[0-9]*'))\n"
        f"process_limit = ambient_tasks + {request.command_process_limit}\n"
        "process_hard_limit = resource.getrlimit(resource.RLIMIT_NPROC)[1]\n"
        "if process_hard_limit != resource.RLIM_INFINITY:\n"
        "    process_limit = min(process_limit, process_hard_limit)\n"
        "resource.setrlimit(resource.RLIMIT_NPROC, (process_limit, process_hard_limit))\n"
        f"resource.setrlimit(resource.RLIMIT_NOFILE, ({request.command_open_files_limit}, "
        "resource.getrlimit(resource.RLIMIT_NOFILE)[1]))\n"
        "os.execve(command[0], command, environment)\n"
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
                executable=executable,
                arguments=argv[1:],
                runtime_root=runtime_root,
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
                "command_process_limit_scope": "additional_uid_tasks_within_outer_pid_boundary",
                "command_open_files_limit": request.command_open_files_limit,
                "sandbox_backend_digest": sha256_file(bubblewrap),
                "sandbox_backend": "claude_code_pinned_bubblewrap",
                "outer_process_boundary": "minimal_mount_manifest",
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
            "\n\nExecution boundary: no shell command is approved. Use the supplied visible-file "
            "manifest and Read for inspection, and Edit for file changes."
        )
    lines = [
        "",
        "",
        "Execution boundary: use the supplied visible-file manifest and Read for inspection, and "
        "Edit for file changes. The only approved shell commands are the exact bounded aliases "
        "below. Invoke an alias exactly as shown, without arguments, chaining, redirection, "
        "substitution, a path prefix, or a replacement Python command. Do not use Bash for file "
        "discovery, navigation, or inspection. Do not inspect .acl-condition.md or .acl-runtime; "
        "the condition is already injected and runner state is not task input:",
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


def _isolated_target_command(
    *,
    runtime: VerifiedClaudeRuntime,
    claude_command: list[str],
    config_dir: Path,
    workspace: Path,
    bash_policy_shell: Path,
) -> list[str]:
    """Place the whole target inside a minimal filesystem while retaining provider network."""

    return [
        str(runtime.bubblewrap),
        "--unshare-all",
        "--share-net",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        str(bash_policy_shell),
        "/usr/bin/bash",
        "--ro-bind",
        str(bash_policy_shell),
        "/usr/bin/sh",
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
        "/mnt/c/Program Files/ClaudeCode",
        "--dir",
        str(_WSL_RESOLV_CONF.parent),
        "--ro-bind",
        str(_WSL_RESOLV_CONF),
        str(_WSL_RESOLV_CONF),
        "--dir",
        str(_OUTER_RUNTIME_ROOT),
        "--ro-bind",
        str(runtime.executable),
        str(_OUTER_CLAUDE),
        "--ro-bind",
        str(runtime.bubblewrap),
        str(_OUTER_BWRAP),
        "--ro-bind",
        str(runtime.socat),
        str(_OUTER_SOCAT),
        "--ro-bind",
        str(runtime.sandbox_library_path),
        str(_OUTER_SANDBOX_LIB),
        "--bind",
        str(workspace),
        str(workspace),
        "--bind",
        str(config_dir),
        str(config_dir),
        "--chdir",
        str(workspace),
        "--",
        str(_OUTER_CLAUDE),
        *claude_command[1:],
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
    bash_policy_audit: tuple[_BashPolicyAuditEntry, ...],
) -> tuple[
    tuple[TargetCommandAuditEntry, ...],
    tuple[TargetDeniedCommandAuditEntry, ...],
]:
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
        if init.get("permissionMode") != "dontAsk":
            raise TargetExecutionError("Claude did not initialize in the frozen permission mode")
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
    denied_audit: list[TargetDeniedCommandAuditEntry] = []
    unmatched_policy_entries = list(bash_policy_audit)
    denied_tool_use_ids = {
        nested.get("tool_use_id")
        for event in events
        for nested in _iter_objects(event)
        if nested.get("type") == "tool_result"
        and nested.get("is_error") is True
        and isinstance(nested.get("tool_use_id"), str)
    }
    permission_denied_bash_ids: set[str] = set()
    for event in events:
        if event.get("type") != "result":
            continue
        permission_denials = event.get("permission_denials", [])
        if not isinstance(permission_denials, list):
            raise TargetExecutionError("Claude result has malformed permission denials")
        for denial in permission_denials:
            if (
                isinstance(denial, dict)
                and denial.get("tool_name") == "Bash"
                and isinstance(denial.get("tool_use_id"), str)
            ):
                permission_denied_bash_ids.add(cast(str, denial["tool_use_id"]))
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
                    tool_use_id = nested.get("id")
                    if not isinstance(tool_use_id, str):
                        raise TargetExecutionError("Claude Bash tool omitted its use ID")
                    raw_command = tool_input.get("command")
                    if not isinstance(raw_command, str):
                        raise TargetExecutionError("Claude Bash tool omitted its command")
                    prepared = prepared_by_alias.get(raw_command)
                    run_in_background = tool_input.get("run_in_background", False)
                    expected_policy_decision = (
                        "allow" if prepared is not None and run_in_background is False else "deny"
                    )
                    raw_command_digest = sha256_bytes(raw_command.encode("utf-8"))
                    matching_policy_index = next(
                        (
                            index
                            for index, entry in enumerate(unmatched_policy_entries)
                            if entry.decision == expected_policy_decision
                            and any(raw_command in argument for argument in entry.arguments)
                        ),
                        None,
                    )
                    if matching_policy_index is None:
                        if (
                            expected_policy_decision == "deny"
                            and tool_use_id in permission_denied_bash_ids
                        ):
                            denied_audit.append(
                                TargetDeniedCommandAuditEntry(
                                    sequence=len(denied_audit) + 1,
                                    requested_command_digest=raw_command_digest,
                                    reason="claude_permission_layer_denial",
                                )
                            )
                            continue
                        raise TargetExecutionError(
                            "Bash tool use lacks matching pre-execution policy evidence",
                            failure_code="bash_policy_evidence_missing",
                            failure_subject_digest=raw_command_digest,
                            partial_command_audit=tuple(audit),
                        )
                    unmatched_policy_entries.pop(matching_policy_index)
                    if prepared is None:
                        if tool_use_id in denied_tool_use_ids:
                            denied_audit.append(
                                TargetDeniedCommandAuditEntry(
                                    sequence=len(denied_audit) + 1,
                                    requested_command_digest=raw_command_digest,
                                    reason="out_of_manifest_bash_command",
                                )
                            )
                            continue
                        raise TargetExecutionError(
                            "an out-of-manifest Bash command was not proven blocked",
                            failure_code="unblocked_out_of_manifest_bash_command",
                            failure_subject_digest=raw_command_digest,
                            partial_command_audit=tuple(audit),
                        )
                    if run_in_background is not False:
                        if tool_use_id in denied_tool_use_ids:
                            denied_audit.append(
                                TargetDeniedCommandAuditEntry(
                                    sequence=len(denied_audit) + 1,
                                    requested_command_digest=raw_command_digest,
                                    reason="background_bash_forbidden",
                                )
                            )
                            continue
                        raise TargetExecutionError(
                            "a background Bash command was not proven blocked",
                            failure_code="unblocked_background_bash_command",
                            failure_subject_digest=raw_command_digest,
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
    if any(entry.decision == "allow" for entry in unmatched_policy_entries):
        raise TargetExecutionError("Bash policy audit contains an unmatched allowed execution")
    return tuple(audit), tuple(denied_audit)


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
        runtime_root: Path,
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
            if key in {"LANG", "LC_ALL", "LOGNAME", "SHELL", "TERM", "USER"}
        }
        path_parts = [
            str(commands_dir),
            str(_OUTER_RUNTIME_ROOT),
            "/usr/bin",
            "/bin",
        ]
        environment["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))
        environment["LD_LIBRARY_PATH"] = str(_OUTER_SANDBOX_LIB)
        environment["SHELL"] = "/bin/bash"
        environment["HOME"] = str(runtime_root / "home")
        environment["TMPDIR"] = str(runtime_root / "tmp")
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
                bash_policy_audit_path = config_dir / "bounded-bash-policy-audit.jsonl"
                bash_policy_shell = config_dir / "bounded-bash-policy-shell"
                _write_bash_policy_shell(
                    bash_policy_shell,
                    prepared_commands=prepared_commands,
                    audit_path=bash_policy_audit_path,
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
                    "bwrapPath": str(_OUTER_BWRAP),
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
                    runtime_root=workspace / ".acl-runtime",
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
                command = _isolated_target_command(
                    runtime=runtime,
                    claude_command=claude_command,
                    config_dir=config_dir,
                    workspace=workspace,
                    bash_policy_shell=bash_policy_shell,
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
                denied_command_audit: tuple[TargetDeniedCommandAuditEntry, ...] = ()
                bash_policy_audit_digest = sha256_bytes(b"")
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
                    bash_policy_audit, bash_policy_audit_digest = _read_bash_policy_audit(
                        bash_policy_audit_path
                    )
                    command_audit, denied_command_audit = _assert_trace_conformance(
                        events,
                        model_id=runtime.model_id,
                        timed_out=timed_out,
                        workspace=workspace,
                        condition_file=condition_file,
                        prepared_commands=prepared_commands,
                        command_timeout_seconds=request.command_timeout_seconds,
                        bash_policy_audit=bash_policy_audit,
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
                bash_policy_audit_digest=bash_policy_audit_digest,
                command_audit=command_audit,
                denied_command_audit=denied_command_audit,
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
            bash_policy_audit_digest=bash_policy_audit_digest,
            command_audit=command_audit,
            denied_command_audit=denied_command_audit,
            config_destroyed=not config_dir.exists(),
        )
