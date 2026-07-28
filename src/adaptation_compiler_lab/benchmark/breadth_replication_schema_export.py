"""JSON Schema export for Milestone 6A.4 breadth replication."""

from __future__ import annotations

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthJudgeDecision,
    BreadthProfileConstructionReceipt,
    BreadthProfileSet,
    BreadthReplicationCell,
    BreadthReplicationContract,
    BreadthReplicationDesign,
    BreadthReplicationPublicPlan,
    BreadthReplicationResult,
    BreadthReplicationTask,
    BreadthTaskPairOutcome,
)
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairComparisonTrialReceipt,
)


def breadth_replication_schemas() -> dict[str, dict[str, object]]:
    """Return portable, versioned schemas for every public 6A.4 record."""

    return {
        "breadth_judge_decision.schema.json": BreadthJudgeDecision.model_json_schema(),
        "breadth_profile_construction_receipt.schema.json": (
            BreadthProfileConstructionReceipt.model_json_schema()
        ),
        "breadth_profile_set.schema.json": BreadthProfileSet.model_json_schema(),
        "breadth_replication_cell.schema.json": BreadthReplicationCell.model_json_schema(),
        "breadth_replication_contract.schema.json": (
            BreadthReplicationContract.model_json_schema()
        ),
        "breadth_replication_design.schema.json": BreadthReplicationDesign.model_json_schema(),
        "breadth_replication_public_plan.schema.json": (
            BreadthReplicationPublicPlan.model_json_schema()
        ),
        "breadth_replication_result.schema.json": BreadthReplicationResult.model_json_schema(),
        "breadth_replication_task.schema.json": BreadthReplicationTask.model_json_schema(),
        "breadth_task_pair_outcome.schema.json": BreadthTaskPairOutcome.model_json_schema(),
        "fair_comparison_trial_receipt.schema.json": (
            FairComparisonTrialReceipt.model_json_schema()
        ),
    }
