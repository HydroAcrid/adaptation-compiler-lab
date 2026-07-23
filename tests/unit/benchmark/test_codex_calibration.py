from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_calibration import (
    CALIBRATION_CONDITIONS,
    build_codex_calibration_plan,
    load_codex_calibration_design,
)
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def _root() -> Path:
    return Path(__file__).parents[3] / "development_benchmark_v2"


def test_calibration_design_is_exactly_one_task_and_two_luna_cells() -> None:
    design = load_codex_calibration_design(_root(), frozen_at=NOW)

    assert design.task.task_id == "development-v2-research-integrity"
    assert design.conditions == CALIBRATION_CONDITIONS
    assert design.planned_runs == 2
    assert design.model == "gpt-5.6-luna"
    assert design.reasoning_effort == "medium"
    assert design.service_mode == "standard"
    assert not design.retry_allowed
    assert not design.milestone_6_custody_accessed


def test_calibration_plan_is_blinded_complete_and_seed_deterministic() -> None:
    design = load_codex_calibration_design(_root(), frozen_at=NOW)
    first_private, first_public = build_codex_calibration_plan(
        design=design,
        seed=RandomizationSeed(b"c" * 32),
        created_at=NOW,
    )
    second_private, second_public = build_codex_calibration_plan(
        design=design,
        seed=RandomizationSeed(b"c" * 32),
        created_at=NOW,
    )

    assert first_private == second_private
    assert first_public == second_public
    assert len(first_private.run_order) == 2
    assert len({item.blind_condition_id for item in first_private.run_order}) == 2
    assert first_public.private_plan_digest == first_private.content_digest
    assert "strong_static_profile" not in first_public.model_dump_json()
    assert "compiled_adaptation" not in first_public.model_dump_json()
