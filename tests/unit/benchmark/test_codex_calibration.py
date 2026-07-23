from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.codex_calibration import (
    CALIBRATION_CONDITIONS,
    CodexCalibrationPreferenceRating,
    CodexCalibrationUnblindedResult,
    build_codex_calibration_plan,
    load_codex_calibration_design,
    unblind_codex_calibration_preference,
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


def test_pairwise_preference_is_frozen_before_mapping_and_then_unblinded() -> None:
    design = load_codex_calibration_design(_root(), frozen_at=NOW)
    private, public = build_codex_calibration_plan(
        design=design,
        seed=RandomizationSeed(b"c" * 32),
        created_at=NOW,
    )
    ordered = (
        public.run_order[0].blind_output_id,
        public.run_order[1].blind_output_id,
    )
    rating = CodexCalibrationPreferenceRating(
        rating_id="calibration-rating-kevin-0001",
        public_plan_digest=public.content_digest,
        blind_report_digest="sha256:" + "a" * 64,
        presentation_sha256="sha256:" + "b" * 64,
        ordered_output_ids=ordered,
        preference="first_better",
        preferred_output_id=ordered[0],
        rationale="The first output has the better failure mode.",
        rated_at=NOW,
    )

    result = unblind_codex_calibration_preference(
        design=design,
        public_plan=public,
        private_plan=private,
        rating=rating,
        created_at=NOW,
    )

    condition_by_blind = {
        item.blind_condition_id: item.condition for item in private.condition_assignments
    }
    expected = condition_by_blind[private.run_order[0].blind_condition_id]
    assert result.preferred_condition is expected
    assert result.other_condition is not expected
    assert not result.cross_agent_claim_allowed
    assert not result.milestone_6_custody_accessed


def test_pairwise_rating_rejects_preference_that_disagrees_with_order() -> None:
    with pytest.raises(ValueError, match="does not match"):
        CodexCalibrationPreferenceRating(
            rating_id="calibration-rating-kevin-0001",
            public_plan_digest="sha256:" + "a" * 64,
            blind_report_digest="sha256:" + "b" * 64,
            presentation_sha256="sha256:" + "c" * 64,
            ordered_output_ids=("output-first", "output-second"),
            preference="first_better",
            preferred_output_id="output-second",
            rationale="Mismatch.",
            rated_at=NOW,
        )


def test_committed_rating_precedes_and_binds_unblinded_result() -> None:
    rating = CodexCalibrationPreferenceRating.model_validate_json(
        (_root() / "codex-development-v2-kevin-rating.json").read_text(encoding="utf-8")
    )
    result = CodexCalibrationUnblindedResult.model_validate_json(
        (_root() / "codex-development-v2-unblinded-result.json").read_text(encoding="utf-8")
    )

    assert not rating.condition_mapping_seen
    assert rating.rated_at < result.created_at
    assert result.preference_rating_digest == rating.content_digest
    assert result.preferred_condition is CALIBRATION_CONDITIONS[1]
    assert result.other_condition is CALIBRATION_CONDITIONS[0]
