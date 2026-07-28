"""Freeze the typed-decision comparison after the v1.19 product-gate failure."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionComparisonDesign,
    CompactProjectionTask,
    load_compact_projection_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _exclusive_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.absolute()
    benchmark = repo / "development_benchmark_compact_projection"
    prior = load_compact_projection_design(benchmark, version="1.19")
    result = json.loads(
        (benchmark / "results-v1.19" / "unblinded-result.json").read_text(encoding="utf-8")
    )
    task_paths = (
        benchmark / "tasks-v2.0" / "stage_1_retained_publish" / "task.json",
        benchmark / "tasks-v2.0" / "stage_2_cache_publish" / "task.json",
        benchmark / "tasks-v2.0" / "stage_3_retained_default" / "task.json",
    )
    tasks = tuple(
        CompactProjectionTask.model_validate_json(path.read_bytes()) for path in task_paths
    )
    runtime = benchmark / "runtime-fixture-v2.0"
    design = CompactProjectionComparisonDesign(
        design_version="2.0.0",
        tasks=tasks,
        task_fixture_digests=tuple(
            development_tree_digest(benchmark / task.fixture_directory) for task in tasks
        ),
        independent_scorer_digest=prior.independent_scorer_digest,
        renderer_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/targets/codex_runtime_v3.py"
        ),
        renderer_id="codex-decision-runtime",
        renderer_version="2.0.0",
        runtime_fixture_measurements_digest=sha256_file(runtime / "MEASUREMENTS-v2.0.json"),
        runtime_fixture_tree_digest=development_tree_digest(runtime),
        shared_execution_envelope_digest=prior.shared_execution_envelope_digest,
        profile_author_sessions=0,
        profile_review_sessions=0,
        instrument_smoke_sessions=1,
        maximum_subscription_sessions=8,
        supersedes_design_digest=prior.content_digest,
        superseded_scorer_digest=prior.independent_scorer_digest,
        amendment_reason="typed_decision_projection_and_fresh_tasks",
        policy_observer_digest=prior.policy_observer_digest,
        scorer_sandbox_digest=prior.scorer_sandbox_digest,
        prior_failed_result_digest=canonical_digest(result),
        prior_failed_profile_receipt_digest=prior.prior_failed_profile_receipt_digest,
        prior_failed_target_receipt_digest=result["scorer_adjudication_receipt_digest"],
        prior_failed_smoke_receipt_digest=prior.prior_failed_smoke_receipt_digest,
    )
    target = benchmark / "PREREGISTRATION-v2.0.json"
    checksum = benchmark / "PREREGISTRATION-v2.0.sha256"
    document = canonical_json(design.model_dump(mode="json", round_trip=True)) + "\n"
    _exclusive_write(target, document)
    _exclusive_write(
        checksum,
        f"{sha256_file(target).removeprefix('sha256:')}  {target.name}\n",
    )
    loaded = load_compact_projection_design(benchmark, version="2.0")
    if loaded != design:
        raise RuntimeError("frozen v2.0 design did not round-trip")
    print(
        json.dumps(
            {
                "design_digest": design.content_digest,
                "prior_failed_result_digest": design.prior_failed_result_digest,
                "runtime_bytes": [
                    len((runtime / f"codex-runtime-stage-{stage}.md").read_bytes())
                    for stage in (1, 2, 3)
                ],
                "task_fixture_digests": list(design.task_fixture_digests),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
