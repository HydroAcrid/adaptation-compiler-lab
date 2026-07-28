from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_remediation import (
    BreadthRemediationTask,
    load_breadth_remediation_contract,
    load_breadth_remediation_design,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from scripts.score_breadth_remediation_task import score


def _root() -> Path:
    return Path(__file__).parents[2] / "development_benchmark_breadth_remediation"


def _tasks() -> tuple[BreadthRemediationTask, ...]:
    return tuple(
        BreadthRemediationTask.model_validate_json(path.read_bytes())
        for path in sorted((_root() / "tasks").glob("*/task.json"))
    )


def _workspace(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(
        ["git", "config", "user.email", "benchmark@example.invalid"],
        cwd=target,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Benchmark"],
        cwd=target,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=target, check=True)


def _visible(workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-m", "unittest", "discover", "-v"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_remediation_tasks_replace_only_failed_slots_with_family_coverage() -> None:
    tasks = _tasks()

    assert len(tasks) == 5
    assert {item.replaces_task_id for item in tasks} == {
        "communication-shell",
        "debugging-status",
        "environment-layout",
        "environment-publish",
        "research-trials",
    }
    assert Counter(item.task.family for item in tasks) == Counter(
        {
            ApprovedSourceFamily.COMMUNICATION: 1,
            ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION: 1,
            ApprovedSourceFamily.ENVIRONMENT_SAFETY: 2,
            ApprovedSourceFamily.RESEARCH_INTEGRITY: 1,
        }
    )


def test_starters_pass_visible_tests_but_remain_diagnostically_sensitive(
    tmp_path: Path,
) -> None:
    for task in _tasks():
        workspace = tmp_path / task.task_id
        _workspace(_root() / f"tasks/{task.task_id}/fixture", workspace)

        assert _visible(workspace).returncode == 0
        result = score(task.task_id, workspace)
        assert not all(result["diagnostic"].values())


def test_references_pass_and_every_oracle_check_has_public_basis(tmp_path: Path) -> None:
    for task in _tasks():
        task_root = _root() / f"tasks/{task.task_id}"
        workspace = tmp_path / task.task_id
        _workspace(task_root / "fixture", workspace)
        for allowed in task.task.allowed_change_paths:
            shutil.copyfile(task_root / "reference" / allowed, workspace / allowed)

        assert _visible(workspace).returncode == 0
        result = score(task.task_id, workspace)
        assert all(passed for checks in result.values() for passed in checks.values()), json.dumps(
            result, indent=2, sort_keys=True
        )
        registered = {(contract.group, contract.check_id) for contract in task.oracle_checks}
        observed = {(group, check_id) for group, checks in result.items() for check_id in checks}
        assert registered == observed
        assert all(
            contract.public_basis.strip()
            and contract.exact_undisclosed_vocabulary_required is False
            for contract in task.oracle_checks
        )


def test_frozen_remediation_design_and_contract_revalidate() -> None:
    root = _root()

    design = load_breadth_remediation_design(root)
    contract = load_breadth_remediation_contract(root, design=design)

    assert len(design.tasks) == 5
    assert design.planned_target_sessions == 10
    assert design.maximum_subscription_sessions == 11
    assert design.oracle_contract_audited is True
    assert contract.provider_billed_calls == 0
    assert contract.external_validation_accessed is False
