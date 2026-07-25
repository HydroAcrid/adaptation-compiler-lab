from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest

ROOT = Path(__file__).resolve().parents[2] / "development_benchmark_claude" / "instrument_canary"
EXPECTED_FIXTURE_DIGEST = "sha256:5be1cf278d4927cdfc5665dcd1c91abe7764ab550aa19331533511befe5a3de4"
EXPECTED_SCORER_DIGEST = "sha256:3b373c105d96b55252c08e70b18d63aa9f8a88244281f05ad7ff65946099b1b7"
REFERENCE_SOLUTION = '''"""Retry decisions for independent background jobs."""

from __future__ import annotations

_failure_counts: dict[str, int] = {}


def _normalized_job_id(job_id: str) -> str:
    normalized = job_id.strip().casefold()
    if not normalized:
        raise ValueError("job_id must not be blank")
    return normalized


def should_retry(job_id: str, max_failures: int) -> bool:
    """Record one failure and report whether this job remains within its retry budget."""

    key = _normalized_job_id(job_id)
    if max_failures < 1:
        raise ValueError("max_failures must be positive")
    failures = _failure_counts.get(key, 0) + 1
    _failure_counts[key] = failures
    return failures <= max_failures


def reset_job(job_id: str) -> None:
    """Forget the recorded failures for one completed or cancelled job."""

    _failure_counts.pop(_normalized_job_id(job_id), None)
'''


def _run(command: tuple[str, ...], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            "HOME": str(cwd),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )


def _initialize_git(workspace: Path) -> None:
    for command in (
        ("git", "init", "--quiet"),
        ("git", "config", "user.name", "Canary Test"),
        ("git", "config", "user.email", "canary-test@invalid.local"),
        ("git", "add", "--all"),
        ("git", "commit", "--quiet", "-m", "fixture"),
    ):
        completed = _run(command, cwd=workspace)
        assert completed.returncode == 0, completed.stderr


def _score(workspace: Path) -> dict[str, dict[str, bool]]:
    completed = _run(
        (sys.executable, str(ROOT / "independent" / "score.py"), str(workspace)),
        cwd=workspace,
    )
    assert completed.returncode == 0, completed.stderr
    return cast(dict[str, dict[str, bool]], json.loads(completed.stdout))


def test_canary_task_is_public_bounded_and_digest_frozen() -> None:
    task = json.loads((ROOT / "task.json").read_text(encoding="utf-8"))

    assert task["held_out"] is False
    assert task["family"] == "debugging_and_verification"
    assert task["focused_test_command"] == [
        "python3",
        "-m",
        "unittest",
        "-v",
        "test_retry_budget.RetryBudgetTests.test_failure_budget_isolated_between_jobs",
    ]
    assert task["full_test_command"] == ["python3", "-m", "unittest", "-v"]
    assert development_tree_digest(ROOT / "fixture") == EXPECTED_FIXTURE_DIGEST
    assert development_tree_digest(ROOT / "independent") == EXPECTED_SCORER_DIGEST


def test_defective_fixture_fails_the_reproduction_and_diagnostics(tmp_path: Path) -> None:
    workspace = tmp_path / "fixture"
    shutil.copytree(ROOT / "fixture", workspace)
    _initialize_git(workspace)

    focused = _run(
        (
            "python3",
            "-m",
            "unittest",
            "-v",
            "test_retry_budget.RetryBudgetTests.test_failure_budget_isolated_between_jobs",
        ),
        cwd=workspace,
    )
    scores = _score(workspace)

    assert focused.returncode != 0
    assert not all(scores["diagnostic"].values())
    assert all(scores["neutral"].values())


def test_reference_solution_passes_visible_and_independent_checks(tmp_path: Path) -> None:
    workspace = tmp_path / "reference"
    shutil.copytree(ROOT / "fixture", workspace)
    _initialize_git(workspace)
    (workspace / "retry_budget.py").write_text(REFERENCE_SOLUTION, encoding="utf-8")

    visible = _run(("python3", "-m", "unittest", "-v"), cwd=workspace)
    scores = _score(workspace)

    assert visible.returncode == 0, visible.stdout + visible.stderr
    assert all(
        passed
        for group in ("objective", "diagnostic", "neutral")
        for passed in scores[group].values()
    )
