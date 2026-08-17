"""Export stable JSON Schema snapshots for the persona-evaluation public contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaBenchmarkPlan,
    PersonaConditionMaterial,
    PersonaEvaluationReport,
    PersonaExecutionReceipt,
    PersonaJudgePacket,
    PersonaProfileAuthorOutput,
)

_MODELS: tuple[type[BaseModel], ...] = (
    PersonaBenchmarkPlan,
    PersonaConditionMaterial,
    PersonaJudgePacket,
    PersonaProfileAuthorOutput,
    PersonaExecutionReceipt,
    PersonaEvaluationReport,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for model in _MODELS:
        name = model.__name__.removeprefix("Persona")
        slug = "".join(("-" + char.lower()) if char.isupper() else char for char in name).lstrip(
            "-"
        )
        path = output / f"persona-{slug}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
