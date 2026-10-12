from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from adaptation_compiler_lab.autonomy.analyzer import HabitBatchV1, habit_output_schema
from adaptation_compiler_lab.autonomy.budget import background_budget_available
from adaptation_compiler_lab.autonomy.evaluation_run import ShadowEvaluationRunner
from adaptation_compiler_lab.autonomy.models import HabitContradictionProposalV1
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import proposal

DATASET = Path("tests/fixtures/autonomy/habit_eval_v3.json")
MANIFEST = Path("tests/fixtures/autonomy/habit_eval_v3.manifest.json")
BINDING = {"model": "fictional-model", "effort": "medium", "runtime_pin_digest": "fixture-pin"}


def test_provider_schema_requires_every_property_and_preserves_host_constraints() -> None:
    schema = habit_output_schema()
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    objects = [schema, *definitions.values()]
    for value in objects:
        if "properties" in value:
            assert set(value["required"]) == set(value["properties"])
            assert value["additionalProperties"] is False
    batch = HabitBatchV1(proposals=(proposal(("fictional-task",)),))
    Draft202012Validator(schema).validate(batch.model_dump(mode="json"))
    assert "default" not in json.dumps(schema)
    assert HabitBatchV1.model_json_schema()["properties"]["contradictions"]["default"] == []
    wrong = batch.model_dump(mode="json")
    wrong["proposals"][0]["evaluation_version"] = "unfrozen-version"
    assert not Draft202012Validator(schema).is_valid(wrong)


class Sensor:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def analyze(self, episodes: Any, **kwargs: Any) -> HabitBatchV1:
        self.calls.append((episodes, kwargs))
        if kwargs["existing_habits"]:
            return HabitBatchV1(
                proposals=(),
                contradictions=(
                    HabitContradictionProposalV1(
                        habit_id=kwargs["existing_habits"][0].habit_id,
                        evidence_episode_ids=(episodes[0].episode_id,),
                        evaluation_version="habit-eval-v3",
                    ),
                ),
            )
        return HabitBatchV1(proposals=(proposal(tuple(e.episode_id for e in episodes)),))


def runner(app: Any, sensor: Any, capacity: Any = lambda: 50) -> ShadowEvaluationRunner:
    service, clock = app
    return ShadowEvaluationRunner(
        dataset=DATASET,
        manifest=MANIFEST,
        store=service.store,
        sensor=sensor,
        remaining_capacity=capacity,
        runtime_binding=BINDING,
        clock=clock,
    )


def mark_prefix_complete(value: ShadowEvaluationRunner, stop_case: str) -> None:
    for phase in value.phases:
        if phase.case_id == stop_case:
            return
        value.store.append(
            "fixture-result-" + phase.key,
            "evaluation_phase",
            {
                "phase": phase.key,
                "case_id": phase.case_id,
                "stage": phase.stage,
                "status": "complete",
                "hypotheses": [],
            },
            at=value.clock(),
        )


def test_evaluation_is_resumable_encrypted_and_never_enables_the_personal_profile(app: Any) -> None:
    service, clock = app
    before = (service.publisher.home / "AGENTS.md").read_bytes()
    grant = service.grant()
    sensor = Sensor()
    value = runner(app, sensor)
    result = value.advance()
    assert result["cases_completed"] == 1 and result["cases_total"] == 120
    assert result["hypothesis_detection"]["precision"] == 1
    assert not result["complete"] and not result["automatic_serving_gate_passed"]
    assert not service.hypotheses() and service.grant() == grant
    assert (service.publisher.home / "AGENTS.md").read_bytes() == before
    assert not service.switch("personalization")
    private_files = list(service.store.raw_store.root.rglob("*"))
    assert all(p.read_bytes().startswith(b"ACLAB-RAW-1") for p in private_files if p.is_file())
    resumed = runner(app, sensor)
    assert resumed.advance()["status"] == "capacity_or_cadence_deferred"
    assert len(sensor.calls) == 1
    clock.value += timedelta(minutes=5)
    resumed.advance()
    assert len(sensor.calls) == 2


def test_unknown_capacity_and_interrupted_reservation_never_retry_a_model_turn(app: Any) -> None:
    sensor = Sensor()
    value = runner(app, sensor, capacity=lambda: None)
    assert value.advance()["status"] == "capacity_or_cadence_deferred"
    assert not sensor.calls
    phase = value.phases[0]
    value.store.append(
        "evaluation-analysis-" + value.run_id + "-" + phase.key,
        "analysis",
        {
            "started_at": value.clock().isoformat(),
            "sessions": 1,
        },
        at=value.clock(),
    )
    assert value.advance()["status"] == "interrupted_analysis_needs_attention"
    assert not sensor.calls


def test_resume_rejects_changed_native_model_binding(app: Any) -> None:
    sensor = Sensor()
    value = runner(app, sensor)
    with pytest.raises(AutonomyIntegrityError, match="binding changed"):
        ShadowEvaluationRunner(
            dataset=DATASET,
            manifest=MANIFEST,
            store=value.store,
            sensor=sensor,
            remaining_capacity=lambda: 50,
            runtime_binding={**BINDING, "model": "substitute"},
        )
    assert not sensor.calls


def test_frozen_thresholds_cannot_be_lowered_to_make_a_run_pass(app: Any, tmp_path: Path) -> None:
    sensor = Sensor()
    manifest = json.loads(MANIFEST.read_text())
    manifest["precision_gate"] = 0.1
    changed = tmp_path / "manifest.json"
    changed.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="frozen habit evaluation changed"):
        ShadowEvaluationRunner(
            dataset=DATASET,
            manifest=changed,
            store=app[0].store,
            sensor=sensor,
            remaining_capacity=lambda: 50,
            runtime_binding=BINDING,
        )
    assert not sensor.calls


def test_disallowed_fixture_origins_are_filtered_before_the_model(app: Any) -> None:
    sensor = Sensor()
    value = runner(app, sensor)
    mark_prefix_complete(value, "untrusted-00")
    result = value.advance()
    assert result["phase"] == "untrusted-00:initial"
    assert not sensor.calls
    assert value.completed()[result["phase"]]["hypotheses"] == []


def test_changing_case_uses_fresh_counterevidence_against_cached_prefix(app: Any) -> None:
    _service, clock = app
    sensor = Sensor()
    value = runner(app, sensor)
    mark_prefix_complete(value, "changing-00")
    value.advance()
    clock.value += timedelta(minutes=5)
    result = runner(app, sensor).advance()
    assert result["phase"] == "changing-00:contradiction"
    assert len(sensor.calls[0][0]) == 3 and len(sensor.calls[1][0]) == 1
    assert len(sensor.calls[1][1]["existing_habits"]) == 1
    assert result["contradiction_pauses"] == 1
    assert result["native_scope_controls"] == "not_measured"
    assert not result["automatic_serving_gate_passed"]


@pytest.mark.parametrize("sessions", [-1, 0, 13, True, "1"])
def test_malformed_historical_session_counts_cannot_relax_the_budget(
    app: Any, sessions: Any
) -> None:
    _service, clock = app
    events = (
        {
            "type": "analysis",
            "payload": {
                "started_at": clock.value.isoformat(),
                "sessions": sessions,
            },
        },
    )
    assert not background_budget_available(
        events, now=clock.value + timedelta(minutes=5), remaining_percent=50
    )
