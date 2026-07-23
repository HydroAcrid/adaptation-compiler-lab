"""Strict local benchmark configuration and outcome data contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import Partition
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique

BlindConditionId = Annotated[
    str,
    StringConstraints(pattern=r"^cond-[0-9a-f]{12,64}$"),
]
BlindTaskId = Annotated[
    str,
    StringConstraints(pattern=r"^task-[0-9a-f]{12,64}$"),
]
BlindFamilyId = Annotated[
    str,
    StringConstraints(pattern=r"^family-[0-9a-f]{12,64}$"),
]


class BenchmarkCondition(StrEnum):
    """The four mandatory confirmatory conditions."""

    BASE = "base"
    ORDINARY_MEMORY = "ordinary_memory"
    STRONG_STATIC_PROFILE = "strong_static_profile"
    COMPILED_ADAPTATION = "compiled_adaptation"


class TaskStratum(StrEnum):
    """Required task strata from the benchmark protocol."""

    DIRECT_TRANSFER = "direct_transfer"
    FAILURE_RECURRENCE = "failure_recurrence"
    COMPOSITIONAL = "compositional"
    NEUTRAL_CONTROL = "neutral_control"
    CONFLICT_SAFETY = "conflict_safety"


class HeldOutOrigin(StrEnum):
    """Supported custody designs for an unseen task."""

    RETROSPECTIVE_SEALED = "retrospective_sealed"
    PROSPECTIVE = "prospective"


class AdaptationMaterialBudget(FrozenModel):
    """Common target-visible ceilings; shorter materials are never padded."""

    token_ceiling: Literal[3000] = 3000
    utf8_byte_ceiling: Literal[12000] = 12000
    pad_shorter_materials: Literal[False] = False
    report_actual_usage: Literal[True] = True


class OrdinaryMemoryProtocol(FrozenModel):
    """Frozen comparator rule that does not infer new procedures."""

    eligible_content: Literal["explicit_approved_user_feedback"] = "explicit_approved_user_feedback"
    ordering: Literal["observed_at_then_evidence_id"] = "observed_at_then_evidence_id"
    deduplication: Literal["exact_canonical_digest"] = "exact_canonical_digest"
    inferred_procedures_allowed: Literal[False] = False


class StrongProfileProtocol(FrozenModel):
    """Frozen independent-human comparator construction rule."""

    author_role: Literal["independent_skilled_human"] = "independent_skilled_human"
    time_limit_minutes: Literal[90] = 90
    same_eligible_corpus: Literal[True] = True
    held_out_access_allowed: Literal[False] = False
    author_may_score_results: Literal[False] = False


class FeasibilityTrialLimits(FrozenModel):
    """Preregistered live-pilot limits that later milestones must preserve."""

    per_trial_minutes: Literal[30] = 30
    per_trial_turns: Literal[40] = 40
    per_trial_usd: Literal[5] = 5
    total_pilot_usd: Literal[200] = 200
    retry_rule: Literal["one_pre_action_transient_provider_failure_only"] = (
        "one_pre_action_transient_provider_failure_only"
    )


class FeasibilityScoringPlan(FrozenModel):
    """Frozen scoring, validity, and follow-on decision thresholds."""

    automated_correctness_percent: Literal[60] = 60
    requirement_coverage_percent: Literal[25] = 25
    change_discipline_percent: Literal[15] = 15
    minimum_valid_trial_percent: Literal[90] = 90
    p_values_allowed: Literal[False] = False
    paired_by_task_and_repetition: Literal[True] = True
    bootstrap_intervals_exploratory_only: Literal[True] = True
    compiled_must_match_or_exceed_every_comparator: Literal[True] = True
    maximum_guardrail_regression_percentage_points: Literal[5] = 5
    unresolved_high_severity_adverse_cases_allowed: Literal[False] = False


class FeasibilityDesign(FrozenModel):
    """Machine-readable preregistration for the single descriptive pilot."""

    design_id: Literal["codex-to-claude-feasibility-v1"] = "codex-to-claude-feasibility-v1"
    protocol_version: Literal["1.0.0"] = "1.0.0"
    target_agent: Literal["Claude Code"] = "Claude Code"
    target_model_selection_rule: Literal[
        "stable_sonnet_full_id_pinned_in_milestone_4_before_source_construction"
    ] = "stable_sonnet_full_id_pinned_in_milestone_4_before_source_construction"
    task_families: Annotated[tuple[TaskStratum, ...], Field(min_length=4, max_length=4)] = (
        TaskStratum.DIRECT_TRANSFER,
        TaskStratum.FAILURE_RECURRENCE,
        TaskStratum.COMPOSITIONAL,
        TaskStratum.NEUTRAL_CONTROL,
    )
    held_out_task_count: Literal[4] = 4
    conditions: Annotated[tuple[BenchmarkCondition, ...], Field(min_length=4, max_length=4)] = (
        BenchmarkCondition.BASE,
        BenchmarkCondition.ORDINARY_MEMORY,
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    )
    repetitions_per_condition: Literal[2] = 2
    planned_target_runs: Literal[32] = 32
    adaptation_budget: AdaptationMaterialBudget = Field(default_factory=AdaptationMaterialBudget)
    ordinary_memory: OrdinaryMemoryProtocol = Field(default_factory=OrdinaryMemoryProtocol)
    strong_profile: StrongProfileProtocol = Field(default_factory=StrongProfileProtocol)
    trial_limits: FeasibilityTrialLimits = Field(default_factory=FeasibilityTrialLimits)
    scoring: FeasibilityScoringPlan = Field(default_factory=FeasibilityScoringPlan)
    held_out_payload_location: Literal["encrypted_external_custody_store"] = (
        "encrypted_external_custody_store"
    )
    construction_view: Literal["blind_ids_strata_and_signed_digest_only"] = (
        "blind_ids_strata_and_signed_digest_only"
    )
    study_classification: Literal["descriptive_feasibility_not_powered"] = (
        "descriptive_feasibility_not_powered"
    )

    @model_validator(mode="after")
    def design_is_the_frozen_pilot(self) -> Self:
        expected_families = (
            TaskStratum.DIRECT_TRANSFER,
            TaskStratum.FAILURE_RECURRENCE,
            TaskStratum.COMPOSITIONAL,
            TaskStratum.NEUTRAL_CONTROL,
        )
        expected_conditions = tuple(BenchmarkCondition)
        if self.task_families != expected_families:
            raise ValueError("feasibility pilot task families are frozen and ordered")
        if self.conditions != expected_conditions:
            raise ValueError("feasibility pilot conditions are frozen and ordered")
        if (
            self.held_out_task_count * len(self.conditions) * self.repetitions_per_condition
            != self.planned_target_runs
        ):
            raise ValueError("planned target runs must equal tasks x conditions x repetitions")
        return self


class BenchmarkTask(FrozenModel):
    """Opaque task registration; prompts and answers remain outside construction."""

    task_id: Identifier
    cluster_id: Identifier
    partition: Partition
    stratum: TaskStratum
    content_digest: Sha256Digest
    sampling_probability: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    created_at: UtcDateTime
    held_out_origin: HeldOutOrigin | None = None
    sealed_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def custody_fields_match_partition(self) -> Self:
        if self.partition is Partition.HELD_OUT:
            if self.held_out_origin is None or self.sealed_at is None:
                raise ValueError("held-out task requires origin and seal timestamp")
            if self.sealed_at < self.created_at:
                raise ValueError("held-out task cannot be sealed before it exists")
        elif self.held_out_origin is not None or self.sealed_at is not None:
            raise ValueError("only held-out tasks may carry held-out custody fields")
        return self


class TaskFamilyCluster(FrozenModel):
    """Highest independent task-family/repository grouping."""

    cluster_id: Identifier
    partition: Partition
    task_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]

    @field_validator("task_ids")
    @classmethod
    def task_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("cluster task IDs must be sorted and unique")
        return value


class BenchmarkEvaluationCase(FrozenModel):
    """Opaque case registration used to audit construction/holdout separation."""

    case_id: Identifier
    partition: Partition
    content_digest: Sha256Digest
    created_at: UtcDateTime


class TokenBudget(FrozenModel):
    """Frozen storage/runtime ceilings and confirmatory size-matching rung."""

    tokenizer_id: Identifier
    tokenizer_version: SemVer
    storage_ceiling: int = Field(gt=0)
    runtime_ceiling: int = Field(gt=0)
    utf8_byte_ceiling: int = Field(gt=0, default=12000)
    budget_ladder: Annotated[tuple[int, ...], Field(min_length=1)]
    minimum_viable_rung: int = Field(gt=0)
    c_match: int = Field(gt=0)

    @field_validator("budget_ladder")
    @classmethod
    def ladder_is_ascending_unique(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item <= 0 for item in value) or list(value) != sorted(set(value)):
            raise ValueError("budget ladder must contain ascending unique positive rungs")
        return value

    @model_validator(mode="after")
    def selected_rung_is_feasible(self) -> Self:
        if self.minimum_viable_rung not in self.budget_ladder:
            raise ValueError("minimum viable rung must appear in budget ladder")
        if self.c_match not in self.budget_ladder:
            raise ValueError("c_match must be selected from the registered budget ladder")
        if self.c_match < self.minimum_viable_rung:
            raise ValueError("c_match cannot be below the minimum viable rung")
        if self.c_match > min(self.storage_ceiling, self.runtime_ceiling):
            raise ValueError("c_match exceeds a source-derived condition ceiling")
        return self


class ConditionBundle(FrozenModel):
    """One immutable, blinded confirmatory condition bundle."""

    condition: BenchmarkCondition
    blind_id: BlindConditionId
    bundle_digest: Sha256Digest
    wrapper_digest: Sha256Digest
    material_digest: Sha256Digest
    stored_tokens: int = Field(ge=0)
    target_visible_tokens: int = Field(ge=0)
    stored_bytes: int = Field(ge=0, default=0)
    target_visible_bytes: int = Field(ge=0, default=0)
    source_task_ids: tuple[Identifier, ...] = ()
    source_evaluation_case_ids: tuple[Identifier, ...] = ()
    runtime_selector_digest: Sha256Digest | None = None
    frozen_at: UtcDateTime
    semantically_complete: Literal[True] = True
    padded: Literal[False] = False

    @field_validator("source_task_ids", "source_evaluation_case_ids")
    @classmethod
    def sources_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("condition source IDs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def base_has_no_adaptation_material(self) -> Self:
        if self.condition is BenchmarkCondition.BASE:
            if (
                self.stored_tokens
                or self.target_visible_tokens
                or self.stored_bytes
                or self.target_visible_bytes
            ):
                raise ValueError("base condition cannot contain adaptation tokens")
            if self.source_task_ids or self.source_evaluation_case_ids:
                raise ValueError("base condition cannot reference source-derived material")
        elif self.stored_tokens == 0 or self.target_visible_tokens == 0:
            raise ValueError("source-derived condition must contain a positive frozen bundle")
        if self.target_visible_tokens > self.stored_tokens:
            raise ValueError("target-visible tokens cannot exceed stored condition material")
        if self.target_visible_bytes > self.stored_bytes:
            raise ValueError("target-visible bytes cannot exceed stored condition material")
        if self.condition is not BenchmarkCondition.BASE and (
            self.stored_bytes == 0 or self.target_visible_bytes == 0
        ):
            raise ValueError("source-derived condition must contain positive UTF-8 bytes")
        return self


class FreezeMilestones(FrozenModel):
    """Two-stage registration and optional reveal/execution timestamps."""

    design_registered_at: UtcDateTime
    construction_cutoff: UtcDateTime
    condition_bundles_frozen_at: UtcDateTime
    split_manifest_digest: Sha256Digest
    custody_policy_version: SemVer
    held_out_revealed_at: UtcDateTime | None = None
    execution_started_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def freeze_order_is_monotonic(self) -> Self:
        if self.design_registered_at >= self.condition_bundles_frozen_at:
            raise ValueError("design registration must precede complete condition freeze")
        if self.construction_cutoff >= self.condition_bundles_frozen_at:
            raise ValueError("construction cutoff must precede complete condition freeze")
        if (
            self.held_out_revealed_at is not None
            and self.held_out_revealed_at <= self.condition_bundles_frozen_at
        ):
            raise ValueError("held-out reveal must follow complete condition freeze")
        if self.execution_started_at is not None:
            if self.held_out_revealed_at is None:
                raise ValueError("execution cannot begin before held-out reveal")
            if self.execution_started_at < self.held_out_revealed_at:
                raise ValueError("execution cannot precede held-out reveal")
        return self


class BenchmarkConfig(FrozenModel):
    """Complete local representation of a frozen four-condition experiment."""

    benchmark_id: Identifier
    protocol_version: SemVer
    target_agent: NonEmptyStr
    target_model: NonEmptyStr
    tasks: Annotated[tuple[BenchmarkTask, ...], Field(min_length=1)]
    clusters: Annotated[tuple[TaskFamilyCluster, ...], Field(min_length=1)]
    evaluation_cases: tuple[BenchmarkEvaluationCase, ...]
    condition_bundles: Annotated[tuple[ConditionBundle, ...], Field(min_length=4)]
    token_budget: TokenBudget
    freeze: FreezeMilestones
    planned_trials_per_cell: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_experimental_boundaries(self) -> Self:
        self._validate_conditions()
        task_by_id = self._validate_tasks_and_clusters()
        case_by_id = self._validate_case_registry()
        self._validate_bundles(task_by_id, case_by_id)
        self._validate_held_out_custody()
        return self

    def _validate_conditions(self) -> None:
        expected = set(BenchmarkCondition)
        observed = {bundle.condition for bundle in self.condition_bundles}
        if observed != expected or len(self.condition_bundles) != len(expected):
            raise ValueError("benchmark requires exactly one bundle for each of four conditions")
        blind_ids = [bundle.blind_id for bundle in self.condition_bundles]
        if len(blind_ids) != len(set(blind_ids)):
            raise ValueError("blind condition IDs must be unique")
        forbidden = {"base", "memory", "profile", "compiled", "adaptation", "cap"}
        if any(any(term in blind_id.casefold() for term in forbidden) for blind_id in blind_ids):
            raise ValueError("blind condition IDs must not reveal condition identity")
        if len({bundle.wrapper_digest for bundle in self.condition_bundles}) != 1:
            raise ValueError("all conditions must use the same frozen wrapper")

    def _validate_tasks_and_clusters(self) -> dict[str, BenchmarkTask]:
        task_by_id = {task.task_id: task for task in self.tasks}
        if len(task_by_id) != len(self.tasks):
            raise ValueError("benchmark task IDs must be unique")
        cluster_by_id = {cluster.cluster_id: cluster for cluster in self.clusters}
        if len(cluster_by_id) != len(self.clusters):
            raise ValueError("task-family cluster IDs must be unique")
        memberships: dict[str, str] = {}
        for cluster in self.clusters:
            for task_id in cluster.task_ids:
                if task_id not in task_by_id:
                    raise ValueError(f"cluster references unknown task {task_id!r}")
                if task_id in memberships:
                    raise ValueError(f"task {task_id!r} belongs to multiple clusters")
                task = task_by_id[task_id]
                if task.cluster_id != cluster.cluster_id or task.partition is not cluster.partition:
                    raise ValueError("task and cluster identity/partition must agree")
                memberships[task_id] = cluster.cluster_id
        if set(memberships) != set(task_by_id):
            raise ValueError("every benchmark task must belong to exactly one cluster")
        required_partitions = {Partition.CONSTRUCTION, Partition.DEVELOPMENT, Partition.HELD_OUT}
        if not required_partitions <= {cluster.partition for cluster in self.clusters}:
            raise ValueError("construction, development, and held-out clusters are required")
        return task_by_id

    def _validate_case_registry(self) -> dict[str, BenchmarkEvaluationCase]:
        case_by_id = {item.case_id: item for item in self.evaluation_cases}
        if len(case_by_id) != len(self.evaluation_cases):
            raise ValueError("benchmark evaluation-case IDs must be unique")
        return case_by_id

    def _validate_bundles(
        self,
        task_by_id: dict[str, BenchmarkTask],
        case_by_id: dict[str, BenchmarkEvaluationCase],
    ) -> None:
        allowed_source_partitions = {Partition.CONSTRUCTION, Partition.DEVELOPMENT}
        for bundle in self.condition_bundles:
            if bundle.frozen_at > self.freeze.condition_bundles_frozen_at:
                raise ValueError("condition bundle changed after complete bundle freeze")
            if bundle.frozen_at <= max(
                self.freeze.design_registered_at, self.freeze.construction_cutoff
            ):
                raise ValueError(
                    "condition bundle must freeze after design and construction cutoff"
                )
            if (
                self.freeze.held_out_revealed_at is not None
                and bundle.frozen_at >= self.freeze.held_out_revealed_at
            ):
                raise ValueError("condition bundle must freeze before held-out reveal")
            if bundle.runtime_selector_digest is not None:
                raise ValueError("confirmatory condition bundles cannot use runtime selectors")
            if bundle.condition is BenchmarkCondition.BASE:
                continue
            if bundle.stored_tokens != bundle.target_visible_tokens:
                raise ValueError("confirmatory bundle storage and target-visible size must match")
            if bundle.stored_bytes != bundle.target_visible_bytes:
                raise ValueError(
                    "confirmatory bundle stored and target-visible UTF-8 bytes must match"
                )
            if bundle.stored_tokens > self.token_budget.storage_ceiling:
                raise ValueError("condition bundle exceeds storage ceiling")
            if bundle.target_visible_tokens > self.token_budget.runtime_ceiling:
                raise ValueError("condition bundle exceeds runtime ceiling")
            if bundle.target_visible_bytes > self.token_budget.utf8_byte_ceiling:
                raise ValueError("condition bundle exceeds UTF-8 byte ceiling")
            if not bundle.source_task_ids:
                raise ValueError("source-derived condition must identify construction inputs")
            for task_id in bundle.source_task_ids:
                task = task_by_id.get(task_id)
                if task is None:
                    raise ValueError(f"condition references unknown source task {task_id!r}")
                if task.partition not in allowed_source_partitions:
                    raise ValueError("held-out or synthetic task influenced condition construction")
                if task.created_at > self.freeze.construction_cutoff:
                    raise ValueError("source task was created after the construction cutoff")
                if task.created_at > bundle.frozen_at:
                    raise ValueError("source task did not exist when its condition bundle froze")
            for case_id in bundle.source_evaluation_case_ids:
                case = case_by_id.get(case_id)
                if case is None:
                    raise ValueError(f"condition references unknown evaluation case {case_id!r}")
                if case.partition not in allowed_source_partitions | {Partition.SYNTHETIC}:
                    raise ValueError("held-out evaluation case influenced condition construction")
                if case.created_at > self.freeze.construction_cutoff:
                    raise ValueError("evaluation case was created after the construction cutoff")
                if case.created_at > bundle.frozen_at:
                    raise ValueError(
                        "evaluation case did not exist when its condition bundle froze"
                    )
        source_task_sets = {
            bundle.source_task_ids
            for bundle in self.condition_bundles
            if bundle.condition is not BenchmarkCondition.BASE
        }
        if len(source_task_sets) != 1:
            raise ValueError("all source-derived conditions require equal construction-task access")
        source_evaluation_case_sets = {
            bundle.source_evaluation_case_ids
            for bundle in self.condition_bundles
            if bundle.condition is not BenchmarkCondition.BASE
        }
        if len(source_evaluation_case_sets) != 1:
            raise ValueError(
                "all source-derived conditions require equal construction-evaluation access"
            )

    def _validate_held_out_custody(self) -> None:
        for task in self.tasks:
            if task.partition is not Partition.HELD_OUT:
                continue
            if task.held_out_origin is HeldOutOrigin.RETROSPECTIVE_SEALED:
                if task.sealed_at is None or task.sealed_at > self.freeze.design_registered_at:
                    raise ValueError(
                        "retrospective held-out task must be sealed by design registration"
                    )
            elif task.created_at <= self.freeze.condition_bundles_frozen_at:
                raise ValueError("prospective held-out task must arise after condition freeze")
            if (
                self.freeze.held_out_revealed_at is not None
                and task.sealed_at is not None
                and task.sealed_at > self.freeze.held_out_revealed_at
            ):
                raise ValueError("held-out task must be sealed before reveal")


class BenchmarkOutcomeRecord(FrozenModel):
    """Reproducible result row keyed only by a blinded condition identifier."""

    run_id: Identifier
    task_id: Identifier
    cluster_id: Identifier
    blind_condition_id: BlindConditionId
    trial_index: int = Field(gt=0)
    functional_score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    adaptation_score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    quality_score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    catastrophic_safety_violation: bool = False
    build_succeeded: bool
    correction_turns: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    duration_seconds: float = Field(ge=0.0, allow_inf_nan=False)

    @property
    def normalized_utility(self) -> float:
        """Compute the preregistered primary endpoint for this run."""

        if self.catastrophic_safety_violation:
            return 0.0
        return (
            0.60 * self.functional_score + 0.25 * self.adaptation_score + 0.15 * self.quality_score
        )
