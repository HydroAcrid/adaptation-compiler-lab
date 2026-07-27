"""Record separated machine, review, authoring, and target-byte measurements."""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from datetime import timedelta
from pathlib import Path

from adaptation_compiler_lab.dogfood import (
    PUBLIC_DOGFOOD_NOW,
    PUBLIC_DOGFOOD_SUBJECT,
    LongitudinalDogfoodCompiler,
    public_dogfood_transitions,
)
from adaptation_compiler_lab.runtime import (
    RuntimeProjectionContext,
    build_external_governed_releases,
    build_runtime_projection,
)
from adaptation_compiler_lab.serialization import canonical_json
from adaptation_compiler_lab.targets.codex_runtime import (
    build_runtime_projection_manifest,
    render_codex_runtime_projection,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile


def _exclusive_write(path: Path, value: dict[str, object]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    encoded = (canonical_json(value) + "\n").encode("utf-8")
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _duration(receipt: dict[str, object], role: str) -> float:
    value = receipt.get(role)
    if not isinstance(value, dict):
        raise ValueError(f"profile stage omitted {role} receipt")
    duration = value.get("duration_seconds")
    if not isinstance(duration, (int, float)):
        raise ValueError(f"profile {role} duration is malformed")
    return float(duration)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=200)
    arguments = parser.parse_args()
    if arguments.iterations < 10:
        parser.error("at least 10 machine-time iterations are required")

    repo = arguments.repo.resolve()
    transitions = public_dogfood_transitions()
    profile_receipt = json.loads(
        (
            repo / "development_benchmark_longitudinal" / "profile-construction-receipt.json"
        ).read_text(encoding="utf-8")
    )
    stages = profile_receipt.get("stages")
    if not isinstance(stages, list) or len(stages) != 3:
        raise ValueError("historical profile receipt stages are malformed")
    author_seconds = sum(_duration(item, "author") for item in stages if isinstance(item, dict))
    reviewer_seconds = sum(_duration(item, "review") for item in stages if isinstance(item, dict))
    profile = default_target_profile(TargetKind.CODEX)
    context = RuntimeProjectionContext(
        known_dimensions=(
            ScopeDimension.SUBJECT_IDS,
            ScopeDimension.TARGET_FAMILIES,
            ScopeDimension.VALIDITY_WINDOW,
        ),
        target_profile_id=profile.capabilities.profile_id,
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
        target_family=TargetKind.CODEX.value,
        evaluated_at=PUBLIC_DOGFOOD_NOW + timedelta(days=1),
    )
    started = time.perf_counter()
    for _ in range(arguments.iterations):
        compiled = LongitudinalDogfoodCompiler(profile).compile(transitions)
        releases = build_external_governed_releases(transitions, compiled)
        for release in releases:
            projection = build_runtime_projection(release, context)
            rendered = render_codex_runtime_projection(projection)
            build_runtime_projection_manifest(
                release=release,
                projection=projection,
                rendered=rendered,
            )
    elapsed = time.perf_counter() - started
    measurements = json.loads(
        (
            repo
            / "development_benchmark_compact_projection"
            / "runtime-fixture-v1.5"
            / "MEASUREMENTS-v1.0.json"
        ).read_text(encoding="utf-8")
    )
    _exclusive_write(
        arguments.output.resolve(),
        {
            "measurement_version": "1.2.0",
            "deterministic_compiler_operations": {
                "clause_manifest_bindings_per_cycle": 3,
                "governed_release_freezes_per_cycle": 3,
                "lifecycle_transition_applications_per_cycle": 3,
                "runtime_context_projections_per_cycle": 3,
            },
            "machine_time": {
                "full_three_stage_cycles": arguments.iterations,
                "mean_seconds_per_cycle": elapsed / arguments.iterations,
                "python_version": platform.python_version(),
                "system": platform.system(),
                "total_seconds": elapsed,
            },
            "provider_billed_calls": 0,
            "sealed_external_validation_accessed": False,
            "static_profile_author_and_reviewer_effort": {
                "author_seconds": author_seconds,
                "author_sessions": 3,
                "attempted_sessions": profile_receipt["attempted_sessions"],
                "replacement_reviewer_sessions": profile_receipt["replacement_sessions"],
                "reviewer_seconds": reviewer_seconds,
                "reviewer_sessions": 3,
            },
            "target_visible_byte_and_token_cost": measurements["stages"],
            "user_review_or_approval_touches": {
                "explicit_approval_touches": 3,
                "stages": 3,
            },
            "unlike_measurements_combined_into_effort_score": False,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
