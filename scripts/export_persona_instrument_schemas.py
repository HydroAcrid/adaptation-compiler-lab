"""Export deterministic JSON Schema snapshots for the hardened v2.1 persona instrument."""

from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaCalibrationReport,
    PersonaGuidanceOutcome,
    PersonaHiddenOracle,
    PersonaMaterialSnapshot,
    PersonaObjectiveScore,
    PersonaProfileAuthorPacket,
    PersonaProfileReviewPacket,
    PersonaSensorRecord,
    PersonaV21EvaluationReport,
    PersonaV21ExecutionReceipt,
    PersonaV21JudgePacket,
    PersonaV21Protocol,
)
from adaptation_compiler_lab.serialization import canonical_json

_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("persona-calibration-report", PersonaCalibrationReport),
    ("persona-guidance-outcome", PersonaGuidanceOutcome),
    ("persona-hidden-oracle", PersonaHiddenOracle),
    ("persona-material-snapshot", PersonaMaterialSnapshot),
    ("persona-objective-score", PersonaObjectiveScore),
    ("persona-profile-author-packet", PersonaProfileAuthorPacket),
    ("persona-profile-review-packet", PersonaProfileReviewPacket),
    ("persona-sensor-record", PersonaSensorRecord),
    ("persona-v21-judge-packet", PersonaV21JudgePacket),
    ("persona-v21-evaluation-report", PersonaV21EvaluationReport),
    ("persona-v21-execution-receipt", PersonaV21ExecutionReceipt),
    ("persona-v21-protocol", PersonaV21Protocol),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, model in _MODELS:
        payload = (canonical_json(model.model_json_schema()) + "\n").encode("utf-8")
        (output / f"{name}.schema.json").write_bytes(payload)


if __name__ == "__main__":
    main()
