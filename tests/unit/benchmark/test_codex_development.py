from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentBlindReport,
    CodexDevelopmentRunObservation,
    build_codex_development_plan,
    development_tree_digest,
    load_codex_development_design,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily

DIGEST = "sha256:" + "a" * 64
NOW = datetime(2026, 7, 23, tzinfo=UTC)


def _root() -> Path:
    return Path(__file__).parents[3] / "development_benchmark"


def test_public_development_design_covers_four_new_nonheldout_families() -> None:
    design = load_codex_development_design(_root(), frozen_at=NOW)

    assert len(design.tasks) == 4
    assert {item.family for item in design.tasks} == set(ApprovedSourceFamily)
    assert all(not item.held_out for item in design.tasks)
    assert design.conditions == tuple(BenchmarkCondition)
    assert design.planned_runs == 16
    assert design.authentication == "saved_chatgpt"
    assert not design.milestone_6_custody_accessed


def test_development_plan_is_complete_blinded_and_seed_deterministic() -> None:
    design = load_codex_development_design(_root(), frozen_at=NOW)
    private, public = build_codex_development_plan(
        design=design,
        seed=RandomizationSeed(b"d" * 32),
        created_at=NOW,
    )

    assert len(private.run_order) == 16
    assert len({(item.task_id, item.blind_condition_id) for item in private.run_order}) == 16
    assert public.run_order == private.run_order
    assert public.private_plan_digest == private.content_digest
    assert public.condition_mapping_withheld is True
    assert "compiled_adaptation" not in public.model_dump_json()


def test_fixture_tree_digest_changes_with_content(tmp_path: Path) -> None:
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    before = development_tree_digest(tmp_path)
    (tmp_path / "value.py").write_text("VALUE = 2\n", encoding="utf-8")

    assert development_tree_digest(tmp_path) != before


def test_fixture_tree_digest_ignores_runtime_cache_files(tmp_path: Path) -> None:
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    before = development_tree_digest(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "value.cpython-312.pyc").write_bytes(b"runtime-only")

    assert development_tree_digest(tmp_path) == before


def _observation(task: str, condition: str, index: int) -> CodexDevelopmentRunObservation:
    return CodexDevelopmentRunObservation(
        run_id=f"run-{index:02d}",
        task_id=task,
        blind_condition_id=condition,
        blind_output_id=f"output-{index:02d}",
        condition_digest=DIGEST,
        trace_digest=DIGEST,
        diff_digest=DIGEST,
        final_response_digest=DIGEST,
        scorer_output_digest=DIGEST,
        command_digest=DIGEST,
        environment_digest=DIGEST,
        started_at=NOW,
        finished_at=NOW,
        duration_seconds=0,
        input_tokens=1,
        cached_input_tokens=0,
        output_tokens=1,
        reasoning_output_tokens=0,
        objective_checks_passed=1,
        objective_checks_total=1,
        diagnostic_checks_passed=1,
        diagnostic_checks_total=1,
        neutral_checks_passed=1,
        neutral_checks_total=1,
        timed_out=False,
        exit_code=0,
        trace_conformant=True,
        config_destroyed=True,
        workspace_destroyed=True,
        valid=True,
    )


def test_blind_report_requires_complete_grid() -> None:
    tasks = tuple(f"task-{index}" for index in range(4))
    conditions = tuple(f"condition-{index}" for index in range(4))
    observations = tuple(
        _observation(task, condition, index)
        for index, (task, condition) in enumerate(
            (task, condition) for task in tasks for condition in conditions
        )
    )

    report = CodexDevelopmentBlindReport(
        design_digest=DIGEST,
        observations=observations,
        created_at=NOW,
    )

    assert len(report.observations) == 16
    with pytest.raises(ValueError, match="16"):
        CodexDevelopmentBlindReport(
            design_digest=DIGEST,
            observations=observations[:-1],
            created_at=NOW,
        )
