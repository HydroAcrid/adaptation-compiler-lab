"""Frozen Mode-effectiveness instrument and scorer-boundary tests."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Literal

import pytest

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.modes import MODE_EVALUATION_DESIGNS
from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationFixtureV1,
    ModeEvaluationPublicPlanV1,
    ModeJudgeDecisionV1,
    ModeJudgePairDecisionV1,
    build_mode_evaluation_plan,
    load_mode_evaluation_contract,
)
from scripts.observe_mode_evaluation_policy import _tree
from scripts.unblind_mode_evaluation import build_mode_outcome

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "development_benchmark_mode_evaluation"


def test_frozen_contract_covers_three_modes_and_fifteen_fresh_tasks() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v1.json")

    assert len(contract.fixtures) == 15
    assert Counter(item.mode_id for item in contract.fixtures) == Counter(
        {"frontend-studio": 5, "research-analyst": 5, "secure-backend": 5}
    )
    assert Counter(item.kind for item in contract.fixtures) == Counter(
        {"diagnostic": 9, "neutral_control": 6}
    )
    assert contract.catalog_design_digests == tuple(
        sorted(item.content_digest for item in MODE_EVALUATION_DESIGNS)
    )
    assert contract.target_runs == 30
    assert contract.provider_billed_calls == 0
    assert contract.external_validation_accessed is False


def test_contract_binds_every_fixture_and_instrument_source() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v1.json")

    for fixture in contract.fixtures:
        assert (
            development_tree_digest(BENCHMARK / fixture.fixture_directory) == fixture.fixture_digest
        )
    assert contract.runner_source_digest == sha256_file(ROOT / "scripts/run_mode_evaluation.py")
    assert contract.scorer_source_digest == sha256_file(
        ROOT / "scripts/score_mode_evaluation_task.py"
    )
    assert contract.observer_source_digest == sha256_file(
        ROOT / "scripts/observe_mode_evaluation_policy.py"
    )
    assert contract.judge_role_runner_source_digest == sha256_file(
        ROOT / "src/adaptation_compiler_lab/runners/codex_mode_judge.py"
    )
    assert contract.judge_source_digest == sha256_file(ROOT / "scripts/judge_mode_evaluation.py")
    assert contract.unblind_source_digest == sha256_file(
        ROOT / "scripts/unblind_mode_evaluation.py"
    )


def test_public_plan_is_deterministic_complete_and_condition_blind() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v1.json")
    public, private = build_mode_evaluation_plan(contract, seed=b"m" * 32)
    repeated, _ = build_mode_evaluation_plan(contract, seed=b"m" * 32)

    assert public == repeated
    assert len(public.run_order) == 30
    assert len({(item.task_id, item.blind_condition_id) for item in public.run_order}) == 30
    assert "core-only" not in public.model_dump_json()
    assert "core-plus-mode" not in public.model_dump_json()
    assert "condition_assignments" in private


def test_public_plan_rejects_an_incomplete_or_replayed_order() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v1.json")
    public, _ = build_mode_evaluation_plan(contract, seed=b"n" * 32)
    payload = public.model_dump(mode="json")
    payload["run_order"][-1]["run_id"] = payload["run_order"][0]["run_id"]

    with pytest.raises(ValueError, match="run IDs must be unique"):
        ModeEvaluationPublicPlanV1.model_validate_json(json.dumps(payload), strict=True)


def test_restricted_observer_accepts_fixture_policy_and_rejects_imports(tmp_path: Path) -> None:
    fixture_source = BENCHMARK / "fixtures/frontend/src/solution.py"
    assert _tree(fixture_source, "settings_layout")
    unsafe = tmp_path / "solution.py"
    unsafe.write_text(
        "import os\n\ndef settings_layout(width, state, reduced_motion):\n"
        "    return os.listdir('/')\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="only function definitions"):
        _tree(unsafe, "settings_layout")


def test_seed_requires_at_least_256_bits() -> None:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v1.json")

    with pytest.raises(ValueError, match="256 bits"):
        build_mode_evaluation_plan(contract, seed=b"short")


def test_judge_preference_must_select_an_output_in_the_bound_pair() -> None:
    with pytest.raises(ValueError, match="must select an output"):
        ModeJudgePairDecisionV1(
            task_id="task-one",
            ordered_output_ids=("output-a", "output-b"),
            preferred_output_id="output-c",
            rationale="The third identifier is not part of this anonymous comparison.",
        )


def _passing_mode_inputs() -> tuple[
    str,
    tuple[ModeEvaluationFixtureV1, ...],
    dict[str, dict[Literal["core-only", "core-plus-mode"], JsonObject]],
    ModeJudgeDecisionV1,
    dict[str, Literal["core-only", "core-plus-mode"]],
]:
    contract = load_mode_evaluation_contract(BENCHMARK / "EXECUTION_CONTRACT-v1.json")
    mode_id = "frontend-studio"
    fixtures = tuple(item for item in contract.fixtures if item.mode_id == mode_id)
    trials: dict[
        str,
        dict[Literal["core-only", "core-plus-mode"], JsonObject],
    ] = {}
    output_conditions: dict[str, Literal["core-only", "core-plus-mode"]] = {}
    ratings: list[ModeJudgePairDecisionV1] = []
    for index, fixture in enumerate(fixtures):
        core_output = f"output-core-{index}"
        mode_output = f"output-mode-{index}"
        core_passed = 4 if fixture.kind == "diagnostic" and index == 0 else 5
        trials[fixture.task_id] = {
            "core-only": {
                "blind_output_id": core_output,
                "checks_passed": core_passed,
                "checks_total": 5,
                "behavior_conformant": core_passed == 5,
                "behavior_failures": [] if core_passed == 5 else ["one hidden check failed"],
                "integrity_valid": True,
                "mode_projection_utf8_bytes": 0,
                "activation_exact": True,
                "deactivation_exact": True,
            },
            "core-plus-mode": {
                "blind_output_id": mode_output,
                "checks_passed": 5,
                "checks_total": 5,
                "behavior_conformant": True,
                "behavior_failures": [],
                "integrity_valid": True,
                "mode_projection_utf8_bytes": 800,
                "activation_exact": True,
                "deactivation_exact": True,
            },
        }
        output_conditions[core_output] = "core-only"
        output_conditions[mode_output] = "core-plus-mode"
        ratings.append(
            ModeJudgePairDecisionV1(
                task_id=fixture.task_id,
                ordered_output_ids=(core_output, mode_output),
                preferred_output_id=mode_output if index == 0 else None,
                rationale="The selected implementation is more complete, or the pair is tied.",
            )
        )
    decision = ModeJudgeDecisionV1(
        mode_id=mode_id,
        pair_ratings=tuple(ratings),
        overall_assessment="The Mode improves one diagnostic without harming neutral controls.",
        limitations=("This is a bounded same-agent development comparison.",),
    )
    return mode_id, fixtures, trials, decision, output_conditions


def test_frozen_mode_gate_requires_improvement_without_neutral_regression() -> None:
    mode_id, fixtures, trials, decision, output_conditions = _passing_mode_inputs()

    outcome = build_mode_outcome(
        mode_id=mode_id,
        fixtures=fixtures,
        trials_by_task=trials,
        decision=decision,
        output_conditions=output_conditions,
    )

    assert outcome.gate_passed is True
    assert outcome.diagnostic_mode_passed > outcome.diagnostic_core_passed
    assert outcome.neutral_mode_passed == outcome.neutral_core_passed
    assert outcome.permitted_claim == "bounded_same_agent_mode_evidence"


def test_frozen_mode_gate_rejects_a_neutral_control_regression() -> None:
    mode_id, fixtures, trials, decision, output_conditions = _passing_mode_inputs()
    neutral = next(item for item in fixtures if item.kind == "neutral_control")
    trials[neutral.task_id]["core-plus-mode"]["checks_passed"] = 4

    outcome = build_mode_outcome(
        mode_id=mode_id,
        fixtures=fixtures,
        trials_by_task=trials,
        decision=decision,
        output_conditions=output_conditions,
    )

    assert outcome.gate_passed is False
    assert "Mode regressed a neutral-control aggregate" in outcome.failure_reasons
