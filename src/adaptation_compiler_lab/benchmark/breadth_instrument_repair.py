"""Typed records for the clean Milestone 6A.4 instrument-and-expression repair."""

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


class BreadthInstrumentTask(FrozenModel):
    """One answer-blind task in the repaired four-family breadth gate."""

    task: CodexDevelopmentTask
    stage: Literal[3] = 3
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
            raise ValueError("instrument-repair oracle IDs must be sorted and unique")
        if set(item.group for item in self.oracle_checks) != {
            "objective",
            "diagnostic",
            "neutral",
        }:
            raise ValueError("instrument-repair oracle must cover all score groups")
        return self


class BreadthInstrumentCell(FrozenModel):
    """One blinded target cell."""

    sequence: Annotated[int, Field(ge=1, le=8)]
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class BreadthInstrumentPublicPlan(FrozenModel):
    """Public eight-cell order with the condition mapping withheld."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    seed_commitment: Sha256Digest
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[tuple[BreadthInstrumentCell, ...], Field(min_length=8, max_length=8)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_complete(self) -> Self:
        if self.blind_condition_ids != tuple(sorted(set(self.blind_condition_ids))):
            raise ValueError("instrument-repair condition IDs must be unique and sorted")
        if tuple(item.sequence for item in self.run_order) != tuple(range(1, 9)):
            raise ValueError("instrument-repair sequence must be contiguous")
        if len({item.run_id for item in self.run_order}) != 8:
            raise ValueError("instrument-repair run IDs must be unique")
        if len({item.blind_output_id for item in self.run_order}) != 8:
            raise ValueError("instrument-repair output IDs must be unique")
        if len({(item.task_id, item.blind_condition_id) for item in self.run_order}) != 8:
            raise ValueError("instrument-repair plan must contain every task-condition cell")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthInstrumentDesign(FrozenModel):
    """Frozen clean replication after instrument and expression repair."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a4-instrument-and-expression-repair"] = (
        "milestone-6a4-instrument-and-expression-repair"
    )
    tasks: Annotated[tuple[BreadthInstrumentTask, ...], Field(min_length=4, max_length=4)]
    task_manifest_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=4, max_length=4)]
    original_failed_result_digest: Sha256Digest
    remediation_failed_result_digest: Sha256Digest
    compiled_material_digest: Sha256Digest
    profile_material_digest: Sha256Digest
    compiled_material_bytes: Annotated[int, Field(gt=0)]
    profile_material_bytes: Annotated[int, Field(gt=0)]
    scorer_source_digest: Sha256Digest
    runner_source_digest: Sha256Digest
    target_runner_source_digest: Sha256Digest
    task_delivery_source_digest: Sha256Digest
    command_audit_source_digest: Sha256Digest
    protocol_digest: Sha256Digest
    prior_results_preserved: Literal[True] = True
    eligible_evidence_unchanged: Literal[True] = True
    profile_material_unchanged: Literal[True] = True
    compiled_change_kind: Literal["expression_strength_only"] = "expression_strength_only"
    fresh_tasks: Literal[True] = True
    automated_scoring_primary: Literal[True] = True
    judge_cannot_rescue_primary_gate: Literal[True] = True
    planned_target_sessions: Literal[8] = 8
    isolated_judge_sessions: Literal[1] = 1
    maximum_subscription_sessions: Literal[9] = 9
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        ids = tuple(item.task_id for item in self.tasks)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("instrument-repair task IDs must be sorted and unique")
        if Counter(item.task.family for item in self.tasks) != Counter(ApprovedSourceFamily):
            raise ValueError("instrument-repair design must contain one task per family")
        if self.compiled_material_bytes >= self.profile_material_bytes:
            raise ValueError("compiled material must remain smaller than the strong profile")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthInstrumentContract(FrozenModel):
    """Pinned execution contract for the clean replication."""

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


