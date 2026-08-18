"""Freeze a zero-session condition-neutral v3.2 construction-oracle adjudication."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_v3 import PersonaV3ProfileOutput
from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32ConstructionReport,
    PersonaV32Freeze,
    PersonaV32Oracle,
    PersonaV32Protocol,
)
from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32MaterialsFreezeV11,
    PersonaV321Protocol,
    build_v32_construction_adjudication,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text


def _bytes(value: BaseModel) -> bytes:
    return (canonical_json(value.model_dump(mode="json", round_trip=True)) + "\n").encode()


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"v3.2 adjudication artifact drifted: {path.name}")
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
    if (root / "target-results-v1").exists():
        raise RuntimeError("v3.2 adjudication must freeze before target execution")
    original_protocol = PersonaV32Protocol.model_validate_json(
        (root / "PROTOCOL-v3.2.json").read_bytes()
    )
    original_freeze = PersonaV32Freeze.model_validate_json((root / "FREEZE-v1.json").read_bytes())
    original_oracle = PersonaV32Oracle.model_validate_json((root / "ORACLE-v1.json").read_bytes())
    report = PersonaV32ConstructionReport.model_validate_json(
        (root / "construction-results-v1/CONSTRUCTION-REPORT-v1.json").read_bytes()
    )
    reviewed = PersonaV3ProfileOutput.model_validate_json(
        (root / "construction-results-v1/PROFILE-REVIEWED-v1.json").read_bytes()
    )
    corrected, adjudication = build_v32_construction_adjudication(
        original_protocol_digest=canonical_digest(original_protocol),
        original_freeze_digest=canonical_digest(original_freeze),
        original_oracle=original_oracle,
        report=report,
        reviewed=reviewed,
        route_policy_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/automatic_runtime/semantic_routing.py"
        ),
    )
    successor = PersonaV321Protocol(
        superseded_protocol_digest=canonical_digest(original_protocol),
        superseded_freeze_digest=canonical_digest(original_freeze),
        failed_construction_report_digest=canonical_digest(report),
        corrected_oracle_digest=canonical_digest(corrected),
        adjudication_digest=canonical_digest(adjudication),
    )
    material_freeze = PersonaV32MaterialsFreezeV11(
        successor_protocol_digest=canonical_digest(successor),
        original_construction_report_digest=canonical_digest(report),
        construction_adjudication_digest=canonical_digest(adjudication),
        corrected_oracle_digest=canonical_digest(corrected),
        compiled_material_digest=sha256_text(report.compiled_material.target_guidance),
        static_material_digest=sha256_text(report.static_material.target_guidance),
        compiled_material_bytes=report.compiled_material_bytes,
        static_material_bytes=report.static_material_bytes,
        target_runner_digest=sha256_file(repo / "scripts/run_persona_v32_targets.py"),
        judge_runner_digest=sha256_file(repo / "scripts/run_persona_v32_judges.py"),
        unblinder_digest=sha256_file(repo / "scripts/unblind_persona_v32_canary.py"),
    )
    artifacts = {
        "ORACLE-v1.1.json": _bytes(corrected),
        "CONSTRUCTION-ADJUDICATION-v1.1.json": _bytes(adjudication),
        "PROTOCOL-v3.2.1.json": _bytes(successor),
        "MATERIALS-FREEZE-v1.1.json": _bytes(material_freeze),
    }
    for name, payload in artifacts.items():
        _write_or_verify(root / name, payload)
    print(
        canonical_json({name: sha256_text(payload.decode()) for name, payload in artifacts.items()})
    )


if __name__ == "__main__":
    main()
