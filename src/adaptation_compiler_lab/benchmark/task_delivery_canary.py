"""Frozen one-session task-channel delivery canary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import CompactProjectionTask
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest


class TaskDeliveryCanaryDesign(FrozenModel):
    """Fresh test of content-addressed task-channel material delivery."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a2-task-channel-canary"] = "milestone-6a2-task-channel-canary"
    task: CompactProjectionTask
    condition: Literal["compiled_adaptation"] = "compiled_adaptation"
    task_fixture_digest: Sha256Digest
    renderer_source_digest: Sha256Digest
    renderer_id: Literal["codex-semantic-decision-runtime"] = "codex-semantic-decision-runtime"
    renderer_version: Literal["3.1.0"] = "3.1.0"
    runtime_fixture_measurements_digest: Sha256Digest
    runtime_fixture_tree_digest: Sha256Digest
    task_delivery_source_digest: Sha256Digest
    command_audit_source_digest: Sha256Digest
    independent_scorer_digest: Sha256Digest
    policy_observer_digest: Sha256Digest
    scorer_sandbox_digest: Sha256Digest
    prior_failed_result_digest: Sha256Digest
    inherited_smoke_receipt_digest: Sha256Digest
    preceding_product_sessions: Literal[13] = 13
    planned_target_sessions: Literal[1] = 1
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    target_sessions_started: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False
    delivery_channel: Literal["user_task"] = "user_task"
    material_occurrences: Literal[1] = 1
    all_records_must_be_valid: Literal[True] = True
    every_scenario_must_pass: Literal[True] = True
    comparative_claims_allowed: Literal[False] = False
    retries_allowed: Literal[False] = False

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        if self.task.stage != 1:
            raise ValueError("task-channel canary must target the failed first stage")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class TaskDeliveryCanaryContract(FrozenModel):
    """Exact zero-billing execution contract for task-channel delivery."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    execution_protocol_digest: Sha256Digest
    cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    cli_digest: Literal[
        "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    ] = "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["medium"] = "medium"
    service_mode: Literal["standard"] = "standard"
    max_seconds: Literal[600] = 600
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    target_sessions: Literal[1] = 1
    target_runner_source_digest: Sha256Digest
    target_orchestrator_source_digest: Sha256Digest
    outer_sandbox_digest: Literal[
        "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    ] = "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    inherited_smoke_receipt_digest: Sha256Digest
    sealed_external_validation_accessed: Literal[False] = False

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def load_task_delivery_canary_design(root: Path) -> TaskDeliveryCanaryDesign:
    """Load and revalidate the task-channel design."""

    path = root / "TASK_DELIVERY_CANARY_PREREGISTRATION-v1.json"
    fields = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(fields) != 2 or fields[1] != path.name or sha256_file(path) != f"sha256:{fields[0]}":
        raise ValueError("task-delivery canary preregistration checksum drifted")
    design = TaskDeliveryCanaryDesign.model_validate_json(path.read_bytes())
    fixture = (root / design.task.fixture_directory).resolve()
    manifest = fixture.parent / "task.json"
    if root.resolve() not in fixture.parents or not fixture.is_dir():
        raise ValueError("task-delivery canary fixture is unavailable")
    if json.loads(manifest.read_text(encoding="utf-8")) != design.task.model_dump(
        mode="json", round_trip=True
    ):
        raise ValueError("task-delivery canary manifest drifted")
    if development_tree_digest(fixture) != design.task_fixture_digest:
        raise ValueError("task-delivery canary fixture drifted")
    repo = root.parent
    checks = (
        (
            repo / "src/adaptation_compiler_lab/targets/codex_runtime_v6.py",
            design.renderer_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py",
            design.task_delivery_source_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py",
            design.command_audit_source_digest,
        ),
        (repo / "scripts/score_compact_projection_task.py", design.independent_scorer_digest),
        (repo / "scripts/observe_compact_projection_policy.py", design.policy_observer_digest),
        (
            repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
            design.scorer_sandbox_digest,
        ),
        (
            root / "runtime-fixture-v2.4/MEASUREMENTS-v2.4.json",
            design.runtime_fixture_measurements_digest,
        ),
        (root / "closed-world-canary-v1/result.json", design.prior_failed_result_digest),
        (root / "INSTRUMENT_SMOKE-v2.1.json", design.inherited_smoke_receipt_digest),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"task-delivery canary artifact drifted: {artifact.name}")
    if development_tree_digest(root / "runtime-fixture-v2.4") != (
        design.runtime_fixture_tree_digest
    ):
        raise ValueError("task-delivery runtime fixture drifted")
    return design


def load_task_delivery_canary_contract(
    root: Path,
    *,
    design: TaskDeliveryCanaryDesign,
) -> TaskDeliveryCanaryContract:
    """Load and validate exact execution source bindings."""

    contract = TaskDeliveryCanaryContract.model_validate_json(
        (root / "TASK_DELIVERY_CANARY_CONTRACT-v1.json").read_bytes()
    )
    if contract.design_digest != design.content_digest:
        raise ValueError("task-delivery contract design binding drifted")
    repo = root.parent
    checks = (
        (root / "TASK_DELIVERY_CANARY_PROTOCOL-v1.md", contract.execution_protocol_digest),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py",
            contract.target_runner_source_digest,
        ),
        (
            repo / "scripts/run_task_delivery_canary.py",
            contract.target_orchestrator_source_digest,
        ),
        (root / "INSTRUMENT_SMOKE-v2.1.json", contract.inherited_smoke_receipt_digest),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"task-delivery canary contract drifted: {artifact.name}")
    return contract
