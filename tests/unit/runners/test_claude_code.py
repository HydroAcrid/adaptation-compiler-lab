from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from adaptation_compiler_lab.connectors.models import JsonObject, TargetRunRequest
from adaptation_compiler_lab.connectors.pins import (
    ClaudeCodePin,
    ExecutablePin,
    RuntimePinSet,
    SandboxPin,
    load_runtime_pins,
    sha256_file,
)
from adaptation_compiler_lab.runners import (
    ClaudeCodeTargetRunner,
    ClaudeRuntimePaths,
    LiveSmokeReceipt,
    TargetExecutionError,
    run_live_no_user_data_smoke,
)
from adaptation_compiler_lab.runners.claude_code import (
    _PreparedCommand,
    _write_bash_policy_shell,
    serialize_target_trace,
)

_FAKE_CLAUDE = """#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

args = sys.argv[1:]
if args == ["--version"]:
    print("9.9.9 (Synthetic Claude Code)")
    raise SystemExit(0)
if args == ["--help"]:
    print("--bare")
    raise SystemExit(0)

def argument_after(flag):
    return args[args.index(flag) + 1]

prompt = sys.stdin.read()
if "PROCESS_TIMEOUT_MARKER" in prompt:
    time.sleep(30)
if "LEAK_KEY_MARKER" in prompt:
    print(os.environ["ANTHROPIC_API_KEY"], flush=True)

condition_path = pathlib.Path(argument_after("--append-system-prompt-file"))
settings_path = pathlib.Path(argument_after("--settings"))
model = argument_after("--model")
tools = argument_after("--tools").split(",")
settings = json.loads(settings_path.read_text(encoding="utf-8"))
managed_settings_dir = pathlib.Path(os.environ["CLAUDE_CODE_MANAGED_SETTINGS_PATH"])
managed_settings = json.loads(
    (managed_settings_dir / "managed-settings.json").read_text(encoding="utf-8")
)

def invoke_bash(command):
    return subprocess.run(
        [
            os.environ["SHELL"],
            "-c",
            f"__acl_bootstrap__ {command} __acl_bootstrap_end__",
            "--",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

print(json.dumps({
    "type": "system",
    "subtype": "init",
    "model": model,
    "permissionMode": "dontAsk",
    "tools": tools,
    "mcp_servers": [],
    "plugins": [],
}), flush=True)

if "M4_LIVE_SMOKE_TASK" in prompt:
    pathlib.Path("smoke-output.txt").write_text("synthetic-smoke-ok", encoding="utf-8")
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Read", "input": {}},
                {"type": "tool_use", "name": "Write", "input": {}},
            ]
        },
    }), flush=True)

if "BOUNDED_COMMAND_SMOKE" in prompt:
    pathlib.Path("solution.py").write_text(
        "def add(left, right):\\n    return left + right\\n",
        encoding="utf-8",
    )
    completed = invoke_bash("acl-test-full")
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "edit-1",
                    "name": "Edit",
                    "input": {"file_path": str(pathlib.Path("solution.py").resolve())},
                },
                {
                    "type": "tool_use",
                    "id": "bash-1",
                    "name": "Bash",
                    "input": {"command": "acl-test-full", "timeout": 5000},
                },
            ]
        },
    }), flush=True)
    print(json.dumps({
        "type": "user",
        "message": {
            "content": [{
                "type": "tool_result",
                "tool_use_id": "bash-1",
                "content": completed.stdout + completed.stderr,
                "is_error": completed.returncode != 0,
            }]
        },
    }), flush=True)

if "TWO_COMMAND_SMOKE" in prompt:
    pathlib.Path("solution.py").write_text(
        "def add(left, right):\\n    return left + right\\n",
        encoding="utf-8",
    )
    for sequence, alias in enumerate(("acl-test-focused", "acl-test-full"), start=1):
        completed = invoke_bash(alias)
        use_id = f"bash-two-{sequence}"
        print(json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": use_id,
                        "name": "Bash",
                        "input": {"command": alias, "timeout": 5000},
                    },
                ]
            },
        }), flush=True)
        print(json.dumps({
            "type": "user",
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": completed.stdout + completed.stderr,
                    "is_error": completed.returncode != 0,
                }]
            },
        }), flush=True)

if "UNBOUNDED_COMMAND_MARKER" in prompt:
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "id": "unbounded-bash-1",
                "name": "Bash",
                "input": {"command": "python3 -m unittest -v"},
            }]
        },
    }), flush=True)

if "BLOCKED_COMMAND_MARKER" in prompt:
    completed = invoke_bash("find / -type f")
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "id": "blocked-bash-1",
                "name": "Bash",
                "input": {"command": "find / -type f"},
            }]
        },
    }), flush=True)
    print(json.dumps({
        "type": "user",
        "message": {
            "content": [{
                "type": "tool_result",
                "tool_use_id": "blocked-bash-1",
                "content": completed.stdout + completed.stderr,
                "is_error": completed.returncode != 0,
            }]
        },
    }), flush=True)

if "OVERSIZED_TIMEOUT_MARKER" in prompt:
    completed = invoke_bash("acl-test-full")
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "id": "oversized-timeout-1",
                "name": "Bash",
                "input": {"command": "acl-test-full", "timeout": 60001},
            }]
        },
    }), flush=True)
    print(json.dumps({
        "type": "user",
        "message": {
            "content": [{
                "type": "tool_result",
                "tool_use_id": "oversized-timeout-1",
                "content": completed.stdout + completed.stderr,
                "is_error": completed.returncode != 0,
            }]
        },
    }), flush=True)

if "HOST_FILE_MARKER" in prompt:
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": "/home/private-material"},
            }]
        },
    }), flush=True)

if "RESERVED_READ_MARKER" in prompt:
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [{
                "type": "tool_use",
                "name": "Read",
                "input": {"file_path": str(pathlib.Path("CLAUDE.md").resolve())},
            }]
        },
    }), flush=True)

if "FORBIDDEN_TOOL_MARKER" in prompt:
    print(json.dumps({
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "WebFetch", "input": {}}]
        },
    }), flush=True)

print(json.dumps({
    "type": "result",
    "subtype": "success",
    "argv": args,
    "stdin_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    "condition_sha256": hashlib.sha256(condition_path.read_bytes()).hexdigest(),
    "settings": settings,
    "ambient_loaded": False if "--bare" in args else pathlib.Path("CLAUDE.md").exists(),
    "session_persisted": "--no-session-persistence" not in args,
    "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    "host_platform": os.environ.get("CLAUDE_CODE_HOST_PLATFORM"),
    "managed_settings_path": os.environ.get("CLAUDE_CODE_MANAGED_SETTINGS_PATH"),
    "managed_settings": managed_settings,
    "path": os.environ.get("PATH"),
    "prompt_has_full_alias": "acl-test-full" in prompt,
    "prompt_has_focused_alias": "acl-test-focused" in prompt,
    "prompt_exposes_python_implementation": (
        "python3 -m unittest" in prompt.split("Execution boundary:", 1)[-1]
    ),
    "total_cost_usd": 0.01,
}), flush=True)
"""

