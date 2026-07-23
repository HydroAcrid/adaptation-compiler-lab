"""Typed two-cell Codex development calibration, separate from the historical v1 grid."""

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
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest

CALIBRATION_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)


class CodexCalibrationDesign(FrozenModel):
    """One v2 development task evaluated under exactly two frozen conditions."""

    design_version: Literal["2.0.0"] = "2.0.0"
    design_id: Literal["codex-development-v2-research-calibration"] = (
        "codex-development-v2-research-calibration"
    )
    task: CodexDevelopmentTask
    conditions: tuple[BenchmarkCondition, BenchmarkCondition] = CALIBRATION_CONDITIONS
    planned_runs: Literal[2] = 2
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
        if self.conditions != CALIBRATION_CONDITIONS:
            raise ValueError("calibration must compare only strong profile and compiled adaptation")
        if self.task.family is not ApprovedSourceFamily.RESEARCH_INTEGRITY:
            raise ValueError("calibration task must belong to the research-integrity family")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexCalibrationConditionAssignment(FrozenModel):
    """Secret condition-to-blind-ID mapping."""

    condition: BenchmarkCondition
    blind_condition_id: Identifier


class CodexCalibrationRunCell(FrozenModel):
    """One condition-blind cell in the committed two-run order."""

    sequence: int = Field(ge=1, le=2)
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class CodexCalibrationPrivatePlan(FrozenModel):
    """Secret randomized mapping stored only under development encryption."""

    plan_version: Literal["2.0.0"] = "2.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    condition_assignments: Annotated[
        tuple[CodexCalibrationConditionAssignment, ...],
        Field(min_length=2, max_length=2),
    ]
    run_order: Annotated[
        tuple[CodexCalibrationRunCell, ...],
        Field(min_length=2, max_length=2),
    ]
    created_at: UtcDateTime
    milestone_6_custody_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_exact(self) -> Self:
        if tuple(item.condition for item in self.condition_assignments) != CALIBRATION_CONDITIONS:
            raise ValueError("calibration condition mapping is incomplete")
        if tuple(item.sequence for item in self.run_order) != (1, 2):
            raise ValueError("calibration sequence must contain exactly two cells")
        condition_ids = tuple(item.blind_condition_id for item in self.condition_assignments)
        if len(set(condition_ids)) != 2:
            raise ValueError("calibration blind condition IDs must be unique")
        if {item.blind_condition_id for item in self.run_order} != set(condition_ids):
            raise ValueError("calibration run order must use each blind condition once")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexCalibrationPublicPlan(FrozenModel):
    """Condition-blind two-cell commitment safe to expose."""

    plan_version: Literal["2.0.0"] = "2.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[
        tuple[CodexCalibrationRunCell, ...],
        Field(min_length=2, max_length=2),
    ]
    private_plan_digest: Sha256Digest
    created_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False

    @field_validator("blind_condition_ids")
    @classmethod
    def blind_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("calibration blind condition IDs must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexCalibrationBlindReport(FrozenModel):
    """Two anonymous observations with the condition mapping withheld."""

    report_version: Literal["2.0.0"] = "2.0.0"
    design_digest: Sha256Digest
    observations: Annotated[
        tuple[CodexDevelopmentRunObservation, ...],
        Field(min_length=2, max_length=2),
    ]
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False
    created_at: UtcDateTime

    @model_validator(mode="after")
    def report_is_exact(self) -> Self:
        if len({item.run_id for item in self.observations}) != 2:
            raise ValueError("calibration report requires two unique run IDs")
        if len({item.blind_condition_id for item in self.observations}) != 2:
            raise ValueError("calibration report requires two unique blind conditions")
        if len({item.task_id for item in self.observations}) != 1:
            raise ValueError("calibration report must cover exactly one task")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_codex_calibration_design(
    root: Path,
    *,
    frozen_at: UtcDateTime,
) -> CodexCalibrationDesign:
    """Load and bind the exact v2 research-integrity task bytes."""

    task_root = root.resolve() / "tasks" / "research_integrity"
    value = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
    value["family"] = ApprovedSourceFamily(value["family"])
    for field in ("visible_test_command", "allowed_change_paths", "neutral_control_requirements"):
        value[field] = tuple(value[field])
    task = CodexDevelopmentTask(
        **value,
        fixture_digest=development_tree_digest(task_root / "fixture"),
        independent_scorer_digest=development_tree_digest(task_root / "independent"),
    )
    return CodexCalibrationDesign(task=task, frozen_at=frozen_at)


def build_codex_calibration_plan(
    *,
    design: CodexCalibrationDesign,
    seed: RandomizationSeed,
    created_at: UtcDateTime,
) -> tuple[CodexCalibrationPrivatePlan, CodexCalibrationPublicPlan]:
    """Create a deterministic, development-only two-cell blind plan."""

    assignments = tuple(
        CodexCalibrationConditionAssignment(
            condition=condition,
            blind_condition_id=seed.blind_id(
                prefix="cond",
                domain=f"{design.design_id}/condition",
                stable_key=condition.value,
            ),
        )
        for condition in design.conditions
    )
    shuffled = seed.shuffled(
        tuple(item.blind_condition_id for item in assignments),
        domain=f"{design.design_id}/run-order",
    )
    run_order = tuple(
        CodexCalibrationRunCell(
            sequence=sequence,
            run_id=f"calibration-run-{sequence:04d}",
            task_id=design.task.task_id,
            blind_condition_id=condition_id,
            blind_output_id=seed.blind_id(
                prefix="output",
                domain=f"{design.design_id}/output",
                stable_key=condition_id,
            ),
        )
        for sequence, condition_id in enumerate(shuffled, start=1)
    )
    private = CodexCalibrationPrivatePlan(
        design_digest=design.content_digest,
        randomization_seed_commitment=seed.commitment,
        condition_assignments=assignments,
        run_order=run_order,
        created_at=created_at,
    )
    public = CodexCalibrationPublicPlan(
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
