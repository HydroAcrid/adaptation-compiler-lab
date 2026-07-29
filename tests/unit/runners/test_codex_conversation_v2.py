from __future__ import annotations

import hashlib
import stat
import subprocess
from pathlib import Path

import pytest

from adaptation_compiler_lab.runners import codex_subscription
from adaptation_compiler_lab.runners.codex_conversation import (
    CodexConversationTurnRequest,
)
from adaptation_compiler_lab.runners.codex_conversation_v2 import (
    CodexConversationRunnerV2,
)
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract


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
    print("Logged in using ChatGPT")
    raise SystemExit(0)
if sys.argv[1] == "app-server":
    raise SystemExit(0)

home = pathlib.Path(os.environ["CODEX_HOME"])
prompt = sys.stdin.read()
counter_path = home / "counter"
counter = int(counter_path.read_text()) + 1 if counter_path.exists() else 1
counter_path.write_text(str(counter))
(home / "sessions" / "thread-fake").mkdir(parents=True, exist_ok=True)
if sys.argv[1:3] == ["exec", "resume"]:
    assert 'sandbox_mode="workspace-write"' in sys.argv
    assert "thread-fake" in sys.argv
else:
    assert sys.argv[1] == "exec"
    assert sys.argv[sys.argv.index("--sandbox") + 1] == "workspace-write"

solution = pathlib.Path.cwd() / f"solution-{counter}.txt"
solution.write_text(f"{counter}:{len(prompt)}\\n")
events = [
    {"type": "thread.started", "thread_id": "thread-fake"},
    {"type": "turn.started"},
    {
        "type": "item.completed",
        "item": {"id": f"item-{counter}", "type": "agent_message", "text": "Done."},
    },
    {
        "type": "turn.completed",
        "usage": {
            "input_tokens": counter * 10,
            "cached_input_tokens": counter,
            "output_tokens": 5,
            "reasoning_output_tokens": 1,
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


def test_v2_reasserts_workspace_write_on_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _fake_cli(tmp_path / "codex")
    digest = _sha(executable.read_bytes())
    monkeypatch.setattr(codex_subscription, "_EXPECTED_CLI_DIGEST", digest)
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for turn in (1, 2):
        (workspace / f"solution-{turn}.txt").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    runner = CodexConversationRunnerV2(
        executable=executable,
        saved_auth_file=auth,
        bubblewrap=None,
        contract=CodexExecutionContract(
            cli_version="codex-cli 0.145.0",
            cli_digest=digest,
            model="gpt-5.6-luna",
            reasoning_effort="medium",
            service_mode="standard",
            max_seconds=10,
        ),
    )

    result = runner.run_smoke(
        episode_id="v2-resume-write-smoke",
        common_instructions="Work only in this repository and do not use network.",
        turns=(
            CodexConversationTurnRequest(
                turn=1,
                task_id="task-1",
                prompt="Complete task 1.",
                allowed_change_paths=("solution-1.txt",),
                adaptation_stage=1,
            ),
            CodexConversationTurnRequest(
                turn=2,
                task_id="task-2",
                prompt="Complete task 2.",
                allowed_change_paths=("solution-2.txt",),
                adaptation_stage=1,
            ),
        ),
        workspace=workspace,
    )

    assert len(result.turns) == 2
    assert {item.thread_id for item in result.turns} == {"thread-fake"}
    assert all(item.trace_conformant for item in result.turns)
    assert (workspace / "solution-1.txt").read_text() != ""
    assert (workspace / "solution-2.txt").read_text() != ""
    assert result.config_destroyed
    assert result.session_destroyed