_FAKE_BWRAP = """#!/usr/bin/env python3
import os
import pathlib
import sys

args = sys.argv[1:]
if args == ["--version"]:
    print("bubblewrap synthetic")
    raise SystemExit(0)
if args[-1:] == ["/bin/true"] and {
    "--ro-bind",
    "--proc",
    "--dev",
    "--unshare-user",
    "--unshare-pid",
    "--die-with-parent",
}.issubset(args):
    raise SystemExit(0)
required_flags = {"--unshare-all", "--share-net", "--die-with-parent", "--new-session"}
if not required_flags.issubset(args):
    print("synthetic bwrap: required isolation flag missing", file=sys.stderr)
    raise SystemExit(91)
if "--unshare-net" in args or "--clearenv" in args:
    print("synthetic bwrap: target environment or provider network drifted", file=sys.stderr)
    raise SystemExit(92)
if args.count("--bind") != 2 or args.count("--ro-bind") != 9:
    print("synthetic bwrap: unexpected host mount count", file=sys.stderr)
    raise SystemExit(93)

binds = {}
working_directory = None
command = None
directories = set()
tmpfs_paths = set()
index = 0
two_values = {"--bind", "--ro-bind", "--setenv", "--symlink"}
one_value = {"--chdir", "--dev", "--dir", "--proc", "--tmpfs"}
no_values = {"--unshare-all", "--share-net", "--die-with-parent", "--new-session"}
while index < len(args):
    item = args[index]
    if item == "--":
        command = args[index + 1:]
        break
    if item in two_values:
        left, right = args[index + 1:index + 3]
        if item in {"--bind", "--ro-bind"}:
            binds[right] = left
        index += 3
        continue
    if item in one_value:
        if item == "--chdir":
            working_directory = args[index + 1]
        elif item == "--dir":
            directories.add(args[index + 1])
        elif item == "--tmpfs":
            tmpfs_paths.add(args[index + 1])
        index += 2
        continue
    if item in no_values:
        index += 1
        continue
    print(f"synthetic bwrap: unknown option {item}", file=sys.stderr)
    raise SystemExit(94)

expected_fixed = {
    "/usr": "/usr",
    "/etc": "/etc",
    "/mnt/wsl/resolv.conf": "/mnt/wsl/resolv.conf",
    "/opt/acl-runtime/claude": str(pathlib.Path(sys.argv[0]).parent / "fake-claude"),
    "/opt/acl-runtime/bwrap": str(pathlib.Path(sys.argv[0]).resolve()),
    "/opt/acl-runtime/socat": str(pathlib.Path(sys.argv[0]).parent / "socat"),
    "/opt/acl-runtime/lib": str(pathlib.Path(sys.argv[0]).parent / "lib"),
    "/usr/bin/bash": binds.get("/usr/bin/bash"),
    "/usr/bin/sh": binds.get("/usr/bin/sh"),
}
if (
    not isinstance(expected_fixed["/usr/bin/bash"], str)
    or expected_fixed["/usr/bin/bash"] != expected_fixed["/usr/bin/sh"]
    or not expected_fixed["/usr/bin/bash"].startswith("/tmp/acl-claude-config-")
):
    print("synthetic bwrap: Bash policy shell mount drifted", file=sys.stderr)
    raise SystemExit(95)
if any(binds.get(destination) != source for destination, source in expected_fixed.items()):
    print("synthetic bwrap: fixed runtime mount drifted", file=sys.stderr)
    raise SystemExit(95)
rw_binds = {
    destination: source
    for destination, source in binds.items()
    if destination not in expected_fixed
}
if len(rw_binds) != 2 or any(source != destination for destination, source in rw_binds.items()):
    print("synthetic bwrap: disposable writable mounts drifted", file=sys.stderr)
    raise SystemExit(96)
if any(
    source in {"/", "/home", "/mnt"} or not source.startswith("/tmp/")
    for source in rw_binds.values()
):
    print("synthetic bwrap: forbidden host mount", file=sys.stderr)
    raise SystemExit(97)
if (
    "/tmp" not in tmpfs_paths
    or "/opt/acl-runtime" not in directories
    or "/mnt/wsl" not in directories
    or "/mnt/c/Program Files/ClaudeCode" not in directories
):
    print("synthetic bwrap: masked compatibility or runtime directory missing", file=sys.stderr)
    raise SystemExit(98)
if working_directory not in rw_binds or not command:
    print("synthetic bwrap: workspace or command missing", file=sys.stderr)
    raise SystemExit(99)
if command[0] != "/opt/acl-runtime/claude":
    print("synthetic bwrap: unexpected target executable", file=sys.stderr)
    raise SystemExit(100)

command[0] = expected_fixed["/opt/acl-runtime/claude"]
os.environ["SHELL"] = expected_fixed["/usr/bin/bash"]
os.chdir(working_directory)
os.execve(command[0], command, os.environ)
"""


