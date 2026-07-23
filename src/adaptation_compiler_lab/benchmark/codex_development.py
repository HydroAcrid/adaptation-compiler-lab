"""Typed Milestone 5.5 Codex subscription development-benchmark records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

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


class CodexDevelopmentTask(FrozenModel):
    """One newly authored non-held-out task with an independent scorer."""

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
            raise ValueError("development-task sequences must be sorted and unique")
        return value

    @field_validator("visible_test_command")
    @classmethod
    def command_is_safe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item or "\x00" in item for item in value):
            raise ValueError("development visible-test command is invalid")
        return value


class CodexDevelopmentIsolationPolicy(FrozenModel):
    """Exact ambient-state exclusions for every subscription-backed run."""

    ephemeral_session: Literal[True] = True
    isolated_codex_home: Literal[True] = True
    copied_saved_chatgpt_auth_only: Literal[True] = True
    api_key_environment_forbidden: Literal[True] = True
    user_config_ignored: Literal[True] = True
    exec_rules_ignored: Literal[True] = True
    agents_md_forbidden: Literal[True] = True
    project_codex_config_forbidden: Literal[True] = True
    memories_forbidden: Literal[True] = True
    skills_forbidden: Literal[True] = True
    plugins_forbidden: Literal[True] = True
    mcp_forbidden: Literal[True] = True
    web_search_forbidden: Literal[True] = True
    prior_transcripts_forbidden: Literal[True] = True
    shell_environment_inherit: Literal["none"] = "none"
    sandbox: Literal["workspace-write"] = "workspace-write"
    approval_policy: Literal["never"] = "never"


class CodexDevelopmentDesign(FrozenModel):
    """Frozen 4-task by 4-condition subscription development design."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["codex-subscription-development-gate-v1"] = (
        "codex-subscription-development-gate-v1"
    )
    task_count: Literal[4] = 4
    conditions: Annotated[tuple[BenchmarkCondition, ...], Field(min_length=4, max_length=4)] = (
        BenchmarkCondition.BASE,
        BenchmarkCondition.ORDINARY_MEMORY,
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    )
    runs_per_task_condition: Literal[1] = 1
    planned_runs: Literal[16] = 16
    cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    model: Literal["gpt-5.6-terra"] = "gpt-5.6-terra"
    reasoning_effort: Literal["high"] = "high"
    max_seconds: Literal[1200] = 1200
    exec_turn_limit: Literal[1] = 1
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    isolation: CodexDevelopmentIsolationPolicy = Field(
        default_factory=CodexDevelopmentIsolationPolicy
    )
    tasks: Annotated[tuple[CodexDevelopmentTask, ...], Field(min_length=4, max_length=4)]
    milestone_6_custody_accessed: Literal[False] = False
    cross_agent_claim_allowed: Literal[False] = False
    frozen_at: UtcDateTime

    @model_validator(mode="after")
    def design_is_complete(self) -> Self:
        if self.conditions != tuple(BenchmarkCondition):
            raise ValueError("development conditions must contain the four frozen conditions")
        if self.task_count * len(self.conditions) != self.planned_runs:
            raise ValueError("development run count must equal tasks x conditions")
        task_ids = tuple(item.task_id for item in self.tasks)
        if not strings_are_sorted_unique(task_ids):
            raise ValueError("development tasks must be sorted and unique")
        if {item.family for item in self.tasks} != set(ApprovedSourceFamily):
            raise ValueError("development tasks must cover the four approved source families")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexDevelopmentRunRequest(FrozenModel):
    """One blinded condition/task cell passed to the isolated Codex runner."""

    run_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier
    task: CodexDevelopmentTask
    condition_text: str = Field(repr=False)
    condition_digest: Sha256Digest
    common_instructions: NonEmptyStr


class CodexDevelopmentConditionAssignment(FrozenModel):
    """Secret mapping between one frozen condition and its development blind ID."""

    condition: BenchmarkCondition
    blind_condition_id: Identifier


