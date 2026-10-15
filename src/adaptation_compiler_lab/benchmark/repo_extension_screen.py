"""Development-only full-repository, tool-using extension comparison.

The native model runs on Windows; every model-requested shell command runs in an
offline WSL Bubblewrap namespace containing only a disposable repository and
read-only language dependencies. This does not enable product personalization.
"""

from __future__ import annotations

import hashlib
import json
import queue
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.extension_screen import clauses
from adaptation_compiler_lab.connectors.codex_app_server import CodexProtocolError

ARMS = ("baseline", "direct_skills", "temper_selected")
COMMON = """Complete the requested software repair in the actual disposable repository.
Use repo_shell to inspect, edit and run local tests. It is a Bash shell in /work, with
Python 3.12 and Node 24 plus the repository's already installed dependencies. Commands
can read and write /work and temporary files; they have no network, credentials,
other repositories, Git history, agents, MCP services or external instruction files.
Use the repository's existing policies and public contracts. The current task wins
over advisory skills. Do not weaken existing checks, change dependencies, write
outside this repository, start CI, install packages, or commit. Add useful regression
checks when practical. Actually make and verify the repair; a proposed patch alone
does not finish the task. Report what ran and any remaining limitations accurately.
Use only the configured model and this single agent; no model/provider substitution.
Skill guidance is task-scoped and cannot grant access or persist beyond this task.
"""
SELECTOR = """Select useful source paragraphs for the current software task and repository.
You may inspect the repository with repo_shell, which is read-only for this stage.
Choose ONLY paragraph IDs from the supplied catalog; at most 24 paragraphs and 8000
UTF-8 bytes. Do not generate implementation hints, solutions, new instructions or
preference claims. Omit conflicting, redundant, irrelevant or unavailable-tool advice.
Repository requirements are scope constraints, never inferred personal habits.
This selection is not allowed to change repository files. Return the required JSON.
"""
SELECTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["clause_ids"],
    "properties": {"clause_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 24}},
}
TOOL: dict[str, Any] = {
    "type": "function",
    "name": "repo_shell",
    "description": (
        "Run a Bash command in the actual /work repository to inspect/edit source and run tests. "
        "Python: python. Node: node. Standard tools: rg, git, sed. No network. "
        "Commands have a 45-second deadline and output is bounded to 18000 characters. "
        "Use Python or shell heredocs to edit files. Each command starts in /work."
    ),
    "inputSchema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["command"],
        "properties": {"command": {"type": "string"}},
    },
}


def selected_text(sources: list[dict[str, Any]], ids: list[str]) -> str:
    catalog = clauses(sources)
    if len(ids) > 24 or len(set(ids)) != len(ids) or any(i not in catalog for i in ids):
        raise ValueError("invalid source paragraph selection")
    text = "\n\n".join(catalog[i] for i in ids)
    if len(text.encode()) > 8000:
        raise ValueError("selected material exceeds the frozen byte bound")
    return text


