from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _root() -> Path:
    return Path(__file__).parents[2] / "development_benchmark" / "tasks"


@pytest.mark.parametrize(
    "task_name",
    ("communication", "debugging", "environment_safety", "research_integrity"),
)
def test_development_fixture_and_independent_scorer_are_runnable(
    tmp_path: Path,
    task_name: str,
) -> None:
    task_root = _root() / task_name
    workspace = tmp_path / "workspace"
    shutil.copytree(task_root / "fixture", workspace)
    commands = (
        ("git", "init", "--quiet"),
        ("git", "config", "user.name", "Test"),
        ("git", "config", "user.email", "test@invalid.local"),
        ("git", "add", "--all"),
        ("git", "commit", "--quiet", "-m", "fixture"),
    )
    for command in commands:
        subprocess.run(command, cwd=workspace, check=True)

    (workspace / "runtime-only.pyc").write_bytes(b"interpreter-generated")
    runtime_cache = workspace / "__pycache__"
    runtime_cache.mkdir(exist_ok=True)
    (runtime_cache / "runtime-only.cpython-312.pyc").write_bytes(b"interpreter-generated")
    result = subprocess.run(
        (sys.executable, str(task_root / "independent" / "score.py"), str(workspace)),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    score = json.loads(result.stdout)

    assert set(score) == {"diagnostic", "neutral", "objective"}
    assert score["neutral"]["only_allowed_source_changed"] is True
    assert all(
        group and all(isinstance(value, bool) for value in group.values())
        for group in score.values()
    )


def test_neutral_scorer_still_detects_material_untracked_files(tmp_path: Path) -> None:
    task_root = _root() / "communication"
    workspace = tmp_path / "workspace"
    shutil.copytree(task_root / "fixture", workspace)
    for command in (
        ("git", "init", "--quiet"),
        ("git", "config", "user.name", "Test"),
        ("git", "config", "user.email", "test@invalid.local"),
        ("git", "add", "--all"),
        ("git", "commit", "--quiet", "-m", "fixture"),
    ):
        subprocess.run(command, cwd=workspace, check=True)
    (workspace / "unrelated.txt").write_text("material change\n", encoding="utf-8")

    result = subprocess.run(
        (sys.executable, str(task_root / "independent" / "score.py"), str(workspace)),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(result.stdout)["neutral"]["only_allowed_source_changed"] is False
