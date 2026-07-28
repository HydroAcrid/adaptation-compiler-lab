"""Run one real subscription smoke for the v3 target runner."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunRequest,
    CodexDevelopmentTask,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.runners.codex_subscription_v3 import (
    CodexSubscriptionRunnerV3,
)
from adaptation_compiler_lab.serialization import canonical_json
from scripts.run_durable_progress_comparison import _create_key

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def _write(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for the v3 runner smoke")
    repo = arguments.repo.resolve()
    runner = CodexSubscriptionRunnerV3(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        contract=CodexExecutionContract(
            model="gpt-5.6-luna",
            reasoning_effort="medium",
            max_seconds=300,
        ),
        bubblewrap=arguments.bubblewrap,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_target_preconditions()))
        return
    if _run(["git", "status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("v3 runner smoke requires a clean repository")
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    receipt_path = repo / "development_benchmark_breadth_instrument_repair/RUNNER_SMOKE-v3.json"
    if output_root.exists() or config_root.exists() or receipt_path.exists():
        raise RuntimeError("v3 runner smoke output already exists")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    _create_key(config_root / "trace-encryption.key")
    store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key",
            workspace_root=repo,
        ),
    )
    source_commit = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="acl-v3-smoke-") as temporary:
        workspace = Path(temporary) / "task"
        workspace.mkdir()
        _write(workspace / "solution.py", "def increment(value: int) -> int:\n    return value\n")
        _write(
            workspace / "test_solution.py",
            "import unittest\n"
            "from solution import increment\n"
            "class Tests(unittest.TestCase):\n"
            "    def test_increment(self) -> None:\n"
            "        self.assertEqual(increment(4), 5)\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
        )
        for command in (
            ["git", "init", "-q"],
            ["git", "config", "user.name", "Instrument Smoke"],
            ["git", "config", "user.email", "smoke@example.invalid"],
            ["git", "add", "."],
            ["git", "commit", "-q", "-m", "fixture"],
        ):
            completed = _run(command, cwd=workspace)
            if completed.returncode:
                raise RuntimeError("unable to initialize v3 smoke fixture")
        task = CodexDevelopmentTask(
            task_id="breadth-v3-edit-test-smoke",
            family=ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION,
            prompt=(
                "Repair increment(value) so the existing test passes. Change only solution.py "
                "and run python3 -m unittest discover -v."
            ),
            fixture_digest="sha256:" + "a" * 64,
            independent_scorer_digest="sha256:" + "b" * 64,
            visible_test_command=("python3", "-m", "unittest", "discover", "-v"),
            allowed_change_paths=("solution.py",),
            neutral_control_requirements=(
                "ambient agent configuration remains absent",
                "only solution.py changes",
            ),
        )
        pointer = "No adaptation material is supplied for this synthetic instrument smoke."
        request = CodexDevelopmentRunRequest(
            run_id="breadth-v3-edit-test-smoke",
            blind_condition_id="condition-none",
            blind_output_id="output-smoke",
            task=task,
            condition_text=pointer,
            condition_digest=sha256_bytes(pointer.encode()),
            common_instructions=(
                "Work only in the supplied repository. Use no network, agents, memories, skills, "
                "plugins, MCP servers, prior transcripts, or external files. Do not inspect "
                ".agents or .codex. Change only solution.py and run the requested tests."
            ),
        )
        result = runner.run(request, workspace=workspace)
        status = _run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=workspace,
        )
        diff = _run(["git", "diff", "--binary", "HEAD"], cwd=workspace)
        tests = _run(["python3", "-m", "unittest", "discover", "-v"], cwd=workspace)
        control_absent = (
            not (workspace / ".agents").exists() and not (workspace / ".codex").exists()
        )
        changed_only_source = (
            status.stdout.strip().endswith("solution.py") and len(status.stdout.splitlines()) == 1
        )
        smoke_passed = (
            result.trace_conformant
            and result.config_destroyed
            and not result.session_files_persisted
            and not result.forbidden_ambient_surface_observed
            and tests.returncode == 0
            and "Ran 1 test" in tests.stderr
            and changed_only_source
            and control_absent
            and "return value + 1" in (workspace / "solution.py").read_text(encoding="utf-8")
        )
        raw = (
            canonical_json(
                {
                    "commands_and_trace_base64": base64.b64encode(result.trace_bytes).decode(),
                    "diff": diff.stdout,
                    "final_response": result.final_response,
                    "status": status.stdout,
                    "stderr": result.stderr,
                    "test_stderr": tests.stderr,
                    "test_stdout": tests.stdout,
                }
            )
            + "\n"
        ).encode()
        raw_ref = store.put(
            raw,
            media_type="application/vnd.adaptation-compiler-lab.breadth-v3-smoke+json",
        )
    receipt = {
        "receipt_version": "1.0.0",
        "api_key_environment_present": False,
        "authentication": "saved_chatgpt",
        "changed_only_registered_source": changed_only_source,
        "config_destroyed": result.config_destroyed,
        "control_mountpoints_absent_before_scoring": control_absent,
        "external_validation_accessed": False,
        "model": result.model,
        "provider_billed_calls": 0,
        "raw_trace_ref": f"sha256:{raw_ref.sha256}",
        "reasoning_effort": result.reasoning_effort,
        "runner_source_digest": sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v3.py"
        ),
        "smoke_passed": smoke_passed,
        "source_commit": source_commit,
        "tests_passed": tests.returncode == 0,
        "trace_conformant": result.trace_conformant,
        "workspace_destroyed": True,
    }
    receipt_path.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    if not smoke_passed:
        raise RuntimeError("v3 real edit-and-test smoke failed")
    print(canonical_json(receipt))


if __name__ == "__main__":
    main()
