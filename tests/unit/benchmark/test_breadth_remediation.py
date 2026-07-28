from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_remediation import (
    BreadthRemediationTask,
    build_breadth_remediation_plan,
)
from scripts.run_breadth_remediation_judge import _strict_schema


def _tasks() -> tuple[BreadthRemediationTask, ...]:
    root = Path(__file__).parents[3] / "development_benchmark_breadth_remediation" / "tasks"
    return tuple(
        BreadthRemediationTask.model_validate_json(path.read_bytes())
        for path in sorted(root.glob("*/task.json"))
    )


def test_remediation_plan_is_deterministic_paired_and_blind() -> None:
    first_public, first_private = build_breadth_remediation_plan(
        design_digest="sha256:" + "1" * 64,
        tasks=_tasks(),
        seed=bytes(range(32)),
    )
    second_public, second_private = build_breadth_remediation_plan(
        design_digest="sha256:" + "1" * 64,
        tasks=_tasks(),
        seed=bytes(range(32)),
    )

    assert first_public == second_public
    assert first_private == second_private
    assert "compiled_adaptation" not in first_public.model_dump_json()
    assert "strong_static_profile" not in first_public.model_dump_json()
    assert all(
        first_public.run_order[index].task_id == first_public.run_order[index + 1].task_id
        for index in range(0, 10, 2)
    )


def test_remediation_judge_schema_is_strict() -> None:
    stack: list[object] = [_strict_schema()]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                assert node["required"] == list(properties)
                assert node["additionalProperties"] is False
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
