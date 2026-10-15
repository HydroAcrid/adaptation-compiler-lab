from __future__ import annotations

import hashlib
import io
import json
import queue
import tarfile
from collections import deque
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from adaptation_compiler_lab.benchmark.repo_extension_screen import (
    ARMS,
    command_argument,
    parse_grade,
    run_tool_turn,
    scope_failures,
    selected_text,
    summarize,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from scripts.run_repo_extension_screen import copy_candidate_production, event_journal, extract


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


def test_candidate_tests_cannot_replace_authoritative_tests(tmp_path: Path) -> None:
    candidate, graded = tmp_path / "candidate", tmp_path / "graded"
    for root in (candidate, graded):
        (root / "tests").mkdir(parents=True)
        (root / "src").mkdir()
    (graded / "tests/check.py").write_text("assert real_behavior()\n")
    (candidate / "tests/check.py").write_text("assert True\n")
    (candidate / "tests/new_test.py").write_text("assert True\n")
    (candidate / "src/code.py").write_text("fixed = True\n")
    copy_candidate_production(
        candidate, graded, ["tests/check.py", "tests/new_test.py", "src/code.py"], []
    )
    assert (graded / "tests/check.py").read_text() == "assert real_behavior()\n"
    assert not (graded / "tests/new_test.py").exists()
    assert (graded / "src/code.py").read_text() == "fixed = True\n"


def test_readonly_node_workspace_has_a_mountpoint_before_binding(tmp_path: Path) -> None:
    fixtures, destination = tmp_path / "fixtures", tmp_path / "project"
    fixture = fixtures / "case"
    fixture.mkdir(parents=True)
    archive = fixture / "base.tar"
    with tarfile.open(archive, "w") as tar:
        payload = b"source = True\n"
        member = tarfile.TarInfo("code.py")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))
    case = {
        "id": "case",
        "kind": "node",
        "archive_sha256": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    extract(case, fixtures, destination, git_init=False)
    assert (destination / "node_modules").is_dir()
    assert not list((destination / "node_modules").iterdir())
    assert (destination / "code.py").read_bytes() == payload


def test_argument_transport_normalization_and_validation() -> None:
    assert command_argument('{"command":"printf valid"}') == "printf valid"
    invalid: Any
    for invalid in ({"cmd": "wrong"}, {"command": []}, {"command": " ", "timeout": 1}, "not JSON"):
        with pytest.raises(ValueError):
            command_argument(invalid)


def test_invalid_model_arguments_return_an_error_and_allow_a_retry(tmp_path: Path) -> None:
    invalid, valid = tool_request(), tool_request()
    invalid["params"]["arguments"] = {"cmd": "wrong"}
    valid["params"]["callId"] = "retry"
    valid["id"] = 102
    rpc = Rpc(
        [
            invalid,
            valid,
            {
                "method": "turn/completed",
                "params": {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}},
            },
        ]
    )
    shell = MagicMock()
    shell.run.return_value = {"returncode": 0, "output": "actual", "instrument_valid": True}
    seen: list[dict[str, Any]] = []
    result = run_tool_turn(
        rpc,
        MagicMock(),
        workspace=tmp_path,
        model="model",
        effort="medium",
        prompt="task",
        shell=shell,
        skills=[],
        on_event=seen.append,
    )
    assert result["status"] == "completed" and len(result["tool_calls"]) == 2
    assert result["tool_calls"][0]["validation_error"]
    assert not rpc.responses[0]["result"]["success"]
    assert rpc.responses[1]["result"]["success"]
    shell.run.assert_called_once_with("printf actual")
    assert seen[0] == invalid


def test_event_journal_is_encrypted_and_saved_before_dispatch(tmp_path: Path) -> None:
    # Synthetic test-only key, never an owner credential.
    raw = LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"k" * 32))
    save = event_journal(tmp_path, "attempt", raw)
    event = {
        "method": "item/tool/call",
        "params": {"arguments": {"private-marker": "invalid input"}},
    }
    save(event)
    text = (tmp_path / "event-journals/attempt.jsonl").read_text(encoding="utf-8")
    assert "private-marker" not in text and "invalid input" not in text
    receipt = json.loads(text)
    assert json.loads(raw.read(RawPayloadRef(**receipt["raw_ref"]))) == event
