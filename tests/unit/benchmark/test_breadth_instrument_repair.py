from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    build_breadth_instrument_plan,
)
from scripts.build_breadth_instrument_tasks import build
from scripts.score_breadth_instrument_task import score


def _git(workspace: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )


def _reference_workspace(root: Path, task_id: str, source_name: str, target: Path) -> Path:
    shutil.copytree(root / f"tasks/{task_id}/fixture", target)
    _git(target, "init", "-q")
    _git(target, "config", "user.name", "Fixture")
    _git(target, "config", "user.email", "fixture@example.invalid")
    _git(target, "add", ".")
    _git(target, "commit", "-q", "-m", "fixture")
    shutil.copy2(root / f"tasks/{task_id}/reference/{source_name}", target / source_name)
    return target


def test_reference_implementations_pass_every_semantic_check(tmp_path: Path) -> None:
    repo = Path(__file__).parents[3]
    root = repo / "development_benchmark_breadth_instrument_repair"
    task_sources = {
        "communication-release-handoff": "release_handoff.py",
        "debugging-deployment-state": "deployment_state.py",
        "environment-migration-plan": "migration_plan.py",
        "research-cutoff-report": "cutoff_report.py",
    }

    for task_id, source_name in task_sources.items():
        workspace = _reference_workspace(
            root,
            task_id,
            source_name,
            tmp_path / task_id,
        )
        result = score(task_id, workspace)

        assert all(passed for checks in result.values() for passed in checks.values()), result


def test_blind_plan_is_deterministic_and_complete() -> None:
    repo = Path(__file__).parents[3]
    root = repo / "development_benchmark_breadth_instrument_repair"
    tasks = build(root, scorer=repo / "scripts/score_breadth_instrument_task.py")
    first = build_breadth_instrument_plan(
        design_digest="sha256:" + "a" * 64,
        tasks=tasks,
        seed=b"s" * 32,
    )
    second = build_breadth_instrument_plan(
        design_digest="sha256:" + "a" * 64,
        tasks=tasks,
        seed=b"s" * 32,
    )

    assert first == second
    public, private = first
    assert len(public.run_order) == 8
    assert len({(cell.task_id, cell.blind_condition_id) for cell in public.run_order}) == 8
    assert private["external_validation_accessed"] is False
