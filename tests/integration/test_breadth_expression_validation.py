from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_expression_validation import (
    BreadthExpressionPublicPlan,
    BreadthExpressionTask,
    build_breadth_expression_plan,
    load_breadth_expression_contract,
    load_breadth_expression_design,
    noncommunication_rules_are_identical,
)
from scripts.score_breadth_expression_task import score


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_breadth_expression_validation"


def _tasks() -> tuple[BreadthExpressionTask, ...]:
    return tuple(
        BreadthExpressionTask.model_validate_json(path.read_bytes())
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


def test_starters_pass_visible_tests_but_remain_diagnostically_sensitive(
    tmp_path: Path,
) -> None:
    for task in _tasks():
        workspace = tmp_path / task.task_id
        _workspace(_root() / f"tasks/{task.task_id}/fixture", workspace)

        assert _visible(workspace).returncode == 0
        result = score(task.task_id, workspace)
        assert not all(result["diagnostic"].values())


def test_references_pass_every_public_semantic_check(tmp_path: Path) -> None:
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


def test_expression_plan_is_deterministic_complete_and_condition_blind() -> None:
    tasks = _tasks()
    first_public, first_private = build_breadth_expression_plan(
        design_digest="sha256:" + "a" * 64,
        tasks=tasks,
        seed=b"expression-plan-test-seed",
    )
    second_public, second_private = build_breadth_expression_plan(
        design_digest="sha256:" + "a" * 64,
        tasks=tasks,
        seed=b"expression-plan-test-seed",
    )

    assert first_public == second_public
    assert first_private == second_private
    assert len(first_public.run_order) == 4
    assert len({(cell.task_id, cell.blind_condition_id) for cell in first_public.run_order}) == 4
    public_payload = json.dumps(first_public.model_dump(mode="json"))
    assert "compiled_adaptation" not in public_payload
    assert "strong_static_profile" not in public_payload


def test_frozen_design_binds_only_a_communication_expression_change() -> None:
    design = load_breadth_expression_design(_root())
    contract = load_breadth_expression_contract(_root(), design=design)
    public = BreadthExpressionPublicPlan.model_validate_json(
        (_root() / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    old_material = (
        _repo() / "development_benchmark_breadth_instrument_repair/condition-materials/"
        "compiled-final.md"
    )
    repaired_material = (
        _repo() / "development_benchmark_breadth_instrument_repair/condition-materials/"
        "compiled-final-v4.md"
    )

    assert noncommunication_rules_are_identical(old_material, repaired_material)
    assert design.communication_expression_only
    assert design.noncommunication_material_byte_identical
    assert not design.new_behavior_added
    assert design.repaired_compiled_material_bytes == 974
    assert design.profile_material_bytes == 986
    assert design.maximum_subscription_sessions == 5
    assert contract.target_model == "gpt-5.6-luna"
    assert contract.judge_model == "gpt-5.6-sol"
    assert len(public.run_order) == 4
