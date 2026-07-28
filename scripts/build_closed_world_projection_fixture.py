"""Build the deterministic closed-world semantic runtime fixture."""

from __future__ import annotations

import argparse
import json
import math
from datetime import timedelta
from pathlib import Path

from adaptation_compiler_lab.benchmark.decision_fixture import (
    public_semantic_decision_tables,
)
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
from adaptation_compiler_lab.targets.codex_runtime import (
    SharedExecutionEnvelope,
    render_shared_execution_envelope,
)
from adaptation_compiler_lab.targets.codex_runtime_v6 import (
    build_codex_runtime_projection_v6,
    build_runtime_projection_manifest_v6,
    render_codex_runtime_projection_v6,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile
from scripts.build_semantic_decision_projection_fixture import (
    _canonical_document,
    _exclusive_write,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()

    output = arguments.output_root.absolute()
    if output.exists():
        raise FileExistsError("closed-world fixture output already exists")
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
        semantic_release = bind_semantic_decision_release(release, tables)
        projection = build_codex_runtime_projection_v6(semantic_release, context)
        rendered = render_codex_runtime_projection_v6(projection)
        manifest = build_runtime_projection_manifest_v6(
            release=semantic_release,
            projection=projection,
            rendered=rendered,
        )
        release_document = _canonical_document(semantic_release)
        projection_document = _canonical_document(projection)
        manifest_document = _canonical_document(manifest)
        _exclusive_write(
            output / f"external-semantic-decision-release-stage-{stage}.json",
            release_document,
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
                "external_decision_release_bytes": len(release_document.encode("utf-8")),
                "runtime_projection_bytes": rendered.utf8_bytes,
                "stage": stage,
            }
        )
    measurement = {
        "measurement_version": "2.4.0",
        "adaptation_bytes_exclude_shared_envelope": True,
        "profile_comparison_pending": False,
        "provider_billed_calls": 0,
        "sealed_external_validation_accessed": False,
        "shared_execution_envelope_bytes": envelope.utf8_bytes,
        "stages": stages,
        "target_sessions_started": 0,
    }
    _exclusive_write(output / "MEASUREMENTS-v2.4.json", _canonical_document(measurement))
    print(json.dumps(measurement, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
