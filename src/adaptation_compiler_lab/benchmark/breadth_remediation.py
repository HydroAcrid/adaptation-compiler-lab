"""Typed Milestone 6A.4 repair-replication records."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthTaskPairOutcome,
)
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


class OracleCheckContract(FrozenModel):
    """Public basis for one answer-blind semantic check."""

    check_id: Identifier
    group: Literal["objective", "diagnostic", "neutral"]
    public_basis: NonEmptyStr
    exact_undisclosed_vocabulary_required: Literal[False] = False


class BreadthRemediationTask(FrozenModel):
    """One fresh replacement task with an audited oracle contract."""

    task: CodexDevelopmentTask
    stage: Annotated[int, Field(ge=1, le=3)]
    replaces_task_id: Identifier
    reference_fixture_digest: Sha256Digest
    oracle_checks: Annotated[tuple[OracleCheckContract, ...], Field(min_length=8, max_length=16)]

    @property
    def task_id(self) -> str:
        return self.task.task_id

    @model_validator(mode="after")
    def oracle_contract_is_complete(self) -> Self:
        check_ids = tuple(item.check_id for item in self.oracle_checks)
        if check_ids != tuple(sorted(set(check_ids))):
            raise ValueError("remediation oracle check IDs must be sorted and unique")
        if set(item.group for item in self.oracle_checks) != {
            "objective",
            "diagnostic",
            "neutral",
        }:
            raise ValueError("remediation oracle must cover all three score groups")
        return self


class BreadthRemediationCell(FrozenModel):
    """One condition-blind cell in the 10-run repair grid."""

    sequence: Annotated[int, Field(ge=1, le=10)]
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class BreadthRemediationPublicPlan(FrozenModel):
    """Public repair order with condition mapping withheld."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    seed_commitment: Sha256Digest
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[tuple[BreadthRemediationCell, ...], Field(min_length=10, max_length=10)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_complete(self) -> Self:
        if self.blind_condition_ids != tuple(sorted(set(self.blind_condition_ids))):
            raise ValueError("remediation condition IDs must be sorted and unique")
        if tuple(item.sequence for item in self.run_order) != tuple(range(1, 11)):
            raise ValueError("remediation run sequence must be contiguous")
        if len({item.run_id for item in self.run_order}) != 10:
            raise ValueError("remediation run IDs must be unique")
        if len({item.blind_output_id for item in self.run_order}) != 10:
            raise ValueError("remediation output IDs must be unique")
        if len({(item.task_id, item.blind_condition_id) for item in self.run_order}) != 10:
            raise ValueError("remediation plan must contain every task-condition cell")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthRemediationDesign(FrozenModel):
    """Frozen five-task replacement design plus three inherited valid pairs."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a4-oracle-contract-remediation"] = (
        "milestone-6a4-oracle-contract-remediation"
    )
    tasks: Annotated[tuple[BreadthRemediationTask, ...], Field(min_length=5, max_length=5)]
    task_manifest_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=5, max_length=5)]
    inherited_task_ids: tuple[
        Literal["communication-handoff"],
        Literal["debugging-request-context"],
        Literal["research-advisory"],
    ] = (
        "communication-handoff",
        "debugging-request-context",
        "research-advisory",
    )
    inherited_adjudication_result_digest: Sha256Digest
    original_breadth_design_digest: Sha256Digest
    original_breadth_contract_digest: Sha256Digest
    compiled_material_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    profile_material_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    compiled_material_bytes: tuple[int, int, int]
    profile_material_bytes: tuple[int, int, int]
    scorer_source_digest: Sha256Digest
    task_delivery_source_digest: Sha256Digest
    command_audit_source_digest: Sha256Digest
    oracle_contract_audited: Literal[True] = True
    undisclosed_exact_vocabulary_forbidden: Literal[True] = True
    planned_target_sessions: Literal[10] = 10
    isolated_judge_sessions: Literal[1] = 1
    maximum_subscription_sessions: Literal[11] = 11
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    delivery_channel: Literal["user_task"] = "user_task"
    material_occurrences: Literal[1] = 1
    same_delivery_adapter_required: Literal[True] = True
    automated_scoring_primary: Literal[True] = True
    judge_cannot_rescue_primary_gate: Literal[True] = True
    external_validation_accessed: Literal[False] = False
    prior_failed_tasks_reused: Literal[False] = False
    condition_materials_changed: Literal[False] = False
    tuning_on_repair_outputs_forbidden: Literal[True] = True

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        ids = tuple(item.task_id for item in self.tasks)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("remediation tasks must be sorted and unique")
        if len({item.replaces_task_id for item in self.tasks}) != 5:
            raise ValueError("remediation tasks must replace five unique failed slots")
        if Counter(item.task.family for item in self.tasks) != Counter(
            {
                ApprovedSourceFamily.COMMUNICATION: 1,
                ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION: 1,
                ApprovedSourceFamily.ENVIRONMENT_SAFETY: 2,
                ApprovedSourceFamily.RESEARCH_INTEGRITY: 1,
            }
        ):
            raise ValueError("remediation tasks do not cover the failed family slots")
        if any(
            compiled >= profile
            for compiled, profile in zip(
                self.compiled_material_bytes,
                self.profile_material_bytes,
                strict=True,
            )
        ):
            raise ValueError("remediation compiled material must remain strictly smaller")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthRemediationContract(FrozenModel):
    """Pinned execution and source contract for the repair replication."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    protocol_digest: Sha256Digest
    runner_source_digest: Sha256Digest
    judge_runner_source_digest: Sha256Digest
    unblind_source_digest: Sha256Digest
    model_source_digest: Sha256Digest
    scorer_source_digest: Sha256Digest
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


class BreadthRemediationJudgeDecision(FrozenModel):
    """Secondary blind judgment over the five fresh replacement pairs."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[tuple[CompactJudgePair, ...], Field(min_length=5, max_length=5)]
    overall_assessment: NonEmptyStr
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def tasks_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 5:
            raise ValueError("remediation judge must cover five unique tasks")
        return self


class BreadthRemediationResult(FrozenModel):
    """Combined result from three inherited and five fresh task pairs."""

    result_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    contract_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    source_commit: NonEmptyStr
    new_trials: Annotated[
        tuple[FairComparisonTrialReceipt, ...],
        Field(min_length=10, max_length=10),
    ]
    inherited_task_pairs: Annotated[
        tuple[BreadthTaskPairOutcome, ...],
        Field(min_length=3, max_length=3),
    ]
    replacement_task_pairs: Annotated[
        tuple[BreadthTaskPairOutcome, ...],
        Field(min_length=5, max_length=5),
    ]
    combined_task_pairs: Annotated[
        tuple[BreadthTaskPairOutcome, ...],
        Field(min_length=8, max_length=8),
    ]
    instrument_valid: bool
    primary_gate_passed: bool
    family_gates_passed: Annotated[int, Field(ge=0, le=4)]
    judge_compiled_wins: Annotated[int, Field(ge=0, le=5)]
    judge_profile_wins: Annotated[int, Field(ge=0, le=5)]
    judge_ties: Annotated[int, Field(ge=0, le=5)]
    permitted_claim: Literal[
        "compiled_matched_profile_across_all_approved_families_with_lifecycle_advantages",
        "compiled_outperformed_on_combined_multifamily_suite",
        "breadth_remediation_gate_failed",
        "breadth_remediation_instrumentation_failure",
    ]
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def result_is_coherent(self) -> Self:
        if self.instrument_valid != all(item.integrity_valid for item in self.new_trials):
            raise ValueError("remediation instrument state does not match trial integrity")
        if len({item.task_id for item in self.combined_task_pairs}) != 8:
            raise ValueError("combined remediation result must contain eight unique tasks")
        if not self.instrument_valid and (
            self.permitted_claim != "breadth_remediation_instrumentation_failure"
        ):
            raise ValueError("invalid remediation instrumentation permits no comparison")
        if self.primary_gate_passed and self.family_gates_passed != 4:
            raise ValueError("passing remediation gate requires all family gates")
        if self.judge_compiled_wins + self.judge_profile_wins + self.judge_ties != 5:
            raise ValueError("remediation judge counts must cover five pairs")
        return self


def remediation_seed_commitment(seed: bytes) -> Sha256Digest:
    """Domain-separated commitment for the repair randomization."""

    domain = b"acl/breadth-remediation/seed/v1\x00"
    return f"sha256:{hashlib.sha256(domain + seed).hexdigest()}"


def _blind_id(seed: bytes, *, label: str, prefix: str) -> str:
    value = hmac.new(seed, label.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{prefix}-{value}"


def build_breadth_remediation_plan(
    *,
    design_digest: Sha256Digest,
    tasks: tuple[BreadthRemediationTask, ...],
    seed: bytes,
) -> tuple[BreadthRemediationPublicPlan, dict[str, object]]:
    """Build the task-blocked private/public 10-cell plan."""

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
        conditions = sorted(
            _CONDITIONS,
            key=lambda condition: hmac.new(
                seed,
                f"condition-order:{task.task_id}:{condition.value}".encode(),
                hashlib.sha256,
            ).digest(),
        )
        for condition in conditions:
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
    public = BreadthRemediationPublicPlan(
        design_digest=design_digest,
        seed_commitment=remediation_seed_commitment(seed),
        blind_condition_ids=tuple(sorted(assignments.values())),
        run_order=tuple(
            BreadthRemediationCell.model_validate(
                {key: value for key, value in item.items() if key != "condition"}
            )
            for item in cells
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


def load_breadth_remediation_design(root: Path) -> BreadthRemediationDesign:
    """Load and revalidate the repair preregistration."""

    path = root / "PREREGISTRATION-v1.json"
    checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(checksum) != 2 or checksum[1] != path.name:
        raise ValueError("remediation preregistration checksum is malformed")
    if sha256_file(path) != f"sha256:{checksum[0]}":
        raise ValueError("remediation preregistration drifted")
    design = BreadthRemediationDesign.model_validate_json(path.read_bytes())
    repo = root.parent
    for index, task in enumerate(design.tasks):
        task_root = root / f"tasks/{task.task_id}"
        manifest = task_root / "task.json"
        if sha256_file(manifest) != design.task_manifest_digests[index]:
            raise ValueError(f"remediation manifest drifted: {task.task_id}")
        if development_tree_digest(task_root / "fixture") != task.task.fixture_digest:
            raise ValueError(f"remediation fixture drifted: {task.task_id}")
        if development_tree_digest(task_root / "reference") != task.reference_fixture_digest:
            raise ValueError(f"remediation reference drifted: {task.task_id}")
        if BreadthRemediationTask.model_validate_json(manifest.read_bytes()) != task:
            raise ValueError(f"remediation task model drifted: {task.task_id}")
    checks = (
        (repo / "scripts/score_breadth_remediation_task.py", design.scorer_source_digest),
        (
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py",
            design.task_delivery_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py",
            design.command_audit_source_digest,
        ),
        (
            repo
            / "development_benchmark_breadth_replication/results-v1.1"
            / "SCORING_ADJUDICATION-v1.json",
            design.inherited_adjudication_result_digest,
        ),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"remediation dependency drifted: {artifact.name}")
    original = repo / "development_benchmark_breadth_replication"
    for stage in range(1, 4):
        compiled = original / f"condition-materials/compiled-stage-{stage}.md"
        profile = original / f"condition-materials/strong-profile-stage-{stage}.md"
        if sha256_file(compiled) != design.compiled_material_digests[stage - 1]:
            raise ValueError(f"remediation compiled Stage {stage} drifted")
        if sha256_file(profile) != design.profile_material_digests[stage - 1]:
            raise ValueError(f"remediation profile Stage {stage} drifted")
    return design


def load_breadth_remediation_contract(
    root: Path,
    *,
    design: BreadthRemediationDesign,
) -> BreadthRemediationContract:
    """Load and revalidate the repair execution contract."""

    contract = BreadthRemediationContract.model_validate_json(
        (root / "EXECUTION_CONTRACT-v1.json").read_bytes()
    )
    if contract.design_digest != design.content_digest:
        raise ValueError("remediation contract design binding drifted")
    public = BreadthRemediationPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if contract.public_plan_digest != public.content_digest:
        raise ValueError("remediation public plan binding drifted")
    repo = root.parent
    checks = (
        (root / "EXECUTION_PROTOCOL-v1.md", contract.protocol_digest),
        (repo / "scripts/run_breadth_remediation.py", contract.runner_source_digest),
        (repo / "scripts/run_breadth_remediation_judge.py", contract.judge_runner_source_digest),
        (
            repo / "scripts/unblind_breadth_remediation.py",
            contract.unblind_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/breadth_remediation.py",
            contract.model_source_digest,
        ),
        (repo / "scripts/score_breadth_remediation_task.py", contract.scorer_source_digest),
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
            raise ValueError(f"remediation contract dependency drifted: {artifact.name}")
    return contract