def test_target_trace_serializer_accepts_an_ordered_event_tuple() -> None:
    events: tuple[JsonObject, ...] = (
        {"type": "system", "subtype": "init"},
        {"type": "result", "result": "done", "total_cost_usd": 0.01},
    )

    payload = serialize_target_trace(events)

    assert json.loads(payload) == list(events)
    assert payload.startswith(b'[{"subtype":"init","type":"system"}')


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)


def _executable_pin(
    path: Path,
    *,
    package: str,
    version: str,
    version_stdout: str,
    version_args: tuple[str, ...],
    help_flags: tuple[str, ...] = (),
) -> ExecutablePin:
    return ExecutablePin(
        package=package,
        package_version=version,
        package_integrity="synthetic-only",
        executable_sha256=sha256_file(path),
        version_args=version_args,
        version_stdout=version_stdout,
        required_help_flags=help_flags,
    )


def _runner(
    tmp_path: Path,
    *,
    environment: dict[str, str] | None = None,
    api_key_file: Path | None = None,
) -> ClaudeCodeTargetRunner:
    executable = tmp_path / "fake-claude"
    bubblewrap = tmp_path / "bwrap"
    socat = tmp_path / "socat"
    library_path = tmp_path / "lib"
    library_path.mkdir(exist_ok=True)
    _write_executable(executable, _FAKE_CLAUDE)
    _write_executable(bubblewrap, _FAKE_BWRAP)
    _write_executable(
        socat,
        """#!/bin/sh
echo "socat synthetic"
""",
    )
    checked_in = load_runtime_pins()
    claude_pin = ClaudeCodePin(
        executable=_executable_pin(
            executable,
            package="synthetic-claude-code",
            version="9.9.9",
            version_stdout="9.9.9 (Synthetic Claude Code)",
            version_args=("--version",),
            help_flags=("--bare",),
        ),
        model_id="claude-sonnet-5",
        api_base_url="https://api.anthropic.com",
    )
    sandbox_pin = SandboxPin(
        bubblewrap=_executable_pin(
            bubblewrap,
            package="synthetic-bubblewrap",
            version="1.0",
            version_stdout="bubblewrap synthetic",
            version_args=("--version",),
        ),
        socat=_executable_pin(
            socat,
            package="synthetic-socat",
            version="1.0",
            version_stdout="socat synthetic",
            version_args=("-V",),
        ),
    )
    pins = RuntimePinSet(
        lock_version=checked_in.lock_version,
        codex=checked_in.codex,
        claude_code=claude_pin,
        sandbox=sandbox_pin,
        node=checked_in.node,
    )
    selected_environment = {
        "ANTHROPIC_API_KEY": "synthetic-api-key-placeholder",
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
    }
    if environment is not None:
        selected_environment = environment
    return ClaudeCodeTargetRunner(
        paths=ClaudeRuntimePaths(
            executable=executable,
            bubblewrap=bubblewrap,
            socat=socat,
            sandbox_library_path=library_path,
        ),
        pins=pins,
        environment=selected_environment,
        api_key_file=api_key_file,
    )


