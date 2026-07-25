from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.benchmark.claude_development import (
    CLAUDE_DEVELOPMENT_CONDITIONS,
    build_claude_development_plan,
    load_claude_development_design,
)
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def _root() -> Path:
    return Path(__file__).parents[3] / "development_benchmark_claude"


def test_design_is_a_budgeted_nonheldout_cross_agent_development_gate() -> None:
    design = load_claude_development_design(_root(), frozen_at=NOW)

    assert len(design.tasks) == 4
    assert {item.family for item in design.tasks} == set(ApprovedSourceFamily)
    assert design.conditions == CLAUDE_DEVELOPMENT_CONDITIONS
    assert design.planned_runs == 16
    assert design.model == "claude-haiku-4-5-20251001"
    assert design.max_usd_per_run == 1.0
    assert design.max_usd_total == 18.0
    assert not design.retry_allowed
    assert not design.held_out
    assert not design.milestone_6_custody_accessed
    assert design.cross_agent_development_evidence
    assert not design.general_thesis_claim_allowed


def test_plan_is_complete_blinded_and_seed_deterministic() -> None:
    design = load_claude_development_design(_root(), frozen_at=NOW)
    first_private, first_public = build_claude_development_plan(
        design=design,
        seed=RandomizationSeed(b"h" * 32),
        created_at=NOW,
    )
    second_private, second_public = build_claude_development_plan(
        design=design,
        seed=RandomizationSeed(b"h" * 32),
        created_at=NOW,
    )

    assert first_private == second_private
    assert first_public == second_public
    assert len(first_private.run_order) == 16
    assert (
        len(
            {
                (item.task_id, item.blind_condition_id, item.repetition)
                for item in first_private.run_order
            }
        )
        == 16
    )
    assert first_public.private_plan_digest == first_private.content_digest
    assert first_public.condition_mapping_withheld
    assert "compiled_adaptation" not in first_public.model_dump_json()
    assert "strong_static_profile" not in first_public.model_dump_json()
