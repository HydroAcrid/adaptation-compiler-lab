"""Freeze the raw-free disposable calibration report and v2.1 protocol."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_calibration import run_disposable_calibration
from adaptation_compiler_lab.benchmark.persona_instrument import PersonaV21Protocol
from adaptation_compiler_lab.serialization import canonical_json


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"persona instrument output drifted: {path.name}")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _payload(value: BaseModel | Mapping[str, object]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = run_disposable_calibration()
    protocol = PersonaV21Protocol()
    _write_or_verify(output / "CALIBRATION-REPORT-v1.json", _payload(report))
    _write_or_verify(output / "V2.1-PREREGISTRATION.json", _payload(protocol))
    _write_or_verify(
        output / "V2-SUPERSESSION.json",
        _payload(
            {
                "effective_before_any_v2_execution": True,
                "original_preregistration_immutable": True,
                "reason": (
                    "V1 exposed answer-key leakage, future-stage judge context, non-objective "
                    "learning-state scoring, and an unreviewed static baseline."
                ),
                "replacement": "temper-6a2l-persona-evaluation-v2.1",
                "status": "superseded_unexecuted",
                "superseded": "temper-6a2l-persona-evaluation-v2",
            }
        ),
    )
    print(canonical_json(report))


if __name__ == "__main__":
    main()
