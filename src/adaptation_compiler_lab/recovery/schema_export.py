"""Export recovery v1 contracts as reviewable JSON Schema snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.recovery.models import (
    EncryptedTemperRecoveryBundleV1,
    RecoveryFileV1,
    RecoveryPreviewV1,
    RecoveryProjectSelectionV1,
    RecoveryProjectV1,
    RecoveryRestoreReceiptV1,
    RecoveryRestoreResultV1,
    TemperRecoveryBundleV1,
)

_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("encrypted_temper_recovery_bundle", EncryptedTemperRecoveryBundleV1),
    ("recovery_file", RecoveryFileV1),
    ("recovery_preview", RecoveryPreviewV1),
    ("recovery_project", RecoveryProjectV1),
    ("recovery_project_selection", RecoveryProjectSelectionV1),
    ("recovery_restore_receipt", RecoveryRestoreReceiptV1),
    ("recovery_restore_result", RecoveryRestoreResultV1),
    ("temper_recovery_bundle", TemperRecoveryBundleV1),
)


def recovery_schema_bundle() -> dict[str, dict[str, object]]:
    """Return deterministic serialization schemas for drift tests."""

    return {name: model.model_json_schema(mode="serialization") for name, model in _MODELS}


def export_recovery_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for name, schema in recovery_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        outputs.append(path)
    return tuple(outputs)
