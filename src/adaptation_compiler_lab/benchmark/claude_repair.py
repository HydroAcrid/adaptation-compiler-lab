"""Typed four-cell public Claude benchmark repair."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.claude_development import (
    CLAUDE_DEVELOPMENT_CONDITIONS,
    ClaudeDevelopmentConditionAssignment,
    ClaudeDevelopmentEncryptedPayloadRef,
    ClaudeDevelopmentRunObservation,
    ClaudeDevelopmentTask,
)
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
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest

CLAUDE_REPAIR_TASK_DIRECTORIES = ("communication", "environment_safety")
CLAUDE_REPAIR_FAMILIES = {
    ApprovedSourceFamily.COMMUNICATION,
    ApprovedSourceFamily.ENVIRONMENT_SAFETY,
}


class ClaudeRepairDesign(FrozenModel):
    """Two repaired public tasks crossed with two frozen conditions once."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["claude-haiku-compiler-v2-public-repair"] = (
        "claude-haiku-compiler-v2-public-repair"
    )
    tasks: Annotated[tuple[ClaudeDevelopmentTask, ...], Field(min_length=2, max_length=2)]
    conditions: tuple[BenchmarkCondition, BenchmarkCondition] = CLAUDE_DEVELOPMENT_CONDITIONS
    repetitions_per_condition: Literal[1] = 1
    planned_runs: Literal[4] = 4
    cli_version: Literal["2.1.218"] = "2.1.218"
    model: Literal["claude-haiku-4-5-20251001"] = "claude-haiku-4-5-20251001"
    compiler_renderer_version: Literal["2.0.0"] = "2.0.0"
    max_seconds: Literal[600] = 600
    max_turns: Literal[20] = 20
    max_usd_per_run: float = Field(default=0.25, ge=0.25, le=0.25, allow_inf_nan=False)
    max_usd_total: float = Field(default=1.0, ge=1.0, le=1.0, allow_inf_nan=False)
    retry_allowed: Literal[False] = False
    held_out: Literal[False] = False
    milestone_6_custody_accessed: Literal[False] = False
    cross_agent_development_evidence: Literal[True] = True
    general_thesis_claim_allowed: Literal[False] = False
    frozen_at: UtcDateTime

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        if self.conditions != CLAUDE_DEVELOPMENT_CONDITIONS:
            raise ValueError("Claude repair must compare strong and compiled v2")
        task_ids = tuple(item.task_id for item in self.tasks)
        if not strings_are_sorted_unique(task_ids):
            raise ValueError("Claude repair tasks must be sorted and unique")
        if {item.family for item in self.tasks} != CLAUDE_REPAIR_FAMILIES:
            raise ValueError("Claude repair tasks must cover communication and environment safety")
        if len(self.tasks) * len(self.conditions) != self.planned_runs:
            raise ValueError("Claude repair requires a complete 2 x 2 grid")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeRepairRunCell(FrozenModel):
    sequence: int = Field(ge=1, le=4)
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier
    repetition: Literal[1] = 1


class ClaudeRepairPrivatePlan(FrozenModel):
    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    condition_assignments: Annotated[
        tuple[ClaudeDevelopmentConditionAssignment, ...],
        Field(min_length=2, max_length=2),
    ]
    run_order: Annotated[tuple[ClaudeRepairRunCell, ...], Field(min_length=4, max_length=4)]
    created_at: UtcDateTime
    milestone_6_custody_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_exact(self) -> Self:
        if tuple(item.condition for item in self.condition_assignments) != (
            CLAUDE_DEVELOPMENT_CONDITIONS
        ):
            raise ValueError("Claude repair condition mapping is incomplete")
        if tuple(item.sequence for item in self.run_order) != (1, 2, 3, 4):
            raise ValueError("Claude repair plan requires four contiguous cells")
        condition_ids = {item.blind_condition_id for item in self.condition_assignments}
        cells = {(item.task_id, item.blind_condition_id) for item in self.run_order}
        if len(condition_ids) != 2 or len(cells) != 4:
            raise ValueError("Claude repair plan must contain the complete 2 x 2 grid")
        if {item.blind_condition_id for item in self.run_order} != condition_ids:
            raise ValueError("Claude repair plan contains an unknown condition")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeRepairPublicPlan(FrozenModel):
    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[tuple[ClaudeRepairRunCell, ...], Field(min_length=4, max_length=4)]
    private_plan_digest: Sha256Digest
    created_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False

    @field_validator("blind_condition_ids")
    @classmethod
    def blind_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("Claude repair condition IDs must be sorted and unique")
        return value


