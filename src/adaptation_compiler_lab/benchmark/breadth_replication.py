"""Typed Milestone 6A.4 multi-family breadth-replication records."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentTask,
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.compact_execution import CompactJudgePair
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairComparisonTrialReceipt,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest

_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)


class BreadthReplicationTask(FrozenModel):
    """One fresh natural task assigned to an evidence stage."""

    task: CodexDevelopmentTask
    stage: Annotated[int, Field(ge=1, le=3)]
    reference_fixture_digest: Sha256Digest

    @property
    def task_id(self) -> str:
        return self.task.task_id


class BreadthReplicationCell(FrozenModel):
    """One condition-blind cell in the frozen 16-run grid."""

    sequence: Annotated[int, Field(ge=1, le=16)]
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class BreadthReplicationPublicPlan(FrozenModel):
    """Public paired run order with condition mapping withheld."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    seed_commitment: Sha256Digest
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[tuple[BreadthReplicationCell, ...], Field(min_length=16, max_length=16)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_complete(self) -> Self:
        if self.blind_condition_ids != tuple(sorted(set(self.blind_condition_ids))):
            raise ValueError("breadth blind condition IDs must be sorted and unique")
        if tuple(cell.sequence for cell in self.run_order) != tuple(range(1, 17)):
            raise ValueError("breadth run sequence must be contiguous")
        if len({cell.run_id for cell in self.run_order}) != 16:
            raise ValueError("breadth run IDs must be unique")
        if len({cell.blind_output_id for cell in self.run_order}) != 16:
            raise ValueError("breadth output IDs must be unique")
        if len({(cell.task_id, cell.blind_condition_id) for cell in self.run_order}) != 16:
            raise ValueError("breadth plan must contain every task-condition cell once")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthProfileSet(FrozenModel):
    """Three cumulative strong-profile snapshots from one isolated role."""

    profile_version: Literal["1.0.0"] = "1.0.0"
    stage_1: NonEmptyStr
    stage_2: NonEmptyStr
    stage_3: NonEmptyStr

    @field_validator("stage_1", "stage_2", "stage_3")
    @classmethod
    def profile_is_compact(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 3000:
            raise ValueError("breadth profile stage exceeds its 3,000-byte ceiling")
        return value


class BreadthProfileConstructionReceipt(FrozenModel):
    """Sanitized author or reviewer construction receipt."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    role: Literal["profile_author", "profile_reviewer"]
    packet_digest: Sha256Digest
    input_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=2)]
    output_digest: Sha256Digest
    output_bytes: tuple[int, int, int]
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["medium"] = "medium"
    condition_mapping_accessed: Literal[False] = False
    compiled_material_accessed: Literal[False] = False
    task_content_accessed: Literal[False] = False
    external_validation_accessed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    encrypted_trace_ref: Sha256Digest


class BreadthReplicationDesign(FrozenModel):
    """Frozen eight-task, four-family staged comparison."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a4-breadth-replication"] = "milestone-6a4-breadth-replication"
    tasks: Annotated[tuple[BreadthReplicationTask, ...], Field(min_length=8, max_length=8)]
    task_manifest_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=8, max_length=8)]
    evidence_stages_digest: Sha256Digest
    compiled_material_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    profile_material_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    compiled_material_bytes: tuple[int, int, int]
    profile_material_bytes: tuple[int, int, int]
    profile_author_receipt_digest: Sha256Digest
    profile_reviewer_receipt_digest: Sha256Digest
    scorer_source_digest: Sha256Digest
    task_delivery_source_digest: Sha256Digest
    command_audit_source_digest: Sha256Digest
    conditions: tuple[
        Literal[BenchmarkCondition.STRONG_STATIC_PROFILE],
        Literal[BenchmarkCondition.COMPILED_ADAPTATION],
    ] = (
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    )
    evidence_stages: Literal[3] = 3
    approved_source_families: Literal[4] = 4
    tasks_per_family: Literal[2] = 2
    planned_target_sessions: Literal[16] = 16
    profile_construction_sessions: Literal[2] = 2
    isolated_judge_sessions: Literal[1] = 1
    global_preact_transient_retries: Literal[1] = 1
    maximum_subscription_sessions: Literal[20] = 20
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    delivery_channel: Literal["user_task"] = "user_task"
    material_occurrences: Literal[1] = 1
    same_delivery_adapter_required: Literal[True] = True
    automated_scoring_primary: Literal[True] = True
    judge_cannot_rescue_primary_gate: Literal[True] = True
    external_validation_accessed: Literal[False] = False
    prior_live_tasks_reused: Literal[False] = False
    tuning_on_live_outputs_forbidden: Literal[True] = True

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        ids = tuple(item.task_id for item in self.tasks)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("breadth tasks must be sorted and unique")
        if Counter(item.task.family for item in self.tasks) != Counter(
            {
                ApprovedSourceFamily.COMMUNICATION: 2,
                ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION: 2,
                ApprovedSourceFamily.ENVIRONMENT_SAFETY: 2,
                ApprovedSourceFamily.RESEARCH_INTEGRITY: 2,
            }
        ):
            raise ValueError("breadth tasks must contain two tasks per approved family")
        if set(item.stage for item in self.tasks) != {1, 2, 3}:
            raise ValueError("breadth tasks must span all three evidence stages")
        if any(
            compiled > profile
            for compiled, profile in zip(
                self.compiled_material_bytes,
                self.profile_material_bytes,
                strict=True,
            )
        ):
            raise ValueError("compiled breadth material exceeds strong-profile bytes")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthReplicationContract(FrozenModel):
    """Pinned execution and source contract."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    protocol_digest: Sha256Digest
    runner_source_digest: Sha256Digest
    judge_runner_source_digest: Sha256Digest
    unblind_source_digest: Sha256Digest
    profile_runner_source_digest: Sha256Digest
    target_runner_source_digest: Sha256Digest
    structured_role_runner_source_digest: Sha256Digest
    cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    cli_digest: Literal[
        "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    ] = "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    target_reasoning_effort: Literal["medium"] = "medium"
    judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    judge_reasoning_effort: Literal["xhigh"] = "xhigh"
    profile_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    profile_reasoning_effort: Literal["medium"] = "medium"
    service_mode: Literal["standard"] = "standard"
    max_seconds_per_session: Literal[600] = 600
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    outer_sandbox_digest: Literal[
        "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    ] = "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    external_validation_accessed: Literal[False] = False

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthTaskPairOutcome(FrozenModel):
    """Unblinded automated outcome for one task pair."""

    task_id: Identifier
    family: ApprovedSourceFamily
    stage: Annotated[int, Field(ge=1, le=3)]
    compiled_output_id: Identifier
    profile_output_id: Identifier
    automated_winner: Literal["compiled_adaptation", "strong_static_profile", "tie"]
    compiled_total_passed: Annotated[int, Field(ge=0)]
    profile_total_passed: Annotated[int, Field(ge=0)]
    compiled_behavior_conformant: bool
    profile_behavior_conformant: bool


class BreadthReplicationResult(FrozenModel):
    """Final breadth result and bounded claim."""

    result_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    contract_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    source_commit: NonEmptyStr
    trials: Annotated[tuple[FairComparisonTrialReceipt, ...], Field(min_length=16, max_length=16)]
    task_pairs: Annotated[tuple[BreadthTaskPairOutcome, ...], Field(min_length=8, max_length=8)]
    instrument_valid: bool
    primary_gate_passed: bool
    family_gates_passed: Annotated[int, Field(ge=0, le=4)]
    judge_receipt_digest: Sha256Digest
    judge_compiled_wins: Annotated[int, Field(ge=0, le=8)]
    judge_profile_wins: Annotated[int, Field(ge=0, le=8)]
    judge_ties: Annotated[int, Field(ge=0, le=8)]
    permitted_claim: Literal[
        "compiled_outperformed_on_multifamily_suite_without_family_regression",
        "compiled_matched_profile_across_all_approved_families",
        "breadth_gate_failed",
        "instrumentation_failure",
    ]
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def result_is_coherent(self) -> Self:
        if self.instrument_valid != all(trial.integrity_valid for trial in self.trials):
            raise ValueError("breadth instrument state does not match trial integrity")
        if not self.instrument_valid and self.permitted_claim != "instrumentation_failure":
            raise ValueError("invalid breadth instrumentation permits no comparative claim")
        if self.primary_gate_passed and self.family_gates_passed != 4:
            raise ValueError("passing breadth gate requires all family gates")
        if self.judge_compiled_wins + self.judge_profile_wins + self.judge_ties != 8:
            raise ValueError("breadth judge counts must cover eight task pairs")
        return self


class BreadthJudgeDecision(FrozenModel):
    """Secondary condition-blind judgment over all eight pairs."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[tuple[CompactJudgePair, ...], Field(min_length=8, max_length=8)]
    overall_assessment: NonEmptyStr
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def tasks_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 8:
            raise ValueError("breadth judge must cover eight unique tasks")
        return self