class BreadthInstrumentJudgeDecision(FrozenModel):
    """Secondary blind judgment over the four clean task pairs."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[tuple[CompactJudgePair, ...], Field(min_length=4, max_length=4)]
    overall_assessment: NonEmptyStr
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def tasks_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 4:
            raise ValueError("instrument-repair judge must cover four unique tasks")
        return self


class BreadthInstrumentResult(FrozenModel):
    """Final result for the clean four-family replication."""

    result_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    contract_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    source_commit: NonEmptyStr
    trials: Annotated[
        tuple[FairComparisonTrialReceipt, ...],
        Field(min_length=8, max_length=8),
    ]
    task_pairs: Annotated[
        tuple[BreadthTaskPairOutcome, ...],
        Field(min_length=4, max_length=4),
    ]
    instrument_valid: bool
    compiled_objective_perfect: bool
    compiled_neutral_perfect: bool
    no_family_regression: bool
    compactness_gate_passed: bool
    primary_gate_passed: bool
    judge_compiled_wins: Annotated[int, Field(ge=0, le=4)]
    judge_profile_wins: Annotated[int, Field(ge=0, le=4)]
    judge_ties: Annotated[int, Field(ge=0, le=4)]
    permitted_claim: Literal[
        "compiled_matched_or_outperformed_profile_across_four_families_with_lifecycle_advantages",
        "breadth_instrument_repair_gate_failed",
        "breadth_instrument_repair_instrumentation_failure",
    ]
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def result_is_coherent(self) -> Self:
        if self.instrument_valid != all(item.integrity_valid for item in self.trials):
            raise ValueError("instrument state does not match trial integrity")
        if len({item.task_id for item in self.task_pairs}) != 4:
            raise ValueError("instrument-repair result must cover four tasks")
        expected_gate = (
            self.instrument_valid
            and self.compiled_objective_perfect
            and self.compiled_neutral_perfect
            and self.no_family_regression
            and self.compactness_gate_passed
        )
        if self.primary_gate_passed != expected_gate:
            raise ValueError("instrument-repair primary gate fields disagree")
        if (
            not self.instrument_valid
            and self.permitted_claim != "breadth_instrument_repair_instrumentation_failure"
        ):
            raise ValueError("invalid instrumentation permits no comparison")
        if self.judge_compiled_wins + self.judge_profile_wins + self.judge_ties != 4:
            raise ValueError("judge counts must cover four pairs")
        return self


def breadth_instrument_seed_commitment(seed: bytes) -> Sha256Digest:
    """Return the domain-separated commitment for the private seed."""

    return f"sha256:{hashlib.sha256(b'acl/breadth-instrument/v1\\x00' + seed).hexdigest()}"


def _blind_id(seed: bytes, *, label: str, prefix: str) -> str:
    value = hmac.new(seed, label.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{prefix}-{value}"


def build_breadth_instrument_plan(
    *,
    design_digest: Sha256Digest,
    tasks: tuple[BreadthInstrumentTask, ...],
    seed: bytes,
) -> tuple[BreadthInstrumentPublicPlan, dict[str, object]]:
    """Build the task-blocked public/private eight-cell plan."""

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
    public = BreadthInstrumentPublicPlan(
        design_digest=design_digest,
        seed_commitment=breadth_instrument_seed_commitment(seed),
        blind_condition_ids=tuple(sorted(assignments.values())),
        run_order=tuple(
            BreadthInstrumentCell.model_validate(
                {key: value for key, value in item.items() if key != "condition"}
            )
            for item in cells
        ),
    )
    private: dict[str, object] = {
        "plan_version": "1.0.0",
        "design_digest": design_digest,
        "public_plan_digest": public.content_digest,
        "seed_commitment": breadth_instrument_seed_commitment(seed),
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


def load_breadth_instrument_design(root: Path) -> BreadthInstrumentDesign:
    """Load and digest-check the frozen design."""

    path = root / "PREREGISTRATION-v1.json"
    checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(checksum) != 2 or checksum[1] != path.name:
        raise ValueError("instrument-repair checksum record is malformed")
    if sha256_file(path) != f"sha256:{checksum[0]}":
        raise ValueError("instrument-repair preregistration drifted")
    design = BreadthInstrumentDesign.model_validate_json(path.read_bytes())
    repo = root.parent
    dependencies = (
        (root / "EXECUTION_PROTOCOL-v1.md", design.protocol_digest),
        (repo / "scripts/score_breadth_instrument_task.py", design.scorer_source_digest),
        (repo / "scripts/run_breadth_instrument.py", design.runner_source_digest),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v2.py",
            design.target_runner_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py",
            design.task_delivery_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py",
            design.command_audit_source_digest,
        ),
        (root / "condition-materials/compiled-final.md", design.compiled_material_digest),
        (
            repo / "development_benchmark_breadth_replication/condition-materials/"
            "strong-profile-stage-3.md",
            design.profile_material_digest,
        ),
    )
    for artifact, expected in dependencies:
        if sha256_file(artifact) != expected:
            raise ValueError(f"instrument-repair dependency drifted: {artifact.name}")
    for task, expected in zip(design.tasks, design.task_manifest_digests, strict=True):
        if sha256_file(root / f"tasks/{task.task_id}/task.json") != expected:
            raise ValueError(f"instrument-repair task manifest drifted: {task.task_id}")
    return design


def load_breadth_instrument_contract(
    root: Path,
    *,
    design: BreadthInstrumentDesign,
) -> BreadthInstrumentContract:
    """Load and digest-check the frozen execution contract."""

    contract = BreadthInstrumentContract.model_validate_json(
        (root / "EXECUTION_CONTRACT-v1.json").read_bytes()
    )
    if contract.design_digest != design.content_digest:
        raise ValueError("instrument-repair contract design binding drifted")
    public = BreadthInstrumentPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if contract.public_plan_digest != public.content_digest:
        raise ValueError("instrument-repair public plan binding drifted")
    repo = root.parent
    dependencies = (
        (root / "EXECUTION_PROTOCOL-v1.md", contract.protocol_digest),
        (repo / "scripts/run_breadth_instrument.py", contract.runner_source_digest),
        (
            repo / "scripts/run_breadth_instrument_judge.py",
            contract.judge_runner_source_digest,
        ),
        (
            repo / "scripts/unblind_breadth_instrument.py",
            contract.unblind_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/breadth_instrument_repair.py",
            contract.model_source_digest,
        ),
        (repo / "scripts/score_breadth_instrument_task.py", contract.scorer_source_digest),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v2.py",
            contract.target_runner_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py",
            contract.structured_role_runner_source_digest,
        ),
    )
    for artifact, expected in dependencies:
        if sha256_file(artifact) != expected:
            raise ValueError(f"instrument-repair contract dependency drifted: {artifact.name}")
    return contract
