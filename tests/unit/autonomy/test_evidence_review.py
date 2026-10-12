from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.analyzer import (
    EVALUATION_VERSION,
    HabitAnalysisV1,
    SchemaBoundHabitSensor,
    bound_output_schema,
    habit_review_schema,
    safe_analysis_failure,
)
from adaptation_compiler_lab.autonomy.retention import purge_expired_raw
from adaptation_compiler_lab.autonomy.styles import StyleKey
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import episode
from tests.unit.autonomy.test_classified_evidence import response
from tests.unit.autonomy.wire_fixture import wire_result


@pytest.mark.parametrize("review_basis", ["task_requirement", "quoted_or_learned", "uncertain"])
def test_independent_review_can_withhold_personal_sounding_requirements(
    app: Any,
    review_basis: str,
) -> None:
    _service, clock = app
    e = episode(0, clock)
    original = response([{"episode_id": e.episode_id, "quote": e.text, "basis": "personal_choice"}])
    review = response([{"episode_id": e.episode_id, "quote": e.text, "basis": review_basis}])
    outputs = iter((original, review))
    prompts = []

    def run(contract: str, prompt: str, schema: Any) -> str:
        prompts.append(json.loads(prompt))
        return wire_result(next(outputs), schema)

    batch = SchemaBoundHabitSensor(run).analyze((e,), context="Externally required format.")
    assert not batch.proposals
    assert "basis" not in json.dumps(prompts[1]["candidate_styles_to_review"])
    assert "origin" not in json.dumps(prompts[1]["candidate_styles_to_review"])


def test_verifier_cannot_add_styles_or_manufacture_uncorroborated_tasks(app: Any) -> None:
    _service, clock = app
    e = episode(0, clock)
    original = response([{"episode_id": e.episode_id, "quote": e.text, "basis": "personal_choice"}])
    review = json.loads(json.dumps(original))
    review["candidates"][0]["style_key"] = "outcome_first"
    outputs = iter((original, review))
    with pytest.raises(ValueError, match="new style"):
        SchemaBoundHabitSensor(lambda *args: wire_result(next(outputs), args[-1])).analyze(
            (e,), context=""
        )
    other = episode(1, clock)
    review = response(
        [{"episode_id": other.episode_id, "quote": other.text, "basis": "personal_choice"}]
    )
    outputs = iter((original, review))
    with pytest.raises(ValueError, match="omitted a style or cited task"):
        SchemaBoundHabitSensor(lambda *args: wire_result(next(outputs), args[-1])).analyze(
            (e, other), context=""
        )


def test_background_budget_reserves_both_fresh_model_passes(app: Any) -> None:
    from adaptation_compiler_lab.autonomy.analyzer import HabitBatchV1
    from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker, CapturePage

    service, clock = app
    service.store.append(
        "used-eleven",
        "analysis",
        {"sessions": 11, "started_at": (clock.value - timedelta(minutes=10)).isoformat()},
        at=clock.value,
    )

    class Sensor:
        analysis_sessions = 2

        def analyze(self, episodes: Any, **kwargs: Any) -> HabitBatchV1:
            pytest.fail("both model sessions must be reserved before either pass")

    worker = BackgroundHabitWorker(
        service,
        sensor=Sensor(),
        read_completed=lambda *args: CapturePage("next", (episode(0, clock),)),
        remaining_capacity=lambda: 50,
        context=lambda project: "",
    )
    assert worker.poll()["status"] == "capacity_deferred"


def test_unknown_schema_fields_never_leak_in_failure_diagnostics() -> None:
    raw = {
        "evaluation_version": EVALUATION_VERSION,
        "candidates": [],
        "known_habit_assessments": [],
        "private fictional phrase": "private value",
    }
    with pytest.raises(ValueError) as caught:
        HabitAnalysisV1.model_validate_json(json.dumps(raw), strict=True)
    safe = json.dumps(safe_analysis_failure(caught.value))
    assert "private" not in safe
    assert "unknown_field" in safe and "sensor_wire_schema_invalid" in safe


def test_provider_review_bounds_known_targets_and_candidate_styles() -> None:
    from jsonschema import Draft202012Validator

    from tests.unit.autonomy.wire_fixture import wire_result

    original = response(
        [{"episode_id": "task", "quote": "Shorten it.", "basis": "personal_choice"}]
    )
    schema = bound_output_schema(
        habit_review_schema(),
        episode_ids={"task"},
        habit_ids=set(),
        style_keys={StyleKey.CONCISE_PROGRESS},
    )
    payload = json.loads(wire_result(original, schema))
    validator = Draft202012Validator(schema)
    assert validator.is_valid(payload)
    payload["style_reviews"][0]["style_key"] = "outcome_first"
    assert not validator.is_valid(payload)
    payload = json.loads(wire_result(original, schema))
    payload["known_habit_assessments"] = [
        {"habit_id": "invented", "verdict": "unrelated", "evidence": []}
    ]
    assert not validator.is_valid(payload)


def test_multiple_valid_quotes_from_one_task_cannot_manufacture_confidence(app: Any) -> None:
    _service, clock = app
    e = episode(0, clock)
    evidence = [{"episode_id": e.episode_id, "quote": e.text, "basis": "personal_choice"}] * 3
    payload = response(evidence)
    sensor = SchemaBoundHabitSensor(lambda *args: wire_result(payload, args[-1]))
    result = sensor.analyze((e,), context="")
    assert result.proposals[0].evidence_episode_ids == (e.episode_id,)
    # Every cited quote is checked, even when an ID was already seen.
    payload["candidates"][0]["evidence"][-1] = {
        "episode_id": e.episode_id,
        "quote": "invented later quote",
        "basis": "personal_choice",
    }
    with pytest.raises(ValueError, match="evidence quotes"):
        sensor.analyze((e,), context="")


def test_failed_analysis_wire_results_remain_encrypted_and_expire(app: Any) -> None:
    service, clock = app
    from dataclasses import asdict

    ref = service.store.save_raw(b"fictional rejected semantic output")
    service.store.append(
        "wire",
        "evaluation_wire",
        {"raw_ref": asdict(ref), "completed_at": clock.value.isoformat()},
        at=clock.value,
    )
    raw = service.store.raw_store.root / ref.relative_path
    assert b"fictional rejected" not in raw.read_bytes()
    assert purge_expired_raw(service.store, now=clock.value) == 0
    assert purge_expired_raw(service.store, now=clock.value + timedelta(days=31)) == 1
    assert not raw.exists()
