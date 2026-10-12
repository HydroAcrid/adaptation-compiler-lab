from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.analyzer import (
    EVALUATION_VERSION,
    HabitAnalysisV1,
    SchemaBoundHabitSensor,
    safe_analysis_failure,
)
from adaptation_compiler_lab.autonomy.retention import purge_expired_raw
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import episode
from tests.unit.autonomy.test_classified_evidence import response


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
        return json.dumps(next(outputs))

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
        SchemaBoundHabitSensor(lambda *args: json.dumps(next(outputs))).analyze((e,), context="")
    other = episode(1, clock)
    review = response(
        [{"episode_id": other.episode_id, "quote": other.text, "basis": "personal_choice"}]
    )
    outputs = iter((original, review))
    assert (
        not SchemaBoundHabitSensor(lambda *args: json.dumps(next(outputs)))
        .analyze((e, other), context="")
        .proposals
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
