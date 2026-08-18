"""Freeze the post-unblind v3.2 scoring incident and bounded repair."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path

from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32FinalReportV11,
    PersonaV32ScoringAmendment,
    PersonaV32ScoringInstrumentIncident,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _write_new(path: Path, value: Mapping[str, object]) -> None:
    payload = (canonical_json(value) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_v32"
    final_path = root / "FINAL-REPORT-v1.json"
    blind_path = root / "target-results-v1/BLIND-REPORT-v1.json"
    note_path = root / "FINAL-REPORT-v1-INVALIDATION.md"
    original = PersonaV32FinalReportV11.model_validate_json(final_path.read_bytes())
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    tide = next(item for item in original.task_outcomes if item.applicable_adaptation)
    if (
        tide.compiled_checks_passed != 0
        or tide.static_checks_passed != 0
        or tide.checks_total != 8
        or not original.behavioral_gate_passed
    ):
        raise RuntimeError("v3.2 scoring incident preconditions changed")
    blind_ids = {
        item["observation"]["blind_output_id"]
        for item in blind["trials"]
        if item["observation"]["blind_output_id"]
        in {tide.compiled_output_id, tide.static_output_id}
    }
    if blind_ids != {tide.compiled_output_id, tide.static_output_id}:
        raise RuntimeError("v3.2 affected frozen outputs are not bound to the blind report")
    incident = PersonaV32ScoringInstrumentIncident(
        original_final_report_digest=canonical_digest(original),
        target_blind_report_digest=sha256_file(blind_path),
        invalidation_note_digest=sha256_file(note_path),
        affected_output_ids=tuple(sorted(blind_ids)),
    )
    incident_path = root / "SCORING-INSTRUMENT-INCIDENT-002.json"
    _write_new(incident_path, incident.model_dump(mode="json", round_trip=True))
    amendment = PersonaV32ScoringAmendment(
        incident_digest=canonical_digest(incident),
        invalidated_final_report_digest=canonical_digest(original),
        prior_observer_digest=sha256_file(repo / "scripts/observe_compact_projection_policy.py"),
        amended_observer_digest=sha256_file(
            repo / "scripts/observe_compact_projection_policy_v12.py"
        ),
        prior_scorer_digest=sha256_file(repo / "scripts/score_compact_projection_task.py"),
        amended_scorer_digest=sha256_file(repo / "scripts/score_compact_projection_task_v12.py"),
        frozen_rescorer_digest=sha256_file(repo / "scripts/rescore_persona_v32_frozen_outputs.py"),
        amended_unblinder_digest=sha256_file(repo / "scripts/unblind_persona_v32_canary_v14.py"),
    )
    _write_new(
        root / "SCORING-AMENDMENT-v1.4.json",
        amendment.model_dump(mode="json", round_trip=True),
    )


if __name__ == "__main__":
    main()
