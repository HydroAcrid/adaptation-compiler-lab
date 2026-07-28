"""Freeze the one v3 breadth retry after the successful real runner smoke."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    build_breadth_instrument_plan,
    load_breadth_instrument_contract,
    load_breadth_instrument_design,
)
from adaptation_compiler_lab.benchmark.breadth_instrument_retry import (
    BreadthInstrumentRetryContract,
    BreadthInstrumentRetryDesign,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("frozen retry artifact must be an object")
    return (canonical_json(value) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_instrument_repair"
    external = arguments.external_root.resolve()
    if repo == external or repo in external.parents:
        raise RuntimeError("retry private state must remain outside the repository")
    external.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(external, 0o700)
    base_design = load_breadth_instrument_design(root)
    base_contract = load_breadth_instrument_contract(root, design=base_design)
    smoke = root / "RUNNER_SMOKE-v3.json"
    smoke_value = smoke.read_text(encoding="utf-8")
    if '"smoke_passed":true' not in smoke_value:
        raise RuntimeError("v3 retry requires a successful real runner smoke")
    retry_design = BreadthInstrumentRetryDesign(
        base_design_digest=base_design.content_digest,
        base_contract_digest=base_contract.content_digest,
        failed_blind_report_digest=sha256_file(root / "results-v1/blind-report.json"),
        failure_receipt_digest=sha256_file(root / "results-v1/instrument-failure.json"),
        successful_smoke_receipt_digest=sha256_file(smoke),
        runner_v3_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v3.py"
        ),
        scorer_source_digest=sha256_file(repo / "scripts/score_breadth_instrument_task.py"),
        protocol_digest=sha256_file(root / "RETRY_PROTOCOL-v1.md"),
    )
    preregistration = root / "RETRY_PREREGISTRATION-v1.json"
    checksum = root / "RETRY_PREREGISTRATION-v1.sha256"
    public_path = root / "RETRY_PUBLIC_PLAN-v1.json"
    contract_path = root / "RETRY_EXECUTION_CONTRACT-v1.json"
    if any(path.exists() for path in (preregistration, checksum, public_path, contract_path)):
        raise RuntimeError("v3 retry is already frozen")
    _exclusive_write(preregistration, _canonical_bytes(retry_design), mode=0o644)
    _exclusive_write(
        checksum,
        f"{sha256_file(preregistration).removeprefix('sha256:')}  {preregistration.name}\n".encode(
            "ascii"
        ),
        mode=0o644,
    )
    seed_path = external / "randomization-seed.bin"
    seed = secrets.token_bytes(32)
    _exclusive_write(seed_path, seed)
    public, private = build_breadth_instrument_plan(
        design_digest=retry_design.content_digest,
        tasks=base_design.tasks,
        seed=seed,
    )
    _exclusive_write(public_path, _canonical_bytes(public), mode=0o644)
    _exclusive_write(
        external / "private-plan-preregistration.json",
        _canonical_bytes(private),
    )
    contract = BreadthInstrumentRetryContract(
        retry_design_digest=retry_design.content_digest,
        public_plan_digest=public.content_digest,
        protocol_digest=sha256_file(root / "RETRY_PROTOCOL-v1.md"),
        runner_source_digest=sha256_file(repo / "scripts/run_breadth_instrument_retry.py"),
        judge_runner_source_digest=sha256_file(
            repo / "scripts/run_breadth_instrument_retry_judge.py"
        ),
        unblind_source_digest=sha256_file(repo / "scripts/unblind_breadth_instrument_retry.py"),
        retry_model_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/breadth_instrument_retry.py"
        ),
        base_model_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/breadth_instrument_repair.py"
        ),
        scorer_source_digest=sha256_file(repo / "scripts/score_breadth_instrument_task.py"),
        target_runner_v3_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v3.py"
        ),
        structured_role_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py"
        ),
    )
    _exclusive_write(contract_path, _canonical_bytes(contract), mode=0o644)
    print(
        canonical_json(
            {
                "maximum_subscription_sessions": retry_design.maximum_subscription_sessions,
                "provider_billed_calls": 0,
                "public_plan_digest": public.content_digest,
                "retry_design_digest": retry_design.content_digest,
            }
        )
    )


if __name__ == "__main__":
    main()
