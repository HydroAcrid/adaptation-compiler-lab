"""Independent semantic scorer for the Milestone 6A.4 replacement tasks."""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import subprocess
from collections.abc import Callable
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
        raise RuntimeError("unable to load remediation task module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _neutral(workspace: Path, allowed: str, source: str) -> dict[str, bool]:
    changed = _changed_paths(workspace)
    return {
        "ambient_agent_configuration_absent": not any(
            (workspace / name).exists() for name in ("AGENTS.md", ".codex", ".agents")
        ),
        "frozen_tests_unchanged": not any(path.startswith("test_") for path in changed),
        "no_command_execution_api_added": not any(
            token in source for token in ("os.system", "subprocess.", "Popen(", "eval(", "exec(")
        ),
        "only_registered_source_changed": bool(changed) and changed <= {allowed},
    }


def _false(names: tuple[str, ...]) -> dict[str, bool]:
    return dict.fromkeys(names, False)


def _communication(workspace: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    module = _load(workspace, "archive_guide.py", "remediation_archive")
    function = module.build_archive_guide
    source = "/Volumes/Team O'Brien/$live"
    destination = "/Users/ops/Release Data/$(touch nope)"
    first = function(source, destination, "zsh")
    second = function(source, destination, "zsh")
    quoted_source = "'/Volumes/Team O'\"'\"'Brien/$live'"
    quoted_destination = "'/Users/ops/Release Data/$(touch nope)'"
    objective = {
        "deterministic_for_identical_inputs": first == second,
        "public_signature_is_preserved": tuple(inspect.signature(function).parameters)
        == ("source_path", "destination_path", "target_shell"),
        "returns_nonempty_text": isinstance(first, str) and bool(first.strip()),
        "supplied_paths_are_represented": "Team O" in first and "Release Data" in first,
    }
    command_indexes = [index for token in ("cp -a", "test -e") if (index := first.find(token)) >= 0]
    first_command = min(command_indexes) if command_indexes else -1
    diagnostic = {
        "archive_copy_semantics_are_used": "cp -a" in first,
        "commands_match_zsh": "cp " in first
        and "test -e" in first
        and "Copy-Item" not in first
        and "Test-Path" not in first,
        "literal_shell_quoting_handles_metacharacters": quoted_source in first
        and quoted_destination in first,
        "purpose_precedes_commands": first_command > 0
        and first[:first_command].strip() != ""
        and "\n\n" in first[:first_command],
    }
    return objective, diagnostic


def _debugging(workspace: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    module = _load(workspace, "ledger_status.py", "remediation_status")
    function = module.derive_status
    events = (
        {"at": "2026-07-01T12:00:00Z", "status": "completed"},
        {"at": "2026-07-01T12:05:00Z", "status": "failed"},
        {"at": "2026-07-01T12:03:00Z", "status": "running"},
    )
    snapshot = json.loads(json.dumps(events))
    result = function(events, "ready")
    objective = {
        "event_input_is_not_mutated": list(events) == snapshot,
        "no_event_uses_note_fallback": function((), "ready")
        == {"classification": "ready", "source": "status_note"},
        "public_signature_is_preserved": tuple(inspect.signature(function).parameters)
        == ("events", "note_status"),
        "returns_structured_status": isinstance(result, dict)
        and set(result) >= {"classification", "source"},
    }
    diagnostic = {
        "latest_event_is_selected_by_timestamp": result["classification"] == "blocked",
        "live_events_outrank_stale_note": result["source"] == "event_ledger",
        "public_contract_values_are_used": result["classification"]
        == module.EVENT_CLASSIFICATIONS["failed"]
        and result["source"] == module.LIVE_SOURCE,
        "shuffled_events_produce_same_result": function(tuple(reversed(events)), "ready") == result,
    }
    return objective, diagnostic


def _publish(workspace: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    module = _load(workspace, "publish_actions.py", "remediation_publish")
    function = module.plan_publish
    unauthorized = function(True, True, False)
    authorized = function(True, True, True)
    public_tokens = {
        module.CREATE,
        module.NO_CHANGE,
        module.REPORT_RISK,
        module.REFUSE,
        module.CREATE_BACKUP,
        module.REPLACE,
        module.VERIFY_BACKUP,
    }
    objective = {
        "matching_destination_is_unchanged": function(True, False, False) == (module.NO_CHANGE,),
        "missing_destination_is_created": function(False, True, False) == (module.CREATE,),
        "public_action_tokens_are_used": set(unauthorized + authorized) <= public_tokens,
        "public_signature_is_preserved": tuple(inspect.signature(function).parameters)
        == ("destination_exists", "contents_differ", "replace_authorized"),
    }
    diagnostic = {
        "authorized_replacement_is_recoverable": authorized
        == (
            module.REPORT_RISK,
            module.CREATE_BACKUP,
            module.REPLACE,
            module.VERIFY_BACKUP,
        ),
        "different_content_without_authorization_is_refused": unauthorized
        == (module.REPORT_RISK, module.REFUSE),
        "risk_is_reported_before_mutation": authorized.index(module.REPORT_RISK)
        < authorized.index(module.REPLACE),
    }
    return objective, diagnostic


def _sync(workspace: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    module = _load(workspace, "sync_actions.py", "remediation_sync")
    function = module.plan_sync
    root = workspace / "layout"
    source = root / "source"
    destination = root / "destination"
    objective = {
        "matching_content_is_a_noop": function(str(source), str(destination), True, False, False)
        == (module.NO_CHANGE,),
        "missing_destination_is_copied": function(str(source), str(destination), False, True, False)
        == (module.CREATE,),
        "public_signature_is_preserved": tuple(inspect.signature(function).parameters)
        == (
            "source",
            "destination",
            "destination_exists",
            "contents_differ",
            "replace_authorized",
        ),
    }
    overlap = []
    for left, right in (
        (source, source),
        (source, source / "nested"),
        (source / "nested", source),
    ):
        try:
            function(str(left), str(right), True, True, True)
        except Exception as error:
            overlap.append(type(error).__name__ == "UnsafeLayoutError")
        else:
            overlap.append(False)
    diagnostic = {
        "authorized_difference_has_recovery_plan": function(
            str(source), str(destination), True, True, True
        )
        == (
            module.REPORT_RISK,
            module.CREATE_BACKUP,
            module.SYNC,
            module.VERIFY,
            module.RESTORE_HINT,
        ),
        "identical_and_nested_layouts_are_rejected": all(overlap),
        "unauthorized_difference_is_refused": function(
            str(source), str(destination), True, True, False
        )
        == (module.REPORT_RISK, module.REFUSE),
    }
    return objective, diagnostic


def _research(workspace: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    module = _load(workspace, "registered_report.py", "remediation_report")
    function = module.build_registered_report
    protocol = {"minimum_valid_rate": 0.8, "success_threshold": 0.75}
    ledger = (
        {"status": "completed", "score": 0.9},
        {"status": "completed", "score": 0.8},
        {"status": "failed"},
        {"status": "timeout"},
    )
    protocol_snapshot = dict(protocol)
    ledger_snapshot = json.loads(json.dumps(ledger))
    report = function(protocol, ledger)
    objective = {
        "inputs_are_not_mutated": protocol == protocol_snapshot and list(ledger) == ledger_snapshot,
        "outcome_counts_cover_every_trial": report["outcome_counts"]
        == {"completed": 2, "failed": 1, "timeout": 1},
        "public_signature_is_preserved": tuple(inspect.signature(function).parameters)
        == ("protocol", "ledger"),
        "returns_structured_report": isinstance(report, dict),
    }
    diagnostic = {
        "failed_and_timeout_remain_distinct": set(report["outcome_counts"])
        == set(module.OUTCOME_STATUSES),
        "frozen_validity_threshold_is_applied": report["valid_rate"] == 0.5,
        "insufficient_run_rate_is_inconclusive": report["classification"] == "inconclusive",
        "registered_fields_only": set(report) == set(module.REPORT_FIELDS),
    }
    return objective, diagnostic


_SCORERS: dict[
    str,
    tuple[str, Callable[[Path], tuple[dict[str, bool], dict[str, bool]]]],
] = {
    "communication-zsh-archive": ("archive_guide.py", _communication),
    "debugging-ledger-status": ("ledger_status.py", _debugging),
    "environment-publish-actions": ("publish_actions.py", _publish),
    "environment-sync-actions": ("sync_actions.py", _sync),
    "research-registered-report": ("registered_report.py", _research),
}


def score(task_id: str, workspace: Path) -> dict[str, dict[str, bool]]:
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
