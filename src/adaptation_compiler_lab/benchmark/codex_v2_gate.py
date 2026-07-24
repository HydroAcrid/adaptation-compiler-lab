"""Typed six-cell Codex v2 development gate, separate from Milestone 6 custody."""

from __future__ import annotations

import json
from collections.abc import Mapping
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


class CodexV2GateCheckCounts(FrozenModel):
    """Passed and available checks for one score group."""

    passed: int = Field(ge=0)
    total: int = Field(ge=1)

    @model_validator(mode="after")
    def passed_does_not_exceed_total(self) -> Self:
        if self.passed > self.total:
            raise ValueError("v2 gate passed checks cannot exceed total checks")
        return self


class CodexV2GateConditionResult(FrozenModel):
    """One unblinded task/condition result."""

    condition: BenchmarkCondition
    blind_output_id: Identifier
    valid: bool
    objective: CodexV2GateCheckCounts
    diagnostic: CodexV2GateCheckCounts
    neutral: CodexV2GateCheckCounts
    failed_checks: tuple[NonEmptyStr, ...]
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)

    @field_validator("failed_checks")
    @classmethod
    def failed_checks_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("v2 gate failed checks must be sorted and unique")
        return value


class CodexV2GateTaskResult(FrozenModel):
    """One post-rating task comparison."""

    task_id: Identifier
    preference: Literal["first_better", "second_better", "tie"]
    preferred_condition: BenchmarkCondition | None
    other_condition: BenchmarkCondition | None
    condition_results: tuple[CodexV2GateConditionResult, CodexV2GateConditionResult]

    @model_validator(mode="after")
    def task_result_is_coherent(self) -> Self:
        if tuple(item.condition for item in self.condition_results) != V2_GATE_CONDITIONS:
            raise ValueError("v2 task results must use the frozen condition order")
        if self.preference == "tie":
            if self.preferred_condition is not None or self.other_condition is not None:
                raise ValueError("v2 tied preference must omit both condition identities")
        elif (
            self.preferred_condition is None
            or self.other_condition is None
            or self.preferred_condition == self.other_condition
        ):
            raise ValueError("v2 non-tied preference must identify two different conditions")
        return self


class CodexV2GateConditionAggregate(FrozenModel):
    """Aggregate descriptive result for one condition."""

    condition: BenchmarkCondition
    preference_wins: int = Field(ge=0, le=3)
    objective: CodexV2GateCheckCounts
    diagnostic: CodexV2GateCheckCounts
    neutral: CodexV2GateCheckCounts
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)


