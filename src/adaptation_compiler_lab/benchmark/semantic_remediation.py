"""Frozen three-run semantic-renderer remediation gate."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import CompactProjectionTask
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest


class SemanticRemediationDesign(FrozenModel):
    """Fresh compiled-only validation within the twelve-target-run ceiling."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a1-semantic-renderer-remediation"] = (
        "milestone-6a1-semantic-renderer-remediation"
    )
    tasks: Annotated[tuple[CompactProjectionTask, ...], Field(min_length=3, max_length=3)]
    condition: Literal["compiled_adaptation"] = "compiled_adaptation"
    task_fixture_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    renderer_source_digest: Sha256Digest
    renderer_id: Literal["codex-semantic-decision-runtime"] = "codex-semantic-decision-runtime"
    renderer_version: Literal["3.0.0"] = "3.0.0"
    runtime_fixture_measurements_digest: Sha256Digest
    runtime_fixture_tree_digest: Sha256Digest
    independent_scorer_digest: Sha256Digest
    policy_observer_digest: Sha256Digest
    scorer_sandbox_digest: Sha256Digest
    prior_comparison_result_digest: Sha256Digest
    inherited_smoke_receipt_digest: Sha256Digest
    prior_target_sessions_completed: Literal[9] = 9
    planned_target_sessions: Literal[3] = 3
    cumulative_target_session_ceiling: Literal[12] = 12
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    target_sessions_started: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False
    all_records_must_be_valid: Literal[True] = True
    every_scenario_must_pass: Literal[True] = True
    comparative_claims_allowed: Literal[False] = False

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("semantic remediation tasks must be sorted and unique")
        if Counter(item.stage for item in self.tasks) != Counter({1: 1, 2: 1, 3: 1}):
            raise ValueError("semantic remediation needs one task per stage")
        if self.prior_target_sessions_completed + self.planned_target_sessions > (
            self.cumulative_target_session_ceiling
        ):
            raise ValueError("semantic remediation exceeds the target-session ceiling")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticRemediationContract(FrozenModel):
    """Exact zero-billing target execution contract."""

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
    target_sessions: Literal[3] = 3
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


def load_semantic_remediation_design(root: Path) -> SemanticRemediationDesign:
    """Load and revalidate the complete compiled-only design."""

    path = root / "SEMANTIC_REMEDIATION_PREREGISTRATION-v1.json"
    fields = path.with_suffix(".sha256").read_text(encoding="ascii").split()
    if len(fields) != 2 or fields[1] != path.name or sha256_file(path) != f"sha256:{fields[0]}":
        raise ValueError("semantic remediation preregistration checksum drifted")
    design = SemanticRemediationDesign.model_validate_json(path.read_bytes())
    observed: list[Sha256Digest] = []
    for task in design.tasks:
        fixture = (root / task.fixture_directory).resolve()
        manifest = fixture.parent / "task.json"
        if root.resolve() not in fixture.parents or not fixture.is_dir():
            raise ValueError("semantic remediation fixture is unavailable")
        if json.loads(manifest.read_text(encoding="utf-8")) != task.model_dump(
            mode="json", round_trip=True
        ):
            raise ValueError("semantic remediation task manifest drifted")
        observed.append(development_tree_digest(fixture))
    if tuple(observed) != design.task_fixture_digests:
        raise ValueError("semantic remediation fixture digest drifted")
    repo = root.parent
    checks = (
        (
            repo / "src/adaptation_compiler_lab/targets/codex_runtime_v5.py",
            design.renderer_source_digest,
        ),
        (repo / "scripts/score_compact_projection_task.py", design.independent_scorer_digest),
        (repo / "scripts/observe_compact_projection_policy.py", design.policy_observer_digest),
        (
            repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
            design.scorer_sandbox_digest,
        ),
        (
            root / "runtime-fixture-v2.3/MEASUREMENTS-v2.3.json",
            design.runtime_fixture_measurements_digest,
        ),
        (
            root / "results-v2.2/unblinded-result.json",
            design.prior_comparison_result_digest,
        ),
        (root / "INSTRUMENT_SMOKE-v2.1.json", design.inherited_smoke_receipt_digest),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"semantic remediation artifact drifted: {artifact.name}")
    if development_tree_digest(root / "runtime-fixture-v2.3") != (
        design.runtime_fixture_tree_digest
    ):
        raise ValueError("semantic remediation runtime fixture drifted")
    return design


def load_semantic_remediation_contract(
    root: Path,
    *,
    design: SemanticRemediationDesign,
) -> SemanticRemediationContract:
    """Load and validate the execution contract and its exact source bindings."""

    contract = SemanticRemediationContract.model_validate_json(
        (root / "SEMANTIC_REMEDIATION_CONTRACT-v1.json").read_bytes()
    )
    if contract.design_digest != design.content_digest:
        raise ValueError("semantic remediation contract design binding drifted")
    repo = root.parent
    checks = (
        (
            root / "SEMANTIC_REMEDIATION_PROTOCOL-v1.md",
            contract.execution_protocol_digest,
        ),
        (
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py",
            contract.target_runner_source_digest,
        ),
        (
            repo / "scripts/run_semantic_remediation_gate.py",
            contract.target_orchestrator_source_digest,
        ),
        (root / "INSTRUMENT_SMOKE-v2.1.json", contract.inherited_smoke_receipt_digest),
    )
    for artifact, expected in checks:
        if sha256_file(artifact) != expected:
            raise ValueError(f"semantic remediation contract drifted: {artifact.name}")
    return contract
