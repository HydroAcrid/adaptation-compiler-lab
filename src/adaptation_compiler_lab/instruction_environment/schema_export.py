"""Deterministic JSON Schema bundle for native instruction interoperability."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.instruction_environment.models import (
    InstructionConflictSummaryV1,
    InstructionConflictV1,
    InstructionDeltaPlanV1,
    InstructionEnvironmentSnapshotV1,
    InstructionEnvironmentSummaryV1,
    InstructionGlobalPreviewV1,
    InstructionReconciliationPlanV1,
    InstructionRelationV1,
    InstructionSourceManifestV1,
    InstructionSourceSummaryV1,
    NativeInstructionChangePreviewV1,
    NativeInstructionChangeReceiptV1,
    NativeInstructionClauseV1,
    NativeMemoryAdoptionPreviewV1,
    NativeMemoryCapabilityV1,
    ReconciliationDispositionV1,
)
from adaptation_compiler_lab.instruction_environment.semantic import (
    ClauseRelationAnalysisV1,
    ClauseSemanticAnalysisV1,
    InstructionRelationPairV1,
    SemanticAnalysisEnvelopeV1,
    SemanticRelationEnvelopeV1,
)

_MODELS: dict[str, type[BaseModel]] = {
    "clause_relation_analysis": ClauseRelationAnalysisV1,
    "clause_semantic_analysis": ClauseSemanticAnalysisV1,
    "instruction_conflict": InstructionConflictV1,
    "instruction_conflict_summary": InstructionConflictSummaryV1,
    "instruction_delta_plan": InstructionDeltaPlanV1,
    "instruction_environment_snapshot": InstructionEnvironmentSnapshotV1,
    "instruction_environment_summary": InstructionEnvironmentSummaryV1,
    "instruction_reconciliation_plan": InstructionReconciliationPlanV1,
    "instruction_global_preview": InstructionGlobalPreviewV1,
    "instruction_relation": InstructionRelationV1,
    "instruction_relation_pair": InstructionRelationPairV1,
    "instruction_source_manifest": InstructionSourceManifestV1,
    "instruction_source_summary": InstructionSourceSummaryV1,
    "native_instruction_change_preview": NativeInstructionChangePreviewV1,
    "native_instruction_change_receipt": NativeInstructionChangeReceiptV1,
    "native_instruction_clause": NativeInstructionClauseV1,
    "native_memory_adoption_preview": NativeMemoryAdoptionPreviewV1,
    "native_memory_capability": NativeMemoryCapabilityV1,
    "reconciliation_disposition": ReconciliationDispositionV1,
    "semantic_analysis_envelope": SemanticAnalysisEnvelopeV1,
    "semantic_relation_envelope": SemanticRelationEnvelopeV1,
}


def instruction_environment_schema_bundle() -> dict[str, dict[str, object]]:
    """Return the complete stable v1 validation-schema bundle."""

    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_instruction_environment_schemas(directory: Path) -> tuple[Path, ...]:
    """Write deterministic checked-in schemas for drift detection."""

    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in instruction_environment_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
