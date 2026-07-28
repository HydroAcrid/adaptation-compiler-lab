"""Freeze the one-session task-channel delivery canary."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import CompactProjectionTask
from adaptation_compiler_lab.benchmark.task_delivery_canary import (
    TaskDeliveryCanaryContract,
    TaskDeliveryCanaryDesign,
    load_task_delivery_canary_contract,
    load_task_delivery_canary_design,
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
    task_path = benchmark / "tasks-v2.5/stage_1_task_delivery/task.json"
    task = CompactProjectionTask.model_validate_json(task_path.read_bytes())
    runtime = benchmark / "runtime-fixture-v2.4"
    design = TaskDeliveryCanaryDesign(
        task=task,
        task_fixture_digest=development_tree_digest(benchmark / task.fixture_directory),
        renderer_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/codex_runtime_v6.py"
        ),
        runtime_fixture_measurements_digest=sha256_file(runtime / "MEASUREMENTS-v2.4.json"),
        runtime_fixture_tree_digest=development_tree_digest(runtime),
        task_delivery_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py"
        ),
        command_audit_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py"
        ),
        independent_scorer_digest=sha256_file(repo / "scripts/score_compact_projection_task.py"),
        policy_observer_digest=sha256_file(repo / "scripts/observe_compact_projection_policy.py"),
        scorer_sandbox_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py"
        ),
        prior_failed_result_digest=sha256_file(benchmark / "closed-world-canary-v1/result.json"),
        inherited_smoke_receipt_digest=sha256_file(benchmark / "INSTRUMENT_SMOKE-v2.1.json"),
    )
    design_path = benchmark / "TASK_DELIVERY_CANARY_PREREGISTRATION-v1.json"
    checksum_path = design_path.with_suffix(".sha256")
    _exclusive_write(
        design_path,
        canonical_json(design.model_dump(mode="json", round_trip=True)) + "\n",
    )
    _exclusive_write(
        checksum_path,
        f"{sha256_file(design_path).removeprefix('sha256:')}  {design_path.name}\n",
    )
    if load_task_delivery_canary_design(benchmark) != design:
        raise RuntimeError("task-delivery canary design did not round-trip")

    contract = TaskDeliveryCanaryContract(
        design_digest=design.content_digest,
        execution_protocol_digest=sha256_file(benchmark / "TASK_DELIVERY_CANARY_PROTOCOL-v1.md"),
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py"
        ),
        target_orchestrator_source_digest=sha256_file(repo / "scripts/run_task_delivery_canary.py"),
        inherited_smoke_receipt_digest=design.inherited_smoke_receipt_digest,
    )
    contract_path = benchmark / "TASK_DELIVERY_CANARY_CONTRACT-v1.json"
    _exclusive_write(
        contract_path,
        canonical_json(contract.model_dump(mode="json", round_trip=True)) + "\n",
    )
    if (
        load_task_delivery_canary_contract(
            benchmark,
            design=design,
        )
        != contract
    ):
        raise RuntimeError("task-delivery canary contract did not round-trip")
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