class ClaudeRepairProgressReceipt(FrozenModel):
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier
    bundle_ref: ClaudeDevelopmentEncryptedPayloadRef
    completed: int = Field(ge=1, le=4)
    valid: bool


class ClaudeRepairCompletionReceipt(FrozenModel):
    blind_packet_digest: Sha256Digest
    blind_report_digest: Sha256Digest
    blind_report_ref: ClaudeDevelopmentEncryptedPayloadRef
    completed_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False
    private_plan_ref: ClaudeDevelopmentEncryptedPayloadRef
    raw_retention_deadline: UtcDateTime
    runs: Literal[4] = 4
    scores_withheld: Literal[True] = True
    total_cost_usd: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def retention_follows_completion(self) -> Self:
        if self.raw_retention_deadline <= self.completed_at:
            raise ValueError("raw retention deadline must follow completion")
        return self


class ClaudeRepairBlindReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    observations: Annotated[
        tuple[ClaudeDevelopmentRunObservation, ...],
        Field(min_length=4, max_length=4),
    ]
    condition_mapping_withheld: Literal[True] = True
    scores_withheld_from_preference_scorer: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False
    created_at: UtcDateTime

    @model_validator(mode="after")
    def report_is_exact(self) -> Self:
        run_ids = {item.run_id for item in self.observations}
        output_ids = {item.blind_output_id for item in self.observations}
        cells = {(item.task_id, item.blind_condition_id) for item in self.observations}
        if len(run_ids) != 4 or len(output_ids) != 4 or len(cells) != 4:
            raise ValueError("Claude repair report requires four unique complete cells")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_claude_repair_design(
    root: Path,
    *,
    frozen_at: UtcDateTime,
) -> ClaudeRepairDesign:
    tasks_root = root.resolve() / "tasks"
    tasks = []
    for directory in CLAUDE_REPAIR_TASK_DIRECTORIES:
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
    return ClaudeRepairDesign(
        tasks=tuple(sorted(tasks, key=lambda item: item.task_id)),
        frozen_at=frozen_at,
    )


def build_claude_repair_plan(
    *,
    design: ClaudeRepairDesign,
    seed: RandomizationSeed,
    created_at: UtcDateTime,
) -> tuple[ClaudeRepairPrivatePlan, ClaudeRepairPublicPlan]:
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
        (task.task_id, assignment.blind_condition_id)
        for task in design.tasks
        for assignment in assignments
    )
    shuffled = seed.shuffled(unshuffled, domain=f"{design.design_id}/run-order")
    run_order = []
    for sequence, (task_id, condition_id) in enumerate(shuffled, start=1):
        stable_key = f"{task_id}:{condition_id}:1"
        output_id = seed.blind_id(
            prefix="output",
            domain=f"{design.design_id}/output",
            stable_key=stable_key,
        )
        run_digest = hashlib.sha256(f"{seed.commitment}:{stable_key}".encode()).hexdigest()
        run_order.append(
            ClaudeRepairRunCell(
                sequence=sequence,
                run_id=f"run-{run_digest[:24]}",
                task_id=task_id,
                blind_condition_id=condition_id,
                blind_output_id=output_id,
            )
        )
    private = ClaudeRepairPrivatePlan(
        design_digest=design.content_digest,
        randomization_seed_commitment=seed.commitment,
        condition_assignments=assignments,
        run_order=tuple(run_order),
        created_at=created_at,
    )
    public = ClaudeRepairPublicPlan(
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
