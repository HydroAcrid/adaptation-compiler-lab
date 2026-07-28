from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunRequest,
    CodexDevelopmentTask,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.runners import codex_subscription
from adaptation_compiler_lab.runners.codex_subscription import CodexSubscriptionError
from adaptation_compiler_lab.runners.codex_subscription_v3 import (
    CodexSubscriptionRunnerV3,
)


def _fake_cli(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/python3
import json
import pathlib
import sys
if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.145.0")
    raise SystemExit(0)
workspace = pathlib.Path(sys.argv[sys.argv.index("--cd") + 1])
assert (workspace / ".agents").is_dir()
assert (workspace / ".codex").is_dir()
(workspace / "solution.py").write_text("VALUE = 2\\n", encoding="utf-8")
for event in (
    {"type": "thread.started", "thread_id": "thread-v3"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "done"}},
    {"type": "turn.completed", "usage": {"input_tokens": 1, "cached_input_tokens": 0,
     "output_tokens": 1, "reasoning_output_tokens": 0}},
):
    print(json.dumps(event))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _request() -> CodexDevelopmentRunRequest:
    task = CodexDevelopmentTask(
        task_id="v3-smoke",
        family=ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION,
        prompt="Edit solution.py.",
        fixture_digest="sha256:" + "a" * 64,
        independent_scorer_digest="sha256:" + "b" * 64,
        visible_test_command=("python3", "-m", "unittest"),
        allowed_change_paths=("solution.py",),
        neutral_control_requirements=("ambient state absent",),
    )
    return CodexDevelopmentRunRequest(
        run_id="run-v3",
        blind_condition_id="condition-v3",
        blind_output_id="output-v3",
        task=task,
        condition_text="pointer",
        condition_digest="sha256:" + hashlib.sha256(b"pointer").hexdigest(),
        common_instructions="isolated",
    )


def test_v3_removes_empty_runner_created_mountpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _fake_cli(tmp_path / "codex")
    monkeypatch.setattr(
        codex_subscription,
        "_EXPECTED_CLI_DIGEST",
        "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest(),
    )
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / "solution.py").write_text("VALUE = 1\n", encoding="utf-8")
    runner = CodexSubscriptionRunnerV3(executable=executable, saved_auth_file=auth)

    def create_ephemeral_mountpoints(**arguments: object) -> list[str]:
        del arguments
        (workspace / ".agents").mkdir()
        (workspace / ".codex").mkdir()
        return [
            str(executable),
            "exec",
            "--cd",
            str(workspace),
            "--model",
            "gpt-5.6-terra",
            "--config",
            'model_reasoning_effort="high"',
            "--config",
            'approval_policy="never"',
            "--config",
            'shell_environment_policy.set={ PYTHONDONTWRITEBYTECODE = "1" }',
            "-",
        ]

    monkeypatch.setattr(runner, "_outer_sandbox_command", create_ephemeral_mountpoints)
    result = runner.run(_request(), workspace=workspace)

    assert result.trace_conformant
    assert not (workspace / ".agents").exists()
    assert not (workspace / ".codex").exists()


def test_v3_does_not_remove_preexisting_control_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _fake_cli(tmp_path / "codex")
    monkeypatch.setattr(
        codex_subscription,
        "_EXPECTED_CLI_DIGEST",
        "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest(),
    )
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / "solution.py").write_text("VALUE = 1\n", encoding="utf-8")
    ambient = workspace / ".agents"
    ambient.mkdir()
    (ambient / "rules.md").write_text("ambient\n", encoding="utf-8")
    runner = CodexSubscriptionRunnerV3(executable=executable, saved_auth_file=auth)

    with pytest.raises(CodexSubscriptionError, match="scratch path"):
        runner.run(_request(), workspace=workspace)

    assert (ambient / "rules.md").read_text(encoding="utf-8") == "ambient\n"
