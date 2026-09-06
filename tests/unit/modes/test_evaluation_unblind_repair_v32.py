"""Deterministic checks for the Mode evaluation v3.2 unblind repair."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.modes.evaluation import ModeJudgeDecisionV1
from adaptation_compiler_lab.serialization import canonical_json
from scripts.mode_evaluation_v31_judge_common import load_object
from scripts.mode_evaluation_v32_unblind_common import validate_unblind_repair

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "development_benchmark_mode_evaluation"


def test_v32_repair_binds_completed_judges_without_reruns() -> None:
    contract = validate_unblind_repair(ROOT)

    assert contract["target_grid_reexecution_allowed"] is False
    assert contract["judge_reexecution_allowed"] is False
    assert contract["provider_billed_calls"] == 0


def test_v32_parses_the_json_round_trip_strictly() -> None:
    receipt = load_object(BENCHMARK / "results-v3/judges-v31/frontend-studio.json")
    raw_decision = receipt["decision"]
    assert isinstance(raw_decision, dict)

    decision = ModeJudgeDecisionV1.model_validate_json(canonical_json(raw_decision), strict=True)

    assert decision.content_digest == receipt["decision_digest"]


def test_v32_has_not_written_a_result_before_execution() -> None:
    assert not (BENCHMARK / "results-v3/unblinded-result-v32.json").exists()
    assert not (BENCHMARK / "results-v3/MODE_EVALUATION_RESULT-v32.md").exists()
