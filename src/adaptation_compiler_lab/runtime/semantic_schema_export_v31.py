"""Deterministic schema bundle for closed-world semantic projections."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.runtime.models import (
    ExternalSemanticDecisionRelease,
    SemanticDecisionCase,
    SemanticDecisionTable,
)
from adaptation_compiler_lab.targets.codex_runtime_v6 import (
    RenderedClosedWorldDecisionProjection,
)

_MODELS: dict[str, type[BaseModel]] = {
    "external_semantic_decision_release": ExternalSemanticDecisionRelease,
    "rendered_closed_world_decision_projection": RenderedClosedWorldDecisionProjection,
    "semantic_decision_case": SemanticDecisionCase,
    "semantic_decision_table": SemanticDecisionTable,
}


def semantic_v31_schema_bundle() -> dict[str, dict[str, object]]:
    """Return canonical validation schemas sorted by artifact name."""

    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_semantic_v31_schemas(directory: Path) -> tuple[Path, ...]:
    """Write runtime-v3.1 schema snapshots."""

    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in semantic_v31_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
