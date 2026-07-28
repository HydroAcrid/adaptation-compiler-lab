"""Freeze the clean Milestone 6A.4 breadth preregistration and blind plan."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentContract,
    BreadthInstrumentDesign,
    build_breadth_instrument_plan,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json
from scripts.build_breadth_instrument_tasks import build


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
        raise TypeError("frozen breadth instrument artifact must be an object")
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
        raise RuntimeError("clean breadth private state must remain outside the repository")
    external.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(external, 0o700)
    scorer = repo / "scripts/score_breadth_instrument_task.py"
    tasks = build(root, scorer=scorer)
    for item in tasks:
        path = root / f"tasks/{item.task_id}/task.json"
        expected = _canonical_bytes(item)
        if path.read_bytes() != expected:
            raise RuntimeError(f"task manifest must be rebuilt before freeze: {item.task_id}")
    compiled = root / "condition-materials/compiled-final.md"
    profile = (
        repo / "development_benchmark_breadth_replication/condition-materials/"
        "strong-profile-stage-3.md"
    )
    design = BreadthInstrumentDesign(
        tasks=tasks,
        task_manifest_digests=tuple(
            sha256_file(root / f"tasks/{item.task_id}/task.json") for item in tasks
        ),
        original_failed_result_digest=sha256_file(
            repo / "development_benchmark_breadth_replication/results-v1/unblinded-result.json"
        ),
        remediation_failed_result_digest=sha256_file(
            repo / "development_benchmark_breadth_remediation/results-v1/unblinded-result.json"
        ),
        compiled_material_digest=sha256_file(compiled),
        profile_material_digest=sha256_file(profile),
        compiled_material_bytes=len(compiled.read_bytes()),
        profile_material_bytes=len(profile.read_bytes()),
        scorer_source_digest=sha256_file(scorer),
        runner_source_digest=sha256_file(repo / "scripts/run_breadth_instrument.py"),
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v2.py"
        ),
        task_delivery_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py"
        ),
        command_audit_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py"
        ),
        protocol_digest=sha256_file(root / "EXECUTION_PROTOCOL-v1.md"),
    )
    preregistration = root / "PREREGISTRATION-v1.json"
    checksum = root / "PREREGISTRATION-v1.sha256"
    public_path = root / "PUBLIC_PLAN-v1.json"
    contract_path = root / "EXECUTION_CONTRACT-v1.json"
    if any(path.exists() for path in (preregistration, checksum, public_path, contract_path)):
        raise RuntimeError("clean breadth preregistration is already frozen")
    _exclusive_write(preregistration, _canonical_bytes(design), mode=0o644)
    _exclusive_write(
        checksum,
        f"{sha256_file(preregistration).removeprefix('sha256:')}  {preregistration.name}\n".encode(
            "ascii"
        ),
        mode=0o644,
    )
    seed_path = external / "randomization-seed.bin"
    if seed_path.exists():
        if seed_path.stat().st_mode & 0o077:
            raise RuntimeError("existing clean breadth seed permissions are unsafe")
        seed = seed_path.read_bytes()
    else:
        seed = secrets.token_bytes(32)
        _exclusive_write(seed_path, seed)
    public, private = build_breadth_instrument_plan(
        design_digest=design.content_digest,
        tasks=tasks,
        seed=seed,
    )
    _exclusive_write(public_path, _canonical_bytes(public), mode=0o644)
    _exclusive_write(
        external / "private-plan-preregistration.json",
        _canonical_bytes(private),
    )
    contract = BreadthInstrumentContract(
        design_digest=design.content_digest,
        public_plan_digest=public.content_digest,
        protocol_digest=sha256_file(root / "EXECUTION_PROTOCOL-v1.md"),
        runner_source_digest=sha256_file(repo / "scripts/run_breadth_instrument.py"),
        judge_runner_source_digest=sha256_file(repo / "scripts/run_breadth_instrument_judge.py"),
        unblind_source_digest=sha256_file(repo / "scripts/unblind_breadth_instrument.py"),
        model_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/breadth_instrument_repair.py"
        ),
        scorer_source_digest=sha256_file(scorer),
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription_v2.py"
        ),
        structured_role_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py"
        ),
    )
    _exclusive_write(contract_path, _canonical_bytes(contract), mode=0o644)
    print(
        canonical_json(
            {
                "compiled_material_bytes": design.compiled_material_bytes,
                "design_digest": design.content_digest,
                "maximum_subscription_sessions": design.maximum_subscription_sessions,
                "profile_material_bytes": design.profile_material_bytes,
                "provider_billed_calls": 0,
                "public_plan_digest": public.content_digest,
            }
        )
    )


if __name__ == "__main__":
    main()
