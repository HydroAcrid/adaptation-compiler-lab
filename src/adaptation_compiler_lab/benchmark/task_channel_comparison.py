"""Fair strong-profile versus compiled task-channel comparison records."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.compact_execution import CompactJudgePair
from adaptation_compiler_lab.benchmark.compact_projection import CompactProjectionTask
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.task_delivery import TaskMaterialDeliveryReceipt

_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)


class TaskChannelComparisonCell(FrozenModel):
    """One condition-blind target cell."""

    sequence: Annotated[int, Field(ge=1, le=12)]
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class TaskChannelComparisonPublicPlan(FrozenModel):
    """Public randomized order with the condition mapping withheld."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    seed_commitment: Sha256Digest
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[tuple[TaskChannelComparisonCell, ...], Field(min_length=12, max_length=12)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_complete(self) -> Self:
        if self.blind_condition_ids != tuple(sorted(set(self.blind_condition_ids))):
            raise ValueError("blind condition IDs must be sorted and unique")
        if tuple(cell.sequence for cell in self.run_order) != tuple(range(1, 13)):
            raise ValueError("comparison sequence must be contiguous")
        if len({cell.run_id for cell in self.run_order}) != 12:
            raise ValueError("comparison run IDs must be unique")
        if len({cell.blind_output_id for cell in self.run_order}) != 12:
            raise ValueError("comparison output IDs must be unique")
        cells = {(cell.task_id, cell.blind_condition_id) for cell in self.run_order}
        if len(cells) != 12:
            raise ValueError("comparison plan must contain each task-condition cell once")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class TaskChannelComparisonDesign(FrozenModel):
    """Frozen six-task fair-delivery comparison."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a3-fair-task-channel-comparison"] = (
        "milestone-6a3-fair-task-channel-comparison"
    )
    tasks: Annotated[tuple[CompactProjectionTask, ...], Field(min_length=6, max_length=6)]
    conditions: tuple[
        Literal[BenchmarkCondition.STRONG_STATIC_PROFILE],
        Literal[BenchmarkCondition.COMPILED_ADAPTATION],
    ] = (
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    )
    task_fixture_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=6, max_length=6)]
    task_manifest_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=6, max_length=6)]
    compiled_material_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    profile_material_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    compiled_material_bytes: tuple[int, int, int]
    profile_material_bytes: tuple[int, int, int]
    runtime_fixture_tree_digest: Sha256Digest
    independent_scorer_digest: Sha256Digest
    policy_observer_digest: Sha256Digest
    scorer_sandbox_digest: Sha256Digest
    task_delivery_source_digest: Sha256Digest
    command_audit_source_digest: Sha256Digest
    prior_task_delivery_result_digest: Sha256Digest
    evidence_stages: Literal[3] = 3
    tasks_per_stage: Literal[2] = 2
    repetitions_per_condition_task: Literal[1] = 1
    planned_target_sessions: Literal[12] = 12
    isolated_judge_sessions: Literal[1] = 1
    global_preact_transient_retries: Literal[1] = 1
    maximum_subscription_sessions: Literal[14] = 14
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    delivery_channel: Literal["user_task"] = "user_task"
    material_occurrences: Literal[1] = 1
    same_delivery_adapter_required: Literal[True] = True
    automated_scoring_primary: Literal[True] = True
    judge_cannot_rescue_primary_gate: Literal[True] = True
    external_validation_accessed: Literal[False] = False
    materials_frozen_before_tasks: Literal[True] = True
    tuning_on_live_outputs_forbidden: Literal[True] = True

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        task_ids = tuple(task.task_id for task in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("comparison tasks must be sorted and unique")
        if Counter(task.stage for task in self.tasks) != Counter({1: 2, 2: 2, 3: 2}):
            raise ValueError("comparison needs exactly two tasks per evidence stage")
        if len(set(self.task_fixture_digests)) != 6:
            raise ValueError("comparison fixture digests must be unique")
        if any(
            compiled > profile
            for compiled, profile in zip(
                self.compiled_material_bytes,
                self.profile_material_bytes,
                strict=True,
            )
        ):
            raise ValueError("compiled material exceeds its profile comparator")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class TaskChannelComparisonContract(FrozenModel):
    """Pinned zero-provider-billing execution contract."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    protocol_digest: Sha256Digest
    runner_source_digest: Sha256Digest
    judge_runner_source_digest: Sha256Digest
    unblind_source_digest: Sha256Digest
    target_runner_source_digest: Sha256Digest
    structured_role_runner_source_digest: Sha256Digest
    cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    cli_digest: Literal[
        "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    ] = "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    target_reasoning_effort: Literal["medium"] = "medium"
    service_mode: Literal["standard"] = "standard"
    max_seconds_per_target: Literal[600] = 600
    judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    judge_reasoning_effort: Literal["xhigh"] = "xhigh"
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    inherited_smoke_receipt_digest: Sha256Digest
    outer_sandbox_digest: Literal[
        "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    ] = "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    external_validation_accessed: Literal[False] = False

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class FairComparisonTrialReceipt(FrozenModel):
    """Complete per-cell evidence with integrity separated from behavior."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    observation: CodexDevelopmentRunObservation
    delivery: TaskMaterialDeliveryReceipt
    integrity_valid: bool
    integrity_failures: tuple[NonEmptyStr, ...] = ()
    behavior_conformant: bool
    behavior_failures: tuple[NonEmptyStr, ...] = ()
    visible_tests_executed: Annotated[int, Field(ge=0)]
    encrypted_trace_ref: Sha256Digest

    @field_validator("integrity_failures", "behavior_failures")
    @classmethod
    def failures_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("trial failures must be sorted and unique")
        return value

    @model_validator(mode="after")
    def states_are_coherent(self) -> Self:
        if self.integrity_valid != (not self.integrity_failures):
            raise ValueError("integrity state does not match its failures")
        if self.behavior_conformant != (not self.behavior_failures):
            raise ValueError("behavior state does not match its failures")
        return self


class FairTaskPairOutcome(FrozenModel):
    """Unblinded paired automated result for one task."""

    task_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    compiled_output_id: Identifier
    profile_output_id: Identifier
    automated_winner: Literal["compiled_adaptation", "strong_static_profile", "tie"]
    compiled_behavior_conformant: bool
    profile_behavior_conformant: bool
    compiled_total_passed: Annotated[int, Field(ge=0)]
    profile_total_passed: Annotated[int, Field(ge=0)]


class FairComparisonResult(FrozenModel):
    """Final sanitized result and bounded permitted claim."""

    result_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    contract_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    source_commit: NonEmptyStr
    trials: Annotated[tuple[FairComparisonTrialReceipt, ...], Field(min_length=12, max_length=12)]
    task_pairs: Annotated[tuple[FairTaskPairOutcome, ...], Field(min_length=6, max_length=6)]
    instrument_valid: bool
    primary_gate_passed: bool
    judge_receipt_digest: Sha256Digest
    judge_compiled_wins: Annotated[int, Field(ge=0, le=6)]
    judge_profile_wins: Annotated[int, Field(ge=0, le=6)]
    judge_ties: Annotated[int, Field(ge=0, le=6)]
    permitted_claim: Literal[
        "compiled_outperformed_on_fresh_suite",
        "compiled_matched_with_lifecycle_advantages",
        "product_gate_failed",
        "instrumentation_failure",
    ]
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def result_is_coherent(self) -> Self:
        integrity = all(trial.integrity_valid for trial in self.trials)
        if self.instrument_valid != integrity:
            raise ValueError("result instrument state does not match trial integrity")
        if not self.instrument_valid and self.permitted_claim != "instrumentation_failure":
            raise ValueError("invalid instrumentation permits no comparative claim")
        if self.primary_gate_passed and self.permitted_claim not in {
            "compiled_outperformed_on_fresh_suite",
            "compiled_matched_with_lifecycle_advantages",
        }:
            raise ValueError("passing primary gate requires a bounded positive claim")
        if self.judge_compiled_wins + self.judge_profile_wins + self.judge_ties != 6:
            raise ValueError("judge outcome counts must cover all six task pairs")
        return self


class FairTaskChannelJudgeDecision(FrozenModel):
    """Secondary anonymous judgment over all six task pairs."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[tuple[CompactJudgePair, ...], Field(min_length=6, max_length=6)]
    overall_assessment: NonEmptyStr
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def tasks_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 6:
            raise ValueError("fair task-channel judge must cover six unique tasks")
        return self


def seed_commitment(seed: bytes) -> Sha256Digest:
    """Bind a secret randomization seed without exposing it."""

    return f"sha256:{hashlib.sha256(b'acl/fair-task-channel/seed/v1\\x00' + seed).hexdigest()}"


def _blind_id(seed: bytes, *, label: str, prefix: str) -> str:
    value = hmac.new(seed, label.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{prefix}-{value}"


def build_task_channel_plan(
    *,
    design_digest: Sha256Digest,
    tasks: tuple[CompactProjectionTask, ...],
    seed: bytes,
) -> tuple[TaskChannelComparisonPublicPlan, dict[str, object]]:
    """Build a block-randomized public plan and separate private mapping."""

    assignments = {
        condition: _blind_id(seed, label=f"condition:{condition.value}", prefix="condition")
        for condition in _CONDITIONS
    }
    task_order = sorted(
        tasks,
        key=lambda task: hmac.new(
            seed,
            f"task-order:{task.task_id}".encode(),
            hashlib.sha256,
        ).digest(),
    )
    private_cells: list[dict[str, object]] = []
    sequence = 1
    for task in task_order:
        condition_order = sorted(
            _CONDITIONS,
            key=lambda condition: hmac.new(
                seed,
                f"condition-order:{task.task_id}:{condition.value}".encode(),
                hashlib.sha256,
            ).digest(),
        )
        for condition in condition_order:
            private_cells.append(
                {
                    "sequence": sequence,
                    "run_id": _blind_id(
                        seed,
                        label=f"run:{task.task_id}:{condition.value}",
                        prefix="run",
                    ),
                    "task_id": task.task_id,
                    "blind_condition_id": assignments[condition],
                    "blind_output_id": _blind_id(
                        seed,
                        label=f"output:{task.task_id}:{condition.value}",
                        prefix="output",
                    ),
                    "condition": condition.value,
                }
            )
            sequence += 1
    public = TaskChannelComparisonPublicPlan(
        design_digest=design_digest,
        seed_commitment=seed_commitment(seed),
        blind_condition_ids=tuple(sorted(assignments.values())),
        run_order=tuple(
            TaskChannelComparisonCell.model_validate(
                {key: value for key, value in cell.items() if key != "condition"}
            )
            for cell in private_cells
        ),
    )
    private = {
        "plan_version": "1.0.0",
        "design_digest": design_digest,
        "seed_commitment": public.seed_commitment,
        "condition_assignments": [
            {
                "condition": condition.value,
                "blind_condition_id": assignments[condition],
            }
            for condition in _CONDITIONS
        ],
        "run_order": private_cells,
        "public_plan_digest": public.content_digest,
        "external_validation_accessed": False,
    }
    return public, private


def load_task_channel_design(root: Path) -> TaskChannelComparisonDesign:
    """Load and fully revalidate the frozen comparison design."""

    path = root / "PREREGISTRATION-v1.json"
    fields = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(fields) != 2 or fields[1] != path.name or sha256_file(path) != f"sha256:{fields[0]}":
        raise ValueError("fair comparison preregistration checksum drifted")
    design = TaskChannelComparisonDesign.model_validate_json(path.read_bytes())
    repo = root.parent
    tasks_root = root / "tasks"
    for index, task in enumerate(design.tasks):
        task_root = tasks_root / task.task_id
        fixture = task_root / "fixture"
        if development_tree_digest(fixture) != design.task_fixture_digests[index]:
            raise ValueError(f"fair comparison fixture drifted: {task.task_id}")
        manifest = task_root / "task.json"
        if sha256_file(manifest) != design.task_manifest_digests[index]:
            raise ValueError(f"fair comparison manifest drifted: {task.task_id}")
        if json.loads(manifest.read_text(encoding="utf-8")) != task.model_dump(
            mode="json", round_trip=True
        ):
            raise ValueError(f"fair comparison task model drifted: {task.task_id}")
    checks = (
        (repo / "scripts/score_compact_projection_task.py", design.independent_scorer_digest),
        (repo / "scripts/observe_compact_projection_policy.py", design.policy_observer_digest),
        (
            repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
            design.scorer_sandbox_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py",
            design.task_delivery_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py",
            design.command_audit_source_digest,
        ),
        (
            repo / "development_benchmark_compact_projection/task-delivery-canary-v1/result.json",
            design.prior_task_delivery_result_digest,
        ),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"fair comparison dependency drifted: {artifact.name}")
    compiled_root = repo / "development_benchmark_compact_projection/runtime-fixture-v2.4"
    if development_tree_digest(compiled_root) != design.runtime_fixture_tree_digest:
        raise ValueError("fair comparison compiled runtime fixture drifted")
    for stage in range(1, 4):
        compiled = compiled_root / f"codex-runtime-stage-{stage}.md"
        profile = (
            repo
            / "development_benchmark_compact_projection/condition-materials-v1.14"
            / f"strong-profile-stage-{stage}.md"
        )
        if sha256_file(compiled) != design.compiled_material_digests[stage - 1]:
            raise ValueError(f"compiled Stage {stage} material drifted")
        if sha256_file(profile) != design.profile_material_digests[stage - 1]:
            raise ValueError(f"profile Stage {stage} material drifted")
        if compiled.stat().st_size != design.compiled_material_bytes[stage - 1]:
            raise ValueError(f"compiled Stage {stage} size drifted")
        if profile.stat().st_size != design.profile_material_bytes[stage - 1]:
            raise ValueError(f"profile Stage {stage} size drifted")
    plan = TaskChannelComparisonPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if plan.design_digest != design.content_digest:
        raise ValueError("fair comparison public plan binding drifted")
    return design


def load_task_channel_contract(
    root: Path,
    *,
    design: TaskChannelComparisonDesign,
) -> TaskChannelComparisonContract:
    """Load the exact execution contract and source bindings."""

    contract = TaskChannelComparisonContract.model_validate_json(
        (root / "EXECUTION_CONTRACT-v1.json").read_bytes()
    )
    if contract.design_digest != design.content_digest:
        raise ValueError("fair comparison contract design binding drifted")
    plan = TaskChannelComparisonPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if contract.public_plan_digest != plan.content_digest:
        raise ValueError("fair comparison contract public-plan binding drifted")
    repo = root.parent
    checks = (
        (root / "EXECUTION_PROTOCOL-v1.md", contract.protocol_digest),
        (repo / "scripts/run_fair_task_channel_comparison.py", contract.runner_source_digest),
        (
            repo / "scripts/unblind_fair_task_channel_comparison.py",
            contract.unblind_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py",
            contract.target_runner_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py",
            contract.structured_role_runner_source_digest,
        ),
        (
            repo / "development_benchmark_compact_projection/INSTRUMENT_SMOKE-v2.1.json",
            contract.inherited_smoke_receipt_digest,
        ),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"fair comparison contract dependency drifted: {artifact.name}")
    judge_runner = repo / "scripts/run_fair_task_channel_judge.py"
    judge_digest = sha256_file(judge_runner)
    if judge_digest != contract.judge_runner_source_digest:
        amendment_path = root / "JUDGE_INSTRUMENT_AMENDMENT-v1.json"
        try:
            amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError("fair comparison judge runner drifted without amendment") from error
        if (
            not isinstance(amendment, dict)
            or amendment.get("amendment_version") != "1.0.0"
            or amendment.get("original_contract_digest") != contract.content_digest
            or amendment.get("original_judge_runner_digest") != contract.judge_runner_source_digest
            or amendment.get("amended_judge_runner_digest") != judge_digest
            or amendment.get("target_artifacts_changed") is not False
        ):
            raise ValueError("fair comparison judge amendment is invalid")
    return contract
