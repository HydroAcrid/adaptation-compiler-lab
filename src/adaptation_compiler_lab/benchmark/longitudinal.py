"""Frozen public comparison design for Milestone 6A."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.serialization import canonical_digest

LONGITUDINAL_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)


class LongitudinalTaskScenario(FrozenModel):
    """One independently scored call against a task implementation."""

    scenario_id: Identifier
    destination_exists: bool
    backup_requested: bool
    expected_action: Literal[
        "create",
        "backup_then_replace",
        "atomic_replace",
        "refuse",
    ]
    expected_plan: tuple[str, ...]
    metric: Literal["objective", "diagnostic", "neutral"]


class LongitudinalDevelopmentTask(FrozenModel):
    """One public task bound to one evidence stage and implementation surface."""

    task_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    task_kind: Literal["action", "plan"]
    context_kind: Literal["persistent_destination", "disposable_generated_cache"]
    fixture_directory: NonEmptyStr
    task_prompt: NonEmptyStr
    visible_test_command: Literal["python3 -m unittest -v"] = "python3 -m unittest -v"
    scenarios: Annotated[tuple[LongitudinalTaskScenario, ...], Field(min_length=3)]

    @field_validator("scenarios")
    @classmethod
    def scenarios_are_sorted_unique(
        cls, value: tuple[LongitudinalTaskScenario, ...]
    ) -> tuple[LongitudinalTaskScenario, ...]:
        ids = tuple(item.scenario_id for item in value)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("longitudinal task scenarios must be sorted and unique")
        if {item.metric for item in value} != {"diagnostic", "neutral", "objective"}:
            raise ValueError("each task requires objective, diagnostic, and neutral scenarios")
        return value


class LongitudinalComparisonDesign(FrozenModel):
    """Exact 3-stage x 2-task x 2-condition subscription-only comparison."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a-longitudinal-development"] = (
        "milestone-6a-longitudinal-development"
    )
    tasks: Annotated[
        tuple[LongitudinalDevelopmentTask, ...],
        Field(min_length=6, max_length=6),
    ]
    conditions: tuple[BenchmarkCondition, BenchmarkCondition] = LONGITUDINAL_CONDITIONS
    evidence_stage_count: Literal[3] = 3
    tasks_per_stage: Literal[2] = 2
    repetitions_per_condition_task: Literal[1] = 1
    planned_target_runs: Literal[12] = 12
    maximum_target_runs: Literal[12] = 12
    profile_author_sessions: Literal[3] = 3
    profile_review_sessions: Literal[3] = 3
    isolated_judge_sessions: Literal[1] = 1
    maximum_subscription_sessions: Literal[19] = 19
    cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["medium"] = "medium"
    service_mode: Literal["standard"] = "standard"
    target_permissions: Literal["workspace-write"] = "workspace-write"
    target_timeout_seconds: Literal[600] = 600
    target_turn_limit: Literal[1] = 1
    target_network_access: Literal[False] = False
    ambient_context_allowed: Literal[False] = False
    task_workspace_access_only: Literal[True] = True
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    api_keys_allowed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    retries_allowed: Literal[False] = False
    fresh_ephemeral_sessions: Literal[True] = True
    same_eligible_evidence_for_both_conditions: Literal[True] = True
    isolated_judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    isolated_judge_reasoning_effort: Literal["xhigh"] = "xhigh"
    isolated_judge_is_condition_blind: Literal[True] = True
    condition_material_byte_ceiling: Literal[12000] = 12000
    automated_correctness_is_primary: Literal[True] = True
    sealed_external_validation_accessed: Literal[False] = False
    target_runs_executed: Literal[False] = False
    frozen_at: UtcDateTime

    @model_validator(mode="after")
    def grid_is_exact(self) -> Self:
        if self.conditions != LONGITUDINAL_CONDITIONS:
            raise ValueError("longitudinal comparison conditions changed")
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("longitudinal tasks must be sorted and unique")
        stage_counts = Counter(item.stage for item in self.tasks)
        if stage_counts != Counter({1: 2, 2: 2, 3: 2}):
            raise ValueError("longitudinal comparison needs exactly two tasks per stage")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_longitudinal_comparison(root: Path) -> LongitudinalComparisonDesign:
    """Load the frozen public design and verify every fixture path."""

    path = root / "PREREGISTRATION-v1.0.json"
    design = LongitudinalComparisonDesign.model_validate_json(path.read_bytes())
    for task in design.tasks:
        fixture = (root / task.fixture_directory).resolve()
        if root.resolve() not in fixture.parents or not fixture.is_dir():
            raise ValueError(f"longitudinal fixture is missing or escapes the root: {task.task_id}")
        manifest = fixture.parent / "task.json"
        if not manifest.is_file():
            raise ValueError(f"longitudinal task manifest is missing: {task.task_id}")
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        if raw != task.model_dump(mode="json", round_trip=True):
            raise ValueError(f"longitudinal task manifest drifted: {task.task_id}")
    return design
