"""Deterministic JSON Schema snapshots for signed governance objects."""

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.governance.models import (
    AdjudicationRecord,
    BenchmarkRegistration,
    CaptureReceipt,
    ConditionMaterialReceipt,
    ConsentReceipt,
    CustodyAccessEvent,
    CustodyManifest,
    DependencyImpact,
    GovernanceEvent,
    InvalidationEvent,
    RecallReport,
    SignerIdentity,
    TombstoneReceipt,
    TrialResult,
)

GOVERNANCE_MODELS: dict[str, type[BaseModel]] = {
    "capture_receipt": CaptureReceipt,
    "adjudication_record": AdjudicationRecord,
    "benchmark_registration": BenchmarkRegistration,
    "consent_receipt": ConsentReceipt,
    "condition_material_receipt": ConditionMaterialReceipt,
    "custody_access_event": CustodyAccessEvent,
    "custody_manifest": CustodyManifest,
    "dependency_impact": DependencyImpact,
    "governance_event": GovernanceEvent,
    "invalidation_event": InvalidationEvent,
    "recall_report": RecallReport,
    "signer_identity": SignerIdentity,
    "tombstone_receipt": TombstoneReceipt,
    "trial_result": TrialResult,
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
