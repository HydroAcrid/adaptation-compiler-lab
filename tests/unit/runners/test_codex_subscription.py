from __future__ import annotations

import hashlib
import shlex
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
    CodexExecutionContract,
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
    print(
        "WARNING: proceeding, even though we could not create PATH aliases: isolated home",
        file=sys.stderr,
    )
    print("Logged in using ChatGPT")
    raise SystemExit(0)
if sys.argv[1] == "app-server":
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("method") == "initialize":
            print(json.dumps({"id": request["id"], "result": {"userAgent": "fake"}}), flush=True)
        elif request.get("method") == "model/list":
            print(
                json.dumps(
                    {
                        "id": request["id"],
                        "result": {
                            "data": [
                                {
                                    "hidden": False,
                                    "id": "gpt-5.6-terra",
                                    "model": "gpt-5.6-terra",
                                    "supportedReasoningEfforts": [
                                        {"reasoningEffort": "high"}
                                    ],
                                },
                                {
                                    "hidden": False,
                                    "id": "gpt-5.6-luna",
                                    "model": "gpt-5.6-luna",
                                    "supportedReasoningEfforts": [
                                        {"reasoningEffort": "medium"}
                                    ],
                                },
                            ],
                            "nextCursor": None,
                        },
                    }
                ),
                flush=True,
            )
    raise SystemExit(0)
assert "--ask-for-approval" not in sys.argv
assert 'approval_policy="never"' in sys.argv
assert any("PYTHONDONTWRITEBYTECODE" in value for value in sys.argv)
assert sys.argv[-1] == "-"
model = sys.argv[sys.argv.index("--model") + 1]
assert model in {"gpt-5.6-terra", "gpt-5.6-luna"}
if model == "gpt-5.6-luna":
    assert 'model_reasoning_effort="medium"' in sys.argv
assert "Explain the purpose before procedural detail." not in " ".join(sys.argv)
profile = pathlib.Path(os.environ["CODEX_HOME"], "development.config.toml")
assert profile.is_file()
assert profile.stat().st_mode & 0o077 == 0
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
    assert runner.verify_model_availability() == {
        "hidden": False,
        "model": "gpt-5.6-terra",
        "reasoning_effort": "high",
        "service_mode": "standard",
    }
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
    assert not result.model_reroute_observed
    assert result.model == "gpt-5.6-terra"
    assert result.reasoning_effort == "high"
    assert result.service_mode == "standard"


def test_runner_accepts_explicit_luna_medium_standard_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _fake_cli(tmp_path / "codex")
    digest = _sha(executable.read_bytes())
    monkeypatch.setattr(codex_subscription, "_EXPECTED_CLI_DIGEST", digest)
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    runner = CodexSubscriptionRunner(
        executable=executable,
        saved_auth_file=auth,
        contract=CodexExecutionContract(
            cli_version="codex-cli 0.145.0",
            cli_digest=digest,
            model="gpt-5.6-luna",
            reasoning_effort="medium",
            service_mode="standard",
            max_seconds=10,
        ),
    )

    assert runner.verify_model_availability()["model"] == "gpt-5.6-luna"
    result = runner.run(_request(), workspace=_workspace(tmp_path / "workspace"))

    assert result.trace_conformant
    assert result.model == "gpt-5.6-luna"
    assert result.reasoning_effort == "medium"


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


def test_outer_target_sandbox_allows_source_edit_and_tests_but_denies_other_paths(
    tmp_path: Path,
) -> None:
    toolchains = Path.home() / ".local/share/adaptation-compiler-lab/toolchains"
    codex = (
        toolchains / "codex-0.145.0/node_modules/@openai/codex-linux-x64/vendor/"
        "x86_64-unknown-linux-musl/bin/codex"
    )
    bubblewrap = toolchains / "claude-sandbox-runtime-jammy/usr/bin/bwrap"
    if not codex.is_file() or not bubblewrap.is_file():
        pytest.skip("pinned local target sandbox runtime is unavailable")
    workspace = tmp_path / "workspace"
    source = workspace / "src"
    source.mkdir(parents=True)
    (source / "transfer_policy.py").write_text(
        "def value() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    test_file = workspace / "test_transfer_policy.py"
    test_file.write_text(
        "import sys\n"
        "import unittest\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).parent / 'src'))\n"
        "from transfer_policy import value\n"
        "class Tests(unittest.TestCase):\n"
        "    def test_value(self) -> None:\n"
        "        self.assertEqual(value(), 2)\n",
        encoding="utf-8",
    )
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}\n", encoding="utf-8")
    runner = CodexSubscriptionRunner(
        executable=codex,
        saved_auth_file=codex_home / "auth.json",
        bubblewrap=bubblewrap,
    )
    host_probe = Path(__file__).parents[3] / "pyproject.toml"
    command = runner._outer_sandbox_command(
        inner_command=[
            "/bin/sh",
            "-c",
            (
                "set -eu; "
                "printf 'def value() -> int:\\n    return 2\\n' "
                "> /workspace/src/transfer_policy.py; "
                f"test ! -e {shlex.quote(str(host_probe))}; "
                "if printf 'forbidden\\n' > /workspace/test_transfer_policy.py "
                "2>/tmp/root-write-error; then exit 90; fi; "
                "python3 -m unittest -v"
            ),
        ],
        codex_home=codex_home,
        workspace=workspace,
        allowed_change_paths=("src/transfer_policy.py",),
    )

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert "return 2" in (source / "transfer_policy.py").read_text(encoding="utf-8")
    assert "forbidden" not in test_file.read_text(encoding="utf-8")
    assert "OK" in completed.stderr


def test_run_observation_timestamps_remain_utc() -> None:
    assert datetime.now(UTC).tzinfo is UTC
