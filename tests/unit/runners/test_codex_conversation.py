from __future__ import annotations

import hashlib
import stat
import subprocess
from pathlib import Path

import pytest

from adaptation_compiler_lab.runners import codex_subscription
from adaptation_compiler_lab.runners.codex_conversation import (
    CodexConversationRunner,
    CodexConversationTurnRequest,
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
assert (home / "auth.json").is_file()
assert "CODEX_API_KEY" not in os.environ
assert "OPENAI_API_KEY" not in os.environ
prompt = sys.stdin.read()
counter_path = home / "counter"
counter = int(counter_path.read_text()) + 1 if counter_path.exists() else 1
counter_path.write_text(str(counter))
sessions = home / "sessions" / "thread-fake"
sessions.mkdir(parents=True, exist_ok=True)
(sessions / "session.json").write_text(json.dumps({"turn": counter}))

if sys.argv[1:3] == ["exec", "resume"]:
    assert "thread-fake" in sys.argv
else:
    assert sys.argv[1] == "exec"
    assert "--ephemeral" not in sys.argv
    assert "--profile" in sys.argv
    assert (home / "development.config.toml").is_file()

solution = pathlib.Path.cwd() / "solution.txt"
solution.write_text(solution.read_text() + f"{counter}:{len(prompt)}\\n")
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


def _workspace(path: Path) -> Path:
    path.mkdir()
    (path / "solution.txt").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_persistent_runner_resumes_one_thread_then_destroys_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _fake_cli(tmp_path / "codex")
    digest = _sha(executable.read_bytes())
    monkeypatch.setattr(codex_subscription, "_EXPECTED_CLI_DIGEST", digest)
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    material = "Use the current scoped behavior."
    turns = tuple(
        CodexConversationTurnRequest(
            turn=turn,
            task_id=f"task-{turn}",
            prompt=f"Complete task {turn}.",
            allowed_change_paths=("solution.txt",),
            adaptation_stage=1 if turn < 5 else 2 if turn < 12 else 3,
            material_text=material if turn in {1, 5, 12} else None,
            material_digest=_sha(material.encode()) if turn in {1, 5, 12} else None,
        )
        for turn in range(1, 16)
    )
    runner = CodexConversationRunner(
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

    result = runner.run_episode(
        episode_id="episode-a",
        common_instructions="Work only in this repository and do not use network.",
        turns=turns,
        workspace=_workspace(tmp_path / "workspace"),
    )

    assert len(result.turns) == 15
    assert {item.thread_id for item in result.turns} == {"thread-fake"}
    assert all(item.trace_conformant for item in result.turns)
    assert result.session_files_existed_during_episode
    assert result.config_destroyed
    assert result.session_destroyed
    assert not result.api_key_environment_present
    assert len((tmp_path / "workspace" / "solution.txt").read_text().splitlines()) == 15


def test_turn_rejects_mismatched_material_digest() -> None:
    with pytest.raises(ValueError, match="digest"):
        CodexConversationTurnRequest(
            turn=1,
            task_id="task",
            prompt="Do work.",
            allowed_change_paths=("solution.txt",),
            adaptation_stage=1,
            material_text="current",
            material_digest="sha256:" + "0" * 64,
        )