class CodexV2GateUnblindedResult(FrozenModel):
    """Post-rating result under the preregistered development-only decision rule."""

    result_version: Literal["2.1.0"] = "2.1.0"
    benchmark_id: Literal["codex-development-v2-remaining-gate"] = (
        "codex-development-v2-remaining-gate"
    )
    design_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    private_plan_digest: Sha256Digest
    blind_report_digest: Sha256Digest
    preference_rating_digest: Sha256Digest
    task_results: Annotated[
        tuple[CodexV2GateTaskResult, ...],
        Field(min_length=3, max_length=3),
    ]
    condition_aggregates: tuple[
        CodexV2GateConditionAggregate,
        CodexV2GateConditionAggregate,
    ]
    decision: Literal[
        "compiled_strict_win",
        "compiled_tie_or_better",
        "compiled_below_strong",
    ]
    tie_or_better_rule_passed: bool
    strict_win_rule_passed: bool
    decision_reason: NonEmptyStr
    cross_agent_claim_allowed: Literal[False] = False
    milestone_6_custody_accessed: Literal[False] = False
    created_at: UtcDateTime

    @model_validator(mode="after")
    def result_is_coherent(self) -> Self:
        task_ids = tuple(item.task_id for item in self.task_results)
        if not strings_are_sorted_unique(task_ids):
            raise ValueError("v2 unblinded task results must be sorted and unique")
        if tuple(item.condition for item in self.condition_aggregates) != V2_GATE_CONDITIONS:
            raise ValueError("v2 aggregates must use the frozen condition order")
        expected_decision = (
            "compiled_strict_win"
            if self.strict_win_rule_passed
            else (
                "compiled_tie_or_better"
                if self.tie_or_better_rule_passed
                else "compiled_below_strong"
            )
        )
        if self.decision != expected_decision:
            raise ValueError("v2 decision does not match its preregistered rule flags")
        if self.strict_win_rule_passed and not self.tie_or_better_rule_passed:
            raise ValueError("v2 strict win requires the tie-or-better rule")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def unblind_codex_v2_gate(
    *,
    design: CodexV2GateDesign,
    public_plan: CodexV2GatePublicPlan,
    private_plan: CodexV2GatePrivatePlan,
    blind_report: CodexV2GateBlindReport,
    rating: CodexV2GatePreferenceRating,
    failed_checks_by_output: Mapping[str, tuple[str, ...]],
    created_at: UtcDateTime,
) -> CodexV2GateUnblindedResult:
    """Unblind only after the rating and all public/private commitments match."""

    if public_plan.design_digest != design.content_digest:
        raise ValueError("v2 public plan substituted its design")
    if private_plan.design_digest != design.content_digest:
        raise ValueError("v2 private plan substituted its design")
    if blind_report.design_digest != design.content_digest:
        raise ValueError("v2 blind report substituted its design")
    if public_plan.private_plan_digest != private_plan.content_digest:
        raise ValueError("v2 private mapping failed its public commitment")
    if rating.public_plan_digest != public_plan.content_digest:
        raise ValueError("v2 rating substituted its public plan")
    if rating.blind_report_digest != blind_report.content_digest:
        raise ValueError("v2 rating substituted its blind report")
    if rating.rated_at < blind_report.created_at:
        raise ValueError("v2 rating predates its blind report")
    if created_at < rating.rated_at:
        raise ValueError("v2 unblinding predates the frozen rating")

    public_by_output = {item.blind_output_id: item for item in public_plan.run_order}
    observations_by_output = {item.blind_output_id: item for item in blind_report.observations}
    if set(public_by_output) != set(observations_by_output):
        raise ValueError("v2 report outputs differ from the public plan")
    for output_id, observation in observations_by_output.items():
        cell = public_by_output[output_id]
        if (
            observation.run_id != cell.run_id
            or observation.task_id != cell.task_id
            or observation.blind_condition_id != cell.blind_condition_id
        ):
            raise ValueError("v2 observation differs from its public run cell")
    if set(failed_checks_by_output) != set(observations_by_output):
        raise ValueError("v2 failed-check details do not cover every output")

    condition_by_blind = {
        item.blind_condition_id: item.condition for item in private_plan.condition_assignments
    }
    task_results = []
    for preference in rating.task_preferences:
        expected_output_order = tuple(
            item.blind_output_id
            for item in sorted(
                (cell for cell in public_plan.run_order if cell.task_id == preference.task_id),
                key=lambda item: item.sequence,
            )
        )
        if preference.ordered_output_ids != expected_output_order:
            raise ValueError("v2 task rating substituted its output order")
        condition_results = []
        for condition in V2_GATE_CONDITIONS:
            observation = next(
                item
                for item in blind_report.observations
                if item.task_id == preference.task_id
                and condition_by_blind[item.blind_condition_id] is condition
            )
            condition_results.append(
                CodexV2GateConditionResult(
                    condition=condition,
                    blind_output_id=observation.blind_output_id,
                    valid=observation.valid,
                    objective=CodexV2GateCheckCounts(
                        passed=observation.objective_checks_passed,
                        total=observation.objective_checks_total,
                    ),
                    diagnostic=CodexV2GateCheckCounts(
                        passed=observation.diagnostic_checks_passed,
                        total=observation.diagnostic_checks_total,
                    ),
                    neutral=CodexV2GateCheckCounts(
                        passed=observation.neutral_checks_passed,
                        total=observation.neutral_checks_total,
                    ),
                    failed_checks=tuple(
                        sorted(failed_checks_by_output[observation.blind_output_id])
                    ),
                    input_tokens=observation.input_tokens,
                    cached_input_tokens=observation.cached_input_tokens,
                    output_tokens=observation.output_tokens,
                    reasoning_output_tokens=observation.reasoning_output_tokens,
                )
            )
        if preference.preferred_output_id is None:
            preferred_condition = None
            other_condition = None
        else:
            preferred_observation = observations_by_output[preference.preferred_output_id]
            preferred_condition = condition_by_blind[preferred_observation.blind_condition_id]
            other_condition = next(
                condition
                for condition in V2_GATE_CONDITIONS
                if condition is not preferred_condition
            )
        task_results.append(
            CodexV2GateTaskResult(
                task_id=preference.task_id,
                preference=preference.preference,
                preferred_condition=preferred_condition,
                other_condition=other_condition,
                condition_results=(condition_results[0], condition_results[1]),
            )
        )

    aggregates = []
    for condition in V2_GATE_CONDITIONS:
        condition_rows = [
            result
            for task in task_results
            for result in task.condition_results
            if result.condition is condition
        ]
        aggregates.append(
            CodexV2GateConditionAggregate(
                condition=condition,
                preference_wins=sum(task.preferred_condition is condition for task in task_results),
                objective=CodexV2GateCheckCounts(
                    passed=sum(item.objective.passed for item in condition_rows),
                    total=sum(item.objective.total for item in condition_rows),
                ),
                diagnostic=CodexV2GateCheckCounts(
                    passed=sum(item.diagnostic.passed for item in condition_rows),
                    total=sum(item.diagnostic.total for item in condition_rows),
                ),
                neutral=CodexV2GateCheckCounts(
                    passed=sum(item.neutral.passed for item in condition_rows),
                    total=sum(item.neutral.total for item in condition_rows),
                ),
                input_tokens=sum(item.input_tokens for item in condition_rows),
                cached_input_tokens=sum(item.cached_input_tokens for item in condition_rows),
                output_tokens=sum(item.output_tokens for item in condition_rows),
                reasoning_output_tokens=sum(
                    item.reasoning_output_tokens for item in condition_rows
                ),
            )
        )
    aggregate_by_condition = {item.condition: item for item in aggregates}
    strong = aggregate_by_condition[BenchmarkCondition.STRONG_STATIC_PROFILE]
    compiled = aggregate_by_condition[BenchmarkCondition.COMPILED_ADAPTATION]
    all_valid = all(result.valid for task in task_results for result in task.condition_results)
    no_objective_regression = all(
        task.condition_results[1].objective.passed >= task.condition_results[0].objective.passed
        and task.condition_results[1].objective.total == task.condition_results[0].objective.total
        for task in task_results
    )
    no_neutral_regression = all(
        task.condition_results[1].neutral.passed >= task.condition_results[0].neutral.passed
        and task.condition_results[1].neutral.total == task.condition_results[0].neutral.total
        for task in task_results
    )
    diagnostic_not_lower = compiled.diagnostic.passed >= strong.diagnostic.passed
    preference_not_lower = compiled.preference_wins >= strong.preference_wins
    tie_or_better = (
        all_valid
        and no_objective_regression
        and no_neutral_regression
        and diagnostic_not_lower
        and preference_not_lower
    )
    strict_win = tie_or_better and (
        compiled.diagnostic.passed > strong.diagnostic.passed
        or compiled.preference_wins > strong.preference_wins
    )
    if not all_valid:
        reason = "At least one development cell was invalid."
    elif not no_objective_regression:
        reason = "Compiled adaptation had a per-task objective regression."
    elif not no_neutral_regression:
        reason = "Compiled adaptation had a per-task neutral-control regression."
    elif not diagnostic_not_lower:
        reason = "Compiled adaptation had fewer aggregate diagnostic passes."
    elif not preference_not_lower:
        reason = (
            f"Kevin preferred compiled adaptation on {compiled.preference_wins} task(s) "
            f"and the strong static profile on {strong.preference_wins} task(s)."
        )
    elif strict_win:
        reason = "Compiled adaptation met the strict preregistered development rule."
    else:
        reason = "Compiled adaptation met, but did not strictly exceed, the tie-or-better rule."

    return CodexV2GateUnblindedResult(
        design_digest=design.content_digest,
        public_plan_digest=public_plan.content_digest,
        private_plan_digest=private_plan.content_digest,
        blind_report_digest=blind_report.content_digest,
        preference_rating_digest=rating.content_digest,
        task_results=tuple(sorted(task_results, key=lambda item: item.task_id)),
        condition_aggregates=(aggregates[0], aggregates[1]),
        decision=(
            "compiled_strict_win"
            if strict_win
            else ("compiled_tie_or_better" if tie_or_better else "compiled_below_strong")
        ),
        tie_or_better_rule_passed=tie_or_better,
        strict_win_rule_passed=strict_win,
        decision_reason=reason,
        created_at=created_at,
    )


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
