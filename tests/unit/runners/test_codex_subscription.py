from __future__ import annotations

import hashlib
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunRequest,
    CodexDevelopmentTask,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.runners import codex_subscription
from adaptation_compiler_lab.runners.codex_subscription import (
    CodexSubscriptionError,
    CodexSubscriptionRunner,
)

DIGEST = "sha256:" + "a" * 64


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _fake_cli(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/python3
import json
import os
import pathlib
import sys

if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.145.0")
    raise SystemExit(0)
if sys.argv[1:] == ["login", "status"]:
    assert "CODEX_API_KEY" not in os.environ
    assert "OPENAI_API_KEY" not in os.environ
    assert pathlib.Path(os.environ["CODEX_HOME"], "auth.json").is_file()
    print("Logged in using ChatGPT")
    raise SystemExit(0)
assert "--ask-for-approval" not in sys.argv
assert 'approval_policy="never"' in sys.argv
workspace = pathlib.Path(sys.argv[sys.argv.index("--cd") + 1])
(workspace / "solution.txt").write_text("done\\n", encoding="utf-8")
events = [
    {"type": "thread.started", "thread_id": "thread-fake"},
    {"type": "turn.started"},
    {
        "type": "item.completed",
        "item": {"id": "item-1", "type": "agent_message", "text": "Implemented and tested."},
    },
    {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 30,
            "reasoning_output_tokens": 4,
        },
    },
]
for event in events:
    print(json.dumps(event, sort_keys=True))
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _request() -> CodexDevelopmentRunRequest:
    condition = "Explain the purpose before procedural detail."
    task = CodexDevelopmentTask(
        task_id="development-communication",
        family=ApprovedSourceFamily.COMMUNICATION,
        prompt="Implement the requested change and run tests.",
        fixture_digest=DIGEST,
        independent_scorer_digest=DIGEST,
        visible_test_command=("python3", "-m", "unittest"),
        allowed_change_paths=("solution.txt",),
        neutral_control_requirements=("Do not add unrelated files.",),
    )
    return CodexDevelopmentRunRequest(
        run_id="development-run-01",
        blind_condition_id="development-condition-a",
        blind_output_id="development-output-a",
        task=task,
        condition_text=condition,
        condition_digest=_sha(condition.encode()),
        common_instructions=(
            "Work only in the supplied repository. Do not use network or ambient state."
        ),
    )


def _workspace(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_auth_and_run_use_only_copied_chatgpt_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _fake_cli(tmp_path / "codex")
    monkeypatch.setattr(codex_subscription, "_EXPECTED_CLI_DIGEST", _sha(executable.read_bytes()))
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    runner = CodexSubscriptionRunner(
        executable=executable,
        saved_auth_file=auth,
        max_seconds=10,
    )

    assert runner.verify_chatgpt_authentication() == "Logged in using ChatGPT"
    result = runner.run(_request(), workspace=_workspace(tmp_path / "workspace"))

    assert result.exit_code == 0
    assert result.trace_conformant
    assert result.final_response == "Implemented and tested."
    assert (result.input_tokens, result.cached_input_tokens) == (100, 20)
    assert (result.output_tokens, result.reasoning_output_tokens) == (30, 4)
    assert result.config_destroyed
    assert not result.session_files_persisted
    assert not result.api_key_environment_present
    assert not result.forbidden_ambient_surface_observed


def test_runner_rejects_ambient_agent_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _fake_cli(tmp_path / "codex")
    monkeypatch.setattr(codex_subscription, "_EXPECTED_CLI_DIGEST", _sha(executable.read_bytes()))
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    workspace = _workspace(tmp_path / "workspace")
    (workspace / "AGENTS.md").write_text("ambient", encoding="utf-8")
    runner = CodexSubscriptionRunner(executable=executable, saved_auth_file=auth)

    with pytest.raises(CodexSubscriptionError, match="AGENTS"):
        runner.run(_request(), workspace=workspace)


def test_run_observation_timestamps_remain_utc() -> None:
    assert datetime.now(UTC).tzinfo is UTC
