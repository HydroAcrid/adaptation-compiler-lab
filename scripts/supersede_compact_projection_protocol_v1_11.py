"""Issue the immutable shared-envelope task-path alignment amendment."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionComparisonDesign,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    root = arguments.benchmark_root.resolve()
    historical_path = root / "PREREGISTRATION-v1.10.json"
    historical_checksum = root / "PREREGISTRATION-v1.10.sha256"
    fields = historical_checksum.read_text(encoding="ascii").split()
    if (
        len(fields) != 2
        or fields[1] != historical_path.name
        or sha256_file(historical_path) != f"sha256:{fields[0]}"
    ):
        raise ValueError("refusing to amend a drifted v1.10 preregistration")
    historical = CompactProjectionComparisonDesign.model_validate_json(historical_path.read_bytes())
    if historical.design_version != "1.10.0":
        raise ValueError("expected compact projection preregistration v1.10")
    if (
        historical.target_sessions_started
        or historical.profile_sessions_started
        or historical.judge_sessions_started
    ):
        raise ValueError("cannot amend a protocol after any registered session starts")

    runtime_fixture = root / "runtime-fixture-v1.11"
    prior_fixture = root / "runtime-fixture-v1.5"
    if not runtime_fixture.is_dir():
        raise ValueError("v1.11 runtime fixture is missing")
    allowed_changes = {
        "MEASUREMENTS-v1.0.json",
        "shared-execution-envelope.json",
        "shared-execution-envelope.md",
    }
    prior_files = {
        path.relative_to(prior_fixture).as_posix(): path
        for path in prior_fixture.rglob("*")
        if path.is_file()
    }
    replacement_files = {
        path.relative_to(runtime_fixture).as_posix(): path
        for path in runtime_fixture.rglob("*")
        if path.is_file()
    }
    if set(prior_files) != set(replacement_files):
        raise ValueError("v1.11 runtime fixture changed its file inventory")
    drifted_unaffected = tuple(
        name
        for name in sorted(prior_files)
        if name not in allowed_changes
        and prior_files[name].read_bytes() != replacement_files[name].read_bytes()
    )
    if drifted_unaffected:
        raise ValueError(
            "v1.11 changed artifacts outside the shared envelope: " + ", ".join(drifted_unaffected)
        )
    envelope_text = (runtime_fixture / "shared-execution-envelope.md").read_text(encoding="utf-8")
    if "Allowed paths: deployment_policy.py." not in envelope_text:
        raise ValueError("v1.11 shared envelope does not match the task edit path")
    if "Allowed paths: policy.py." in envelope_text:
        raise ValueError("v1.11 shared envelope retained the stale edit path")

    task_digests = tuple(
        development_tree_digest((root / task.fixture_directory).resolve())
        for task in historical.tasks
    )
    unchanged_digests = {
        "independent scorer": (
            sha256_file(repo / "scripts" / "score_compact_projection_task.py"),
            historical.independent_scorer_digest,
        ),
        "policy observer": (
            sha256_file(repo / "scripts" / "observe_compact_projection_policy.py"),
            historical.policy_observer_digest,
        ),
        "renderer": (
            sha256_file(repo / "src/adaptation_compiler_lab/targets/codex_runtime.py"),
            historical.renderer_source_digest,
        ),
        "scorer sandbox": (
            sha256_file(repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py"),
            historical.scorer_sandbox_digest,
        ),
        "task fixtures": (task_digests, historical.task_fixture_digests),
    }
    drifted = tuple(
        label for label, (observed, expected) in unchanged_digests.items() if observed != expected
    )
    if drifted:
        raise ValueError(
            "refusing to rebind artifacts that drifted since v1.10: " + ", ".join(drifted)
        )

    replacement = CompactProjectionComparisonDesign.model_validate(
        {
            **historical.model_dump(exclude_none=True, round_trip=True),
            "amendment_reason": "shared_envelope_task_path_alignment",
            "design_version": "1.11.0",
            "runtime_fixture_measurements_digest": sha256_file(
                runtime_fixture / "MEASUREMENTS-v1.0.json"
            ),
            "runtime_fixture_tree_digest": development_tree_digest(runtime_fixture),
            "shared_execution_envelope_digest": sha256_file(
                runtime_fixture / "shared-execution-envelope.md"
            ),
            "superseded_scorer_digest": historical.independent_scorer_digest,
            "supersedes_design_digest": historical.content_digest,
        }
    )
    preregistration = (
        canonical_json(replacement.model_dump(mode="json", exclude_none=True, round_trip=True))
        + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.11.json"
    checksum_path = root / "PREREGISTRATION-v1.11.sha256"
    if preregistration_path.exists() or checksum_path.exists():
        raise ValueError("compact projection v1.11 amendment is already frozen")
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(checksum_path, f"{digest}  PREREGISTRATION-v1.11.json\n")
    print(
        canonical_json(
            {
                "design_digest": replacement.content_digest,
                "sessions": replacement.maximum_subscription_sessions,
                "supersedes_design_digest": historical.content_digest,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