def _request(tmp_path: Path, *, prompt: str = "Perform the synthetic task.") -> TargetRunRequest:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    (workspace / "CLAUDE.md").write_text(
        "AMBIENT_SENTINEL_MUST_NOT_LOAD",
        encoding="utf-8",
    )
    condition = workspace / "condition.md"
    condition.write_text("BLINDED_CONDITION_SENTINEL", encoding="utf-8")
    return TargetRunRequest(
        run_id="run-000000000001",
        workspace_root=workspace,
        prompt=prompt,
        condition_file=condition,
        condition_digest=sha256_file(condition),
        allowed_bash_commands=("python3 -m unittest -v",),
        command_process_limit=256,
        max_seconds=5,
        max_turns=3,
        max_usd=0.25,
    )


def _result_event(events: tuple[JsonObject, ...]) -> JsonObject:
    return next(event for event in events if event.get("type") == "result")


def test_synthetic_runner_has_clean_state_tools_and_network(tmp_path: Path) -> None:
    request = _request(tmp_path, prompt="PRIVATE_PROMPT_SENTINEL")
    result = _runner(tmp_path).run(request)
    result_event = _result_event(result.events)
    argv = result_event["argv"]
    assert isinstance(argv, list)
    assert "PRIVATE_PROMPT_SENTINEL" not in argv
    assert "--bare" in argv
    assert "--no-session-persistence" in argv
    assert "--append-system-prompt-file" in argv
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--strict-mcp-config" in argv
    assert "--setting-sources" in argv
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "Glob" in argv
    assert "Grep" in argv
    assert any(isinstance(argument, str) and argument.startswith("Write(//") for argument in argv)
    assert "Bash(acl-test-full)" in argv
    assert "Bash(python3 -m unittest -v)" not in argv
    assert result_event["ambient_loaded"] is False
    assert result_event["session_persisted"] is False
    target_path = cast(str, result_event["path"])
    assert "/usr/bin" in target_path.split(os.pathsep)
    assert "/bin" in target_path.split(os.pathsep)
    assert "/opt/acl-runtime" in target_path.split(os.pathsep)
    assert "/mnt/c" not in target_path
    assert result_event["host_platform"] == "linux"
    settings = result_event["settings"]
    assert isinstance(settings, dict)
    managed_settings_path = cast(str, result_event["managed_settings_path"])
    assert managed_settings_path.startswith("/tmp/acl-claude-config-")
    managed_settings = result_event["managed_settings"]
    assert isinstance(managed_settings, dict)
    assert managed_settings["permissions"] == settings["permissions"]
    assert managed_settings["sandbox"] == settings["sandbox"]
    assert managed_settings["bwrapPath"] == "/opt/acl-runtime/bwrap"
    permissions = settings["permissions"]
    assert isinstance(permissions, dict)
    permission_allow = cast(list[object], permissions["allow"])
    assert "Glob" in permission_allow
    assert "Grep" in permission_allow
    assert any(isinstance(rule, str) and rule.startswith("Write(//") for rule in permission_allow)
    permission_deny = cast(list[object], permissions["deny"])
    assert any(
        isinstance(rule, str) and rule.startswith("Write(//") and rule.endswith("/.acl-runtime/**)")
        for rule in permission_deny
    )
    assert result_event["condition_sha256"] == request.condition_digest.removeprefix("sha256:")
    sandbox = settings["sandbox"]
    assert isinstance(sandbox, dict)
    assert sandbox["enabled"] is True
    assert sandbox["failIfUnavailable"] is True
    assert sandbox["allowUnsandboxedCommands"] is False
    assert sandbox["autoAllowBashIfSandboxed"] is False
    assert sandbox["excludedCommands"] == []
    network = sandbox["network"]
    assert isinstance(network, dict)
    assert network["deniedDomains"] == ["*"]
    filesystem = sandbox["filesystem"]
    assert isinstance(filesystem, dict)
    deny_read = cast(list[object], filesystem["denyRead"])
    assert "/" in deny_read
    assert str(request.workspace_root.resolve() / ".env") in deny_read
    assert str(request.workspace_root.resolve()) in cast(list[object], filesystem["allowRead"])
    credentials = sandbox["credentials"]
    assert isinstance(credentials, dict)
    assert {"name": "ANTHROPIC_API_KEY", "mode": "deny"} in cast(
        list[object], credentials["envVars"]
    )
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.config_destroyed is True
    assert not (request.workspace_root / ".claude").exists()


