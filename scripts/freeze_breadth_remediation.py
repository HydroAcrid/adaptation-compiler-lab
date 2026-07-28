"""Freeze the Milestone 6A.4 oracle-contract remediation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.breadth_adjudication import (
    BreadthScoringAdjudicationResult,
)
from adaptation_compiler_lab.benchmark.breadth_remediation import (
    BreadthRemediationContract,
    BreadthRemediationDesign,
    BreadthRemediationTask,
    build_breadth_remediation_plan,
)
from adaptation_compiler_lab.benchmark.breadth_remediation_schema_export import (
    breadth_remediation_schemas,
)
from adaptation_compiler_lab.benchmark.breadth_replication import (
    load_breadth_contract,
    load_breadth_design,
)
from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
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
        raise TypeError("frozen remediation artifact must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _seed(path: Path, *, repo: Path) -> bytes:
    resolved = path.expanduser().absolute()
    if repo == resolved or repo in resolved.parents:
        raise RuntimeError("remediation seed must remain outside the repository")
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if resolved.exists():
        if resolved.stat().st_mode & 0o077:
            raise RuntimeError("existing remediation seed permissions are too broad")
        value = resolved.read_bytes()
    else:
        value = os.urandom(32)
        _exclusive_write(resolved, value, mode=0o600)
    if len(value) != 32:
        raise RuntimeError("remediation seed must contain exactly 32 bytes")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_remediation"
    for name in (
        "PREREGISTRATION-v1.json",
        "PREREGISTRATION-v1.sha256",
        "PUBLIC_PLAN-v1.json",
        "EXECUTION_CONTRACT-v1.json",
    ):
        if (root / name).exists():
            raise RuntimeError(f"remediation artifact already exists: {name}")
    scorer = repo / "scripts/score_breadth_remediation_task.py"
    scorer_digest = sha256_file(scorer)
    tasks = []
    manifest_digests = []
    for task_root in sorted(path for path in (root / "tasks").iterdir() if path.is_dir()):
        manifest = task_root / "task.json"
        task = BreadthRemediationTask.model_validate_json(manifest.read_bytes())
        if task.task_id != task_root.name:
            raise RuntimeError("remediation task directory and manifest disagree")
        if development_tree_digest(task_root / "fixture") != task.task.fixture_digest:
            raise RuntimeError(f"remediation fixture drifted: {task.task_id}")
        if development_tree_digest(task_root / "reference") != task.reference_fixture_digest:
            raise RuntimeError(f"remediation reference drifted: {task.task_id}")
        if task.task.independent_scorer_digest != scorer_digest:
            raise RuntimeError(f"remediation scorer binding drifted: {task.task_id}")
        tasks.append(task)
        manifest_digests.append(sha256_file(manifest))
    original_root = repo / "development_benchmark_breadth_replication"
    original_design = load_breadth_design(original_root)
    original_contract = load_breadth_contract(original_root, design=original_design)
    inherited_path = original_root / "results-v1.1/SCORING_ADJUDICATION-v1.json"
    inherited = BreadthScoringAdjudicationResult.model_validate_json(inherited_path.read_bytes())
    if inherited.replay_instrument_valid is not True:
        raise RuntimeError("remediation requires the valid scoring adjudication")
    compiled_paths = tuple(
        original_root / f"condition-materials/compiled-stage-{stage}.md" for stage in range(1, 4)
    )
    profile_paths = tuple(
        original_root / f"condition-materials/strong-profile-stage-{stage}.md"
        for stage in range(1, 4)
    )
    design = BreadthRemediationDesign(
        tasks=tuple(tasks),
        task_manifest_digests=tuple(manifest_digests),
        inherited_adjudication_result_digest=sha256_file(inherited_path),
        original_breadth_design_digest=original_design.content_digest,
        original_breadth_contract_digest=original_contract.content_digest,
        compiled_material_digests=cast(
            tuple[str, str, str],
            tuple(sha256_file(path) for path in compiled_paths),
        ),
        profile_material_digests=cast(
            tuple[str, str, str],
            tuple(sha256_file(path) for path in profile_paths),
        ),
        compiled_material_bytes=cast(
            tuple[int, int, int],
            tuple(path.stat().st_size for path in compiled_paths),
        ),
        profile_material_bytes=cast(
            tuple[int, int, int],
            tuple(path.stat().st_size for path in profile_paths),
        ),
        scorer_source_digest=scorer_digest,
        task_delivery_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/task_delivery.py"
        ),
        command_audit_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/command_audit.py"
        ),
    )
    seed = _seed(arguments.seed_file, repo=repo)
    public, private = build_breadth_remediation_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed,
    )
    design_path = root / "PREREGISTRATION-v1.json"
    _exclusive_write(design_path, _canonical_bytes(design))
    digest = sha256_file(design_path).removeprefix("sha256:")
    _exclusive_write(
        root / "PREREGISTRATION-v1.sha256",
        f"{digest}  {design_path.name}\n".encode("ascii"),
    )
    _exclusive_write(root / "PUBLIC_PLAN-v1.json", _canonical_bytes(public))
    private_path = (
        arguments.seed_file.expanduser().absolute().with_name("private-plan-preregistration.json")
    )
    if private_path.exists():
        raise RuntimeError("remediation private plan already exists")
    _exclusive_write(private_path, _canonical_bytes(private), mode=0o600)
    contract = BreadthRemediationContract(
        design_digest=design.content_digest,
        public_plan_digest=public.content_digest,
        protocol_digest=sha256_file(root / "EXECUTION_PROTOCOL-v1.md"),
        runner_source_digest=sha256_file(repo / "scripts/run_breadth_remediation.py"),
        judge_runner_source_digest=sha256_file(repo / "scripts/run_breadth_remediation_judge.py"),
        unblind_source_digest=sha256_file(repo / "scripts/unblind_breadth_remediation.py"),
        model_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/breadth_remediation.py"
        ),
        scorer_source_digest=scorer_digest,
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py"
        ),
        structured_role_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py"
        ),
    )
    _exclusive_write(root / "EXECUTION_CONTRACT-v1.json", _canonical_bytes(contract))
    schema_root = repo / "schemas/breadth_remediation/v1"
    schema_root.mkdir(parents=True, exist_ok=False)
    for name, schema in breadth_remediation_schemas().items():
        _exclusive_write(schema_root / name, _canonical_bytes(schema))


if __name__ == "__main__":
    main()
