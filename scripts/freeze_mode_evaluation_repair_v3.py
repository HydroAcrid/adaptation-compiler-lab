"""Freeze the Mode evaluation v3 mechanical repair before its live smoke."""

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
from scripts.mode_evaluation_v3_common import (
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
        raise RuntimeError("Mode evaluation v3 seed must be private and external")
    repair = load_object(benchmark / "REPAIR_PROTOCOL-v3.json")
    if (
        repair.get("repair_of_smoke_digest")
        != "sha256:4c00239f56d245d77f33541977676e74ba852c5a4670eb7ac23b36c3c1071fe5"
        or repair.get("mode_content_changed") is not False
        or repair.get("task_content_changed") is not False
        or repair.get("target_smoke_required") is not True
        or repair.get("scorer_smoke_required") is not True
        or repair.get("scorer_invocation_path_preserved") is not True
        or repair.get("code_mode_host_digest")
        != "sha256:c215117917037afd6b7621ba11ca18054ebdb890c314454f485b27574a73e1b7"
    ):
        raise RuntimeError("Mode evaluation v3 repair protocol is invalid")
    v2 = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v2.json")
    payload = v2.model_dump(mode="python", round_trip=True)
    payload.update(instrument_source_digests(repo))
    contract = ModeEvaluationExecutionContractV1.model_validate(payload, strict=True)
    public, _ = build_mode_evaluation_plan(contract, seed=seed_path.read_bytes())
    contract_path = benchmark / "EXECUTION_CONTRACT-v3.json"
    public_path = benchmark / "PUBLIC_PLAN-v3.json"
    preregistration_path = benchmark / "PREREGISTRATION-v3.json"
    if any(path.exists() for path in (contract_path, public_path, preregistration_path)):
        raise RuntimeError("Mode evaluation v3 is already frozen")
    write_new(contract_path, contract.model_dump(mode="json", round_trip=True))
    write_new(public_path, public.model_dump(mode="json", round_trip=True))
    write_new(
        preregistration_path,
        {
            "instrument_version": "3.0.0",
            "schema_version": "1.0.0",
            "contract_digest": contract.content_digest,
            "public_plan_digest": public.content_digest,
            "repair_protocol_digest": canonical_digest(repair),
            "repair_of_smoke_digest": repair["repair_of_smoke_digest"],
            "mode_content_changed": False,
            "task_content_changed": False,
            "smoke_fixture_digest": sha256_file(benchmark / "tasks/mode-v2-smoke.json"),
            "code_mode_host_digest": repair["code_mode_host_digest"],
            "scorer_invocation_path_preserved": True,
            "target_smoke_required": True,
            "scorer_smoke_required": True,
            "provider_billed_calls": 0,
            "external_validation_accessed": False,
        },
    )


if __name__ == "__main__":
    main()
