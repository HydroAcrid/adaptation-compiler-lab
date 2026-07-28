"""JSON Schema export for the fair task-channel comparison."""

from __future__ import annotations

from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairComparisonResult,
    FairComparisonTrialReceipt,
    FairTaskChannelJudgeDecision,
    FairTaskPairOutcome,
    TaskChannelComparisonContract,
    TaskChannelComparisonDesign,
    TaskChannelComparisonPublicPlan,
)


def task_channel_comparison_schemas() -> dict[str, dict[str, object]]:
    """Return the versioned portable comparison schemas."""

    return {
        "fair_comparison_result.schema.json": FairComparisonResult.model_json_schema(),
        "fair_comparison_trial_receipt.schema.json": (
            FairComparisonTrialReceipt.model_json_schema()
        ),
        "fair_task_pair_outcome.schema.json": FairTaskPairOutcome.model_json_schema(),
        "fair_task_channel_judge_decision.schema.json": (
            FairTaskChannelJudgeDecision.model_json_schema()
        ),
        "task_channel_comparison_contract.schema.json": (
            TaskChannelComparisonContract.model_json_schema()
        ),
        "task_channel_comparison_design.schema.json": (
            TaskChannelComparisonDesign.model_json_schema()
        ),
        "task_channel_comparison_public_plan.schema.json": (
            TaskChannelComparisonPublicPlan.model_json_schema()
        ),
    }
