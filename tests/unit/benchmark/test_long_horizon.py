from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    LongHorizonEpisodeResult,
    LongHorizonMaterialSet,
    LongHorizonTurnKind,
    LongHorizonTurnScore,
    build_long_horizon_plan,
    build_long_horizon_scenario,
)
from adaptation_compiler_lab.benchmark.long_horizon_fixture import (
    apply_reference_implementations,
    create_long_horizon_workspace,
    long_horizon_task_catalog,
    score_long_horizon_task,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition


def _materials(condition: BenchmarkCondition) -> LongHorizonMaterialSet:
    return LongHorizonMaterialSet(
        condition=condition,
        stages=("one", "one two", "one two three"),
        eligible_evidence_digest="sha256:" + "e" * 64,
        independently_maintained=condition is BenchmarkCondition.STRONG_STATIC_PROFILE,
    )


def _design() -> LongHorizonDesign:
    scenario = build_long_horizon_scenario(
        long_horizon_task_catalog(),
        seed=bytes(range(32)),
    )
    return LongHorizonDesign(
        scenario=scenario,
        materials=(
            _materials(BenchmarkCondition.STRONG_STATIC_PROFILE),
            _materials(BenchmarkCondition.COMPILED_ADAPTATION),
        ),
        frozen_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


def test_scenario_is_seeded_varied_and_keeps_feedback_boundaries() -> None:
    catalog = long_horizon_task_catalog()
    first = build_long_horizon_scenario(catalog, seed=bytes(range(32)))
    second = build_long_horizon_scenario(catalog, seed=bytes(range(32)))
    different = build_long_horizon_scenario(catalog, seed=bytes(reversed(range(32))))

    assert first == second
    assert first.turns != different.turns
    assert tuple(
        item.turn for item in first.turns if item.task.kind is LongHorizonTurnKind.EXPLICIT_FEEDBACK
    ) == (4, 11)
    assert tuple(item.turn for item in first.turns if item.horizon_checkpoint) == (3, 10, 15)
    assert tuple(item.turn for item in first.turns if item.delivers_material_update) == (1, 5, 12)
    assert {
        item.task.family
        for item in first.turns
        if item.task.kind is not LongHorizonTurnKind.EXPLICIT_FEEDBACK
    } == {item.family for item in catalog if item.kind is not LongHorizonTurnKind.EXPLICIT_FEEDBACK}


def test_plan_is_blind_deterministic_and_maps_both_conditions() -> None:
    design = _design()
    first_public, first_private = build_long_horizon_plan(design, seed=b"p" * 32)
    second_public, second_private = build_long_horizon_plan(design, seed=b"p" * 32)

    assert first_public == second_public
    assert first_private == second_private
    assert "strong_static_profile" not in first_public.model_dump_json()
    assert "compiled_adaptation" not in first_public.model_dump_json()
    assert {item.condition for item in first_private.assignments} == {
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    }


def test_reference_fixture_passes_every_visible_and_hidden_check() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        create_long_horizon_workspace(workspace)
        apply_reference_implementations(workspace)

        for task in long_horizon_task_catalog():
            score = score_long_horizon_task(task, workspace=workspace)
            assert score["objective_passed"] == score["objective_total"]
            assert score["adaptation_passed"] == score["adaptation_total"]
            assert score["neutral_passed"] == score["neutral_total"]
            assert not score["correction_required"]


def test_seed_fixture_is_diagnostic_but_neutral_reference_is_exact() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        create_long_horizon_workspace(workspace)
        scores = {
            task.task_id: score_long_horizon_task(task, workspace=workspace)
            for task in long_horizon_task_catalog()
        }

    assert any(value["adaptation_passed"] < value["adaptation_total"] for value in scores.values())
    assert (
        scores["tag-normalization"]["neutral_passed"] < scores["tag-normalization"]["neutral_total"]
    )


def test_episode_metrics_are_cumulative_at_3_10_and_15_turns() -> None:
    turn_scores = tuple(
        LongHorizonTurnScore(
            turn=turn,
            task_id=f"task-{turn}",
            kind=(
                LongHorizonTurnKind.EXPLICIT_FEEDBACK
                if turn in {4, 11}
                else LongHorizonTurnKind.DIAGNOSTIC
            ),
            objective_passed=0 if turn in {4, 11} else 1,
            objective_total=0 if turn in {4, 11} else 1,
            adaptation_passed=0 if turn in {4, 11} else int(turn % 2 == 0),
            adaptation_total=0 if turn in {4, 11} else 1,
            neutral_passed=0,
            neutral_total=0,
            correction_required=turn not in {4, 11} and turn % 2 == 1,
        )
        for turn in range(1, 16)
    )
    result = LongHorizonEpisodeResult(
        episode_id="episode-a",
        blind_condition_id="condition-a",
        blind_output_id="output-a",
        scenario_digest="sha256:" + "a" * 64,
        material_digests=(
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            "sha256:" + "3" * 64,
        ),
        turn_scores=turn_scores,
        trace_digests=tuple(f"sha256:{turn:064x}" for turn in range(1, 16)),
        encrypted_raw_ref="sha256:" + "f" * 64,
        input_tokens=100,
        cached_input_tokens=10,
        output_tokens=20,
        reasoning_output_tokens=5,
        duration_seconds=1.0,
        all_turns_conformant=True,
        config_destroyed=True,
        session_destroyed=True,
    )

    assert result.cumulative_at(3)["objective_total"] == 3
    assert result.cumulative_at(10)["objective_total"] == 9
    assert result.cumulative_at(15)["objective_total"] == 13
    assert result.cumulative_at(15)["corrections"] == 7
