"""Deterministic JSON Schema bundle for automatic-runtime contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.automatic_runtime.gate import CodexDogfoodGateReport
from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRenderedMaterial,
    AutomaticRuntimeMetrics,
    AutomaticRuntimeState,
    CapabilityPresetRef,
    ComposedRuntimeRelease,
    RuntimeActivationFeedback,
    RuntimeCycleReceipt,
    RuntimeDeliveryReceipt,
    RuntimeLearningAssessment,
    RuntimeLearningCycleReceipt,
    RuntimeReviewQueueItem,
    RuntimeSourceCheckpoint,
    RuntimeTargetDeliveryAcknowledgement,
    RuntimeTaskActivationReceipt,
    SemanticInterpreterReceipt,
    StandingAutomationPolicy,
)
from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticCorpusAdjudication,
    SemanticEvaluationReport,
    SemanticFeedbackCorpus,
)

_MODELS: dict[str, type[BaseModel]] = {
    "automatic_rendered_material": AutomaticRenderedMaterial,
    "automatic_runtime_metrics": AutomaticRuntimeMetrics,
    "automatic_runtime_state": AutomaticRuntimeState,
    "capability_preset_ref": CapabilityPresetRef,
    "codex_dogfood_gate_report": CodexDogfoodGateReport,
    "composed_runtime_release": ComposedRuntimeRelease,
    "runtime_cycle_receipt": RuntimeCycleReceipt,
    "runtime_delivery_receipt": RuntimeDeliveryReceipt,
    "runtime_learning_assessment": RuntimeLearningAssessment,
    "runtime_learning_cycle_receipt": RuntimeLearningCycleReceipt,
    "runtime_review_queue_item": RuntimeReviewQueueItem,
    "semantic_interpreter_receipt": SemanticInterpreterReceipt,
    "semantic_corpus_adjudication": SemanticCorpusAdjudication,
    "semantic_evaluation_report": SemanticEvaluationReport,
    "semantic_feedback_corpus": SemanticFeedbackCorpus,
    "runtime_source_checkpoint": RuntimeSourceCheckpoint,
    "runtime_target_delivery_acknowledgement": RuntimeTargetDeliveryAcknowledgement,
    "runtime_task_activation_receipt": RuntimeTaskActivationReceipt,
    "runtime_activation_feedback": RuntimeActivationFeedback,
    "standing_automation_policy": StandingAutomationPolicy,
}


def automatic_runtime_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_automatic_runtime_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in automatic_runtime_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
