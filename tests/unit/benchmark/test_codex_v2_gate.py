from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from adaptation_compiler_lab.benchmark.codex_v2_gate import (
    V2_GATE_CONDITIONS,
    V2_GATE_FAMILIES,
    CodexV2GatePreferenceRating,
    CodexV2GateTaskPreference,
    build_codex_v2_gate_plan,
    load_codex_v2_gate_design,
)
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def _root() -> Path:
    return Path(__file__).parents[3] / "development_benchmark_v2"


def test_v2_gate_design_binds_three_tasks_and_six_luna_cells() -> None:
    design = load_codex_v2_gate_design(_root(), frozen_at=NOW)

    assert len(design.tasks) == 3
    assert {task.family for task in design.tasks} == V2_GATE_FAMILIES
    assert design.conditions == V2_GATE_CONDITIONS
    assert design.planned_runs == 6
    assert design.model == "gpt-5.6-luna"
    assert design.reasoning_effort == "medium"
    assert design.service_mode == "standard"
    assert not design.retry_allowed
    assert not design.milestone_6_custody_accessed


def test_v2_gate_plan_is_complete_blinded_and_seed_deterministic() -> None:
    design = load_codex_v2_gate_design(_root(), frozen_at=NOW)
    first_private, first_public = build_codex_v2_gate_plan(
        design=design,
        seed=RandomizationSeed(b"v" * 32),
        created_at=NOW,
    )
    second_private, second_public = build_codex_v2_gate_plan(
        design=design,
        seed=RandomizationSeed(b"v" * 32),
        created_at=NOW,
    )

    assert first_private == second_private
    assert first_public == second_public
    assert len(first_private.run_order) == 6
    assert len({(item.task_id, item.blind_condition_id) for item in first_private.run_order}) == 6
    assert first_public.private_plan_digest == first_private.content_digest
    assert "strong_static_profile" not in first_public.model_dump_json()
    assert "compiled_adaptation" not in first_public.model_dump_json()


def test_committed_v2_gate_preregistration_binds_exact_task_trees() -> None:
    design = load_codex_v2_gate_design(_root(), frozen_at=NOW)
    preregistration = cast(
        dict[str, Any],
        json.loads((_root() / "remaining-gate-preregistration.json").read_text(encoding="utf-8")),
    )

    assert preregistration["conditions"] == [condition.value for condition in V2_GATE_CONDITIONS]
    assert preregistration["held_out"] is False
    assert preregistration["milestone_6_custody_accessed"] is False
    assert preregistration["execution"]["planned_runs"] == 6
    assert [
        {
            "family": task.family.value,
            "fixture_digest": task.fixture_digest,
            "independent_scorer_digest": task.independent_scorer_digest,
            "task_id": task.task_id,
        }
        for task in design.tasks
    ] == [
        {
            "family": task["family"],
            "fixture_digest": task["fixture_digest"],
            "independent_scorer_digest": task["independent_scorer_digest"],
            "task_id": task["task_id"],
        }
        for task in preregistration["tasks"]
    ]


def test_v2_gate_rating_requires_three_sorted_pairs_and_six_outputs() -> None:
    rating = CodexV2GatePreferenceRating(
        rating_id="v2-gate-rating-kevin-0001",
        public_plan_digest="sha256:" + "a" * 64,
        blind_report_digest="sha256:" + "b" * 64,
        presentation_sha256="sha256:" + "c" * 64,
        task_preferences=tuple(
            CodexV2GateTaskPreference(
                task_id=f"task-{index}",
                ordered_output_ids=(f"output-{index}-a", f"output-{index}-b"),
                preference="tie",
                preferred_output_id=None,
                rationale="No meaningful preference.",
            )
            for index in range(1, 4)
        ),
        rated_at=NOW,
    )

    assert len(rating.task_preferences) == 3
    assert not rating.condition_mapping_seen


def test_v2_gate_rating_rejects_incoherent_pairwise_preference() -> None:
    with pytest.raises(ValueError, match="does not match"):
        CodexV2GateTaskPreference(
            task_id="task-1",
            ordered_output_ids=("output-first", "output-second"),
            preference="first_better",
            preferred_output_id="output-second",
            rationale="Mismatch.",
        )