def test_bounded_alias_edits_runs_tests_strips_secret_and_applies_limits(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, prompt="BOUNDED_COMMAND_SMOKE")
    (request.workspace_root / "test_solution.py").write_text(
        """import os
import resource
import unittest

from solution import add


class SolutionTest(unittest.TestCase):
    def test_solution_and_boundary(self):
        self.assertEqual(add(2, 3), 5)
        self.assertIsNone(os.environ.get("ANTHROPIC_API_KEY"))
        self.assertEqual(os.environ.get("ACL_BOUNDED_TEST"), "1")
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_CPU)[0], 30)
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_AS)[0], 512 * 1024 * 1024)
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_FSIZE)[0], 16 * 1024 * 1024)
        self.assertGreaterEqual(resource.getrlimit(resource.RLIMIT_NPROC)[0], 256)
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_NPROC)[0], 1024)
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_NOFILE)[0], 64)
""",
        encoding="utf-8",
    )

    result = _runner(tmp_path).run(request)

    assert (
        (request.workspace_root / "solution.py")
        .read_text(encoding="utf-8")
        .endswith("return left + right\n")
    )
    assert len(result.command_audit) == 1
    audit = result.command_audit[0]
    assert audit.alias == "acl-test-full"
    assert audit.requested_timeout_ms == 5000
    assert audit.approved_command_digest.startswith("sha256:")
    assert result.command_manifest_digest.startswith("sha256:")
    trace = json.dumps(result.events)
    assert '"is_error": false' in trace, trace
    assert "Ran 1 test" in trace
    assert not (request.workspace_root / ".acl-runtime").exists()


