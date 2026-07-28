"""Freeze Milestone 6A.3 before any live target session."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import CompactProjectionTask
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    TaskChannelComparisonContract,
    TaskChannelComparisonDesign,
    build_task_channel_plan,
)
from adaptation_compiler_lab.benchmark.task_channel_schema_export import (
    task_channel_comparison_schemas,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("frozen comparison artifacts must be JSON objects")
    return (canonical_json(value) + "\n").encode("utf-8")


def _seed(path: Path, *, repo: Path) -> bytes:
    resolved = path.expanduser().absolute()
    if repo == resolved or repo in resolved.parents:
        raise RuntimeError("fair comparison seed must remain outside the repository")
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if resolved.exists():
        if resolved.stat().st_mode & 0o077:
            raise RuntimeError("existing fair comparison seed permissions are too broad")
        value = resolved.read_bytes()
    else:
        value = os.urandom(32)
        _exclusive_write(resolved, value, mode=0o600)
    if len(value) != 32:
        raise RuntimeError("fair comparison seed must contain exactly 32 bytes")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_task_channel_comparison"
    for name in (
        "PREREGISTRATION-v1.json",
        "PREREGISTRATION-v1.sha256",
        "PUBLIC_PLAN-v1.json",
        "EXECUTION_CONTRACT-v1.json",
    ):
        if (root / name).exists():
            raise RuntimeError(f"fair comparison artifact already exists: {name}")

    tasks: list[CompactProjectionTask] = []
    fixture_digests = []
    manifest_digests = []
    for task_root in sorted(path for path in (root / "tasks").iterdir() if path.is_dir()):
        manifest = task_root / "task.json"
        task = CompactProjectionTask.model_validate_json(manifest.read_bytes())
        tasks.append(task)
        fixture_digests.append(development_tree_digest(task_root / "fixture"))
        manifest_digests.append(sha256_file(manifest))
    tasks_value = tuple(sorted(tasks, key=lambda item: item.task_id))
    if tuple(task.task_id for task in tasks_value) != tuple(
        path.name for path in sorted(path for path in (root / "tasks").iterdir() if path.is_dir())
    ):
        raise RuntimeError("fair comparison task directories and manifests disagree")

    compiled_root = repo / "development_benchmark_compact_projection/runtime-fixture-v2.4"
    profile_root = repo / "development_benchmark_compact_projection/condition-materials-v1.14"
    compiled_paths = tuple(
        compiled_root / f"codex-runtime-stage-{stage}.md" for stage in range(1, 4)
    )
    profile_paths = tuple(
        profile_root / f"strong-profile-stage-{stage}.md" for stage in range(1, 4)
    )
    design = TaskChannelComparisonDesign(
        tasks=tasks_value,
        task_fixture_digests=tuple(fixture_digests),
        task_manifest_digests=tuple(manifest_digests),
        compiled_material_digests=cast(
            tuple[str, str, str],
            tuple(sha256_file(path) for path in compiled_paths),
        ),
        profile_material_digests=cast(
            tuple[str, str, str],
            tuple(sha256_file(path) for path in profile_paths),
        ),
        compiled_material_bytes=tuple(path.stat().st_size for path in compiled_paths),
        profile_material_bytes=tuple(path.stat().st_size for path in profile_paths),
        runtime_fixture_tree_digest=development_tree_digest(compiled_root),
        independent_scorer_digest=sha256_file(repo / "scripts/score_compact_projection_task.py"),
        policy_observer_digest=sha256_file(repo / "scripts/observe_compact_projection_policy.py"),
        scorer_sandbox_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py"
        ),
        task_delivery_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py"
        ),
        command_audit_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py"
        ),
        prior_task_delivery_result_digest=sha256_file(
            repo / "development_benchmark_compact_projection/task-delivery-canary-v1/result.json"
        ),
    )
    seed = _seed(arguments.seed_file, repo=repo)
    public_plan, private_plan = build_task_channel_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed,
    )
    design_path = root / "PREREGISTRATION-v1.json"
    _exclusive_write(design_path, _canonical_bytes(design))
    design_hash = sha256_file(design_path).removeprefix("sha256:")
    _exclusive_write(
        root / "PREREGISTRATION-v1.sha256",
        f"{design_hash}  {design_path.name}\n".encode("ascii"),
    )
    _exclusive_write(root / "PUBLIC_PLAN-v1.json", _canonical_bytes(public_plan))
    private_path = (
        arguments.seed_file.expanduser().absolute().with_name("private-plan-preregistration.json")
    )
    if private_path.exists():
        raise RuntimeError("fair comparison private preregistration already exists")
    _exclusive_write(private_path, _canonical_bytes(private_plan), mode=0o600)

    contract = TaskChannelComparisonContract(
        design_digest=design.content_digest,
        public_plan_digest=public_plan.content_digest,
        protocol_digest=sha256_file(root / "EXECUTION_PROTOCOL-v1.md"),
        runner_source_digest=sha256_file(repo / "scripts/run_fair_task_channel_comparison.py"),
        judge_runner_source_digest=sha256_file(repo / "scripts/run_fair_task_channel_judge.py"),
        unblind_source_digest=sha256_file(repo / "scripts/unblind_fair_task_channel_comparison.py"),
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py"
        ),
        structured_role_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py"
        ),
        inherited_smoke_receipt_digest=sha256_file(
            repo / "development_benchmark_compact_projection/INSTRUMENT_SMOKE-v2.1.json"
        ),
    )
    _exclusive_write(root / "EXECUTION_CONTRACT-v1.json", _canonical_bytes(contract))
    schema_root = repo / "schemas/task_channel_comparison/v1"
    schema_root.mkdir(parents=True, exist_ok=False)
    for name, schema in task_channel_comparison_schemas().items():
        _exclusive_write(schema_root / name, _canonical_bytes(schema))


if __name__ == "__main__":
    main()
