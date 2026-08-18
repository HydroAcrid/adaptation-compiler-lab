"""Freeze the zero-session strict-JSON v3.2 unblinder amendment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32MaterialsFreezeV12,
    PersonaV32MaterialsFreezeV13,
    PersonaV32UnblindAmendment,
    PersonaV32UnblindInstrumentIncident,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _bytes(value: BaseModel) -> bytes:
    return (canonical_json(value.model_dump(mode="json", round_trip=True)) + "\n").encode()


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"v3.2 unblind amendment drifted: {path.name}")
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
    if (root / "FINAL-REPORT-v1.json").exists():
        raise RuntimeError("v3.2 unblind amendment requires no existing final report")
    prior = PersonaV32MaterialsFreezeV12.model_validate_json(
        (root / "MATERIALS-FREEZE-v1.2.json").read_bytes()
    )
    incident = PersonaV32UnblindInstrumentIncident()
    amended_digest = sha256_file(repo / "scripts/unblind_persona_v32_canary.py")
    amendment = PersonaV32UnblindAmendment(
        superseded_material_freeze_digest=canonical_digest(prior),
        incident_digest=canonical_digest(incident),
        prior_unblinder_digest=prior.unblinder_digest,
        amended_unblinder_digest=amended_digest,
    )
    updated = PersonaV32MaterialsFreezeV13.model_validate(
        {
            **prior.model_dump(mode="json", round_trip=True),
            "unblinder_digest": amended_digest,
            "superseded_unblind_material_freeze_digest": canonical_digest(prior),
            "unblind_incident_digest": canonical_digest(incident),
            "unblind_amendment_digest": canonical_digest(amendment),
        }
    )
    for name, value in (
        ("UNBLIND-INSTRUMENT-INCIDENT-001.json", incident),
        ("UNBLIND-AMENDMENT-v1.3.json", amendment),
        ("MATERIALS-FREEZE-v1.3.json", updated),
    ):
        _write_or_verify(root / name, _bytes(value))


if __name__ == "__main__":
    main()
