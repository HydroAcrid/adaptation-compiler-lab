from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    build_task_channel_plan,
    load_task_channel_design,
    seed_commitment,
)
from scripts.run_fair_task_channel_judge import _terminal_failure_summary


def test_randomization_is_deterministic_blocked_and_condition_blind() -> None:
    root = Path(__file__).parents[3] / "development_benchmark_task_channel_comparison"
    design = load_task_channel_design(root)
    seed = bytes(range(32))
    first_public, first_private = build_task_channel_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed,
    )
    second_public, second_private = build_task_channel_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed,
    )

    assert first_public == second_public
    assert first_private == second_private
    public_json = first_public.model_dump_json()
    assert "compiled_adaptation" not in public_json
    assert "strong_static_profile" not in public_json
    assert all(
        first_public.run_order[index].task_id == first_public.run_order[index + 1].task_id
        for index in range(0, 12, 2)
    )


def test_randomization_seed_changes_commitment_and_order() -> None:
    root = Path(__file__).parents[3] / "development_benchmark_task_channel_comparison"
    design = load_task_channel_design(root)
    first_seed = bytes(range(32))
    second_seed = bytes(reversed(range(32)))
    first, _ = build_task_channel_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=first_seed,
    )
    second, _ = build_task_channel_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=second_seed,
    )

    assert seed_commitment(first_seed) != seed_commitment(second_seed)
    assert first.seed_commitment != second.seed_commitment
    assert first.run_order != second.run_order


def test_terminal_failure_summary_retains_provider_diagnostic() -> None:
    trace = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"turn.failed","error":{"code":"rate_limit",'
        b'"message":"temporary capacity limit"}}\n'
    )

    assert _terminal_failure_summary(trace) == {
        "event_count": 3,
        "terminal_count": 1,
        "trace_parseable": True,
        "terminal_type": "turn.failed",
        "error_code": "rate_limit",
        "error_message": "temporary capacity limit",
    }
