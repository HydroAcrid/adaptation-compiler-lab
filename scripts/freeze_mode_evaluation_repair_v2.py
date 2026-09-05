"""Freeze the Mode evaluation v2 mechanical repair before its live smoke."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationExecutionContractV1,
    build_mode_evaluation_plan,
    load_mode_evaluation_contract,
)
from adaptation_compiler_lab.serialization import canonical_digest
from scripts.mode_evaluation_v2_common import (
    instrument_source_digests,
    load_object,
    write_new,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    seed_path = arguments.seed_file.expanduser().resolve()
    if seed_path.is_relative_to(repo) or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("Mode evaluation v2 seed must be private and external")
    repair = load_object(benchmark / "REPAIR_PROTOCOL-v2.json")
    if (
        repair.get("repair_of_report_digest")
        != "sha256:39126997857d169ae7c8f71b8c27663c6ecbc5f4ba577b72010a48e84c5d2914"
        or repair.get("mode_content_changed") is not False
        or repair.get("task_content_changed") is not False
        or repair.get("target_smoke_required") is not True
        or repair.get("scorer_smoke_required") is not True
    ):
        raise RuntimeError("Mode evaluation v2 repair protocol is invalid")
    v1 = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v1.json")
    payload = v1.model_dump(mode="python", round_trip=True)
    payload.update(instrument_source_digests(repo))
    contract = ModeEvaluationExecutionContractV1.model_validate(payload, strict=True)
    public, _ = build_mode_evaluation_plan(contract, seed=seed_path.read_bytes())
    contract_path = benchmark / "EXECUTION_CONTRACT-v2.json"
    public_path = benchmark / "PUBLIC_PLAN-v2.json"
    preregistration_path = benchmark / "PREREGISTRATION-v2.json"
    if any(path.exists() for path in (contract_path, public_path, preregistration_path)):
        raise RuntimeError("Mode evaluation v2 is already frozen")
    write_new(contract_path, contract.model_dump(mode="json", round_trip=True))
    write_new(public_path, public.model_dump(mode="json", round_trip=True))
    write_new(
        preregistration_path,
        {
            "instrument_version": "2.0.0",
            "schema_version": "1.0.0",
            "contract_digest": contract.content_digest,
            "public_plan_digest": public.content_digest,
            "repair_protocol_digest": canonical_digest(repair),
            "repair_of_report_digest": repair["repair_of_report_digest"],
            "mode_content_changed": False,
            "task_content_changed": False,
            "smoke_fixture_digest": sha256_file(benchmark / "tasks/mode-v2-smoke.json"),
            "target_smoke_required": True,
            "scorer_smoke_required": True,
            "provider_billed_calls": 0,
            "external_validation_accessed": False,
        },
    )


if __name__ == "__main__":
    main()
