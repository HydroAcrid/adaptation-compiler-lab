from __future__ import annotations

import json
import queue
from collections import deque
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from adaptation_compiler_lab.benchmark.repo_extension_screen import (
    ARMS,
    parse_grade,
    run_tool_turn,
    scope_failures,
    selected_text,
    summarize,
)


def test_selection_is_exact_attributed_source_with_a_byte_bound() -> None:
    sources = [{"id": "source", "text": "First paragraph.\n\nSecond paragraph."}]
    assert selected_text(sources, ["source:001"]) == "Second paragraph."
    for ids in (["invented:000"], ["source:000", "source:000"]):
        with pytest.raises(ValueError):
            selected_text(sources, ids)
    with pytest.raises(ValueError, match="byte bound"):
        selected_text([{"id": "source", "text": "x" * 8001}], ["source:000"])


def test_grade_requires_real_checks_and_keeps_failures() -> None:
    assert not parse_grade("python", "no tests ran", 0)["complete"]
    result = parse_grade("python", "3 failed, 52 passed in 2.0s", 1)
    assert result["failed"] == 3 and result["passed"] == 52 and not result["complete"]
    report = {"numTotalTestSuites": 1, "numTotalTests": 3, "numPassedTests": 3, "success": True}
    assert parse_grade("node", "warning\n" + json.dumps(report) + "\nwarning", 0)["complete"]
    assert not parse_grade("node", "{}", 0)["complete"]


def trials() -> list[dict[str, Any]]:
    return [
        {"task_id": task, "arm": arm, "repeat": repeat, "complete": True, "instrument_valid": True}
        for task in ("temper-live-policy", "kairn-runtime-cache")
        for arm in ARMS
        for repeat in (0, 1)
    ]


def test_comparison_rejects_incomplete_data_and_does_not_call_a_tie_a_win() -> None:
    assert summarize(trials())["verdict"] == "no_repeated_completion_advantage"
    with pytest.raises(ValueError, match="incomplete"):
        summarize(trials()[:-1])


def test_gain_must_repeat_and_regression_blocks() -> None:
    cells = trials()
    direct = [
        t for t in cells if t["task_id"] == "temper-live-policy" and t["arm"] == "direct_skills"
    ]
    direct[0]["complete"] = False
    assert summarize(cells)["verdict"] == "no_repeated_completion_advantage"
    direct[1]["complete"] = False
    assert summarize(cells)["verdict"] == "promising_repeated_completion_signal"
    next(
        t for t in cells if t["task_id"] == "kairn-runtime-cache" and t["arm"] == "temper_selected"
    )["complete"] = False
    assert summarize(cells)["verdict"] == "candidate_regression"


class Rpc:
    def __init__(self, requests: list[dict[str, Any]]) -> None:
        self._pending_notifications = deque(requests)
        self._messages: queue.Queue[Any] = queue.Queue()
        self.responses: list[dict[str, Any]] = []

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "thread/start":
            return {
                "model": "model",
                "instructionSources": [],
                "sandbox": {"type": "readOnly"},
                "thread": {"id": "thread"},
            }
        if method == "turn/start":
            return {"turn": {"id": "turn"}}
        raise AssertionError(method)

    def _write(self, payload: dict[str, Any]) -> None:
        self.responses.append(payload)


def tool_request(tool: str = "repo_shell") -> dict[str, Any]:
    return {
        "id": 101,
        "method": "item/tool/call",
        "params": {
            "tool": tool,
            "threadId": "thread",
            "turnId": "turn",
            "callId": "call",
            "arguments": {"command": "printf actual"},
        },
    }


def test_only_declared_tool_runs_and_its_result_is_consumed(tmp_path: Path) -> None:
    rpc = Rpc(
        [
            tool_request(),
            {
                "method": "turn/completed",
                "params": {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}},
            },
        ]
    )
    shell = MagicMock()
    shell.run.return_value = {"returncode": 0, "output": "actual", "instrument_valid": True}
    result = run_tool_turn(
        rpc,
        MagicMock(),
        workspace=tmp_path,
        model="model",
        effort="medium",
        prompt="task",
        shell=shell,
        skills=[],
    )
    shell.run.assert_called_once_with("printf actual")
    assert result["status"] == "completed" and len(result["tool_calls"]) == 1
    assert "actual" in rpc.responses[0]["result"]["contentItems"][0]["text"]


def test_unknown_and_duplicate_tool_requests_are_rejected(tmp_path: Path) -> None:
    for requests, expected in (
        ([tool_request("external_tool")], "unexpected"),
        ([tool_request(), tool_request()], "duplicated"),
    ):
        shell = MagicMock()
        shell.run.return_value = {"returncode": 0, "output": "actual", "instrument_valid": True}
        with pytest.raises(ValueError, match=expected):
            run_tool_turn(
                Rpc(requests),
                MagicMock(),
                workspace=tmp_path,
                model="model",
                effort="medium",
                prompt="task",
                shell=shell,
                skills=[],
            )


def test_source_scope_excludes_configuration_and_history() -> None:
    assert scope_failures(
        ["src/code.py", "tests/check.py", "config.toml", ".git/HEAD"], ["src/", "tests/"]
    ) == ["config.toml", ".git/HEAD"]
