"""Build the deterministic public Milestone 6A.1 engineering projection fixture."""

from __future__ import annotations

import argparse
import json
import math
import os
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
    SharedExecutionEnvelope,
    build_runtime_projection_manifest,
    render_codex_runtime_projection,
    render_shared_execution_envelope,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile

_CEILINGS = (227, 508, 462)


def _exclusive_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_document(value: object) -> str:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json", round_trip=True)
    elif isinstance(value, dict):
        payload = value
    else:
        raise TypeError("fixture document must be a model or JSON object")
    return canonical_json(payload) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    output = arguments.output_root.resolve()
    if output.exists():
        raise FileExistsError("compact projection fixture output already exists")
    output.mkdir(parents=True, mode=0o755)

    transitions = public_dogfood_transitions()
    dogfood_result = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )
    releases = build_external_governed_releases(transitions, dogfood_result)
    context = RuntimeProjectionContext(
        known_dimensions=(
            ScopeDimension.SUBJECT_IDS,
            ScopeDimension.TARGET_FAMILIES,
            ScopeDimension.VALIDITY_WINDOW,
        ),
        target_profile_id=default_target_profile(TargetKind.CODEX).capabilities.profile_id,
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
        target_family=TargetKind.CODEX.value,
        evaluated_at=PUBLIC_DOGFOOD_NOW + timedelta(days=1),
    )
    envelope = render_shared_execution_envelope(
        SharedExecutionEnvelope(allowed_paths=("policy.py",))
    )
    _exclusive_write(output / "shared-execution-envelope.md", envelope.content)
    _exclusive_write(
        output / "shared-execution-envelope.json",
        _canonical_document(envelope),
    )

    old_root = repo / "development_benchmark_longitudinal" / "condition-materials"
    stages: list[dict[str, object]] = []
    for stage, (release, ceiling) in enumerate(zip(releases, _CEILINGS, strict=True), start=1):
        projection = build_runtime_projection(release, context)
        rendered = render_codex_runtime_projection(projection)
        manifest = build_runtime_projection_manifest(
            release=release,
            projection=projection,
            rendered=rendered,
        )
        if rendered.utf8_bytes > ceiling:
            raise RuntimeError(
                f"Stage {stage} projection is {rendered.utf8_bytes} bytes; ceiling is {ceiling}"
            )
        release_document = _canonical_document(release)
        projection_document = _canonical_document(projection)
        manifest_document = _canonical_document(manifest)
        _exclusive_write(
            output / f"external-governed-release-stage-{stage}.json",
            release_document,
        )
        _exclusive_write(
            output / f"canonical-runtime-projection-stage-{stage}.json",
            projection_document,
        )
        _exclusive_write(
            output / f"codex-runtime-stage-{stage}.md",
            rendered.content,
        )
        _exclusive_write(
            output / f"clause-binding-manifest-stage-{stage}.json",
            manifest_document,
        )
        old_compiled_bytes = (old_root / f"compiled-stage-{stage}.md").stat().st_size
        profile_bytes = (old_root / f"strong-profile-stage-{stage}.md").stat().st_size
        stages.append(
            {
                "adaptation_estimated_tokens": math.ceil(rendered.utf8_bytes / 4),
                "canonical_runtime_projection_bytes": len(projection_document.encode("utf-8")),
                "external_clause_manifest_bytes": len(manifest_document.encode("utf-8")),
                "external_governed_release_bytes": len(release_document.encode("utf-8")),
                "old_compiled_adaptation_bytes": old_compiled_bytes,
                "profile_compactness_ceiling_bytes": profile_bytes,
                "runtime_projection_bytes": rendered.utf8_bytes,
                "stage": stage,
            }
        )
    measurement = {
        "measurement_version": "1.0.0",
        "adaptation_bytes_exclude_shared_envelope": True,
        "provider_billed_calls": 0,
        "sealed_external_validation_accessed": False,
        "shared_execution_envelope_bytes": envelope.utf8_bytes,
        "stages": stages,
        "target_sessions_started": 0,
    }
    _exclusive_write(output / "MEASUREMENTS-v1.0.json", _canonical_document(measurement))
    print(json.dumps(measurement, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
