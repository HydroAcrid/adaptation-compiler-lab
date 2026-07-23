"""Sealed internal-pilot bundle contract tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.heldout import (
    FrozenConditionPayload,
    HeldOutFile,
    HeldOutRubric,
    HeldOutTaskPayload,
    SealedHeldOutPlanBundle,
    SealedInternalPilotBundle,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition, TaskStratum
from adaptation_compiler_lab.benchmark.randomization import (
    RandomizationSeed,
    build_software_custody_plan,
)

NOW = datetime(2026, 7, 23, 18, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
TASK_IDS = tuple(f"task-{index:012x}" for index in range(1, 5))


def _task(index: int, stratum: TaskStratum) -> HeldOutTaskPayload:
    return HeldOutTaskPayload(
        task_key=f"hidden-task-{index}",
        blind_task_id=TASK_IDS[index - 1],
        stratum=stratum,
        prompt="Implement the requested behavior in the supplied synthetic fixture.",
        fixture_files=(HeldOutFile(relative_path="project.py", content="VALUE = 1\n"),),
        independent_test_files=(
            HeldOutFile(
                relative_path="tests_hidden/test_project.py", content="def test_x(): pass\n"
            ),
        ),
        test_command=("python", "-m", "pytest", "-q"),
        allowed_bash_commands=("python -m pytest -q",),
        rubric=HeldOutRubric(
            objective_requirements=("Independent tests pass.",),
            preference_requirements=("Explain important risk before action.",),
        ),
        created_at=NOW,
    )


def _condition(condition: BenchmarkCondition) -> FrozenConditionPayload:
    text = "" if condition is BenchmarkCondition.BASE else f"{condition.value} material"
    return FrozenConditionPayload(
        condition=condition,
        material_digest=f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}",
        text=text,
        target_tokens=0 if not text else 10,
        utf8_bytes=len(text.encode("utf-8")),
    )


def test_complete_secret_bundle_cross_binds_tasks_conditions_and_plan() -> None:
    plan = build_software_custody_plan(
        seed=RandomizationSeed(b"s" * 32),
        benchmark_id="benchmark-internal-feasibility-1",
        blind_task_ids=TASK_IDS,
        construction_cutoff=NOW,
        created_at=NOW + timedelta(minutes=1),
    )
    bundle = SealedInternalPilotBundle(
        benchmark_id=plan.benchmark_id,
        construction_cutoff=NOW,
        source_corpus_digest=DIGEST,
        held_out_tasks=tuple(
            _task(index, stratum)
            for index, stratum in enumerate(
                (
                    TaskStratum.DIRECT_TRANSFER,
                    TaskStratum.FAILURE_RECURRENCE,
                    TaskStratum.COMPOSITIONAL,
                    TaskStratum.NEUTRAL_CONTROL,
                ),
                start=1,
            )
        ),
        condition_materials=tuple(_condition(item) for item in BenchmarkCondition),
        software_custody_plan=plan,
        frozen_at=NOW + timedelta(hours=1),
    )

    assert bundle.content_digest.startswith("sha256:")


def test_heldout_plan_bundle_can_freeze_before_condition_construction() -> None:
    plan = build_software_custody_plan(
        seed=RandomizationSeed(b"s" * 32),
        benchmark_id="benchmark-internal-feasibility-1",
        blind_task_ids=TASK_IDS,
        construction_cutoff=NOW,
        created_at=NOW + timedelta(minutes=1),
    )
    tasks = tuple(
        _task(index, stratum)
        for index, stratum in enumerate(
            (
                TaskStratum.DIRECT_TRANSFER,
                TaskStratum.FAILURE_RECURRENCE,
                TaskStratum.COMPOSITIONAL,
                TaskStratum.NEUTRAL_CONTROL,
            ),
            start=1,
        )
    )

    bundle = SealedHeldOutPlanBundle(
        benchmark_id=plan.benchmark_id,
        construction_cutoff=NOW,
        held_out_tasks=tasks,
        software_custody_plan=plan,
        held_out_author_packet_digest=DIGEST,
        held_out_author_receipt_digest="sha256:" + "b" * 64,
        sealed_at=NOW + timedelta(minutes=2),
    )

    assert bundle.content_digest.startswith("sha256:")


@pytest.mark.parametrize("path", ["/absolute.py", "../escape.py", ".git/config"])
def test_heldout_paths_cannot_escape_or_mutate_git(path: str) -> None:
    with pytest.raises(ValidationError, match="safe POSIX-relative"):
        HeldOutFile(relative_path=path, content="synthetic")
