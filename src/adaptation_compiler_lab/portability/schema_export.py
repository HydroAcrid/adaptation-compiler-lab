"""Deterministic JSON Schema bundle for offline shareable packages."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.portability.packages import (
    CapabilityModePackageV1,
    PackageImportItemPreviewV1,
    PackageImportPreviewV1,
    PackageImportReceiptV1,
    PersonalModeOverlayV1,
    ShareableBehaviorClauseV1,
    ShareableBehaviorPackV1,
)

_MODELS: dict[str, type[BaseModel]] = {
    "capability_mode_package": CapabilityModePackageV1,
    "package_import_item_preview": PackageImportItemPreviewV1,
    "package_import_preview": PackageImportPreviewV1,
    "package_import_receipt": PackageImportReceiptV1,
    "personal_mode_overlay": PersonalModeOverlayV1,
    "shareable_behavior_clause": ShareableBehaviorClauseV1,
    "shareable_behavior_pack": ShareableBehaviorPackV1,
}


def package_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_package_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in package_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
