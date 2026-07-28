"""JSON Schema export for the Milestone 6A.4 repair replication."""

from __future__ import annotations

from adaptation_compiler_lab.benchmark.breadth_remediation import (
    BreadthRemediationCell,
    BreadthRemediationContract,
    BreadthRemediationDesign,
    BreadthRemediationJudgeDecision,
    BreadthRemediationPublicPlan,
    BreadthRemediationResult,
    BreadthRemediationTask,
    OracleCheckContract,
)


def breadth_remediation_schemas() -> dict[str, dict[str, object]]:
    """Return portable schemas for the repair-replication records."""

    return {
        "breadth_remediation_cell.schema.json": BreadthRemediationCell.model_json_schema(),
        "breadth_remediation_contract.schema.json": (
            BreadthRemediationContract.model_json_schema()
        ),
        "breadth_remediation_design.schema.json": BreadthRemediationDesign.model_json_schema(),
        "breadth_remediation_judge_decision.schema.json": (
            BreadthRemediationJudgeDecision.model_json_schema()
        ),
        "breadth_remediation_public_plan.schema.json": (
            BreadthRemediationPublicPlan.model_json_schema()
        ),
        "breadth_remediation_result.schema.json": BreadthRemediationResult.model_json_schema(),
        "breadth_remediation_task.schema.json": BreadthRemediationTask.model_json_schema(),
        "oracle_check_contract.schema.json": OracleCheckContract.model_json_schema(),
    }
