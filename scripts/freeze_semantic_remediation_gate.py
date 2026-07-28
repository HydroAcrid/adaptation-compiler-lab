"""Freeze the compiled-only semantic renderer remediation gate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import CompactProjectionTask
from adaptation_compiler_lab.benchmark.semantic_remediation import (
    SemanticRemediationContract,
    SemanticRemediationDesign,
    load_semantic_remediation_contract,
    load_semantic_remediation_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.absolute()
    benchmark = repo / "development_benchmark_compact_projection"
    task_paths = (
        benchmark / "tasks-v2.3" / "stage_1_retained_publish" / "task.json",
        benchmark / "tasks-v2.3" / "stage_2_cache_publish" / "task.json",
        benchmark / "tasks-v2.3" / "stage_3_retained_default" / "task.json",
    )
    tasks = tuple(
        CompactProjectionTask.model_validate_json(path.read_bytes()) for path in task_paths
    )
    runtime = benchmark / "runtime-fixture-v2.3"
    design = SemanticRemediationDesign(
        tasks=tasks,
        task_fixture_digests=tuple(
            development_tree_digest(benchmark / task.fixture_directory) for task in tasks
        ),
        renderer_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/codex_runtime_v5.py"
        ),
        runtime_fixture_measurements_digest=sha256_file(runtime / "MEASUREMENTS-v2.3.json"),
        runtime_fixture_tree_digest=development_tree_digest(runtime),
        independent_scorer_digest=sha256_file(repo / "scripts/score_compact_projection_task.py"),
        policy_observer_digest=sha256_file(repo / "scripts/observe_compact_projection_policy.py"),
        scorer_sandbox_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py"
        ),
        prior_comparison_result_digest=sha256_file(
            benchmark / "results-v2.2/unblinded-result.json"
        ),
        inherited_smoke_receipt_digest=sha256_file(benchmark / "INSTRUMENT_SMOKE-v2.1.json"),
    )
    design_path = benchmark / "SEMANTIC_REMEDIATION_PREREGISTRATION-v1.json"
    checksum_path = design_path.with_suffix(".sha256")
    _exclusive_write(
        design_path,
        canonical_json(design.model_dump(mode="json", round_trip=True)) + "\n",
    )
    _exclusive_write(
        checksum_path,
        f"{sha256_file(design_path).removeprefix('sha256:')}  {design_path.name}\n",
    )
    if load_semantic_remediation_design(benchmark) != design:
        raise RuntimeError("semantic remediation design did not round-trip")

    contract = SemanticRemediationContract(
        design_digest=design.content_digest,
        execution_protocol_digest=sha256_file(benchmark / "SEMANTIC_REMEDIATION_PROTOCOL-v1.md"),
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py"
        ),
        target_orchestrator_source_digest=sha256_file(
            repo / "scripts/run_semantic_remediation_gate.py"
        ),
        inherited_smoke_receipt_digest=design.inherited_smoke_receipt_digest,
    )
    contract_path = benchmark / "SEMANTIC_REMEDIATION_CONTRACT-v1.json"
    _exclusive_write(
        contract_path,
        canonical_json(contract.model_dump(mode="json", round_trip=True)) + "\n",
    )
    if load_semantic_remediation_contract(benchmark, design=design) != contract:
        raise RuntimeError("semantic remediation contract did not round-trip")
    print(
        canonical_json(
            {
                "contract_digest": contract.content_digest,
                "design_digest": design.content_digest,
                "target_sessions": design.planned_target_sessions,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
