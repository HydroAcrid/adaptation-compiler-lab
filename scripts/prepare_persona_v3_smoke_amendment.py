"""Freeze the one instrument-only v3 retry after a pre-output schema rejection."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3InstrumentIncident,
    PersonaV3SensorResult,
    PersonaV3SmokeAmendment,
    PersonaV3SmokeFreeze,
    persona_v3_profile_output_schema,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text

_FAILED_THREAD_ID = "01a01180-ee7b-7010-985e-cd991417a763"
_FAILURE_MESSAGE = (
    "Invalid schema for response_format 'codex_output_schema': In context=(), 'required' is "
    "required to be supplied and to be an array including every key in properties. Missing "
    "'claims'."
)


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _exclusive_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"frozen v3 amendment artifact drifted: {path.name}")
        return
    _exclusive_write(path, payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    input_root = args.input.resolve()
    if not input_root.is_relative_to(repo):
        raise RuntimeError("v3 amendment must remain in the repository")

    freeze = PersonaV3SmokeFreeze.model_validate_json(
        (input_root / "SMOKE-FREEZE-v1.json").read_bytes()
    )
    sensor = PersonaV3SensorResult.model_validate_json(
        (input_root / "results" / "SMOKE-SENSOR-RESULT-v1.json").read_bytes()
    )
    incident = PersonaV3InstrumentIncident(
        failure_message_digest=sha256_text(_FAILURE_MESSAGE),
        failed_thread_digest=sha256_text(_FAILED_THREAD_ID),
    )
    amendment = PersonaV3SmokeAmendment(
        prior_freeze_digest=canonical_digest(freeze),
        incident_digest=canonical_digest(incident),
        retained_sensor_result_digest=canonical_digest(sensor),
        amended_profile_output_schema_digest=canonical_digest(persona_v3_profile_output_schema()),
        amended_benchmark_module_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v3.py"
        ),
        amended_runner_module_digest=sha256_file(repo / "scripts/run_persona_v3_smoke.py"),
    )
    artifacts = {
        "INSTRUMENT-INCIDENT-001.json": _json_bytes(incident),
        "SMOKE-FREEZE-AMENDMENT-v1.1.json": _json_bytes(amendment),
    }
    for name, payload in artifacts.items():
        _write_or_verify(input_root / name, payload)
    print(canonical_json({name: sha256_bytes(payload) for name, payload in artifacts.items()}))


if __name__ == "__main__":
    main()