def test_two_commands_use_semantic_aliases_without_exposing_implementation(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, prompt="TWO_COMMAND_SMOKE").model_copy(
        update={
            "allowed_bash_commands": (
                "python3 -m unittest -v",
                "python3 -m unittest -v test_solution.SolutionTest.test_solution",
            )
        }
    )

    result = _runner(tmp_path).run(request)
    result_event = _result_event(result.events)
    argv = cast(list[str], result_event["argv"])

    assert "Bash(acl-test-full)" in argv
    assert "Bash(acl-test-focused)" in argv
    assert result_event["prompt_has_full_alias"] is True
    assert result_event["prompt_has_focused_alias"] is True
    assert result_event["prompt_exposes_python_implementation"] is False
    settings_value = result_event["settings"]
    assert isinstance(settings_value, dict)
    sandbox_value = settings_value["sandbox"]
    assert isinstance(sandbox_value, dict)
    assert sandbox_value["allowUnsandboxedCommands"] is False
    assert cast(list[str], sandbox_value["excludedCommands"]) == []
    assert [entry.alias for entry in result.command_audit] == [
        "acl-test-focused",
        "acl-test-full",
    ]
    assert all(entry.accepted for entry in result.command_audit)


def test_unbounded_command_attempt_invalidates_run(tmp_path: Path) -> None:
    with pytest.raises(TargetExecutionError, match="policy evidence") as caught:
        _runner(tmp_path).run(_request(tmp_path, prompt="UNBOUNDED_COMMAND_MARKER"))

    error = caught.value
    assert error.failure_code == "bash_policy_evidence_missing"
    assert error.failure_subject_digest == (
        "sha256:dbfc5804c380dc96ce100c67f3d38bc50e0bc971839d354a241a4cc436c9fe92"
    )
    assert error.evidence is not None
    assert error.evidence.failure_code == error.failure_code
    assert error.evidence.failure_subject_digest == error.failure_subject_digest
    assert error.evidence.stdout
    assert error.evidence.events
    assert error.evidence.config_destroyed is True
    assert error.evidence.command_audit == ()
    assert "synthetic-api-key-placeholder" not in repr(error.evidence)
    assert not (tmp_path / "workspace" / ".acl-runtime").exists()


def test_oversized_command_timeout_invalidates_run(tmp_path: Path) -> None:
    with pytest.raises(TargetExecutionError, match="invalid command timeout"):
        _runner(tmp_path).run(_request(tmp_path, prompt="OVERSIZED_TIMEOUT_MARKER"))


def test_bash_policy_shell_allows_only_exact_alias(tmp_path: Path) -> None:
    policy_shell = tmp_path / "bounded-bash-policy-shell"
    audit_path = tmp_path / "bounded-bash-policy-audit.jsonl"
    wrapper = tmp_path / "acl-test-full"
    _write_executable(
        wrapper,
        """#!/usr/bin/python3
raise SystemExit(0)
""",
    )
    _write_bash_policy_shell(
        policy_shell,
        prepared_commands=(
            _PreparedCommand(
                alias="acl-test-full",
                argv=("python3", "-m", "unittest", "-v"),
                command_digest="sha256:" + "0" * 64,
                wrapper_path=wrapper,
            ),
        ),
        audit_path=audit_path,
    )

    def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(policy_shell), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    assert invoke("-c", "acl-test-full").returncode == 0
    assert invoke("-c", "--", "acl-test-full").returncode == 0
    assert invoke("-c", "python3 -m unittest -v").returncode == 126
    assert invoke("-c", "source /ignored && acl-test-full", "--").returncode == 0
    assert invoke("-c", "source /ignored && find / -type f", "--").returncode == 126
    sentinel = tmp_path / "must-not-run"
    assert invoke("-c", "acl-test-full", f"touch {sentinel}").returncode == 0
    assert not sentinel.exists()
    audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [entry["decision"] for entry in audit] == [
        "allow",
        "allow",
        "deny",
        "allow",
        "deny",
        "allow",
    ]
    assert all("arguments" in entry for entry in audit)


