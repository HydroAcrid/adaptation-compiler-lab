"""Freeze exact v3.2 condition materials after construction and before targets."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32ConstructionReport,
    PersonaV32MaterialsFreeze,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_v32"
    report_path = root / "construction-results-v1/CONSTRUCTION-REPORT-v1.json"
    report = PersonaV32ConstructionReport.model_validate_json(report_path.read_bytes())
    if not report.exact_target_gate_passed:
        raise RuntimeError("v3.2 materials cannot freeze after inexact construction")
    freeze = PersonaV32MaterialsFreeze(
        construction_report_digest=canonical_digest(report),
        compiled_material_digest=sha256_text(report.compiled_material.target_guidance),
        static_material_digest=sha256_text(report.static_material.target_guidance),
        compiled_material_bytes=report.compiled_material_bytes,
        static_material_bytes=report.static_material_bytes,
        target_runner_digest=sha256_file(repo / "scripts/run_persona_v32_targets.py"),
    )
    path = root / "MATERIALS-FREEZE-v1.json"
    payload = (canonical_json(freeze.model_dump(mode="json", round_trip=True)) + "\n").encode()
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError("v3.2 materials freeze drifted")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


if __name__ == "__main__":
    main()