class CodexDevelopmentRunCell(FrozenModel):
    """One condition-blind task cell in the frozen development execution order."""

    sequence: int = Field(ge=1, le=16)
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class CodexDevelopmentPrivatePlan(FrozenModel):
    """Secret development-only mapping; never exposed in the blind rating packet."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    condition_assignments: Annotated[
        tuple[CodexDevelopmentConditionAssignment, ...],
        Field(min_length=4, max_length=4),
    ]
    run_order: Annotated[
        tuple[CodexDevelopmentRunCell, ...],
        Field(min_length=16, max_length=16),
    ]
    created_at: UtcDateTime
    milestone_6_custody_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_complete(self) -> Self:
        if tuple(item.condition for item in self.condition_assignments) != tuple(
            BenchmarkCondition
        ):
            raise ValueError("development condition assignments are incomplete")
        condition_ids = tuple(item.blind_condition_id for item in self.condition_assignments)
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("development condition blind IDs must be unique")
        if tuple(item.sequence for item in self.run_order) != tuple(range(1, 17)):
            raise ValueError("development run order must be contiguous")
        cells = {(item.task_id, item.blind_condition_id) for item in self.run_order}
        if len(cells) != 16:
            raise ValueError("development run order must contain each task-condition cell once")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexDevelopmentPublicPlan(FrozenModel):
    """Condition-blind commitment safe to expose before preference ratings."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    randomization_seed_commitment: Sha256Digest
    randomization_algorithm: Literal["sha256_counter_shuffle_v1"] = RANDOMIZATION_ALGORITHM
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=4, max_length=4)]
    run_order: Annotated[
        tuple[CodexDevelopmentRunCell, ...],
        Field(min_length=16, max_length=16),
    ]
    private_plan_digest: Sha256Digest
    created_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False

    @field_validator("blind_condition_ids")
    @classmethod
    def condition_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("blind condition IDs must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CodexDevelopmentRunObservation(FrozenModel):
    """Sanitized result metadata with no condition identity or target-visible text."""

    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier
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
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
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
    api_key_environment_present: Literal[False] = False
    forbidden_ambient_surface_observed: bool = False
    valid: bool
    invalid_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def terminal_state_is_coherent(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("development run cannot finish before it starts")
        if self.objective_checks_passed > self.objective_checks_total:
            raise ValueError("objective pass count exceeds total")
        if self.diagnostic_checks_passed > self.diagnostic_checks_total:
            raise ValueError("diagnostic pass count exceeds total")
        if self.neutral_checks_passed > self.neutral_checks_total:
            raise ValueError("neutral pass count exceeds total")
        if self.valid != (self.invalid_reason is None):
            raise ValueError("invalid development run requires exactly one reason")
        return self


class CodexDevelopmentBlindReport(FrozenModel):
    """Complete anonymous 16-cell report safe to show before condition unblinding."""

    report_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    observations: Annotated[
        tuple[CodexDevelopmentRunObservation, ...],
        Field(min_length=16, max_length=16),
    ]
    condition_mapping_withheld: Literal[True] = True
    milestone_6_custody_accessed: Literal[False] = False
    created_at: UtcDateTime

    @model_validator(mode="after")
    def report_covers_the_complete_grid(self) -> Self:
        run_ids = tuple(item.run_id for item in self.observations)
        output_ids = tuple(item.blind_output_id for item in self.observations)
        if len(run_ids) != len(set(run_ids)) or len(output_ids) != len(set(output_ids)):
            raise ValueError("development observations must be unique")
        task_ids = {item.task_id for item in self.observations}
        condition_ids = {item.blind_condition_id for item in self.observations}
        cells = {(item.task_id, item.blind_condition_id) for item in self.observations}
        if len(task_ids) != 4 or len(condition_ids) != 4 or len(cells) != 16:
            raise ValueError("development report must cover the 4 x 4 grid")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def development_tree_digest(root: Path) -> Sha256Digest:
    """Digest an exact task fixture tree by canonical relative path and file bytes."""

    resolved = root.resolve()
    files = tuple(sorted(path for path in resolved.rglob("*") if path.is_file()))
    if not files:
        raise ValueError("development fixture tree must not be empty")
    digest = hashlib.sha256(b"adaptation-compiler-lab/development-tree/v1\x00")
    for path in files:
        relative = path.relative_to(resolved).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return f"sha256:{digest.hexdigest()}"


def build_codex_development_plan(
    *,
    design: CodexDevelopmentDesign,
    seed: RandomizationSeed,
    created_at: UtcDateTime,
) -> tuple[CodexDevelopmentPrivatePlan, CodexDevelopmentPublicPlan]:
    """Create a separate secret mapping and public run order for Milestone 5.5."""

    assignments = tuple(
        CodexDevelopmentConditionAssignment(
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
        CodexDevelopmentRunCell(
            sequence=sequence,
            run_id=f"development-run-{sequence:04d}",
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
    private = CodexDevelopmentPrivatePlan(
        design_digest=design.content_digest,
        randomization_seed_commitment=seed.commitment,
        condition_assignments=assignments,
        run_order=run_order,
        created_at=created_at,
    )
    public = CodexDevelopmentPublicPlan(
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


def load_codex_development_design(
    root: Path,
    *,
    frozen_at: UtcDateTime,
) -> CodexDevelopmentDesign:
    """Load the four public task manifests and bind their exact fixture/scorer bytes."""

    tasks_root = root.resolve() / "tasks"
    tasks = []
    for task_root in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        value = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
        scorer = task_root / "independent" / "score.py"
        scorer_digest = "sha256:" + hashlib.sha256(scorer.read_bytes()).hexdigest()
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
                independent_scorer_digest=scorer_digest,
            )
        )
    return CodexDevelopmentDesign(
        tasks=tuple(sorted(tasks, key=lambda item: item.task_id)),
        frozen_at=frozen_at,
    )