def test_proven_blocked_command_is_audited_without_invalidating_run(tmp_path: Path) -> None:
    result = _runner(tmp_path).run(_request(tmp_path, prompt="BLOCKED_COMMAND_MARKER"))

    assert result.command_audit == ()
    assert len(result.denied_command_audit) == 1
    denied = result.denied_command_audit[0]
    assert denied.reason == "out_of_manifest_bash_command"
    assert denied.blocked is True
    assert denied.requested_command_digest.startswith("sha256:")


def test_host_file_tool_attempt_invalidates_run(tmp_path: Path) -> None:
    with pytest.raises(TargetExecutionError, match="host-file access"):
        _runner(tmp_path).run(_request(tmp_path, prompt="HOST_FILE_MARKER"))


def test_ambient_configuration_read_attempt_invalidates_run(tmp_path: Path) -> None:
    with pytest.raises(TargetExecutionError, match="read a reserved runner path") as caught:
        _runner(tmp_path).run(_request(tmp_path, prompt="RESERVED_READ_MARKER"))

    assert caught.value.failure_code == "reserved_runner_path_read"
    assert caught.value.failure_subject_digest is not None
    assert caught.value.evidence is not None
    assert caught.value.evidence.failure_code == "reserved_runner_path_read"


def test_reserved_runtime_artifact_fails_closed_without_deletion(tmp_path: Path) -> None:
    request = _request(tmp_path)
    reserved = request.workspace_root / ".claude"
    reserved.mkdir()
    sentinel = reserved / "settings.json"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(TargetExecutionError, match="reserved runner artifacts"):
        _runner(tmp_path).run(request)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"


def test_shell_syntax_is_rejected_before_execution(tmp_path: Path) -> None:
    request = _request(tmp_path)

    with pytest.raises(ValueError, match="single exact argv"):
        request.model_copy(
            update={"allowed_bash_commands": ("python3 -m unittest -v; id",)}
        ).model_validate(
            {
                **request.model_dump(),
                "allowed_bash_commands": ("python3 -m unittest -v; id",),
            }
        )


def test_non_unittest_python_is_rejected_before_target_start(tmp_path: Path) -> None:
    request = _request(tmp_path).model_copy(update={"allowed_bash_commands": ("python3 -c pass",)})

    with pytest.raises(TargetExecutionError, match="only Python unittest"):
        _runner(tmp_path).run(request)


@settings(max_examples=20, deadline=None)
@given(secret_bytes=st.binary(min_size=1, max_size=32))
def test_api_key_never_appears_in_command_or_trace(secret_bytes: bytes) -> None:
    secret = f"generated-key-{secret_bytes.hex()}"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = _runner(
            root,
            environment={
                "ANTHROPIC_API_KEY": secret,
                "HOME": str(root / "home"),
                "PATH": os.environ.get("PATH", ""),
            },
        )

        result = runner.run(_request(root))

        assert secret not in result.model_dump_json()


