"""Typed retry records after the v3 real edit-and-test smoke."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentContract,
    BreadthInstrumentDesign,
    BreadthInstrumentPublicPlan,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest


class BreadthInstrumentRetryDesign(FrozenModel):
    """Frozen retry after a condition-independent pre-command instrument failure."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a4-v3-runner-retry"] = "milestone-6a4-v3-runner-retry"
    base_design_digest: Sha256Digest
    base_contract_digest: Sha256Digest
    failed_blind_report_digest: Sha256Digest
    failure_receipt_digest: Sha256Digest
    successful_smoke_receipt_digest: Sha256Digest
    runner_v3_source_digest: Sha256Digest
    scorer_source_digest: Sha256Digest
    protocol_digest: Sha256Digest
    failure_class: Literal["nested_sandbox_required_empty_control_mountpoints"] = (
        "nested_sandbox_required_empty_control_mountpoints"
    )
    failed_mapping_remains_withheld: Literal[True] = True
    failed_grid_unblinded: Literal[False] = False
    failed_grid_judged: Literal[False] = False
    failed_targets_accessed_task_content: Literal[False] = False
    task_payloads_unchanged: Literal[True] = True
    condition_materials_unchanged: Literal[True] = True
    eligible_evidence_unchanged: Literal[True] = True
    target_sessions: Literal[8] = 8
    judge_sessions: Literal[1] = 1
    maximum_subscription_sessions: Literal[9] = 9
    retries_during_grid: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    external_validation_accessed: Literal[False] = False

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BreadthInstrumentRetryContract(FrozenModel):
    """Pinned v3 execution contract for the one allowed clean retry."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    retry_design_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    protocol_digest: Sha256Digest
    runner_source_digest: Sha256Digest
    judge_runner_source_digest: Sha256Digest
    unblind_source_digest: Sha256Digest
    retry_model_source_digest: Sha256Digest
    base_model_source_digest: Sha256Digest
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


def load_breadth_instrument_retry_design(
    root: Path,
    *,
    base_design: BreadthInstrumentDesign,
    base_contract: BreadthInstrumentContract,
) -> BreadthInstrumentRetryDesign:
    """Load and verify the retry preregistration."""

    path = root / "RETRY_PREREGISTRATION-v1.json"
    checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(checksum) != 2 or checksum[1] != path.name:
        raise ValueError("retry checksum record is malformed")
    if sha256_file(path) != f"sha256:{checksum[0]}":
        raise ValueError("retry preregistration drifted")
    design = BreadthInstrumentRetryDesign.model_validate_json(path.read_bytes())
    if design.base_design_digest != base_design.content_digest:
        raise ValueError("retry base design binding drifted")
    if design.base_contract_digest != base_contract.content_digest:
        raise ValueError("retry base contract binding drifted")
    repo = root.parent
    dependencies = (
        (root / "results-v1/blind-report.json", design.failed_blind_report_digest),
        (root / "results-v1/instrument-failure.json", design.failure_receipt_digest),
        (root / "RUNNER_SMOKE-v3.json", design.successful_smoke_receipt_digest),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v3.py",
            design.runner_v3_source_digest,
        ),
        (repo / "scripts/score_breadth_instrument_task.py", design.scorer_source_digest),
        (root / "RETRY_PROTOCOL-v1.md", design.protocol_digest),
    )
    for artifact, expected in dependencies:
        if sha256_file(artifact) != expected:
            raise ValueError(f"retry dependency drifted: {artifact.name}")
    return design


def load_breadth_instrument_retry_contract(
    root: Path,
    *,
    retry_design: BreadthInstrumentRetryDesign,
) -> BreadthInstrumentRetryContract:
    """Load and verify the exact v3 retry execution contract."""

    contract = BreadthInstrumentRetryContract.model_validate_json(
        (root / "RETRY_EXECUTION_CONTRACT-v1.json").read_bytes()
    )
    if contract.retry_design_digest != retry_design.content_digest:
        raise ValueError("retry contract design binding drifted")
    public = BreadthInstrumentPublicPlan.model_validate_json(
        (root / "RETRY_PUBLIC_PLAN-v1.json").read_bytes()
    )
    if contract.public_plan_digest != public.content_digest:
        raise ValueError("retry public plan binding drifted")
    repo = root.parent
    dependencies = (
        (root / "RETRY_PROTOCOL-v1.md", contract.protocol_digest),
        (repo / "scripts/run_breadth_instrument_retry.py", contract.runner_source_digest),
        (
            repo / "scripts/run_breadth_instrument_retry_judge.py",
            contract.judge_runner_source_digest,
        ),
        (
            repo / "scripts/unblind_breadth_instrument_retry.py",
            contract.unblind_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/breadth_instrument_retry.py",
            contract.retry_model_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/breadth_instrument_repair.py",
            contract.base_model_source_digest,
        ),
        (repo / "scripts/score_breadth_instrument_task.py", contract.scorer_source_digest),
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
            raise ValueError(f"retry contract dependency drifted: {artifact.name}")
    return contract
