"""Typed scoring-adjudication records for Milestone 6A.4."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthTaskPairOutcome,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest

CheckMap = Annotated[dict[NonEmptyStr, bool], Field(min_length=1)]


class BreadthAdjudicationInput(FrozenModel):
    """One immutable public output and original receipt bound for replay."""

    task_id: Identifier
    blind_output_id: Identifier
    public_output_digest: Sha256Digest
    original_trial_digest: Sha256Digest
    diff_digest: Sha256Digest
    final_response_digest: Sha256Digest


class BreadthScoringAdjudicationDesign(FrozenModel):
    """Frozen zero-session correction for the v1 score-adapter defect."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a4-scoring-adjudication"] = "milestone-6a4-scoring-adjudication"
    root_cause: Literal["direct_scorer_maps_were_passed_to_legacy_checks_receipts_helpers"] = (
        "direct_scorer_maps_were_passed_to_legacy_checks_receipts_helpers"
    )
    original_design_digest: Sha256Digest
    original_contract_digest: Sha256Digest
    original_result_file_digest: Sha256Digest
    blind_report_file_digest: Sha256Digest
    completion_file_digest: Sha256Digest
    judge_receipt_file_digest: Sha256Digest
    inputs: Annotated[tuple[BreadthAdjudicationInput, ...], Field(min_length=16, max_length=16)]
    protocol_digest: Sha256Digest
    scorer_source_digest: Sha256Digest
    adjudicator_source_digest: Sha256Digest
    adjudication_model_source_digest: Sha256Digest
    replay_method: Literal[
        "apply_digest_bound_public_diff_to_frozen_fixture_then_run_frozen_scorer"
    ] = "apply_digest_bound_public_diff_to_frozen_fixture_then_run_frozen_scorer"
    original_result_preserved: Literal[True] = True
    condition_materials_changed: Literal[False] = False
    target_outputs_changed: Literal[False] = False
    target_sessions_added: Literal[0] = 0
    judge_sessions_added: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def inputs_are_complete(self) -> Self:
        output_ids = tuple(item.blind_output_id for item in self.inputs)
        if output_ids != tuple(sorted(set(output_ids))):
            raise ValueError("adjudication inputs must contain 16 unique output IDs")
        if len({item.original_trial_digest for item in self.inputs}) != 16:
            raise ValueError("adjudication inputs must contain 16 unique trial receipts")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthScoringCorrection(FrozenModel):
    """Corrected score derived from one immutable output diff."""

    correction_version: Literal["1.0.0"] = "1.0.0"
    task_id: Identifier
    blind_output_id: Identifier
    original_trial_digest: Sha256Digest
    public_output_digest: Sha256Digest
    scorer_output_digest: Sha256Digest
    objective: CheckMap
    diagnostic: CheckMap
    neutral: CheckMap
    objective_passed: Annotated[int, Field(ge=0)]
    objective_total: Annotated[int, Field(ge=1)]
    diagnostic_passed: Annotated[int, Field(ge=0)]
    diagnostic_total: Annotated[int, Field(ge=1)]
    neutral_passed: Annotated[int, Field(ge=0)]
    neutral_total: Annotated[int, Field(ge=1)]
    behavior_conformant: bool
    behavior_failures: tuple[NonEmptyStr, ...]
    original_integrity_valid: Literal[True] = True
    replay_valid: Literal[True] = True
    original_adapter_failure_removed: Literal["independent scorer returned no receipts"] = (
        "independent scorer returned no receipts"
    )

    @model_validator(mode="after")
    def counts_match_check_maps(self) -> Self:
        groups = (
            (self.objective, self.objective_passed, self.objective_total),
            (self.diagnostic, self.diagnostic_passed, self.diagnostic_total),
            (self.neutral, self.neutral_passed, self.neutral_total),
        )
        for checks, passed, total in groups:
            if passed != sum(checks.values()) or total != len(checks):
                raise ValueError("adjudicated counts do not match check maps")
        expected_failures = tuple(
            sorted(
                f"{group}.{name}"
                for group, checks in (
                    ("diagnostic", self.diagnostic),
                    ("neutral", self.neutral),
                    ("objective", self.objective),
                )
                for name, value in checks.items()
                if not value
            )
        )
        if self.behavior_failures != expected_failures:
            raise ValueError("adjudicated behavior failures do not match failed checks")
        if self.behavior_conformant != (not expected_failures):
            raise ValueError("adjudicated conformance does not match failed checks")
        return self

    @property
    def total_passed(self) -> int:
        return self.objective_passed + self.diagnostic_passed + self.neutral_passed


