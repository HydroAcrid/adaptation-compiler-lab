"""Deterministic schema bundle for target material delivery receipts."""

from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.targets.task_delivery import TaskMaterialDeliveryReceipt


def delivery_schema_bundle() -> dict[str, dict[str, object]]:
    """Return the versioned target-delivery validation schemas."""

    return {
        "task_material_delivery_receipt": (
            TaskMaterialDeliveryReceipt.model_json_schema(mode="validation")
        )
    }


def export_delivery_schemas(directory: Path) -> tuple[Path, ...]:
    """Write target-delivery v1 schema snapshots."""

    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in delivery_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
