"""Deterministic schema export for Copilot capability and delivery contracts."""

from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.copilot_delivery.models import CopilotSurfaceCapabilityV1


def copilot_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        "copilot_surface_capability": CopilotSurfaceCapabilityV1.model_json_schema(),
    }


def export_copilot_schemas(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, schema in copilot_schema_bundle().items():
        (root / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
