"""JSON Schema export for the Milestone 6A.4 score adjudication."""

from __future__ import annotations

from adaptation_compiler_lab.benchmark.breadth_adjudication import (
    BreadthAdjudicationInput,
    BreadthScoringAdjudicationDesign,
    BreadthScoringAdjudicationResult,
    BreadthScoringCorrection,
)


def breadth_adjudication_schemas() -> dict[str, dict[str, object]]:
    """Return portable versioned schemas for the scoring correction."""

    return {
        "breadth_adjudication_input.schema.json": (BreadthAdjudicationInput.model_json_schema()),
        "breadth_scoring_adjudication_design.schema.json": (
            BreadthScoringAdjudicationDesign.model_json_schema()
        ),
        "breadth_scoring_adjudication_result.schema.json": (
            BreadthScoringAdjudicationResult.model_json_schema()
        ),
        "breadth_scoring_correction.schema.json": (BreadthScoringCorrection.model_json_schema()),
    }
