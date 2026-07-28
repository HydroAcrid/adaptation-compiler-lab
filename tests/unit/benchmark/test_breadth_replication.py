from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthProfileSet,
    BreadthReplicationTask,
    build_breadth_plan,
    seed_commitment,
    validate_breadth_profile_content,
)
from scripts.render_breadth_compiled_materials import render_breadth_compiled_materials
from scripts.run_breadth_judge import _strict_schema as judge_schema
from scripts.run_breadth_profile_construction import _strict_schema as profile_schema


def _tasks() -> tuple[BreadthReplicationTask, ...]:
    root = Path(__file__).parents[3] / "development_benchmark_breadth_replication" / "tasks"
    return tuple(
        BreadthReplicationTask.model_validate_json(path.read_bytes())
        for path in sorted(root.glob("*/task.json"))
    )


def test_breadth_randomization_is_deterministic_paired_and_blind() -> None:
    seed = bytes(range(32))
    first_public, first_private = build_breadth_plan(
        design_digest="sha256:" + "1" * 64,
        tasks=_tasks(),
        seed=seed,
    )
    second_public, second_private = build_breadth_plan(
        design_digest="sha256:" + "1" * 64,
        tasks=_tasks(),
        seed=seed,
    )

    assert first_public == second_public
    assert first_private == second_private
    assert "compiled_adaptation" not in first_public.model_dump_json()
    assert "strong_static_profile" not in first_public.model_dump_json()
    assert all(
        first_public.run_order[index].task_id == first_public.run_order[index + 1].task_id
        for index in range(0, 16, 2)
    )
    assert seed_commitment(seed) != "sha256:" + "0" * 64


def test_profile_contract_has_three_bounded_stages() -> None:
    profile = BreadthProfileSet(stage_1="one", stage_2="two", stage_3="three")

    assert profile.stage_1 == "one"
    assert len(profile.model_dump()) == 4


def test_profile_content_validation_accepts_cumulative_author_draft() -> None:
    root = Path(__file__).parents[3] / "development_benchmark_breadth_replication"
    profile = BreadthProfileSet.model_validate_json(
        (root / "profile-author-output.json").read_bytes()
    )

    validate_breadth_profile_content(profile)


def test_profile_content_validation_rejects_unresolved_stage_references() -> None:
    root = Path(__file__).parents[3] / "development_benchmark_breadth_replication"
    profile = BreadthProfileSet.model_validate_json(
        (root / "rejected-profile-reviewer-output-v1.json").read_bytes()
    )

    try:
        validate_breadth_profile_content(profile)
    except ValueError as error:
        assert "unresolved stage reference" in str(error)
    else:
        raise AssertionError("non-standalone profile unexpectedly passed")


def test_compiled_materials_match_renderer_and_are_smaller_than_profile() -> None:
    root = Path(__file__).parents[3] / "development_benchmark_breadth_replication"
    rendered = render_breadth_compiled_materials()
    profile = BreadthProfileSet.model_validate_json(
        (root / "profile-reviewer-output.json").read_bytes()
    )

    assert all(
        (root / f"condition-materials/compiled-stage-{stage}.md").read_text(encoding="utf-8")
        == value
        for stage, value in enumerate(rendered, start=1)
    )
    assert all(
        len(compiled.encode("utf-8")) < len(strong.encode("utf-8"))
        for compiled, strong in zip(
            rendered,
            (profile.stage_1, profile.stage_2, profile.stage_3),
            strict=True,
        )
    )


def test_structured_role_schemas_are_strict_for_every_object() -> None:
    for schema in (profile_schema(), judge_schema()):
        stack: list[object] = [schema]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    assert node["required"] == list(properties)
                    assert node["additionalProperties"] is False
                prefix = node.get("prefixItems")
                if isinstance(prefix, list) and prefix:
                    assert node.get("items") == prefix[0]
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
