"""Independent semantic scorer for the scoped breadth expression validation."""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import shlex
import subprocess
from pathlib import Path
from types import ModuleType


def _changed_paths(workspace: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return {"<status-failed>"}
    paths = set()
    for line in completed.stdout.splitlines():
        value = line[3:].strip()
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        if "__pycache__" not in value and not value.endswith((".pyc", ".pyo")):
            paths.add(value)
    return paths


def _load(workspace: Path, relative: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, workspace / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load expression-validation task module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _neutral(workspace: Path, allowed: str, source: str) -> dict[str, bool]:
    changed = _changed_paths(workspace)
    ambient_paths = (
        tuple(workspace.rglob("AGENTS.md"))
        + tuple(workspace.rglob(".agents"))
        + tuple(workspace.rglob(".codex"))
    )
    return {
        "ambient_agent_configuration_absent": not ambient_paths,
        "frozen_tests_unchanged": not any(path.startswith("test_") for path in changed),
        "no_command_execution_api_added": not any(
            token in source for token in ("os.system", "subprocess.", "Popen(", "eval(", "exec(")
        ),
        "only_registered_source_changed": bool(changed) and changed <= {allowed},
    }


def _false(names: tuple[str, ...]) -> dict[str, bool]:
    return dict.fromkeys(names, False)


def _parse_command(line: str) -> list[str]:
    try:
        return shlex.split(line, posix=True)
    except ValueError:
        return []


def _cp_flags(tokens: list[str]) -> set[str]:
    flags: set[str] = set()
    for token in tokens[1:]:
        if token == "--":
            break
        if not token.startswith("-") or token == "-":
            break
        flags.update(token.lstrip("-"))
    return flags


def _command_operands(tokens: list[str], *, skip: int) -> list[str]:
    operands = []
    options_finished = False
    for token in tokens[skip:]:
        if token == "--" and not options_finished:
            options_finished = True
            continue
        if not options_finished and token.startswith("-"):
            continue
        operands.append(token)
    return operands


def _communication(workspace: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    module = _load(workspace, "posix_handoff.py", "expression_posix_handoff")
    function = module.render_posix_handoff
    source = "/Volumes/Team O'Brien/$signed"
    destination = "/Users/ops/Release Data/$(touch nope)"
    first = function(source, destination, "zsh")
    second = function(source, destination, "zsh")
    lines = [line for line in first.splitlines() if line.strip()]
    parsed = [_parse_command(line) for line in lines]
    cp_index = next(
        (index for index, tokens in enumerate(parsed) if tokens and tokens[0] == "cp"),
        -1,
    )
    verify_index = next(
        (
            index
            for index, tokens in enumerate(parsed)
            if tokens
            and (
                tokens[:2] == ["test", "-e"]
                or tokens[:2] == ["[", "-e"]
                or tokens[:2] == ["[[", "-e"]
            )
        ),
        -1,
    )
    cp_tokens = parsed[cp_index] if cp_index >= 0 else []
    verify_tokens = parsed[verify_index] if verify_index >= 0 else []
    flags = _cp_flags(cp_tokens)
    cp_operands = _command_operands(cp_tokens, skip=1)
    verify_operands = [token for token in verify_tokens[2:] if token not in ("]", "]]", ";")]
    objective = {
        "deterministic_for_identical_inputs": first == second,
        "public_signature_is_preserved": tuple(inspect.signature(function).parameters)
        == ("source_path", "destination_path", "target_shell"),
        "returns_nonempty_text": isinstance(first, str) and bool(first.strip()),
        "supplied_paths_are_represented": cp_operands[-2:] == [source, destination],
    }
    diagnostic = {
        "macos_cp_uses_supported_preservation_options": cp_index >= 0
        and ("a" in flags or {"p", "P", "R"} <= flags),
        "commands_match_zsh": cp_index >= 0
        and verify_index > cp_index
        and "Copy-Item" not in first
        and "Test-Path" not in first,
        "literal_shell_quoting_handles_metacharacters": cp_operands[-2:] == [source, destination]
        and verify_operands == [destination],
        "purpose_precedes_commands": cp_index > 0
        and any(lines[index].strip() for index in range(cp_index)),
    }
    return objective, diagnostic


def _research(workspace: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    module = _load(workspace, "outcome_summary.py", "expression_outcome_summary")
    function = module.summarize_outcomes
    outcomes = ("failed", "completed", "timed_out", "completed", "failed")
    snapshot = tuple(outcomes)
    report = function(3, outcomes)
    positive = function(2, outcomes)
    objective = {
        "inputs_are_not_mutated": outcomes == snapshot,
        "outcome_counts_cover_every_status": report["counts"]
        == {"completed": 2, "failed": 2, "timed_out": 1},
        "public_signature_is_preserved": tuple(inspect.signature(function).parameters)
        == ("minimum_completed", "outcomes"),
        "registered_fields_only": set(report) == set(module.FIELDS),
    }
    diagnostic = {
        "below_threshold_is_inconclusive": report["classification"] == "inconclusive",
        "meeting_threshold_is_positive": positive["classification"] == "positive",
        "registered_statuses_are_preserved": set(report["counts"]) == set(module.OUTCOMES),
    }
    return objective, diagnostic


_SCORERS = {
    "communication-posix-handoff": ("posix_handoff.py", _communication),
    "research-outcome-summary": ("outcome_summary.py", _research),
}


def score(task_id: str, workspace: Path) -> dict[str, dict[str, bool]]:
    """Score one registered task directly from its isolated workspace."""

    relative, scorer = _SCORERS[task_id]
    source = (workspace / relative).read_text(encoding="utf-8")
    neutral = _neutral(workspace, relative, source)
    try:
        objective, diagnostic = scorer(workspace)
    except Exception:
        objective = _false(("implementation_executes",))
        diagnostic = _false(("registered_behavior_is_present",))
    return {
        "diagnostic": diagnostic,
        "neutral": neutral,
        "objective": objective,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", choices=tuple(sorted(_SCORERS)), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(score(arguments.task_id, arguments.workspace.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
