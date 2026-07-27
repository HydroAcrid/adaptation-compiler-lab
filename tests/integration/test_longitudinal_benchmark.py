from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from adaptation_compiler_lab.benchmark.longitudinal import (
    load_longitudinal_comparison,
)
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    load_compiled_materials,
)
from adaptation_compiler_lab.benchmark.longitudinal_scoring import (
    score_longitudinal_task,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from tests.unit.dogfood.test_longitudinal import _dogfood


def _root() -> Path:
    return Path(__file__).parents[2] / "development_benchmark_longitudinal"


def test_longitudinal_preregistration_is_frozen_and_unexecuted() -> None:
    root = _root()
    design = load_longitudinal_comparison(root)
    expected = (root / "PREREGISTRATION-v1.0.sha256").read_text(encoding="ascii").split()[0]

    assert sha256_file(root / "PREREGISTRATION-v1.0.json") == f"sha256:{expected}"
    assert len(design.tasks) == 6
    assert design.planned_target_runs == design.maximum_target_runs == 12
    assert design.maximum_subscription_sessions == 19
    assert design.provider_billed_calls == 0
    assert not design.api_keys_allowed
    assert design.target_timeout_seconds == 600
    assert design.target_turn_limit == 1
    assert not design.target_network_access
    assert not design.ambient_context_allowed
    assert design.task_workspace_access_only
    assert design.condition_material_byte_ceiling == 12000
    assert design.isolated_judge_is_condition_blind
    assert not design.target_runs_executed
    assert not design.sealed_external_validation_accessed


def test_all_public_task_fixtures_execute_visible_tests() -> None:
    root = _root()
    design = load_longitudinal_comparison(root)

    for task in design.tasks:
        fixture = root / task.fixture_directory
        completed = subprocess.run(
            ["python3", "-m", "unittest", "-v"],
            cwd=fixture,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        assert completed.returncode == 0, (task.task_id, completed.stdout, completed.stderr)


def test_frozen_compiled_condition_is_exact_dogfood_renderer_output() -> None:
    root = _root()
    materials = load_compiled_materials(root)
    rendered = _dogfood()
    metrics = json.loads((root / "DOGFOOD_METRICS-v1.0.json").read_text(encoding="utf-8"))

    for material, stage in zip(materials, rendered.stages, strict=True):
        agents = next(
            item.content for item in stage.rendered_pack.files if item.path == "AGENTS.md"
        )
        assert material == agents
    assert metrics["stage_pack_bytes"] == [
        stage.measurement.target_visible_bytes for stage in rendered.stages
    ]
    assert metrics["stage_primary_instruction_bytes"] == [
        stage.measurement.primary_instruction_bytes for stage in rendered.stages
    ]
    assert metrics["stage_update_latency_seconds"] == [
        stage.measurement.update_latency_seconds for stage in rendered.stages
    ]
    assert metrics["stage_maintenance_actions"] == [
        stage.measurement.maintenance_actions for stage in rendered.stages
    ]


def test_independent_scorer_detects_each_seeded_stage_defect() -> None:
    root = _root()
    design = load_longitudinal_comparison(root)

    for task in design.tasks:
        score = score_longitudinal_task(task, root / task.fixture_directory)
        assert score.objective_passed == score.objective_total == 1
        assert score.diagnostic_passed == 0
        assert score.diagnostic_total == 1
        if task.task_id == "longitudinal-s3-persistent-action":
            assert score.neutral_passed == score.neutral_total == 1
        else:
            assert score.neutral_passed == 0
            assert score.neutral_total == 1


def test_independent_scorer_accepts_reference_behavior(tmp_path: Path) -> None:
    root = _root()
    design = load_longitudinal_comparison(root)

    for task in design.tasks:
        workspace = tmp_path / task.task_id
        shutil.copytree(root / task.fixture_directory, workspace)
        if task.task_kind == "action":
            source = _reference_action(task.stage, task.context_kind)
        else:
            source = _reference_plan(task.stage, task.context_kind)
        (workspace / "policy.py").write_text(source, encoding="utf-8")
        score = score_longitudinal_task(task, workspace)
        assert all(item.passed for item in score.scenario_results)


def test_independent_scorer_records_broken_target_as_failed_result(tmp_path: Path) -> None:
    root = _root()
    task = load_longitudinal_comparison(root).tasks[0]
    workspace = tmp_path / "broken-target"
    shutil.copytree(root / task.fixture_directory, workspace)
    (workspace / "policy.py").write_text("this is invalid python\n", encoding="utf-8")

    score = score_longitudinal_task(task, workspace)

    assert score.objective_passed == score.diagnostic_passed == score.neutral_passed == 0
    assert all(not item.passed for item in score.scenario_results)
    assert all("SyntaxError" in item.observed for item in score.scenario_results)


def test_comparison_directory_excludes_private_execution_state() -> None:
    root = _root()
    forbidden_names = {
        "private-plan.json",
        "run-result.json",
        "randomization-seed.key",
        "trace-encryption.key",
    }
    assert not forbidden_names & {path.name for path in root.rglob("*") if path.is_file()}
    assert not tuple(root.rglob("__pycache__"))
    assert not tuple(root.rglob("*.pyc"))
    serialized = json.dumps(
        load_longitudinal_comparison(root).model_dump(mode="json"),
        sort_keys=True,
    )
    for forbidden in (
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "CODEX_API_KEY",
        "OPENAI_API_KEY",
        "milestone_6_task",
    ):
        assert forbidden not in serialized


def _reference_action(stage: int, context_kind: str) -> str:
    if context_kind == "disposable_generated_cache":
        existing = 'return "atomic_replace"'
    elif stage == 3:
        existing = 'return "backup_then_replace" if backup_requested else "refuse"'
    else:
        existing = 'return "backup_then_replace"'
    return (
        "def choose_publish_action(destination_exists: bool, "
        "backup_requested: bool = False) -> str:\n"
        "    if not destination_exists:\n"
        '        return "create"\n'
        f"    {existing}\n"
    )


def _reference_plan(stage: int, context_kind: str) -> str:
    if context_kind == "disposable_generated_cache":
        existing = 'return ("write_temporary_tree", "atomically_replace_destination")'
    elif stage == 3:
        existing = (
            'return ("create_recoverable_backup", "replace_destination") '
            'if backup_requested else ("refuse_overwrite",)'
        )
    else:
        existing = 'return ("create_recoverable_backup", "replace_destination")'
    return (
        "def build_publish_plan(destination_exists: bool, "
        "backup_requested: bool = False) -> tuple[str, ...]:\n"
        "    if not destination_exists:\n"
        '        return ("create_destination",)\n'
        f"    {existing}\n"
    )
