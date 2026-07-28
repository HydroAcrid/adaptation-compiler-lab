from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthReplicationTask,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from scripts.run_durable_progress_comparison import _initialize_workspace
from scripts.score_breadth_replication_task import score


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_breadth_replication"


def _tasks() -> tuple[BreadthReplicationTask, ...]:
    return tuple(
        BreadthReplicationTask.model_validate_json(path.read_bytes())
        for path in sorted((_root() / "tasks").glob("*/task.json"))
    )


def _visible(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-m", "unittest", "discover", "-v"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_breadth_tasks_cover_families_and_stages_without_prior_task_ids() -> None:
    tasks = _tasks()

    assert len(tasks) == 8
    assert Counter(task.task.family for task in tasks) == Counter(
        {
            ApprovedSourceFamily.COMMUNICATION: 2,
            ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION: 2,
            ApprovedSourceFamily.ENVIRONMENT_SAFETY: 2,
            ApprovedSourceFamily.RESEARCH_INTEGRITY: 2,
        }
    )
    assert {task.stage for task in tasks} == {1, 2, 3}
    prior_ids = {
        "communication",
        "debugging_and_verification",
        "environment_safety",
        "research_integrity",
        "s1-archive-promotion",
        "s1-theme-rollout",
        "s2-index-refresh",
        "s2-preview-regeneration",
        "s3-ledger-replacement",
        "s3-template-cache-rollout",
    }
    assert not prior_ids.intersection(task.task_id for task in tasks)


def test_every_starter_visible_suite_passes_but_diagnostics_are_sensitive(
    tmp_path: Path,
) -> None:
    for wrapped in _tasks():
        fixture = _root() / "tasks" / wrapped.task_id / "fixture"
        workspace = tmp_path / wrapped.task_id
        _initialize_workspace(fixture, workspace)

        assert _visible(workspace).returncode == 0
        value = score(wrapped.task_id, workspace)
        assert not all(value["diagnostic"].values())


def test_every_reference_passes_all_independent_checks(tmp_path: Path) -> None:
    for wrapped in _tasks():
        task_root = _root() / "tasks" / wrapped.task_id
        workspace = tmp_path / wrapped.task_id
        _initialize_workspace(task_root / "fixture", workspace)
        for allowed in wrapped.task.allowed_change_paths:
            shutil.copyfile(task_root / "reference" / allowed, workspace / allowed)

        assert _visible(workspace).returncode == 0
        value = score(wrapped.task_id, workspace)
        assert all(
            result
            for group in ("objective", "diagnostic", "neutral")
            for result in value[group].values()
        ), json.dumps(value, indent=2, sort_keys=True)
