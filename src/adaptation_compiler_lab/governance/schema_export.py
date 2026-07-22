"""Deterministic JSON Schema snapshots for signed governance objects."""

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.governance.models import (
    CaptureReceipt,
    ConsentReceipt,
    GovernanceEvent,
    SignerIdentity,
)

GOVERNANCE_MODELS: dict[str, type[BaseModel]] = {
    "capture_receipt": CaptureReceipt,
    "consent_receipt": ConsentReceipt,
    "governance_event": GovernanceEvent,
    "signer_identity": SignerIdentity,
}


def governance_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        name: model.model_json_schema(mode="validation")
        for name, model in sorted(GOVERNANCE_MODELS.items())
    }


def export_governance_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in governance_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
