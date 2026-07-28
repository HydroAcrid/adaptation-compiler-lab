"""Build the deterministic semantic-decision runtime fixture."""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import timedelta
from pathlib import Path

from adaptation_compiler_lab.benchmark.decision_fixture import public_semantic_decision_tables
from adaptation_compiler_lab.dogfood import (
    PUBLIC_DOGFOOD_NOW,
    PUBLIC_DOGFOOD_SUBJECT,
    LongitudinalDogfoodCompiler,
    public_dogfood_transitions,
)
from adaptation_compiler_lab.runtime import (
    RuntimeProjectionContext,
    bind_semantic_decision_release,
    build_external_governed_releases,
)
from adaptation_compiler_lab.serialization import canonical_json
from adaptation_compiler_lab.targets.codex_runtime import (
    SharedExecutionEnvelope,
    render_shared_execution_envelope,
)
from adaptation_compiler_lab.targets.codex_runtime_v5 import (
    build_codex_runtime_projection_v5,
    build_runtime_projection_manifest_v5,
    render_codex_runtime_projection_v5,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile


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
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()

    output = arguments.output_root.absolute()
    if output.exists():
        raise FileExistsError("semantic-decision fixture output already exists")
    output.mkdir(parents=True, mode=0o755)

    transitions = public_dogfood_transitions()
    dogfood = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )
    releases = build_external_governed_releases(transitions, dogfood)
    tables = public_semantic_decision_tables(transitions)
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
        SharedExecutionEnvelope(allowed_paths=("src/transfer_policy.py",))
    )
    _exclusive_write(output / "shared-execution-envelope.md", envelope.content)
    _exclusive_write(output / "shared-execution-envelope.json", _canonical_document(envelope))

    stages: list[dict[str, object]] = []
    for stage, release in enumerate(releases, start=1):
        decision_release = bind_semantic_decision_release(release, tables)
        projection = build_codex_runtime_projection_v5(decision_release, context)
        rendered = render_codex_runtime_projection_v5(projection)
        manifest = build_runtime_projection_manifest_v5(
            release=decision_release,
            projection=projection,
            rendered=rendered,
        )
        decision_document = _canonical_document(decision_release)
        projection_document = _canonical_document(projection)
        manifest_document = _canonical_document(manifest)
        _exclusive_write(
            output / f"external-semantic-decision-release-stage-{stage}.json",
            decision_document,
        )
        _exclusive_write(
            output / f"canonical-runtime-projection-stage-{stage}.json",
            projection_document,
        )
        _exclusive_write(output / f"codex-runtime-stage-{stage}.md", rendered.content)
        _exclusive_write(
            output / f"clause-binding-manifest-stage-{stage}.json",
            manifest_document,
        )
        stages.append(
            {
                "adaptation_estimated_tokens": math.ceil(rendered.utf8_bytes / 4),
                "canonical_runtime_projection_bytes": len(projection_document.encode("utf-8")),
                "external_clause_manifest_bytes": len(manifest_document.encode("utf-8")),
                "external_decision_release_bytes": len(decision_document.encode("utf-8")),
                "runtime_projection_bytes": rendered.utf8_bytes,
                "stage": stage,
            }
        )
    measurement = {
        "measurement_version": "2.3.0",
        "adaptation_bytes_exclude_shared_envelope": True,
        "profile_comparison_pending": False,
        "provider_billed_calls": 0,
        "sealed_external_validation_accessed": False,
        "shared_execution_envelope_bytes": envelope.utf8_bytes,
        "stages": stages,
        "target_sessions_started": 0,
    }
    _exclusive_write(output / "MEASUREMENTS-v2.3.json", _canonical_document(measurement))
    print(json.dumps(measurement, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