@settings(max_examples=20, deadline=None)
@given(ambient=st.text(min_size=1, max_size=128))
def test_arbitrary_ambient_instructions_are_not_loaded(ambient: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        request = _request(root)
        (request.workspace_root / "CLAUDE.md").write_text(ambient, encoding="utf-8")

        result = _runner(root).run(request)

        assert _result_event(result.events)["ambient_loaded"] is False


def test_missing_key_fails_closed_and_cleans_temporary_config(tmp_path: Path) -> None:
    temporary_root = Path(tempfile.gettempdir())
    before = set(temporary_root.glob("acl-claude-config-*"))
    runner = _runner(
        tmp_path,
        environment={"HOME": str(tmp_path / "home"), "PATH": os.environ.get("PATH", "")},
    )

    with pytest.raises(TargetExecutionError, match="dedicated Anthropic Console API key"):
        runner.run(_request(tmp_path))

    assert set(temporary_root.glob("acl-claude-config-*")) == before


def test_alternate_provider_endpoint_fails_closed(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        environment={
            "ANTHROPIC_API_KEY": "synthetic-placeholder",
            "ANTHROPIC_BASE_URL": "https://proxy.invalid",
            "HOME": str(tmp_path / "home"),
            "PATH": os.environ.get("PATH", ""),
        },
    )

    with pytest.raises(TargetExecutionError, match="alternate Anthropic base"):
        runner.run(_request(tmp_path))


def test_external_private_key_file_is_supported_without_ambient_secret(tmp_path: Path) -> None:
    key_file = tmp_path / "external-console-key"
    key_file.write_text("synthetic-file-key-placeholder\n", encoding="utf-8")
    key_file.chmod(0o600)
    runner = _runner(
        tmp_path,
        environment={"HOME": str(tmp_path / "home"), "PATH": os.environ.get("PATH", "")},
        api_key_file=key_file,
    )

    result = runner.run(_request(tmp_path))

    assert result.exit_code == 0
    assert "synthetic-file-key-placeholder" not in result.model_dump_json()


def test_external_key_file_permissions_fail_closed(tmp_path: Path) -> None:
    key_file = tmp_path / "external-console-key"
    key_file.write_text("synthetic-file-key-placeholder", encoding="utf-8")
    key_file.chmod(0o644)
    runner = _runner(
        tmp_path,
        environment={"HOME": str(tmp_path / "home"), "PATH": os.environ.get("PATH", "")},
        api_key_file=key_file,
    )

    with pytest.raises(TargetExecutionError, match="permissions are too broad"):
        runner.run(_request(tmp_path))


def test_forbidden_tool_in_trace_invalidates_run(tmp_path: Path) -> None:
    before = set(Path(tempfile.gettempdir()).glob("acl-claude-config-*"))

    with pytest.raises(TargetExecutionError, match="forbidden tool use"):
        _runner(tmp_path).run(_request(tmp_path, prompt="FORBIDDEN_TOOL_MARKER"))

    assert set(Path(tempfile.gettempdir()).glob("acl-claude-config-*")) == before


def test_credential_in_process_output_invalidates_run(tmp_path: Path) -> None:
    with pytest.raises(TargetExecutionError, match="exposed the API credential"):
        _runner(tmp_path).run(_request(tmp_path, prompt="LEAK_KEY_MARKER"))


def test_timeout_terminates_process_and_tears_down(tmp_path: Path) -> None:
    request = _request(tmp_path, prompt="PROCESS_TIMEOUT_MARKER")
    request = request.model_copy(update={"max_seconds": 1})

    result = _runner(tmp_path).run(request)

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.config_destroyed is True


def test_condition_must_remain_inside_workspace_and_match_digest(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request.condition_file.write_text("changed", encoding="utf-8")

    with pytest.raises(TargetExecutionError, match="digest changed"):
        _runner(tmp_path).run(request)


def test_live_smoke_wrapper_returns_only_sanitized_receipt(tmp_path: Path) -> None:
    receipt = run_live_no_user_data_smoke(_runner(tmp_path))

    assert receipt.milestone == 4
    assert receipt.total_cost_usd == 0.01
    assert receipt.workspace_destroyed is True
    assert receipt.raw_trace_persisted is False
    assert receipt.user_data_used is False
    assert "Write" in receipt.tools
    serialized = receipt.model_dump_json()
    assert "synthetic-smoke-ok" not in serialized
    assert "synthetic-api-key-placeholder" not in serialized


def test_committed_live_smoke_receipt_is_minimized_and_digest_bound() -> None:
    repository = Path(__file__).parents[3]
    status = json.loads((repository / "conformance" / "milestone-4.json").read_text())
    receipt_path = repository / status["live_smoke_receipt"]
    receipt = LiveSmokeReceipt.model_validate_json(receipt_path.read_text(), strict=True)

    assert status["live_no_user_data_smoke"] == "passed"
    assert status["live_smoke_receipt_sha256"] == sha256_file(receipt_path)
    assert receipt.model_id == "claude-sonnet-5"
    assert receipt.total_cost_usd <= 0.25
    assert receipt.workspace_destroyed is True
    assert receipt.raw_trace_persisted is False
    assert receipt.user_data_used is False
    assert receipt.source_data_used is False
    assert receipt.held_out_data_used is False
