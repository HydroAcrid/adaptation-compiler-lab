from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaBenchmarkPlan,
    PersonaConditionMaterial,
    PersonaEvaluationReport,
    PersonaExecutionReceipt,
    PersonaJudgePacket,
    PersonaProfileAuthorOutput,
)

_ROOT = Path(__file__).resolve().parents[3]
_BENCHMARK = _ROOT / "development_benchmark_persona_evaluation"


def test_schema_snapshots_match_public_models() -> None:
    models: dict[str, type[BaseModel]] = {
        "persona-benchmark-plan.schema.json": PersonaBenchmarkPlan,
        "persona-condition-material.schema.json": PersonaConditionMaterial,
        "persona-evaluation-report.schema.json": PersonaEvaluationReport,
        "persona-execution-receipt.schema.json": PersonaExecutionReceipt,
        "persona-judge-packet.schema.json": PersonaJudgePacket,
        "persona-profile-author-output.schema.json": PersonaProfileAuthorOutput,
    }
    for filename, model in models.items():
        observed = json.loads(
            (_ROOT / "schemas/persona_evaluation/v1" / filename).read_text(encoding="utf-8")
        )
        assert observed == model.model_json_schema()


def test_frozen_result_remains_an_instrument_failure() -> None:
    report = PersonaEvaluationReport.model_validate_json(
        (_BENCHMARK / "RESULT-v1.json").read_bytes()
    )
    assert report.interpretation == "instrument_failure"
    assert not report.instrument_valid
    assert report.learning_agreement_rate == report.guidance_agreement_rate == 19 / 24
    assert report.sentinel_learning_correct == report.sentinel_guidance_correct == 6
    assert report.adjudication_rate == 9 / 24
    assert report.total_session_count == 63
    assert not report.counts_toward_ordinary_use_gate
    assert not report.cross_agent_transfer_established


def test_every_accepted_model_receipt_attests_isolation() -> None:
    paths = (
        tuple((_BENCHMARK / "profile-author").glob("*.receipt.json"))
        + tuple((_BENCHMARK / "judge-results").glob("*.receipt.json"))
        + tuple((_BENCHMARK / "adjudicator-results").glob("*.receipt.json"))
    )
    assert len(paths) == 63
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["exactly_one_persona"] is True
        assert value["fresh_ephemeral_session"] is True
        assert value["session_destroyed"] is True
        assert value["repository_visible"] is False
        assert value["prior_transcripts_loaded"] is False
        assert value["tools_used"] is False
        assert value["provider_billed_calls"] == 0
        assert value["external_validation_accessed"] is False


def test_replica_two_reverses_both_tracks_and_candidates() -> None:
    for first_path in sorted((_BENCHMARK / "judge-packets").glob("*-r1.json")):
        second_path = first_path.with_name(first_path.name.replace("-r1.json", "-r2.json"))
        first = PersonaJudgePacket.model_validate_json(first_path.read_bytes())
        second = PersonaJudgePacket.model_validate_json(second_path.read_bytes())
        assert first.persona_id == second.persona_id
        assert first.case_id == second.case_id
        assert tuple(item.track for item in first.track_pairs) == tuple(
            reversed(tuple(item.track for item in second.track_pairs))
        )
        for track in (item.track for item in first.track_pairs):
            left = next(item for item in first.track_pairs if item.track is track)
            right = next(item for item in second.track_pairs if item.track is track)
            assert left.alternatives == tuple(reversed(right.alternatives))
