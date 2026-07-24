"""Typed public Claude Haiku development gate for compiler v2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.randomization import (
    RANDOMIZATION_ALGORITHM,
    RandomizationSeed,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest

CLAUDE_DEVELOPMENT_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)
CLAUDE_DEVELOPMENT_TASK_DIRECTORIES = (
    "communication",
    "debugging_and_verification",
    "environment_safety",
    "research_integrity",
)


class ClaudeDevelopmentTask(FrozenModel):
    """One public task tree never used by the frozen Milestone 6 study."""

    task_id: Identifier
    family: ApprovedSourceFamily
    prompt: NonEmptyStr
    fixture_digest: Sha256Digest
    independent_scorer_digest: Sha256Digest
    visible_test_command: tuple[NonEmptyStr, ...]
    allowed_change_paths: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    neutral_control_requirements: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    held_out: Literal[False] = False

    @field_validator("allowed_change_paths", "neutral_control_requirements")
    @classmethod
    def sequences_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("Claude development-task sequences must be sorted and unique")
        return value

    @field_validator("visible_test_command")
    @classmethod
    def command_is_safe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item or "\x00" in item for item in value):
            raise ValueError("Claude development visible-test command is invalid")
        return value


class ClaudeDevelopmentDesign(FrozenModel):
    """Four tasks, two conditions, and two repetitions under a USD $18 gate."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["claude-haiku-compiler-v2-development-gate"] = (
        "claude-haiku-compiler-v2-development-gate"
    )
    tasks: Annotated[tuple[ClaudeDevelopmentTask, ...], Field(min_length=4, max_length=4)]
    conditions: tuple[BenchmarkCondition, BenchmarkCondition] = CLAUDE_DEVELOPMENT_CONDITIONS
    repetitions_per_condition: Literal[2] = 2
    planned_runs: Literal[16] = 16
    cli_version: Literal["2.1.218"] = "2.1.218"
    model: Literal["claude-haiku-4-5-20251001"] = "claude-haiku-4-5-20251001"
    compiler_renderer_version: Literal["2.0.0"] = "2.0.0"
    max_seconds: Literal[600] = 600
    max_turns: Literal[20] = 20
    max_usd_per_run: float = Field(default=1.0, ge=1.0, le=1.0, allow_inf_nan=False)
    max_usd_total: float = Field(default=18.0, ge=18.0, le=18.0, allow_inf_nan=False)
    retry_allowed: Literal[False] = False
    held_out: Literal[False] = False
    milestone_6_custody_accessed: Literal[False] = False
    cross_agent_development_evidence: Literal[True] = True
    general_thesis_claim_allowed: Literal[False] = False
    frozen_at: UtcDateTime

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        if self.conditions != CLAUDE_DEVELOPMENT_CONDITIONS:
            raise ValueError("Claude development gate must compare strong and compiled v2")
        task_ids = tuple(item.task_id for item in self.tasks)
        if not strings_are_sorted_unique(task_ids):
            raise ValueError("Claude development tasks must be sorted and unique")
        if {item.family for item in self.tasks} != set(ApprovedSourceFamily):
            raise ValueError("Claude development tasks must cover all approved source families")
        if (
            len(self.tasks) * len(self.conditions) * self.repetitions_per_condition
            != self.planned_runs
        ):
            raise ValueError("Claude development run count must equal tasks x conditions x reps")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeDevelopmentConditionAssignment(FrozenModel):
    condition: BenchmarkCondition
    blind_condition_id: Identifier


class ClaudeDevelopmentRunCell(FrozenModel):
    sequence: int = Field(ge=1, le=16)
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier
    repetition: int = Field(ge=1, le=2)