def seed_commitment(seed: bytes) -> Sha256Digest:
    """Domain-separated commitment to the private breadth seed."""

    return f"sha256:{hashlib.sha256(b'acl/breadth-replication/seed/v1\\x00' + seed).hexdigest()}"


def _blind_id(seed: bytes, *, label: str, prefix: str) -> str:
    value = hmac.new(seed, label.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{prefix}-{value}"


def build_breadth_plan(
    *,
    design_digest: Sha256Digest,
    tasks: tuple[BreadthReplicationTask, ...],
    seed: bytes,
) -> tuple[BreadthReplicationPublicPlan, dict[str, object]]:
    """Build a task-blocked private/public breadth plan."""

    assignments = {
        condition: _blind_id(seed, label=f"condition:{condition.value}", prefix="condition")
        for condition in _CONDITIONS
    }
    ordered_tasks = sorted(
        tasks,
        key=lambda task: hmac.new(
            seed,
            f"task-order:{task.task_id}".encode(),
            hashlib.sha256,
        ).digest(),
    )
    cells: list[dict[str, object]] = []
    for task in ordered_tasks:
        ordered_conditions = sorted(
            _CONDITIONS,
            key=lambda condition: hmac.new(
                seed,
                f"condition-order:{task.task_id}:{condition.value}".encode(),
                hashlib.sha256,
            ).digest(),
        )
        for condition in ordered_conditions:
            sequence = len(cells) + 1
            cells.append(
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
    public = BreadthReplicationPublicPlan(
        design_digest=design_digest,
        seed_commitment=seed_commitment(seed),
        blind_condition_ids=tuple(sorted(assignments.values())),
        run_order=tuple(
            BreadthReplicationCell.model_validate(
                {key: value for key, value in cell.items() if key != "condition"}
            )
            for cell in cells
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
        "run_order": cells,
        "public_plan_digest": public.content_digest,
        "external_validation_accessed": False,
    }
    return public, private


def load_breadth_design(root: Path) -> BreadthReplicationDesign:
    """Load and revalidate the frozen breadth preregistration."""

    path = root / "PREREGISTRATION-v1.json"
    fields = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(fields) != 2 or fields[1] != path.name or sha256_file(path) != f"sha256:{fields[0]}":
        raise ValueError("breadth preregistration checksum drifted")
    design = BreadthReplicationDesign.model_validate_json(path.read_bytes())
    repo = root.parent
    for index, wrapped in enumerate(design.tasks):
        task_root = root / "tasks" / wrapped.task_id
        fixture = task_root / "fixture"
        reference = task_root / "reference"
        manifest = task_root / "task.json"
        if development_tree_digest(fixture) != wrapped.task.fixture_digest:
            raise ValueError(f"breadth fixture drifted: {wrapped.task_id}")
        if development_tree_digest(reference) != wrapped.reference_fixture_digest:
            raise ValueError(f"breadth reference drifted: {wrapped.task_id}")
        if sha256_file(manifest) != design.task_manifest_digests[index]:
            raise ValueError(f"breadth manifest drifted: {wrapped.task_id}")
        if BreadthReplicationTask.model_validate_json(manifest.read_bytes()) != wrapped:
            raise ValueError(f"breadth task model drifted: {wrapped.task_id}")
    checks = (
        (root / "EVIDENCE_STAGES-v1.json", design.evidence_stages_digest),
        (repo / "scripts/score_breadth_replication_task.py", design.scorer_source_digest),
        (
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py",
            design.task_delivery_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py",
            design.command_audit_source_digest,
        ),
        (
            root / "profile-author-receipt.json",
            design.profile_author_receipt_digest,
        ),
        (
            root / "profile-reviewer-receipt.json",
            design.profile_reviewer_receipt_digest,
        ),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"breadth dependency drifted: {artifact.name}")
    for stage in range(1, 4):
        compiled = root / f"condition-materials/compiled-stage-{stage}.md"
        profile = root / f"condition-materials/strong-profile-stage-{stage}.md"
        if sha256_file(compiled) != design.compiled_material_digests[stage - 1]:
            raise ValueError(f"breadth compiled Stage {stage} drifted")
        if sha256_file(profile) != design.profile_material_digests[stage - 1]:
            raise ValueError(f"breadth profile Stage {stage} drifted")
        if compiled.stat().st_size != design.compiled_material_bytes[stage - 1]:
            raise ValueError(f"breadth compiled Stage {stage} size drifted")
        if profile.stat().st_size != design.profile_material_bytes[stage - 1]:
            raise ValueError(f"breadth profile Stage {stage} size drifted")
    return design


def load_breadth_contract(
    root: Path,
    *,
    design: BreadthReplicationDesign,
) -> BreadthReplicationContract:
    """Load and revalidate the frozen breadth execution contract."""

    contract = BreadthReplicationContract.model_validate_json(
        (root / "EXECUTION_CONTRACT-v1.json").read_bytes()
    )
    if contract.design_digest != design.content_digest:
        raise ValueError("breadth contract design binding drifted")
    plan = BreadthReplicationPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if contract.public_plan_digest != plan.content_digest:
        raise ValueError("breadth contract public-plan binding drifted")
    repo = root.parent
    checks = (
        (root / "EXECUTION_PROTOCOL-v1.md", contract.protocol_digest),
        (repo / "scripts/run_breadth_replication.py", contract.runner_source_digest),
        (repo / "scripts/run_breadth_judge.py", contract.judge_runner_source_digest),
        (repo / "scripts/unblind_breadth_replication.py", contract.unblind_source_digest),
        (
            repo / "scripts/run_breadth_profile_construction.py",
            contract.profile_runner_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py",
            contract.target_runner_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py",
            contract.structured_role_runner_source_digest,
        ),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"breadth contract dependency drifted: {artifact.name}")
    return contract
