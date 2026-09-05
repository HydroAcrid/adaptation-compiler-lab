"""Deterministic JSON Schema bundle for temporary capability Modes."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationExecutionContractV1,
    ModeEvaluationFixtureV1,
    ModeEvaluationModeOutcomeV1,
    ModeEvaluationPublicPlanV1,
    ModeEvaluationResultV1,
    ModeEvaluationRunCellV1,
    ModeEvaluationScenarioV1,
    ModeEvaluationTaskOutcomeV1,
    ModeJudgeDecisionV1,
    ModeJudgePairDecisionV1,
    ModePolicyObservationV1,
)
from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeActivationReceipt,
    ModeClause,
    ModeDeactivationReceipt,
    ModeDeliveryReceipt,
    ModeEvaluationCaseResult,
    ModeEvaluationDesignV1,
    ModeEvaluationReport,
    ModeEvaluationTask,
    ModeSecurityPosture,
    ModeTargetCompatibility,
)

_MODELS: dict[str, type[BaseModel]] = {
    "capability_mode": CapabilityMode,
    "mode_activation_receipt": ModeActivationReceipt,
    "mode_clause": ModeClause,
    "mode_deactivation_receipt": ModeDeactivationReceipt,
    "mode_delivery_receipt": ModeDeliveryReceipt,
    "mode_evaluation_case_result": ModeEvaluationCaseResult,
    "mode_evaluation_design": ModeEvaluationDesignV1,
    "mode_evaluation_report": ModeEvaluationReport,
    "mode_evaluation_task": ModeEvaluationTask,
    "mode_evaluation_execution_contract_v1": ModeEvaluationExecutionContractV1,
    "mode_evaluation_fixture_v1": ModeEvaluationFixtureV1,
    "mode_evaluation_public_plan_v1": ModeEvaluationPublicPlanV1,
    "mode_evaluation_mode_outcome_v1": ModeEvaluationModeOutcomeV1,
    "mode_evaluation_result_v1": ModeEvaluationResultV1,
    "mode_evaluation_run_cell_v1": ModeEvaluationRunCellV1,
    "mode_evaluation_scenario_v1": ModeEvaluationScenarioV1,
    "mode_evaluation_task_outcome_v1": ModeEvaluationTaskOutcomeV1,
    "mode_judge_decision_v1": ModeJudgeDecisionV1,
    "mode_judge_pair_decision_v1": ModeJudgePairDecisionV1,
    "mode_policy_observation_v1": ModePolicyObservationV1,
    "mode_security_posture": ModeSecurityPosture,
    "mode_target_compatibility": ModeTargetCompatibility,
}


def mode_schema_bundle() -> dict[str, dict[str, object]]:
    return {
        name: model.model_json_schema(mode="validation") for name, model in sorted(_MODELS.items())
    }


def export_mode_schemas(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, schema in mode_schema_bundle().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return tuple(written)
