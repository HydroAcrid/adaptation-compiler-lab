"""Freeze the public Mode-evaluation contract and blind execution order."""

from __future__ import annotations

import argparse
import os
import secrets
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.modes import MODE_EVALUATION_DESIGNS
from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationExecutionContractV1,
    build_mode_evaluation_plan,
    load_mode_evaluation_fixture,
)
from adaptation_compiler_lab.serialization import canonical_json


def _write_new(
    path: Path,
    value: BaseModel | Mapping[str, object] | bytes,
    *,
    mode: int = 0o600,
) -> None:
    payload = value if isinstance(value, bytes) else (canonical_json(value) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    parser.add_argument("--create-seed", action="store_true")
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    seed_file = arguments.seed_file.expanduser().resolve()
    if seed_file.is_relative_to(repo):
        raise RuntimeError("Mode evaluation seed must remain outside the repository")
    if arguments.create_seed:
        seed_file.parent.mkdir(parents=True, exist_ok=True)
        _write_new(seed_file, secrets.token_bytes(32))
    if seed_file.stat().st_mode & 0o077:
        raise RuntimeError("Mode evaluation seed permissions are too broad")
    fixtures = tuple(
        load_mode_evaluation_fixture(path) for path in sorted((benchmark / "tasks").glob("*.json"))
    )
    designs = {item.mode_id: item for item in MODE_EVALUATION_DESIGNS}
    for fixture in fixtures:
        design = designs.get(fixture.mode_id)
        if design is None:
            raise RuntimeError("fixture references a Mode without a public evaluation design")
        design_task = next((item for item in design.tasks if item.task_id == fixture.task_id), None)
        if (
            design_task is None
            or design_task.kind != fixture.kind
            or design_task.title != fixture.title
        ):
            raise RuntimeError("fixture no longer matches its public Mode evaluation design")
        if development_tree_digest(benchmark / fixture.fixture_directory) != fixture.fixture_digest:
            raise RuntimeError("fixture tree changed before contract freeze")
    contract = ModeEvaluationExecutionContractV1(
        catalog_design_digests=tuple(sorted(item.content_digest for item in designs.values())),
        fixtures=fixtures,
        runner_source_digest=sha256_file(repo / "scripts/run_mode_evaluation.py"),
        scorer_source_digest=sha256_file(repo / "scripts/score_mode_evaluation_task.py"),
        observer_source_digest=sha256_file(repo / "scripts/observe_mode_evaluation_policy.py"),
        judge_role_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_mode_judge.py"
        ),
        judge_source_digest=sha256_file(repo / "scripts/judge_mode_evaluation.py"),
        unblind_source_digest=sha256_file(repo / "scripts/unblind_mode_evaluation.py"),
    )
    public_plan, _ = build_mode_evaluation_plan(contract, seed=seed_file.read_bytes())
    _write_new(benchmark / "EXECUTION_CONTRACT-v1.json", contract)
    _write_new(benchmark / "PUBLIC_PLAN-v1.json", public_plan)
    _write_new(
        benchmark / "PREREGISTRATION-v1.sha256",
        (contract.content_digest + "\n").encode("ascii"),
    )
    print(
        canonical_json(
            {
                "contract_digest": contract.content_digest,
                "public_plan_digest": public_plan.content_digest,
                "seed_commitment": public_plan.seed_commitment,
                "target_runs": contract.target_runs,
            }
        )
    )


if __name__ == "__main__":
    main()
