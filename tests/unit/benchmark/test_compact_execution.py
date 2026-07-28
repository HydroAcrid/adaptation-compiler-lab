from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
)
from adaptation_compiler_lab.benchmark.compact_execution import (
    CompactJudgeDecision,
    CompactProfileAuthorOutput,
    CompactProfileAuthorStage,
    CompactProfileReviewStage,
    CompactProjectionBlindReport,
    compact_judge_schema,
    compact_profile_author_schema,
    compact_profile_review_schema,
    is_interpreter_generated_path,
    validate_compact_remediated_profile_stages,
)
from adaptation_compiler_lab.benchmark.longitudinal_execution import load_evidence_packets

_DIGEST = "sha256:" + ("a" * 64)


def _author_stage(stage: int) -> CompactProfileAuthorStage:
    evidence_ids = tuple(f"dogfood-evidence-{index}" for index in range(1, stage + 1))
    return CompactProfileAuthorStage(
        stage=stage,
        evidence_ids=evidence_ids,
        profile_text=(
            "For persistent destinations, use a recoverable backup before replacement. "
            "Verify the selected action."
        ),
        change_summary="Preserved the exact active behavior and its verification rule.",
        intentional_edit_operations=1,
    )


def _observation(
    *,
    run_id: str,
    task_id: str,
    condition_id: str,
    output_id: str,
) -> CodexDevelopmentRunObservation:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    return CodexDevelopmentRunObservation(
        run_id=run_id,
        task_id=task_id,
        blind_condition_id=condition_id,
        blind_output_id=output_id,
        condition_digest=_DIGEST,
        trace_digest=_DIGEST,
        diff_digest=_DIGEST,
        final_response_digest=_DIGEST,
        scorer_output_digest=_DIGEST,
        command_digest=_DIGEST,
        environment_digest=_DIGEST,
        started_at=now,
        finished_at=now,
        duration_seconds=0,
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_output_tokens=0,
        objective_checks_passed=1,
        objective_checks_total=1,
        diagnostic_checks_passed=1,
        diagnostic_checks_total=1,
        neutral_checks_passed=1,
        neutral_checks_total=1,
        timed_out=False,
        exit_code=0,
        trace_conformant=True,
        config_destroyed=True,
        workspace_destroyed=True,
        valid=True,
    )


def test_profile_output_requires_ordered_three_stage_set() -> None:
    output = CompactProfileAuthorOutput(
        stages=(_author_stage(1), _author_stage(2), _author_stage(3)),
        overall_strategy="Maintained each stage as a standalone expression of active behavior.",
    )

    assert tuple(item.stage for item in output.stages) == (1, 2, 3)
    with pytest.raises(ValidationError, match="ordered stages"):
        CompactProfileAuthorOutput(
            stages=(_author_stage(2), _author_stage(1), _author_stage(3)),
            overall_strategy="Maintained each stage as a standalone expression of active behavior.",
        )


def test_blind_report_requires_complete_three_by_two_grid() -> None:
    observations = tuple(
        _observation(
            run_id=f"run-{task}-{condition}",
            task_id=f"task-{task}",
            condition_id=f"condition-{condition}",
            output_id=f"output-{task}-{condition}",
        )
        for task in range(1, 4)
        for condition in range(1, 3)
    )
    report = CompactProjectionBlindReport(
        design_digest=_DIGEST,
        execution_protocol_digest=_DIGEST,
        execution_contract_digest=_DIGEST,
        profile_construction_receipt_digest=_DIGEST,
        source_commit="abc123",
        observations=observations,
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    assert len(report.observations) == 6
    with pytest.raises(ValidationError, match="unique run and output IDs"):
        CompactProjectionBlindReport(
            design_digest=_DIGEST,
            execution_protocol_digest=_DIGEST,
            execution_contract_digest=_DIGEST,
            profile_construction_receipt_digest=_DIGEST,
            source_commit="abc123",
            observations=(*observations[:-1], observations[0].model_copy(update={"run_id": "x"})),
            created_at=datetime(2026, 7, 27, tzinfo=UTC),
        )


def test_response_schemas_are_closed_and_exactly_bounded() -> None:
    author = compact_profile_author_schema()
    reviewer = compact_profile_review_schema()
    judge = compact_judge_schema()

    assert author["additionalProperties"] is False
    assert reviewer["additionalProperties"] is False
    assert judge["additionalProperties"] is False
    assert author["properties"]["stages"]["maxItems"] == 3  # type: ignore[index]
    assert judge["properties"]["pair_ratings"]["minItems"] == 3  # type: ignore[index]


def test_judge_rejects_preference_output_mismatch() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        CompactJudgeDecision.model_validate(
            {
                "decision_version": "1.0.0",
                "pair_ratings": tuple(
                    {
                        "task_id": f"task-{index}",
                        "ordered_output_ids": (
                            f"first-{index}",
                            f"second-{index}",
                        ),
                        "preference": "first_better",
                        "preferred_output_id": f"second-{index}",
                        "implementation_quality": "The implementations differ in meaningful ways.",
                        "instruction_adherence": (
                            "The first follows the supplied task more closely."
                        ),
                        "blocker_handling": "Neither output encountered a material blocker here.",
                        "unsupported_verification_claims": (
                            "Neither output made an unsupported claim."
                        ),
                        "overall_rationale": (
                            "The first output is the stronger result for this task."
                        ),
                    }
                    for index in range(1, 4)
                ),
                "overall_assessment": "The anonymous pairs show small but meaningful differences.",
                "evaluator_limitations": ("This is a secondary qualitative judgment only.",),
            }
        )


def test_remediated_profile_requires_verification_and_exact_project_scope() -> None:
    repo = Path(__file__).parents[3]
    packets = load_evidence_packets(repo / "development_benchmark_longitudinal")
    texts = (
        "For persistent destinations, make a recoverable backup before replacement. "
        "Verify the selected action.",
        "For persistent destinations, make a recoverable backup before replacement. "
        "For project generated-cache, atomically replace generated caches without a backup. "
        "Verify the selected action.",
        "For project generated-cache, atomically replace generated caches without a backup. "
        "For persistent destinations, refuse overwrite unless a backup is explicitly requested. "
        "If requested, create the backup before replacement.",
    )
    stages = tuple(
        CompactProfileReviewStage(
            stage=stage,
            evidence_ids=packet.evidence_ids,
            approved_profile_text=text,
            review_summary="Preserved exact active behavior, scope, and verification.",
            intentional_edit_operations=1,
            unsupported_content_removed=False,
        )
        for stage, (packet, text) in enumerate(zip(packets, texts, strict=True), start=1)
    )

    validate_compact_remediated_profile_stages(stages=stages, packets=packets)
    missing_scope = stages[1].model_copy(
        update={
            "approved_profile_text": stages[1].approved_profile_text.replace(
                "project generated-cache, ",
                "",
            )
        }
    )
    with pytest.raises(ValueError, match="exact project scope"):
        validate_compact_remediated_profile_stages(
            stages=(stages[0], missing_scope, stages[2]),
            packets=packets,
        )


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        ("src/__pycache__/policy.cpython-312.pyc", True),
        ("policy.pyc", True),
        ("nested/policy.pyo", True),
        ("src/policy.py", False),
        (None, False),
    ),
)
def test_interpreter_generated_repository_paths_are_deterministic(
    path: str | None,
    expected: bool,
) -> None:
    assert is_interpreter_generated_path(path) is expected
