"""Freeze the exact zero-billing execution contract for design v2.2."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.compact_execution import (
    CompactExecutionContract,
    load_compact_execution_contract,
)
from adaptation_compiler_lab.benchmark.compact_projection import load_compact_projection_design
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
    design = load_compact_projection_design(benchmark, version="2.2")
    contract = CompactExecutionContract(
        contract_version="1.10.0",
        design_digest=design.content_digest,
        execution_protocol_digest=sha256_file(benchmark / "EXECUTION_PROTOCOL-v2.2.md"),
        maximum_subscription_sessions=7,
        profile_author_sessions=0,
        profile_review_sessions=0,
        instrument_smoke_sessions=None,
        target_sandbox="workspace-write-inside-read-only-outer-mount-namespace",
        target_outer_sandbox_digest=(
            "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
        ),
        target_workspace_policy="workspace-read-only-except-registered-source-file",
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py"
        ),
        target_orchestrator_source_digest=sha256_file(
            repo / "scripts/run_durable_progress_comparison.py"
        ),
        inherited_profile_receipt_digest=sha256_file(
            benchmark / "profile-remediation-receipt-v1.14.json"
        ),
        inherited_smoke_receipt_digest=sha256_file(benchmark / "INSTRUMENT_SMOKE-v2.1.json"),
    )
    target = benchmark / "EXECUTION_CONTRACT-v1.10.json"
    _exclusive_write(
        target,
        canonical_json(contract.model_dump(mode="json", exclude_none=True, round_trip=True)) + "\n",
    )
    loaded = load_compact_execution_contract(benchmark, design=design)
    if loaded != contract:
        raise RuntimeError("durable-progress execution contract did not round-trip")
    print(canonical_json({"contract_digest": contract.content_digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
