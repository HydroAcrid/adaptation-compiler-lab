"""Versioned JSON Schema export without import-time filesystem writes."""

import json
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.domain.base import VersionedRecord
from adaptation_compiler_lab.domain.enums import RecordKind
from adaptation_compiler_lab.serialization.canonical import RECORD_MODELS, RECORD_MODELS_V1

SchemaBundleVersion = Literal["1.0", "1.1"]


def schema_bundle(version: SchemaBundleVersion = "1.0") -> dict[str, dict[str, object]]:
    """Return immutable v1.0 schemas or the additive Evidence v1.1 schema."""

    result: dict[str, dict[str, object]] = {}
    models = (
        RECORD_MODELS_V1
        if version == "1.0"
        else {RecordKind.EVIDENCE: RECORD_MODELS[RecordKind.EVIDENCE]}
    )
    for kind, model in sorted(models.items(), key=lambda item: item[0].value):
        result[kind.value] = model.model_json_schema(mode="validation")
    return result


def schema_for(kind: RecordKind, *, version: SchemaBundleVersion = "1.0") -> dict[str, object]:
    if version == "1.1" and kind is not RecordKind.EVIDENCE:
        raise ValueError("schema version 1.1 is defined only for Evidence")
    model: type[VersionedRecord] = (
        RECORD_MODELS_V1[kind] if version == "1.0" else RECORD_MODELS[kind]
    )
    return model.model_json_schema(mode="validation")


def export_json_schemas(
    directory: Path, *, version: SchemaBundleVersion = "1.0"
) -> tuple[Path, ...]:
    """Write deterministic schema documents when explicitly invoked by a caller."""

    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in sorted(schema_bundle(version).items()):
        path = directory / f"{name}.schema.json"
        rendered = json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        path.write_text(rendered, encoding="utf-8", newline="\n")
        written.append(path)
    return tuple(written)
