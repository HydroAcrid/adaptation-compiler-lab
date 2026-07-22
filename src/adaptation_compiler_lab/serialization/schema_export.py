"""Versioned JSON Schema export without import-time filesystem writes."""

import json
from pathlib import Path

from adaptation_compiler_lab.domain.base import VersionedRecord
from adaptation_compiler_lab.domain.enums import RecordKind
from adaptation_compiler_lab.serialization.canonical import RECORD_MODELS


def schema_bundle() -> dict[str, dict[str, object]]:
    """Return all eight validation schemas keyed by stable record-kind value."""

    result: dict[str, dict[str, object]] = {}
    for kind, model in sorted(RECORD_MODELS.items(), key=lambda item: item[0].value):
        result[kind.value] = model.model_json_schema(mode="validation")
    return result


def schema_for(kind: RecordKind) -> dict[str, object]:
    model: type[VersionedRecord] = RECORD_MODELS[kind]
    return model.model_json_schema(mode="validation")


def export_json_schemas(directory: Path) -> tuple[Path, ...]:
    """Write deterministic schema documents when explicitly invoked by a caller."""

    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in sorted(schema_bundle().items()):
        path = directory / f"{name}.schema.json"
        rendered = json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        path.write_text(rendered, encoding="utf-8", newline="\n")
        written.append(path)
    return tuple(written)
