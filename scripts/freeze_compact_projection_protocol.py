"""Freeze the fresh public Milestone 6A.1 tasks and scorer bindings."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import (
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionComparisonDesign,
    CompactProjectionScenario,
    CompactProjectionTask,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json
from adaptation_compiler_lab.targets.codex_runtime import (
    CODEX_RUNTIME_RENDERER_ID,
    CODEX_RUNTIME_RENDERER_VERSION,
)


def _exclusive_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _tasks() -> tuple[
    CompactProjectionTask,
    CompactProjectionTask,
    CompactProjectionTask,
]:
    return (
        CompactProjectionTask(
            task_id="compact-s1-durable-delivery",
            stage=1,
            fixture_directory="tasks/stage_1_durable_delivery/fixture",
            task_prompt=(
                "A teammate reports that plan_delivery has unsafe behavior when publishing "
                "over an existing long-lived release directory. Update deployment_policy.py "
                "to honor the supplied requirements while preserving its public function "
                "signature, new-destination behavior, and unsupported-class handling."
            ),
            scenarios=(
                CompactProjectionScenario(
                    scenario_id="compact-s1-diagnostic-existing-approved",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=True,
                    expected_plan=("create_recovery_copy", "replace_destination"),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s1-diagnostic-existing-default",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("create_recovery_copy", "replace_destination"),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s1-neutral-existing-cache",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=("replace_destination",),
                    metric="neutral",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s1-objective-new-durable",
                    destination_exists=False,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("create_destination",),
                    metric="objective",
                ),
            ),
        ),
        CompactProjectionTask(
            task_id="compact-s2-cache-exception",
            stage=2,
            fixture_directory="tasks/stage_2_cache_exception/fixture",
            task_prompt=(
                "The delivery planner now serves both long-lived release directories and "
                "regenerable build caches. Correct plan_delivery for existing destinations "
                "using the supplied requirements without regressing either class, new "
                "destinations, or unsupported-class handling."
            ),
            scenarios=(
                CompactProjectionScenario(
                    scenario_id="compact-s2-diagnostic-cache-approved",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=True,
                    expected_plan=(
                        "write_temporary_tree",
                        "atomically_replace_destination",
                    ),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s2-diagnostic-cache-default",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=(
                        "write_temporary_tree",
                        "atomically_replace_destination",
                    ),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s2-neutral-durable-default",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("create_recovery_copy", "replace_destination"),
                    metric="neutral",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s2-objective-new-cache",
                    destination_exists=False,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=("create_destination",),
                    metric="objective",
                ),
            ),
        ),
        CompactProjectionTask(
            task_id="compact-s3-durable-default",
            stage=3,
            fixture_directory="tasks/stage_3_durable_default/fixture",
            task_prompt=(
                "The deployment team revised how existing long-lived release destinations are "
                "handled when recovery-copy approval is absent. Bring plan_delivery in line "
                "with the supplied current requirements while preserving regenerable-cache, "
                "new-destination, and unsupported-class behavior."
            ),
            scenarios=(
                CompactProjectionScenario(
                    scenario_id="compact-s3-diagnostic-durable-approved",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=True,
                    expected_plan=("create_recovery_copy", "replace_destination"),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s3-diagnostic-durable-default",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("refuse_replacement",),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s3-neutral-existing-cache",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=(
                        "write_temporary_tree",
                        "atomically_replace_destination",
                    ),
                    metric="neutral",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-s3-objective-new-durable",
                    destination_exists=False,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("create_destination",),
                    metric="objective",
                ),
            ),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    root = arguments.benchmark_root.resolve()
    tasks = _tasks()
    for task in tasks:
        task_root = root / task.fixture_directory
        manifest = task_root.parent / "task.json"
        expected_manifest = canonical_json(task.model_dump(mode="json", round_trip=True)) + "\n"
        if manifest.exists():
            if manifest.read_text(encoding="utf-8") != expected_manifest:
                raise ValueError(f"refusing to replace changed task manifest: {task.task_id}")
        else:
            _exclusive_write(manifest, expected_manifest)
    design = CompactProjectionComparisonDesign(
        tasks=tasks,
        task_fixture_digests=(
            development_tree_digest(root / tasks[0].fixture_directory),
            development_tree_digest(root / tasks[1].fixture_directory),
            development_tree_digest(root / tasks[2].fixture_directory),
        ),
        independent_scorer_digest=sha256_file(
            repo / "scripts" / "score_compact_projection_task.py"
        ),
        renderer_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/codex_runtime.py"
        ),
        renderer_id=CODEX_RUNTIME_RENDERER_ID,
        renderer_version=CODEX_RUNTIME_RENDERER_VERSION,
        runtime_fixture_measurements_digest=sha256_file(
            root / "runtime-fixture" / "MEASUREMENTS-v1.0.json"
        ),
        runtime_fixture_tree_digest=development_tree_digest(root / "runtime-fixture"),
        shared_execution_envelope_digest=sha256_file(
            root / "runtime-fixture" / "shared-execution-envelope.md"
        ),
    )
    preregistration = (
        canonical_json(design.model_dump(mode="json", exclude_none=True, round_trip=True)) + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.0.json"
    checksum_path = root / "PREREGISTRATION-v1.0.sha256"
    if preregistration_path.exists() or checksum_path.exists():
        raise ValueError("compact projection protocol is already frozen")
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(
        checksum_path,
        f"{digest}  PREREGISTRATION-v1.0.json\n",
    )
    print(canonical_json({"design_digest": design.content_digest, "sessions": 9}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
