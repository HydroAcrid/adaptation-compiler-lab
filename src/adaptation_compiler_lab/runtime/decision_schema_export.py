"""Deterministic JSON Schema bundle for typed decision projection contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.runtime.models import (
    ArtifactDecisionTable,
    BehavioralDecisionCase,
    ExternalDecisionRelease,
)
from adaptation_compiler_lab.targets.codex_runtime_v3 import RenderedDecisionProjection

_MODELS: dict[str, type[BaseModel]] = {
    "artifact_decision_table": ArtifactDecisionTable,
    "behavioral_decision_case": BehavioralDecisionCase,
    "external_decision_release": ExternalDecisionRelease,
    "rendered_decision_projection": RenderedDecisionProjection,
}


def decision_schema_bundle() -> dict[str, dict[str, object]]:
    """Return canonical validation schemas sorted by artifact name."""

    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_decision_schemas(directory: Path) -> tuple[Path, ...]:
    """Write the version-2 runtime schema snapshot."""

    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in decision_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
