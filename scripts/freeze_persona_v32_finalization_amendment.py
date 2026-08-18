"""Freeze the zero-session strict-JSON repair for the v3.2 finalizer."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path

from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32FinalizationAmendment,
    PersonaV32FinalizationInstrumentIncident,
    PersonaV32FrozenRescoreReport,
    PersonaV32ScoringAmendment,
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
    amendment = PersonaV32ScoringAmendment.model_validate_json(
        (root / "SCORING-AMENDMENT-v1.4.json").read_bytes()
    )
    rescore_path = root / "FROZEN-RESCORE-v1.4.json"
    rescore = PersonaV32FrozenRescoreReport.model_validate_json(rescore_path.read_bytes())
    if not rescore.all_check_totals_passed:
        raise RuntimeError("v3.2 finalization repair requires the complete frozen rescore")
    incident = PersonaV32FinalizationInstrumentIncident(
        scoring_amendment_digest=canonical_digest(amendment),
        frozen_rescore_report_digest=sha256_file(rescore_path),
        prior_unblinder_digest=amendment.amended_unblinder_digest,
    )
    _write_new(
        root / "FINALIZATION-INSTRUMENT-INCIDENT-003.json",
        incident.model_dump(mode="json", round_trip=True),
    )
    successor = PersonaV32FinalizationAmendment(
        superseded_scoring_amendment_digest=canonical_digest(amendment),
        incident_digest=canonical_digest(incident),
        frozen_rescore_report_digest=sha256_file(rescore_path),
        prior_unblinder_digest=amendment.amended_unblinder_digest,
        amended_unblinder_digest=sha256_file(repo / "scripts/unblind_persona_v32_canary_v14.py"),
    )
    _write_new(
        root / "FINALIZATION-AMENDMENT-v1.4.1.json",
        successor.model_dump(mode="json", round_trip=True),
    )


if __name__ == "__main__":
    main()
