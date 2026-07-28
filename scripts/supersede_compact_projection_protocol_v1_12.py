"""Freeze the fresh-task compact-projection and instrument-repair iteration."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionComparisonDesign,
    CompactProjectionScenario,
    CompactProjectionTask,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json
from adaptation_compiler_lab.targets.codex_runtime_v2 import (
    CODEX_RUNTIME_V2_RENDERER_ID,
    CODEX_RUNTIME_V2_RENDERER_VERSION,
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
    allowed = ("src/transfer_policy.py",)
    return (
        CompactProjectionTask(
            task_id="compact-v2-s1-retained-transfer",
            stage=1,
            fixture_directory=("tasks-v1.12/stage_1_retained_transfer/fixture"),
            task_prompt=(
                "A transfer planner handles retained user trees and rebuildable caches as "
                "defined in its module documentation. Correct the unsafe behavior for an "
                "existing retained user tree using the supplied requirements. Preserve the "
                "public signature, documented action vocabulary, new-target behavior, "
                "rebuildable-cache behavior, and unsupported-class handling."
            ),
            allowed_change_paths=allowed,
            scenarios=(
                CompactProjectionScenario(
                    scenario_id="compact-v2-s1-diagnostic-retained-requested",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=True,
                    expected_plan=("make_recovery_copy", "replace_target"),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s1-diagnostic-retained-unrequested",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("make_recovery_copy", "replace_target"),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s1-neutral-rebuildable",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=("replace_target",),
                    metric="neutral",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s1-objective-new-retained",
                    destination_exists=False,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("create_target",),
                    metric="objective",
                ),
            ),
        ),
        CompactProjectionTask(
            task_id="compact-v2-s2-rebuildable-exception",
            stage=2,
            fixture_directory=("tasks-v1.12/stage_2_rebuildable_exception/fixture"),
            task_prompt=(
                "The transfer planner now serves both retained user trees and rebuildable "
                "caches as defined in its module documentation. Correct existing-target "
                "behavior using the supplied requirements without regressing either class, "
                "new targets, the public signature, documented action vocabulary, or "
                "unsupported-class handling."
            ),
            allowed_change_paths=allowed,
            scenarios=(
                CompactProjectionScenario(
                    scenario_id="compact-v2-s2-diagnostic-cache-requested",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=True,
                    expected_plan=(
                        "write_temporary_tree",
                        "atomically_replace_target",
                    ),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s2-diagnostic-cache-unrequested",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=(
                        "write_temporary_tree",
                        "atomically_replace_target",
                    ),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s2-neutral-retained",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("make_recovery_copy", "replace_target"),
                    metric="neutral",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s2-objective-new-cache",
                    destination_exists=False,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=("create_target",),
                    metric="objective",
                ),
            ),
        ),
        CompactProjectionTask(
            task_id="compact-v2-s3-retained-default",
            stage=3,
            fixture_directory="tasks-v1.12/stage_3_retained_default/fixture",
            task_prompt=(
                "The transfer team revised the default for an existing retained user tree "
                "when no recovery copy is requested. Bring the planner in line with the "
                "supplied current requirements while preserving requested-recovery, "
                "rebuildable-cache, new-target, public-signature, documented-action, and "
                "unsupported-class behavior."
            ),
            allowed_change_paths=allowed,
            scenarios=(
                CompactProjectionScenario(
                    scenario_id="compact-v2-s3-diagnostic-retained-requested",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=True,
                    expected_plan=("make_recovery_copy", "replace_target"),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s3-diagnostic-retained-unrequested",
                    destination_exists=True,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("refuse_transfer",),
                    metric="diagnostic",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s3-neutral-rebuildable",
                    destination_exists=True,
                    storage_class="ephemeral_build_cache",
                    recovery_copy_approved=False,
                    expected_plan=(
                        "write_temporary_tree",
                        "atomically_replace_target",
                    ),
                    metric="neutral",
                ),
                CompactProjectionScenario(
                    scenario_id="compact-v2-s3-objective-new-retained",
                    destination_exists=False,
                    storage_class="durable_release",
                    recovery_copy_approved=False,
                    expected_plan=("create_target",),
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
    historical_path = root / "PREREGISTRATION-v1.11.json"
    historical_checksum = root / "PREREGISTRATION-v1.11.sha256"
    fields = historical_checksum.read_text(encoding="ascii").split()
    if (
        len(fields) != 2
        or fields[1] != historical_path.name
        or sha256_file(historical_path) != f"sha256:{fields[0]}"
    ):
        raise ValueError("refusing to supersede a drifted v1.11 preregistration")
    historical = CompactProjectionComparisonDesign.model_validate_json(historical_path.read_bytes())
    if historical.design_version != "1.11.0":
        raise ValueError("expected compact projection preregistration v1.11")
    prior_result = root / "results" / "unblinded-result.json"
    if not prior_result.is_file():
        raise ValueError("v1.12 requires the durable failed v1.11 result")
    tasks = _tasks()
    for task in tasks:
        fixture = root / task.fixture_directory
        if not fixture.is_dir():
            raise ValueError(f"v1.12 fixture is missing: {task.task_id}")
        manifest = fixture.parent / "task.json"
        payload = canonical_json(task.model_dump(mode="json", round_trip=True)) + "\n"
        if manifest.exists():
            if manifest.read_text(encoding="utf-8") != payload:
                raise ValueError(f"refusing to replace changed v1.12 task: {task.task_id}")
        else:
            _exclusive_write(manifest, payload)

    runtime = root / "runtime-fixture-v1.12"
    replacement = CompactProjectionComparisonDesign.model_validate(
        {
            **historical.model_dump(exclude_none=True, round_trip=True),
            "amendment_reason": ("fresh_tasks_compact_projection_and_instrument_repair"),
            "design_version": "1.12.0",
            "independent_scorer_digest": sha256_file(
                repo / "scripts" / "score_compact_projection_task.py"
            ),
            "policy_observer_digest": sha256_file(
                repo / "scripts" / "observe_compact_projection_policy.py"
            ),
            "prior_failed_result_digest": sha256_file(prior_result),
            "profile_author_sessions": 0,
            "profile_review_sessions": 1,
            "maximum_subscription_sessions": 8,
            "renderer_id": CODEX_RUNTIME_V2_RENDERER_ID,
            "renderer_source_digest": sha256_file(
                repo / "src/adaptation_compiler_lab/targets/codex_runtime_v2.py"
            ),
            "renderer_version": CODEX_RUNTIME_V2_RENDERER_VERSION,
            "runtime_fixture_measurements_digest": sha256_file(runtime / "MEASUREMENTS-v1.1.json"),
            "runtime_fixture_tree_digest": development_tree_digest(runtime),
            "shared_execution_envelope_digest": sha256_file(
                runtime / "shared-execution-envelope.md"
            ),
            "superseded_scorer_digest": historical.independent_scorer_digest,
            "supersedes_design_digest": historical.content_digest,
            "task_fixture_digests": tuple(
                development_tree_digest(root / task.fixture_directory) for task in tasks
            ),
            "tasks": tasks,
        }
    )
    preregistration = (
        canonical_json(replacement.model_dump(mode="json", exclude_none=True, round_trip=True))
        + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.12.json"
    checksum_path = root / "PREREGISTRATION-v1.12.sha256"
    if preregistration_path.exists() or checksum_path.exists():
        raise ValueError("compact projection v1.12 is already frozen")
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(checksum_path, f"{digest}  PREREGISTRATION-v1.12.json\n")
    print(
        canonical_json(
            {
                "design_digest": replacement.content_digest,
                "prior_failed_result_digest": replacement.prior_failed_result_digest,
                "sessions": replacement.maximum_subscription_sessions,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
