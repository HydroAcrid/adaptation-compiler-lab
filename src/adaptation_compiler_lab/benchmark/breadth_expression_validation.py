"""Typed records for the scoped Milestone 6A.4 expression validation."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.benchmark.breadth_remediation import OracleCheckContract
from adaptation_compiler_lab.benchmark.breadth_replication import BreadthTaskPairOutcome
from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentTask
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
_TASK_FAMILIES = {
    ApprovedSourceFamily.COMMUNICATION,
    ApprovedSourceFamily.RESEARCH_INTEGRITY,
}


class BreadthExpressionTask(FrozenModel):
    """One fresh task in the scoped expression-validation comparison."""

    task: CodexDevelopmentTask
    role: Literal["repaired_behavior", "unrelated_neutral_control"]
    reference_fixture_digest: Sha256Digest
    oracle_checks: Annotated[
        tuple[OracleCheckContract, ...],
        Field(min_length=8, max_length=16),
    ]

    @property
    def task_id(self) -> str:
        return self.task.task_id

    @model_validator(mode="after")
    def oracle_is_complete(self) -> Self:
        check_ids = tuple(item.check_id for item in self.oracle_checks)
        if check_ids != tuple(sorted(set(check_ids))):
            raise ValueError("expression-validation oracle IDs must be sorted and unique")
        if set(item.group for item in self.oracle_checks) != {
            "objective",
            "diagnostic",
            "neutral",
        }:
            raise ValueError("expression-validation oracle must cover every score group")
        return self


class BreadthExpressionCell(FrozenModel):
    """One blinded target cell."""

    sequence: Annotated[int, Field(ge=1, le=4)]
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class BreadthExpressionPublicPlan(FrozenModel):
    """Public four-cell order with the condition mapping withheld."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    seed_commitment: Sha256Digest
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[tuple[BreadthExpressionCell, ...], Field(min_length=4, max_length=4)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_complete(self) -> Self:
        if self.blind_condition_ids != tuple(sorted(set(self.blind_condition_ids))):
            raise ValueError("expression-validation condition IDs must be unique and sorted")
        if tuple(item.sequence for item in self.run_order) != (1, 2, 3, 4):
            raise ValueError("expression-validation sequence must be contiguous")
        if len({item.run_id for item in self.run_order}) != 4:
            raise ValueError("expression-validation run IDs must be unique")
        if len({item.blind_output_id for item in self.run_order}) != 4:
            raise ValueError("expression-validation output IDs must be unique")
        if len({(item.task_id, item.blind_condition_id) for item in self.run_order}) != 4:
            raise ValueError("expression-validation plan must contain every task-condition cell")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthExpressionDesign(FrozenModel):
    """Frozen validation of the least-invasive communication expression repair."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a4-scoped-expression-validation"] = (
        "milestone-6a4-scoped-expression-validation"
    )
    tasks: Annotated[tuple[BreadthExpressionTask, ...], Field(min_length=2, max_length=2)]
    task_manifest_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=2, max_length=2)]
    prior_valid_result_digest: Sha256Digest
    prior_compiled_material_digest: Sha256Digest
    repaired_compiled_material_digest: Sha256Digest
    profile_material_digest: Sha256Digest
    repaired_compiled_material_bytes: Annotated[int, Field(gt=0)]
    profile_material_bytes: Annotated[int, Field(gt=0)]
    scorer_source_digest: Sha256Digest
    target_runner_v3_source_digest: Sha256Digest
    task_delivery_source_digest: Sha256Digest
    command_audit_source_digest: Sha256Digest
    protocol_digest: Sha256Digest
    eligible_evidence_unchanged: Literal[True] = True
    new_behavior_added: Literal[False] = False
    communication_expression_only: Literal[True] = True
    noncommunication_material_byte_identical: Literal[True] = True
    profile_material_unchanged: Literal[True] = True
    prior_valid_runs_replaced: Literal[False] = False
    fresh_tasks: Literal[True] = True
    automated_scoring_primary: Literal[True] = True
    judge_cannot_rescue_primary_gate: Literal[True] = True
    target_sessions: Literal[4] = 4
    judge_sessions: Literal[1] = 1
    maximum_subscription_sessions: Literal[5] = 5
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        ids = tuple(item.task_id for item in self.tasks)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("expression-validation task IDs must be sorted and unique")
        if {item.task.family for item in self.tasks} != _TASK_FAMILIES:
            raise ValueError("expression validation requires communication and research tasks")
        roles = Counter(item.role for item in self.tasks)
        if roles != Counter({"repaired_behavior": 1, "unrelated_neutral_control": 1}):
            raise ValueError("expression validation requires one repaired and one control task")
        if self.repaired_compiled_material_bytes >= self.profile_material_bytes:
            raise ValueError("repaired compiled material must remain smaller than the profile")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthExpressionContract(FrozenModel):
    """Pinned execution contract for the four target sessions and blind judge."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    protocol_digest: Sha256Digest
    runner_source_digest: Sha256Digest
    judge_runner_source_digest: Sha256Digest
    unblind_source_digest: Sha256Digest
    model_source_digest: Sha256Digest
    scorer_source_digest: Sha256Digest
    target_runner_v3_source_digest: Sha256Digest
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


class BreadthExpressionJudgeDecision(FrozenModel):
    """Secondary blind judgment over the two fresh task pairs."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[tuple[CompactJudgePair, ...], Field(min_length=2, max_length=2)]
    overall_assessment: NonEmptyStr
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def tasks_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 2:
            raise ValueError("expression-validation judge must cover two unique tasks")
        return self


class BreadthExpressionResult(FrozenModel):
    """Final scoped expression-validation result."""

    result_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    contract_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    source_commit: NonEmptyStr
    trials: Annotated[
        tuple[FairComparisonTrialReceipt, ...],
        Field(min_length=4, max_length=4),
    ]
    task_pairs: Annotated[
        tuple[BreadthTaskPairOutcome, ...],
        Field(min_length=2, max_length=2),
    ]
    prior_noncommunication_task_ids: tuple[
        Literal["debugging-deployment-state"],
        Literal["environment-migration-plan"],
        Literal["research-cutoff-report"],
    ] = (
        "debugging-deployment-state",
        "environment-migration-plan",
        "research-cutoff-report",
    )
    instrument_valid: bool
    compiled_objective_perfect: bool
    compiled_diagnostic_perfect: bool
    compiled_neutral_perfect: bool
    compiled_behavior_conformant: bool
    no_new_task_regression: bool
    prior_noncommunication_pairs_remain_ties: bool
    noncommunication_material_byte_identical: bool
    compactness_gate_passed: bool
    primary_gate_passed: bool
    judge_compiled_wins: Annotated[int, Field(ge=0, le=2)]
    judge_profile_wins: Annotated[int, Field(ge=0, le=2)]
    judge_ties: Annotated[int, Field(ge=0, le=2)]
    permitted_claim: Literal[
        "compiled_matched_or_outperformed_profile_across_four_families_with_lifecycle_advantages",
        "scoped_expression_validation_failed",
        "scoped_expression_validation_instrumentation_failure",
    ]
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def result_is_coherent(self) -> Self:
        if self.instrument_valid != all(item.integrity_valid for item in self.trials):
            raise ValueError("expression-validation instrument state disagrees with trials")
        if len({item.task_id for item in self.task_pairs}) != 2:
            raise ValueError("expression-validation result must cover two fresh tasks")
        expected_gate = (
            self.instrument_valid
            and self.compiled_objective_perfect
            and self.compiled_diagnostic_perfect
            and self.compiled_neutral_perfect
            and self.compiled_behavior_conformant
            and self.no_new_task_regression
            and self.prior_noncommunication_pairs_remain_ties
            and self.noncommunication_material_byte_identical
            and self.compactness_gate_passed
        )
        if self.primary_gate_passed != expected_gate:
            raise ValueError("expression-validation primary gate fields disagree")
        if self.judge_compiled_wins + self.judge_profile_wins + self.judge_ties != 2:
            raise ValueError("expression-validation judge counts must cover two pairs")
        if (
            not self.instrument_valid
            and self.permitted_claim != "scoped_expression_validation_instrumentation_failure"
        ):
            raise ValueError("invalid instrumentation permits no comparison")
        return self


def breadth_expression_seed_commitment(seed: bytes) -> Sha256Digest:
    """Return the domain-separated commitment for the private seed."""

    return f"sha256:{hashlib.sha256(b'acl/breadth-expression/v1\\x00' + seed).hexdigest()}"


def _blind_id(seed: bytes, *, label: str, prefix: str) -> str:
    value = hmac.new(seed, label.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{prefix}-{value}"


def build_breadth_expression_plan(
    *,
    design_digest: Sha256Digest,
    tasks: tuple[BreadthExpressionTask, ...],
    seed: bytes,
) -> tuple[BreadthExpressionPublicPlan, dict[str, object]]:
    """Build the task-blocked public/private four-cell plan."""

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
    public = BreadthExpressionPublicPlan(
        design_digest=design_digest,
        seed_commitment=breadth_expression_seed_commitment(seed),
        blind_condition_ids=tuple(sorted(assignments.values())),
        run_order=tuple(
            BreadthExpressionCell.model_validate(
                {key: value for key, value in item.items() if key != "condition"}
            )
            for item in cells
        ),
    )
    private: dict[str, object] = {
        "plan_version": "1.0.0",
        "design_digest": design_digest,
        "public_plan_digest": public.content_digest,
        "seed_commitment": breadth_expression_seed_commitment(seed),
        "condition_assignments": [
            {
                "blind_condition_id": assignments[condition],
                "condition": condition.value,
            }
            for condition in _CONDITIONS
        ],
        "run_order": cells,
        "external_validation_accessed": False,
    }
    return public, private


def noncommunication_rules_are_identical(old_path: Path, repaired_path: Path) -> bool:
    """Return whether the repair changed only the communication rule."""

    old_lines = old_path.read_text(encoding="utf-8").splitlines()
    repaired_lines = repaired_path.read_text(encoding="utf-8").splitlines()
    return (
        len(old_lines) == len(repaired_lines)
        and len(old_lines) >= 4
        and old_lines[:2] == repaired_lines[:2]
        and old_lines[2] != repaired_lines[2]
        and old_lines[3:] == repaired_lines[3:]
        and old_lines[2].startswith("- Communication handoff")
        and repaired_lines[2].startswith("- Communication handoff")
    )


def load_breadth_expression_design(root: Path) -> BreadthExpressionDesign:
    """Load and digest-check the frozen expression-validation design."""

    path = root / "PREREGISTRATION-v1.json"
    checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(checksum) != 2 or checksum[1] != path.name:
        raise ValueError("expression-validation checksum record is malformed")
    if sha256_file(path) != f"sha256:{checksum[0]}":
        raise ValueError("expression-validation preregistration drifted")
    design = BreadthExpressionDesign.model_validate_json(path.read_bytes())
    repo = root.parent
    old_material = (
        repo / "development_benchmark_breadth_instrument_repair/condition-materials/"
        "compiled-final.md"
    )
    repaired_material = (
        repo / "development_benchmark_breadth_instrument_repair/condition-materials/"
        "compiled-final-v4.md"
    )
    dependencies = (
        (root / "EXECUTION_PROTOCOL-v1.md", design.protocol_digest),
        (repo / "scripts/score_breadth_expression_task.py", design.scorer_source_digest),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v3.py",
            design.target_runner_v3_source_digest,
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
            repo / "development_benchmark_breadth_instrument_repair/results-v2/"
            "unblinded-result.json",
            design.prior_valid_result_digest,
        ),
        (old_material, design.prior_compiled_material_digest),
        (repaired_material, design.repaired_compiled_material_digest),
        (
            repo / "development_benchmark_breadth_replication/condition-materials/"
            "strong-profile-stage-3.md",
            design.profile_material_digest,
        ),
    )
    for artifact, expected in dependencies:
        if sha256_file(artifact) != expected:
            raise ValueError(f"expression-validation dependency drifted: {artifact.name}")
    if not noncommunication_rules_are_identical(old_material, repaired_material):
        raise ValueError("expression repair changed noncommunication material")
    for task, expected in zip(design.tasks, design.task_manifest_digests, strict=True):
        if sha256_file(root / f"tasks/{task.task_id}/task.json") != expected:
            raise ValueError(f"expression-validation task manifest drifted: {task.task_id}")
    return design


def load_breadth_expression_contract(
    root: Path,
    *,
    design: BreadthExpressionDesign,
) -> BreadthExpressionContract:
    """Load and digest-check the frozen expression execution contract."""

    contract = BreadthExpressionContract.model_validate_json(
        (root / "EXECUTION_CONTRACT-v1.json").read_bytes()
    )
    if contract.design_digest != design.content_digest:
        raise ValueError("expression-validation contract design binding drifted")
    public = BreadthExpressionPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if contract.public_plan_digest != public.content_digest:
        raise ValueError("expression-validation public plan binding drifted")
    repo = root.parent
    dependencies = (
        (root / "EXECUTION_PROTOCOL-v1.md", contract.protocol_digest),
        (repo / "scripts/run_breadth_expression_validation.py", contract.runner_source_digest),
        (
            repo / "scripts/run_breadth_expression_judge.py",
            contract.judge_runner_source_digest,
        ),
        (
            repo / "scripts/unblind_breadth_expression_validation.py",
            contract.unblind_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/breadth_expression_validation.py",
            contract.model_source_digest,
        ),
        (repo / "scripts/score_breadth_expression_task.py", contract.scorer_source_digest),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v3.py",
            contract.target_runner_v3_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py",
            contract.structured_role_runner_source_digest,
        ),
    )
    for artifact, expected in dependencies:
        if sha256_file(artifact) != expected:
            raise ValueError(f"expression-validation contract dependency drifted: {artifact.name}")
    return contract


__all__ = [
    "BreadthExpressionContract",
    "BreadthExpressionDesign",
    "BreadthExpressionJudgeDecision",
    "BreadthExpressionPublicPlan",
    "BreadthExpressionResult",
    "BreadthExpressionTask",
    "build_breadth_expression_plan",
    "load_breadth_expression_contract",
    "load_breadth_expression_design",
    "noncommunication_rules_are_identical",
]
