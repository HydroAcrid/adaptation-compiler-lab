"""Typed six-cell Codex v2 development gate, separate from Milestone 6 custody."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
    CodexDevelopmentTask,
    development_tree_digest,
)
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

V2_GATE_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)
V2_GATE_FAMILIES = frozenset(
    {
        ApprovedSourceFamily.COMMUNICATION,
        ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION,
        ApprovedSourceFamily.ENVIRONMENT_SAFETY,
    }
)
V2_GATE_TASK_DIRECTORIES = (
    "communication",
    "debugging_and_verification",
    "environment_safety",
)


class CodexV2GateDesign(FrozenModel):
    """Three public development tasks evaluated under two frozen conditions."""

    design_version: Literal["2.1.0"] = "2.1.0"
    design_id: Literal["codex-development-v2-remaining-gate"] = (
        "codex-development-v2-remaining-gate"
    )
    task_count: Literal[3] = 3
    tasks: Annotated[tuple[CodexDevelopmentTask, ...], Field(min_length=3, max_length=3)]
    conditions: tuple[BenchmarkCondition, BenchmarkCondition] = V2_GATE_CONDITIONS
    planned_runs: Literal[6] = 6
    cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["medium"] = "medium"
    service_mode: Literal["standard"] = "standard"
    max_seconds: Literal[600] = 600
    retry_allowed: Literal[False] = False
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    milestone_6_custody_accessed: Literal[False] = False
    cross_agent_claim_allowed: Literal[False] = False
    frozen_at: UtcDateTime

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        if self.conditions != V2_GATE_CONDITIONS:
            raise ValueError("v2 gate must compare only strong profile and compiled adaptation")
        task_ids = tuple(item.task_id for item in self.tasks)
        if not strings_are_sorted_unique(task_ids):
            raise ValueError("v2 gate tasks must be sorted and unique")
        if {item.family for item in self.tasks} != V2_GATE_FAMILIES:
            raise ValueError("v2 gate must cover the three remaining approved source families")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexV2GateConditionAssignment(FrozenModel):
    """Secret condition-to-blind-ID mapping."""

    condition: BenchmarkCondition
    blind_condition_id: Identifier


class CodexV2GateRunCell(FrozenModel):
    """One condition-blind cell in the six-run order."""

    sequence: int = Field(ge=1, le=6)
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class CodexV2GatePrivatePlan(FrozenModel):
    """Secret randomized mapping encrypted outside the repository."""

    plan_version: Literal["2.1.0"] = "2.1.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    condition_assignments: Annotated[
        tuple[CodexV2GateConditionAssignment, ...],
        Field(min_length=2, max_length=2),
    ]
    run_order: Annotated[
        tuple[CodexV2GateRunCell, ...],
        Field(min_length=6, max_length=6),
    ]
    created_at: UtcDateTime
    milestone_6_custody_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_exact(self) -> Self:
        if tuple(item.condition for item in self.condition_assignments) != V2_GATE_CONDITIONS:
            raise ValueError("v2 gate condition mapping is incomplete")
        if tuple(item.sequence for item in self.run_order) != tuple(range(1, 7)):
            raise ValueError("v2 gate sequence must contain six contiguous cells")
        condition_ids = tuple(item.blind_condition_id for item in self.condition_assignments)
        if len(set(condition_ids)) != 2:
            raise ValueError("v2 gate blind condition IDs must be unique")
        cells = {(item.task_id, item.blind_condition_id) for item in self.run_order}
        task_ids = {item.task_id for item in self.run_order}
        if len(task_ids) != 3 or len(cells) != 6:
            raise ValueError("v2 gate run order must contain the complete 3 x 2 grid")
        if {item.blind_condition_id for item in self.run_order} != set(condition_ids):
            raise ValueError("v2 gate run order contains an unknown blind condition")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexV2GatePublicPlan(FrozenModel):
    """Condition-blind six-cell commitment safe to expose."""

    plan_version: Literal["2.1.0"] = "2.1.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[
        tuple[CodexV2GateRunCell, ...],
        Field(min_length=6, max_length=6),
    ]
    private_plan_digest: Sha256Digest
    created_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False

    @field_validator("blind_condition_ids")
    @classmethod
    def blind_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("v2 gate blind condition IDs must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexV2GateBlindReport(FrozenModel):
    """Six anonymous observations with scores and condition mapping withheld."""

    report_version: Literal["2.1.0"] = "2.1.0"
    design_digest: Sha256Digest
    observations: Annotated[
        tuple[CodexDevelopmentRunObservation, ...],
        Field(min_length=6, max_length=6),
    ]
    condition_mapping_withheld: Literal[True] = True
    scores_withheld_from_preference_scorer: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False
    created_at: UtcDateTime

    @model_validator(mode="after")
    def report_is_exact(self) -> Self:
        run_ids = {item.run_id for item in self.observations}
        output_ids = {item.blind_output_id for item in self.observations}
        condition_ids = {item.blind_condition_id for item in self.observations}
        cells = {(item.task_id, item.blind_condition_id) for item in self.observations}
        task_ids = {item.task_id for item in self.observations}
        if len(run_ids) != 6 or len(output_ids) != 6:
            raise ValueError("v2 gate report requires six unique runs and outputs")
        if len(condition_ids) != 2 or len(task_ids) != 3 or len(cells) != 6:
            raise ValueError("v2 gate report must cover the complete 3 x 2 grid")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexV2GateTaskPreference(FrozenModel):
    """One anonymous pairwise preference for a public development task."""

    task_id: Identifier
    ordered_output_ids: tuple[Identifier, Identifier]
    preference: Literal["first_better", "second_better", "tie"]
    preferred_output_id: Identifier | None
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def preference_matches_order(self) -> Self:
        if len(set(self.ordered_output_ids)) != 2:
            raise ValueError("v2 task rating requires two unique output IDs")
        expected = {
            "first_better": self.ordered_output_ids[0],
            "second_better": self.ordered_output_ids[1],
            "tie": None,
        }[self.preference]
        if self.preferred_output_id != expected:
            raise ValueError("v2 task preference does not match the frozen output order")
        return self


class CodexV2GatePreferenceRating(FrozenModel):
    """Kevin's three pairwise ratings frozen before the condition mapping opens."""

    rating_version: Literal["2.1.0"] = "2.1.0"
    rating_id: Identifier
    public_plan_digest: Sha256Digest
    blind_report_digest: Sha256Digest
    presentation_sha256: Sha256Digest
    task_preferences: Annotated[
        tuple[CodexV2GateTaskPreference, ...],
        Field(min_length=3, max_length=3),
    ]
    scorer_identity: Literal["kevin"] = "kevin"
    condition_mapping_seen: Literal[False] = False
    rated_at: UtcDateTime

    @model_validator(mode="after")
    def rating_is_complete(self) -> Self:
        task_ids = tuple(item.task_id for item in self.task_preferences)
        if not strings_are_sorted_unique(task_ids):
            raise ValueError("v2 gate task ratings must be sorted and unique")
        output_ids = tuple(
            output_id
            for preference in self.task_preferences
            for output_id in preference.ordered_output_ids
        )
        if len(set(output_ids)) != 6:
            raise ValueError("v2 gate ratings must cover six unique outputs")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_codex_v2_gate_design(
    root: Path,
    *,
    frozen_at: UtcDateTime,
) -> CodexV2GateDesign:
    """Load and bind the three remaining public v2 task trees."""

    tasks_root = root.resolve() / "tasks"
    tasks = []
    for directory in V2_GATE_TASK_DIRECTORIES:
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
            CodexDevelopmentTask(
                **value,
                fixture_digest=development_tree_digest(task_root / "fixture"),
                independent_scorer_digest=development_tree_digest(task_root / "independent"),
            )
        )
    return CodexV2GateDesign(
        tasks=tuple(sorted(tasks, key=lambda item: item.task_id)),
        frozen_at=frozen_at,
    )


def build_codex_v2_gate_plan(
    *,
    design: CodexV2GateDesign,
    seed: RandomizationSeed,
    created_at: UtcDateTime,
) -> tuple[CodexV2GatePrivatePlan, CodexV2GatePublicPlan]:
    """Create a deterministic development-only six-cell blind plan."""

    assignments = tuple(
        CodexV2GateConditionAssignment(
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
    run_order = tuple(
        CodexV2GateRunCell(
            sequence=sequence,
            run_id=f"v2-gate-run-{sequence:04d}",
            task_id=task_id,
            blind_condition_id=condition_id,
            blind_output_id=seed.blind_id(
                prefix="output",
                domain=f"{design.design_id}/output",
                stable_key=f"{task_id}:{condition_id}",
            ),
        )
        for sequence, (task_id, condition_id) in enumerate(shuffled, start=1)
    )
    private = CodexV2GatePrivatePlan(
        design_digest=design.content_digest,
        randomization_seed_commitment=seed.commitment,
        condition_assignments=assignments,
        run_order=run_order,
        created_at=created_at,
    )
    public = CodexV2GatePublicPlan(
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