class ClaudeDevelopmentPrivatePlan(FrozenModel):
    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    condition_assignments: Annotated[
        tuple[ClaudeDevelopmentConditionAssignment, ...],
        Field(min_length=2, max_length=2),
    ]
    run_order: Annotated[
        tuple[ClaudeDevelopmentRunCell, ...],
        Field(min_length=16, max_length=16),
    ]
    created_at: UtcDateTime
    milestone_6_custody_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_exact(self) -> Self:
        if tuple(item.condition for item in self.condition_assignments) != (
            CLAUDE_DEVELOPMENT_CONDITIONS
        ):
            raise ValueError("Claude development condition mapping is incomplete")
        if tuple(item.sequence for item in self.run_order) != tuple(range(1, 17)):
            raise ValueError("Claude development plan requires sixteen contiguous cells")
        condition_ids = {item.blind_condition_id for item in self.condition_assignments}
        cells = {
            (item.task_id, item.blind_condition_id, item.repetition) for item in self.run_order
        }
        if len(condition_ids) != 2 or len(cells) != 16:
            raise ValueError("Claude development plan must contain the complete 4 x 2 x 2 grid")
        if {item.blind_condition_id for item in self.run_order} != condition_ids:
            raise ValueError("Claude development plan contains an unknown condition")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeDevelopmentPublicPlan(FrozenModel):
    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[
        tuple[ClaudeDevelopmentRunCell, ...],
        Field(min_length=16, max_length=16),
    ]
    private_plan_digest: Sha256Digest
    created_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False

    @field_validator("blind_condition_ids")
    @classmethod
    def blind_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("Claude development condition IDs must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeDevelopmentRunObservation(FrozenModel):
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier
    repetition: int = Field(ge=1, le=2)
    condition_digest: Sha256Digest
    trace_digest: Sha256Digest
    diff_digest: Sha256Digest
    final_response_digest: Sha256Digest
    scorer_output_digest: Sha256Digest
    command_digest: Sha256Digest
    environment_digest: Sha256Digest
    started_at: UtcDateTime
    finished_at: UtcDateTime
    duration_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    input_tokens: int = Field(ge=0)
    cache_creation_input_tokens: int = Field(ge=0)
    cache_read_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    objective_checks_passed: int = Field(ge=0)
    objective_checks_total: int = Field(ge=1)
    diagnostic_checks_passed: int = Field(ge=0)
    diagnostic_checks_total: int = Field(ge=1)
    neutral_checks_passed: int = Field(ge=0)
    neutral_checks_total: int = Field(ge=1)
    timed_out: bool
    exit_code: int | None
    trace_conformant: bool
    config_destroyed: bool
    workspace_destroyed: bool
    condition_leakage_observed: bool
    valid: bool
    invalid_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def terminal_state_is_coherent(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("Claude development run cannot finish before it starts")
        for passed, total in (
            (self.objective_checks_passed, self.objective_checks_total),
            (self.diagnostic_checks_passed, self.diagnostic_checks_total),
            (self.neutral_checks_passed, self.neutral_checks_total),
        ):
            if passed > total:
                raise ValueError("Claude development passed checks cannot exceed totals")
        if self.valid != (self.invalid_reason is None):
            raise ValueError("invalid Claude development run requires exactly one reason")
        return self


class ClaudeDevelopmentBlindReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    observations: Annotated[
        tuple[ClaudeDevelopmentRunObservation, ...],
        Field(min_length=16, max_length=16),
    ]
    condition_mapping_withheld: Literal[True] = True
    scores_withheld_from_preference_scorer: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False
    created_at: UtcDateTime

    @model_validator(mode="after")
    def report_is_exact(self) -> Self:
        run_ids = {item.run_id for item in self.observations}
        output_ids = {item.blind_output_id for item in self.observations}
        cells = {
            (item.task_id, item.blind_condition_id, item.repetition) for item in self.observations
        }
        if len(run_ids) != 16 or len(output_ids) != 16 or len(cells) != 16:
            raise ValueError("Claude development report requires sixteen unique complete cells")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_claude_development_design(
    root: Path,
    *,
    frozen_at: UtcDateTime,
) -> ClaudeDevelopmentDesign:
    tasks_root = root.resolve() / "tasks"
    tasks = []
    for directory in CLAUDE_DEVELOPMENT_TASK_DIRECTORIES:
        task_root = tasks_root / directory
        value = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
        value["family"] = ApprovedSourceFamily(value["family"])
        for field in (
            "visible_test_command",
            "allowed_change_paths",
            "neutral_control_requirements",
        ):
            value[field] = tuple(value[field])
        tasks.append(
            ClaudeDevelopmentTask(
                **value,
                fixture_digest=development_tree_digest(task_root / "fixture"),
                independent_scorer_digest=development_tree_digest(task_root / "independent"),
            )
        )
    return ClaudeDevelopmentDesign(
        tasks=tuple(sorted(tasks, key=lambda item: item.task_id)),
        frozen_at=frozen_at,
    )


def build_claude_development_plan(
    *,
    design: ClaudeDevelopmentDesign,
    seed: RandomizationSeed,
    created_at: UtcDateTime,
) -> tuple[ClaudeDevelopmentPrivatePlan, ClaudeDevelopmentPublicPlan]:
    assignments = tuple(
        ClaudeDevelopmentConditionAssignment(
            condition=condition,
            blind_condition_id=seed.blind_id(
                prefix="cond",
                domain=f"{design.design_id}/condition",
                stable_key=condition.value,
            ),
        )
        for condition in design.conditions
    )
    unshuffled = tuple(
        (task.task_id, assignment.blind_condition_id, repetition)
        for task in design.tasks
        for assignment in assignments
        for repetition in range(1, design.repetitions_per_condition + 1)
    )
    shuffled = seed.shuffled(unshuffled, domain=f"{design.design_id}/run-order")
    run_order = []
    for sequence, (task_id, condition_id, repetition) in enumerate(shuffled, start=1):
        stable_key = f"{task_id}:{condition_id}:{repetition}"
        output_id = seed.blind_id(
            prefix="output",
            domain=f"{design.design_id}/output",
            stable_key=stable_key,
        )
        run_digest = hashlib.sha256(f"{seed.commitment}:{stable_key}".encode()).hexdigest()
        run_order.append(
            ClaudeDevelopmentRunCell(
                sequence=sequence,
                run_id=f"run-{run_digest[:24]}",
                task_id=task_id,
                blind_condition_id=condition_id,
                blind_output_id=output_id,
                repetition=repetition,
            )
        )
    private = ClaudeDevelopmentPrivatePlan(
        design_digest=design.content_digest,
        randomization_seed_commitment=seed.commitment,
        condition_assignments=assignments,
        run_order=tuple(run_order),
        created_at=created_at,
    )
    public = ClaudeDevelopmentPublicPlan(
        design_digest=design.content_digest,
        randomization_seed_commitment=seed.commitment,
        blind_condition_ids=tuple(
            sorted(item.blind_condition_id for item in private.condition_assignments)
        ),
        run_order=private.run_order,
        private_plan_digest=private.content_digest,
        created_at=created_at,
    )
    return private, public
