"""Freeze the zero-session v3.2 blind-judge role-binding amendment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32JudgeAmendment,
    PersonaV32JudgeInstrumentIncident,
    PersonaV32MaterialsFreezeV11,
    PersonaV32MaterialsFreezeV12,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _bytes(value: BaseModel) -> bytes:
    return (canonical_json(value.model_dump(mode="json", round_trip=True)) + "\n").encode()


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"v3.2 judge amendment drifted: {path.name}")
        return
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
    if any((root / "judge-results-v1").glob("*.json")):
        raise RuntimeError("v3.2 judge amendment must precede every judge output")
    prior = PersonaV32MaterialsFreezeV11.model_validate_json(
        (root / "MATERIALS-FREEZE-v1.1.json").read_bytes()
    )
    incident = PersonaV32JudgeInstrumentIncident()
    amendment = PersonaV32JudgeAmendment(
        superseded_material_freeze_digest=canonical_digest(prior),
        incident_digest=canonical_digest(incident),
        prior_judge_runner_digest=prior.judge_runner_digest,
        amended_judge_runner_digest=sha256_file(repo / "scripts/run_persona_v32_judges.py"),
        amended_unblinder_digest=sha256_file(repo / "scripts/unblind_persona_v32_canary.py"),
    )
    updated = PersonaV32MaterialsFreezeV12.model_validate(
        {
            **prior.model_dump(mode="json", round_trip=True),
            "judge_runner_digest": amendment.amended_judge_runner_digest,
            "unblinder_digest": amendment.amended_unblinder_digest,
            "superseded_material_freeze_digest": canonical_digest(prior),
            "judge_incident_digest": canonical_digest(incident),
            "judge_amendment_digest": canonical_digest(amendment),
        }
    )
    for name, value in (
        ("JUDGE-INSTRUMENT-INCIDENT-001.json", incident),
        ("JUDGE-AMENDMENT-v1.2.json", amendment),
        ("MATERIALS-FREEZE-v1.2.json", updated),
    ):
        _write_or_verify(root / name, _bytes(value))


if __name__ == "__main__":
    main()
