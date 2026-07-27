"""Deterministic JSON Schema bundle for runtime projection contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    ExternalGovernedRelease,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.codex_runtime import (
    RenderedRuntimeProjection,
    SharedExecutionEnvelope,
)

_MODELS: dict[str, type[BaseModel]] = {
    "canonical_runtime_projection": CanonicalRuntimeProjection,
    "external_governed_release": ExternalGovernedRelease,
    "rendered_runtime_projection": RenderedRuntimeProjection,
    "runtime_projection_manifest": RuntimeProjectionManifest,
    "shared_execution_envelope": SharedExecutionEnvelope,
}


def runtime_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_runtime_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in runtime_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
