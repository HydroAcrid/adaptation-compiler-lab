"""Freeze Milestone 6A.4 before any live target session."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthProfileConstructionReceipt,
    BreadthProfileSet,
    BreadthReplicationContract,
    BreadthReplicationDesign,
    BreadthReplicationTask,
    build_breadth_plan,
    validate_breadth_profile_content,
)
from adaptation_compiler_lab.benchmark.breadth_replication_schema_export import (
    breadth_replication_schemas,
)
from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.sanitization import assert_condition_material_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from scripts.render_breadth_compiled_materials import render_breadth_compiled_materials


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
        raise TypeError("frozen breadth artifacts must be JSON objects")
    return (canonical_json(value) + "\n").encode("utf-8")


def _seed(path: Path, *, repo: Path) -> bytes:
    resolved = path.expanduser().absolute()
    if repo == resolved or repo in resolved.parents:
        raise RuntimeError("breadth randomization seed must remain outside the repository")
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if resolved.exists():
        if resolved.stat().st_mode & 0o077:
            raise RuntimeError("existing breadth seed permissions are too broad")
        value = resolved.read_bytes()
    else:
        value = os.urandom(32)
        _exclusive_write(resolved, value, mode=0o600)
    if len(value) != 32:
        raise RuntimeError("breadth randomization seed must contain exactly 32 bytes")
    return value


def _profile(root: Path, role: str) -> BreadthProfileSet:
    output = root / f"profile-{role}-output.json"
    receipt = BreadthProfileConstructionReceipt.model_validate_json(
        (root / f"profile-{role}-receipt.json").read_bytes()
    )
    profile = BreadthProfileSet.model_validate_json(output.read_bytes())
    validate_breadth_profile_content(profile)
    if canonical_digest(profile) != receipt.output_digest:
        raise RuntimeError(f"breadth {role} profile and receipt disagree")
    return profile


def _assert_construction(root: Path) -> None:
    author = _profile(root, "author")
    reviewer = _profile(root, "reviewer")
    for stage, value in enumerate(
        (reviewer.stage_1, reviewer.stage_2, reviewer.stage_3),
        start=1,
    ):
        material = root / f"condition-materials/strong-profile-stage-{stage}.md"
        if material.read_text(encoding="utf-8") != value.rstrip() + "\n":
            raise RuntimeError(f"accepted profile Stage {stage} does not match reviewer output")
        assert_condition_material_safe(value)
    rendered = render_breadth_compiled_materials()
    for stage, value in enumerate(rendered, start=1):
        material = root / f"condition-materials/compiled-stage-{stage}.md"
        if material.read_text(encoding="utf-8") != value:
            raise RuntimeError(f"compiled Stage {stage} does not match its renderer")
        assert_condition_material_safe(value)
    rejected = BreadthProfileSet.model_validate_json(
        (root / "rejected-profile-reviewer-output-v1.json").read_bytes()
    )
    try:
        validate_breadth_profile_content(rejected)
    except ValueError as error:
        if "unresolved stage reference" not in str(error):
            raise
    else:
        raise RuntimeError("rejected reviewer output unexpectedly became valid")
    rejection = canonical_json(
        json.loads((root / "PROFILE_REVIEW_REJECTION-v1.json").read_text(encoding="utf-8"))
    )
    if '"accepted_for_target_delivery":false' not in rejection:
        raise RuntimeError("profile rejection record does not fail closed")
    if len(author.stage_3.encode("utf-8")) > 3000:
        raise RuntimeError("author profile exceeded its construction ceiling")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_replication"
    frozen_names = (
        "PREREGISTRATION-v1.json",
        "PREREGISTRATION-v1.sha256",
        "PUBLIC_PLAN-v1.json",
        "EXECUTION_CONTRACT-v1.json",
    )
    for name in frozen_names:
        if (root / name).exists():
            raise RuntimeError(f"breadth artifact already exists: {name}")
    _assert_construction(root)

    tasks: list[BreadthReplicationTask] = []
    manifest_digests: list[str] = []
    scorer = repo / "scripts/score_breadth_replication_task.py"
    scorer_digest = sha256_file(scorer)
    for task_root in sorted(path for path in (root / "tasks").iterdir() if path.is_dir()):
        manifest = task_root / "task.json"
        wrapped = BreadthReplicationTask.model_validate_json(manifest.read_bytes())
        if wrapped.task_id != task_root.name:
            raise RuntimeError("breadth task directory and manifest disagree")
        if development_tree_digest(task_root / "fixture") != wrapped.task.fixture_digest:
            raise RuntimeError(f"breadth fixture digest drifted: {wrapped.task_id}")
        if development_tree_digest(task_root / "reference") != wrapped.reference_fixture_digest:
            raise RuntimeError(f"breadth reference digest drifted: {wrapped.task_id}")
        if wrapped.task.independent_scorer_digest != scorer_digest:
            raise RuntimeError(f"breadth scorer binding drifted: {wrapped.task_id}")
        tasks.append(wrapped)
        manifest_digests.append(sha256_file(manifest))

    compiled_paths = tuple(
        root / f"condition-materials/compiled-stage-{stage}.md" for stage in range(1, 4)
    )
    profile_paths = tuple(
        root / f"condition-materials/strong-profile-stage-{stage}.md" for stage in range(1, 4)
    )
    design = BreadthReplicationDesign(
        tasks=tuple(tasks),
        task_manifest_digests=tuple(manifest_digests),
        evidence_stages_digest=sha256_file(root / "EVIDENCE_STAGES-v1.json"),
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
        profile_author_receipt_digest=sha256_file(root / "profile-author-receipt.json"),
        profile_reviewer_receipt_digest=sha256_file(root / "profile-reviewer-receipt.json"),
        profile_author_packet_digest=sha256_file(root / "PROFILE_AUTHOR_PACKET.md"),
        profile_reviewer_packet_digest=sha256_file(root / "PROFILE_REVIEWER_PACKET.md"),
        rejected_profile_attempt_digest=sha256_file(
            root / "rejected-profile-reviewer-output-v1.json"
        ),
        profile_rejection_record_digest=sha256_file(root / "PROFILE_REVIEW_REJECTION-v1.json"),
        compiled_renderer_source_digest=sha256_file(
            repo / "scripts/render_breadth_compiled_materials.py"
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
    public_plan, private_plan = build_breadth_plan(
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
        raise RuntimeError("breadth private preregistration already exists")
    _exclusive_write(private_path, _canonical_bytes(private_plan), mode=0o600)

    contract = BreadthReplicationContract(
        design_digest=design.content_digest,
        public_plan_digest=public_plan.content_digest,
        protocol_digest=sha256_file(root / "EXECUTION_PROTOCOL-v1.md"),
        runner_source_digest=sha256_file(repo / "scripts/run_breadth_replication.py"),
        judge_runner_source_digest=sha256_file(repo / "scripts/run_breadth_judge.py"),
        unblind_source_digest=sha256_file(repo / "scripts/unblind_breadth_replication.py"),
        profile_runner_source_digest=sha256_file(
            repo / "scripts/run_breadth_profile_construction.py"
        ),
        breadth_model_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/breadth_replication.py"
        ),
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py"
        ),
        structured_role_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_structured_role.py"
        ),
    )
    _exclusive_write(root / "EXECUTION_CONTRACT-v1.json", _canonical_bytes(contract))
    schema_root = repo / "schemas/breadth_replication/v1"
    schema_root.mkdir(parents=True, exist_ok=False)
    for name, schema in breadth_replication_schemas().items():
        _exclusive_write(schema_root / name, _canonical_bytes(schema))


if __name__ == "__main__":
    main()