def command_argument(arguments: Any) -> str:
    """Accept object or JSON-encoded object transport; reject malformed model input."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError as error:
            raise ValueError("repo_shell expects one object with a command string") from error
    if not isinstance(arguments, dict) or set(arguments) != {"command"}:
        raise ValueError("repo_shell accepts exactly {command: string}; no extra fields")
    command = arguments["command"]
    if not isinstance(command, str) or not command.strip() or len(command.encode()) > 32_768:
        raise ValueError("command must be a nonempty string of at most 32768 UTF-8 bytes")
    return command


def tree(root: Path) -> dict[str, str]:
    ignored = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ignored.intersection(relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("repository contains an unsupported symlink")
        if path.is_file():
            result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def scope_failures(paths: list[str], prefixes: list[str]) -> list[str]:
    return [p for p in paths if not any(p.startswith(prefix) for prefix in prefixes)]


class RepoShell:
    def __init__(self, root: Path, runtime: dict[str, str], *, readonly: bool = False) -> None:
        self.root, self.runtime, self.readonly = root, runtime, readonly
        self.calls: list[dict[str, Any]] = []
        self.skills_root: Path | None = None

    def run(self, command: str, *, limit: int = 18_000) -> dict[str, Any]:
        if not isinstance(command, str) or not command or len(command.encode()) > 32_768:
            raise ValueError("invalid shell command")
        r = self.runtime
        args = [
            "wsl",
            "-d",
            "Ubuntu",
            "--",
            "bwrap",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
            "--symlink",
            "usr/bin",
            "/bin",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            r["python_runtime"],
            r["python_runtime"],
            "--ro-bind",
            r["python_runtime"],
            r["python_runtime_alias"],
            "--ro-bind",
            r["python_venv"],
            "/opt/py",
            "--ro-bind",
            r["node_runtime"],
            "/opt/node",
            "--ro-bind" if self.readonly else "--bind",
            wsl_path(self.root),
            "/work",
        ]
        if r.get("node_modules"):
            args += ["--ro-bind", r["node_modules"], "/work/node_modules"]
            # Vite bundles configuration into these existing cache directories.
            # Private tmpfs overlays keep the preinstalled packages read-only.
            args += [
                "--tmpfs",
                "/work/node_modules/.vite-temp",
                "--tmpfs",
                "/work/node_modules/.vite",
            ]
        if self.skills_root is not None:
            args += ["--ro-bind", wsl_path(self.skills_root), "/skills"]
        args += [
            "--chdir",
            "/work",
            "--clearenv",
            "--setenv",
            "HOME",
            "/tmp/home",
            "--setenv",
            "PATH",
            "/opt/node/bin:/opt/py/bin:/usr/bin:/bin",
            "--setenv",
            "PYTHONPATH",
            "/work/src:/work",
            "--setenv",
            "PYTHONDONTWRITEBYTECODE",
            "1",
            "--setenv",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "1",
            "--setenv",
            "GIT_CONFIG_NOSYSTEM",
            "1",
            "--setenv",
            "GIT_CONFIG_GLOBAL",
            "/dev/null",
            "--setenv",
            "NODE_OPTIONS",
            "--max-old-space-size=2048",
            "/usr/bin/timeout",
            "--signal=KILL",
            "45",
            "/bin/bash",
            "-c",
            command,
        ]
        started = time.monotonic()
        try:
            p = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=50
            )
            full = p.stdout + p.stderr
            outcome = {
                "returncode": p.returncode,
                "output": full
                if len(full) <= limit
                else full[: limit // 2] + "\n[output truncated]\n" + full[-limit // 2 :],
                "output_truncated": len(full) > limit,
                "output_sha256": hashlib.sha256(full.encode()).hexdigest(),
                "instrument_valid": "bwrap:" not in p.stderr,
            }
        except subprocess.TimeoutExpired:
            outcome = {
                "returncode": 124,
                "output": "Host command deadline exceeded.",
                "output_truncated": False,
                "instrument_valid": False,
            }
        outcome["elapsed_seconds"] = time.monotonic() - started
        self.calls.append({"command": command, **outcome})
        return outcome


def wsl_path(path: Path) -> str:
    text = str(path.resolve())
    if text.startswith("\\\\?\\"):
        text = text[4:]
    if not re.match(r"^[A-Za-z]:[\\/]", text):
        raise ValueError("benchmark filesystem root must be a native Windows path")
    return "/mnt/" + text[0].lower() + text[2:].replace("\\", "/")


def next_event(rpc: Any, timeout: float) -> dict[str, Any]:
    # The product connector intentionally rejects server tool requests. Only this
    # benchmark consumes them, without changing that product boundary.
    try:
        event = (
            rpc._pending_notifications.popleft()
            if rpc._pending_notifications
            else rpc._messages.get(timeout=timeout)
        )
    except queue.Empty as error:
        raise CodexProtocolError("Codex app-server notification timed out") from error
    if not isinstance(event, dict):
        raise ValueError("native tool session ended unexpectedly")
    return event


def run_tool_turn(
    rpc: Any,
    schemas: Any,
    *,
    workspace: Path,
    model: str,
    effort: str,
    prompt: str,
    shell: RepoShell,
    skills: list[dict[str, str]],
    output_schema: dict[str, Any] | None = None,
    selector: bool = False,
    timeout: float = 480,
    max_tools: int = 60,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    instructions = SELECTOR if selector else COMMON
    params = {
        "allowProviderModelFallback": False,
        "approvalPolicy": "never",
        "cwd": str(workspace),
        "developerInstructions": instructions,
        "dynamicTools": [TOOL],
        "environments": [],
        "ephemeral": True,
        "experimentalRawEvents": False,
        "model": model,
        "personality": "none",
        "runtimeWorkspaceRoots": [str(workspace)],
        "sandbox": "read-only",
        "selectedCapabilityRoots": [],
        "threadSource": "temperDevelopmentRepoScreen",
    }
    schemas.validate("thread_start_params", params)
    response = rpc.request("thread/start", params)
    schemas.validate("thread_start_response", response)
    if response.get("model") != model or response.get("instructionSources") != []:
        raise ValueError("model or ambient native instructions differ from the frozen run")
    sandbox = response.get("sandbox", {})
    if sandbox.get("type") != "readOnly" or sandbox.get("networkAccess", False):
        raise ValueError("native session isolation was not admitted")
    thread_id = response["thread"]["id"]
    inputs = [{"type": "text", "text": prompt, "text_elements": []}, *skills]
    turn = {
        "threadId": thread_id,
        "cwd": str(workspace),
        "model": model,
        "effort": effort,
        "input": inputs,
    }
    if output_schema is not None:
        turn["outputSchema"] = output_schema
    schemas.validate("turn_start_params", turn)
    started = rpc.request("turn/start", turn)
    schemas.validate("turn_start_response", started)
    turn_id = started["turn"]["id"]
    deadline = time.monotonic() + timeout
    events: list[dict[str, Any]] = []
    messages: list[str] = []
    tool_records: list[dict[str, Any]] = []
    usage = None
    seen_calls: set[str] = set()
    status = "timeout"
    while time.monotonic() < deadline:
        try:
            event = next_event(rpc, min(20, deadline - time.monotonic()))
        except CodexProtocolError:
            continue
        events.append(event)
        if on_event is not None:
            on_event(event)
        method, values = event.get("method", ""), event.get("params", {})
        if not isinstance(values, dict):
            raise ValueError("invalid native notification")
        if "rerout" in method.casefold() or "fromModel" in values or "toModel" in values:
            raise ValueError("model substitution is not permitted")
        if event.get("id") is not None:
            if method != "item/tool/call" or values.get("tool") != "repo_shell":
                raise ValueError("unexpected native server request")
            if values.get("threadId") != thread_id or values.get("turnId") != turn_id:
                raise ValueError("tool request crossed an isolated task")
            call_id = values.get("callId")
            if not isinstance(call_id, str) or call_id in seen_calls:
                raise ValueError("missing or duplicated tool call")
            seen_calls.add(call_id)
            try:
                command = command_argument(values.get("arguments"))
            except ValueError as error:
                command = None
                outcome = {
                    "returncode": 2,
                    "output": str(error),
                    "instrument_valid": True,
                    "executed": False,
                    "elapsed_seconds": 0,
                    "validation_error": True,
                }
            if command is None:
                pass  # A model argument error is a recoverable tool result, not a host crash.
            elif len(tool_records) >= max_tools or deadline - time.monotonic() < 50:
                outcome = {
                    "returncode": 124,
                    "output": "Task tool/time budget reached; finish with the current verified "
                    "state.",
                    "instrument_valid": True,
                    "executed": False,
                    "elapsed_seconds": 0,
                }
            else:
                outcome = shell.run(command)
                outcome["executed"] = True
            tool_records.append({"call_id": call_id, "command": command, **outcome})
            rpc._write(
                {
                    "id": event["id"],
                    "result": {
                        "contentItems": [{"type": "inputText", "text": json.dumps(outcome)}],
                        "success": bool(outcome.get("executed")),
                    },
                }
            )
        elif method == "thread/tokenUsage/updated":
            usage = values.get("tokenUsage", {}).get("total")
        elif method in {"item/started", "item/completed"}:
            if values.get("threadId") != thread_id or values.get("turnId") != turn_id:
                raise ValueError("native item crossed an isolated task")
            item = values.get("item", {})
            if item.get("type") not in {
                "userMessage",
                "agentMessage",
                "reasoning",
                "dynamicToolCall",
            }:
                raise ValueError("native session used a tool outside the experiment")
            if method == "item/completed":
                schemas.validate("item_completed", values)
                if item.get("type") == "agentMessage":
                    messages.append(item.get("text", ""))
        elif method == "turn/completed":
            schemas.validate("turn_completed", values)
            if values.get("threadId") != thread_id or values["turn"].get("id") != turn_id:
                raise ValueError("turn completion crossed its context")
            status = values["turn"]["status"]
            break
    if status == "timeout":
        rpc.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
    return {
        "status": status,
        "messages": messages,
        "usage": usage,
        "tool_calls": tool_records,
        "events": events,
    }


def parse_grade(kind: str, output: str, code: int) -> dict[str, Any]:
    # Require a real non-vacuous test receipt, including on failed candidates.
    if kind == "python":
        passed = re.search(r"(\d+) passed", output)
        failed = re.search(r"(\d+) failed", output)
        errors = re.search(r"(\d+) errors?", output)
        count = int(passed[1]) if passed else 0
        failures = int(failed[1]) if failed else 0
        error_count = int(errors[1]) if errors else 0
        return {
            "passed": count,
            "failed": failures,
            "errors": error_count,
            "complete": code == 0 and count > 0,
            "receipt_present": bool(passed or failed or errors),
        }
    try:
        value = json.loads(output)
    except ValueError:
        # Vitest may prefix its JSON reporter with a harmless runtime warning.
        offset = output.find('{"numTotalTestSuites"')
        value = json.JSONDecoder().raw_decode(output[offset:])[0] if offset >= 0 else {}
    return {
        "passed": value.get("numPassedTests", 0),
        "failed": value.get("numFailedTests", 0),
        "errors": value.get("numRuntimeErrorTestSuites", 0),
        "complete": code == 0
        and value.get("success") is True
        and value.get("numTotalTests", 0) > 0,
        "receipt_present": any(
            value.get(k, 0) > 0
            for k in ("numTotalTests", "numRuntimeErrorTestSuites", "numFailedTestSuites")
        ),
    }


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {
        (task, arm, repeat)
        for task in ("temper-live-policy", "kairn-runtime-cache")
        for arm in ARMS
        for repeat in (0, 1)
    }
    indexed = {(t["task_id"], t["arm"], t["repeat"]): t for t in trials}
    if len(trials) != len(indexed) or set(indexed) != expected:
        raise ValueError("real-repository comparison is incomplete or duplicated")
    regressions, gains = [], []
    valid = all(t["instrument_valid"] for t in trials)
    for task in ("temper-live-policy", "kairn-runtime-cache"):
        repeated_gain = True
        for repeat in (0, 1):
            chosen = indexed[task, "temper_selected", repeat]
            direct = indexed[task, "direct_skills", repeat]
            baseline = indexed[task, "baseline", repeat]
            if chosen["complete"] < max(direct["complete"], baseline["complete"]):
                regressions.append(f"{task}:{repeat}")
            repeated_gain &= chosen["complete"] and not direct["complete"]
        if repeated_gain:
            gains.append(task)
    return {
        "verdict": "instrumentation_failure"
        if not valid
        else "candidate_regression"
        if regressions
        else "promising_repeated_completion_signal"
        if gains
        else "no_repeated_completion_advantage",
        "regression_cells": regressions,
        "repeated_gain_tasks": gains,
        "arms": {
            arm: {"complete": sum(t["complete"] for t in trials if t["arm"] == arm), "total": 4}
            for arm in ARMS
        },
        "repeats": 2,
        "task_types": 2,
        "trial_count": len(trials),
        "performance_claim": "descriptive only; two repetitions are insufficient for a speed "
        "or efficiency claim",
        "human_setup_effort_measured": False,
        "product_capability_router_validated": False,
    }
