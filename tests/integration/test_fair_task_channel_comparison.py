from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentTask
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    TaskChannelComparisonPublicPlan,
    load_task_channel_contract,
    load_task_channel_design,
)
from adaptation_compiler_lab.benchmark.task_channel_schema_export import (
    task_channel_comparison_schemas,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.targets.task_delivery import deliver_task_scoped_material


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_task_channel_comparison"


def _scenario_plan(task_id: str, scenario_id: str) -> tuple[str, ...]:
    design = load_task_channel_design(_root())
    task = next(item for item in design.tasks if item.task_id == task_id)
    scenario = next(item for item in task.scenarios if item.scenario_id == scenario_id)
    return scenario.expected_plan


def _literal(value: tuple[str, ...]) -> str:
    return repr(value)


def _reference(task_id: str) -> str:
    return (
        "def plan_transfer(\n"
        "    destination_exists: bool,\n"
        "    retention_class: str,\n"
        "    recovery_requested: bool = False,\n"
        ") -> tuple[str, ...]:\n"
        '    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:\n'
        '        raise ValueError("unsupported retention class")\n'
        "    if not destination_exists:\n"
        f"        return {_literal(_scenario_plan(task_id, 'missing-persistent-unrequested'))}\n"
        '    if retention_class == "retained_user_tree":\n'
        "        if recovery_requested:\n"
        f"            return {_literal(_scenario_plan(task_id, 'existing-persistent-requested'))}\n"
        f"        return {_literal(_scenario_plan(task_id, 'existing-persistent-unrequested'))}\n"
        "    if recovery_requested:\n"
        f"        return {_literal(_scenario_plan(task_id, 'existing-generated-requested'))}\n"
        f"    return {_literal(_scenario_plan(task_id, 'existing-generated-unrequested'))}\n"
    )


def _workspace(tmp_path: Path, task_id: str, source: str) -> Path:
    task = next(item for item in load_task_channel_design(_root()).tasks if item.task_id == task_id)
    workspace = tmp_path / task_id
    shutil.copytree(_root() / task.fixture_directory, workspace)
    (workspace / "src/transfer_policy.py").write_text(source, encoding="utf-8")
    return workspace


def _score(task_id: str, workspace: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts/score_compact_projection_task.py"),
            "--task-manifest",
            str(_root() / "tasks" / task_id / "task.json"),
            "--workspace",
            str(workspace),
        ],
        cwd=workspace,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


def _checks(value: dict[str, object]) -> dict[str, bool]:
    groups = value["checks"]
    assert isinstance(groups, dict)
    return {
        name: passed
        for group in groups.values()
        if isinstance(group, dict)
        for name, passed in group.items()
        if isinstance(name, str) and isinstance(passed, bool)
    }


def test_every_reference_passes_all_eight_independent_scenarios(tmp_path: Path) -> None:
    for task in load_task_channel_design(_root()).tasks:
        checks = _checks(
            _score(task.task_id, _workspace(tmp_path, task.task_id, _reference(task.task_id)))
        )
        assert len(checks) == 8
        assert all(checks.values())


def test_every_starter_is_diagnostic_but_its_visible_suite_passes(tmp_path: Path) -> None:
    for task in load_task_channel_design(_root()).tasks:
        fixture = _root() / task.fixture_directory
        completed = subprocess.run(
            list(task.visible_test_command),
            cwd=fixture,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert completed.returncode == 0, completed.stderr
        assert "Ran 2 tests" in completed.stderr
        checks = _checks(_score(task.task_id, fixture))
        assert any(checks.values())
        assert not all(checks.values())


def test_both_conditions_use_the_same_exact_once_delivery_adapter() -> None:
    repo = _repo()
    design = load_task_channel_design(_root())
    for task in design.tasks:
        generic = CodexDevelopmentTask(
            task_id=task.task_id,
            family=ApprovedSourceFamily.ENVIRONMENT_SAFETY,
            prompt=task.task_prompt,
            fixture_digest=design.task_fixture_digests[
                tuple(item.task_id for item in design.tasks).index(task.task_id)
            ],
            independent_scorer_digest=design.independent_scorer_digest,
            visible_test_command=task.visible_test_command,
            allowed_change_paths=task.allowed_change_paths,
            neutral_control_requirements=("Preserve behavior outside the active rule.",),
        )
        materials = (
            repo
            / "development_benchmark_compact_projection/runtime-fixture-v2.4"
            / f"codex-runtime-stage-{task.stage}.md",
            repo
            / "development_benchmark_compact_projection/condition-materials-v1.14"
            / f"strong-profile-stage-{task.stage}.md",
        )
        deliveries = [
            deliver_task_scoped_material(generic, path.read_text(encoding="utf-8"))
            for path in materials
        ]
        assert deliveries[0][1].original_prompt_digest == deliveries[1][1].original_prompt_digest
        assert all(receipt.channel == "user_task" for _, receipt in deliveries)
        assert all(receipt.material_occurrences == 1 for _, receipt in deliveries)
        assert all(
            delivered.prompt.count(path.read_text(encoding="utf-8").rstrip()) == 1
            for (delivered, _), path in zip(deliveries, materials, strict=True)
        )


def test_frozen_design_plan_contract_and_schemas_revalidate() -> None:
    design = load_task_channel_design(_root())
    contract = load_task_channel_contract(_root(), design=design)
    plan = TaskChannelComparisonPublicPlan.model_validate_json(
        (_root() / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    assert contract.public_plan_digest == plan.content_digest
    assert len(plan.run_order) == 12
    assert all(
        plan.run_order[index].task_id == plan.run_order[index + 1].task_id
        for index in range(0, 12, 2)
    )
    assert all(
        plan.run_order[index].blind_condition_id != plan.run_order[index + 1].blind_condition_id
        for index in range(0, 12, 2)
    )
    assert design.compiled_material_bytes == (216, 336, 343)
    assert design.profile_material_bytes == (221, 460, 504)
    assert contract.runner_source_digest == sha256_file(
        _repo() / "scripts/run_fair_task_channel_comparison.py"
    )
    schema_root = _repo() / "schemas/task_channel_comparison/v1"
    schemas = task_channel_comparison_schemas()
    assert {path.name for path in schema_root.glob("*.schema.json")} == set(schemas)
    for name, schema in schemas.items():
        assert json.loads((schema_root / name).read_text(encoding="utf-8")) == schema


def test_judge_instrument_amendment_preserves_target_artifacts() -> None:
    amendment = json.loads(
        (_root() / "JUDGE_INSTRUMENT_AMENDMENT-v1.json").read_text(encoding="utf-8")
    )

    assert amendment["target_artifacts_changed"] is False
    assert amendment["target_session_count"] == 12
    assert amendment["condition_mapping_accessed"] is False