class BreadthScoringAdjudicationResult(FrozenModel):
    """Final corrected analysis that leaves the failed v1 result immutable."""

    result_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    original_result_file_digest: Sha256Digest
    source_commit: NonEmptyStr
    corrections: Annotated[
        tuple[BreadthScoringCorrection, ...],
        Field(min_length=16, max_length=16),
    ]
    task_pairs: Annotated[tuple[BreadthTaskPairOutcome, ...], Field(min_length=8, max_length=8)]
    replay_instrument_valid: bool
    primary_gate_passed: bool
    family_gates_passed: Annotated[int, Field(ge=0, le=4)]
    judge_compiled_wins: Annotated[int, Field(ge=0, le=8)]
    judge_profile_wins: Annotated[int, Field(ge=0, le=8)]
    judge_ties: Annotated[int, Field(ge=0, le=8)]
    permitted_claim: Literal[
        "compiled_outperformed_on_multifamily_suite_without_family_regression",
        "compiled_matched_profile_across_all_approved_families",
        "breadth_gate_failed_after_adjudication",
        "scoring_adjudication_instrument_failure",
    ]
    original_result_preserved: Literal[True] = True
    target_sessions_added: Literal[0] = 0
    judge_sessions_added: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def result_is_coherent(self) -> Self:
        if len({item.blind_output_id for item in self.corrections}) != 16:
            raise ValueError("adjudication result must contain 16 unique corrections")
        if len({item.task_id for item in self.task_pairs}) != 8:
            raise ValueError("adjudication result must contain eight unique task pairs")
        if not self.replay_instrument_valid and (
            self.permitted_claim != "scoring_adjudication_instrument_failure"
        ):
            raise ValueError("invalid replay permits no comparative claim")
        if self.primary_gate_passed and self.family_gates_passed != 4:
            raise ValueError("passing adjudication gate requires all family gates")
        if self.judge_compiled_wins + self.judge_profile_wins + self.judge_ties != 8:
            raise ValueError("adjudicated judge counts must cover all task pairs")
        return self


def direct_check_counts(checks: CheckMap) -> tuple[int, int]:
    """Count a direct scorer map without a legacy wrapper."""

    return sum(checks.values()), len(checks)


def validate_direct_score(value: object) -> dict[str, dict[str, bool]]:
    """Validate the exact v1 breadth scorer output contract."""

    if not isinstance(value, dict) or set(value) != {"diagnostic", "neutral", "objective"}:
        raise ValueError("breadth scorer must return three direct check groups")
    result: dict[str, dict[str, bool]] = {}
    for group in ("diagnostic", "neutral", "objective"):
        checks = value[group]
        if (
            not isinstance(checks, dict)
            or not checks
            or not all(
                isinstance(name, str) and name and isinstance(item, bool)
                for name, item in checks.items()
            )
        ):
            raise ValueError(f"breadth scorer group is malformed: {group}")
        result[group] = checks
    return result


def load_breadth_adjudication_design(root: Path) -> BreadthScoringAdjudicationDesign:
    """Load and revalidate the frozen score-adjudication design."""

    path = root / "SCORING_ADJUDICATION_PREREGISTRATION-v1.json"
    checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(checksum) != 2 or checksum[1] != path.name:
        raise ValueError("breadth adjudication checksum record is malformed")
    if sha256_file(path) != f"sha256:{checksum[0]}":
        raise ValueError("breadth adjudication preregistration drifted")
    design = BreadthScoringAdjudicationDesign.model_validate_json(path.read_bytes())
    repo = root.parent
    checks = (
        (root / "SCORING_ADJUDICATION_PROTOCOL-v1.md", design.protocol_digest),
        (repo / "scripts/score_breadth_replication_task.py", design.scorer_source_digest),
        (repo / "scripts/adjudicate_breadth_scoring.py", design.adjudicator_source_digest),
        (
            repo / "src/adaptation_compiler_lab/benchmark/breadth_adjudication.py",
            design.adjudication_model_source_digest,
        ),
        (root / "results-v1/unblinded-result.json", design.original_result_file_digest),
        (root / "results-v1/blind-report.json", design.blind_report_file_digest),
        (root / "results-v1/completion.json", design.completion_file_digest),
        (root / "results-v1/judge-receipt.json", design.judge_receipt_file_digest),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"breadth adjudication dependency drifted: {artifact.name}")
    inputs = {item.blind_output_id: item for item in design.inputs}
    for output_id, item in inputs.items():
        path = root / f"results-v1/anonymous-outputs/{output_id}.json"
        if sha256_file(path) != item.public_output_digest:
            raise ValueError(f"breadth adjudication public output drifted: {output_id}")
    return design
