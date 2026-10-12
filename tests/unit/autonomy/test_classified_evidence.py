from __future__ import annotations

import json
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, SchemaBoundHabitSensor
from adaptation_compiler_lab.autonomy.models import HabitState, InputOrigin
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import episode, trial


def response(
    evidence: list[dict[str, str]], assessments: list[Any] | None = None
) -> dict[str, Any]:
    return {
        "evaluation_version": EVALUATION_VERSION,
        "candidates": [
            {"style_key": "concise_progress", "origin": "inferred", "evidence": evidence}
        ],
        "known_habit_assessments": assessments or [],
    }


@pytest.mark.parametrize("basis", ["task_requirement", "quoted_or_learned", "uncertain"])
def test_repeated_nonpersonal_evidence_cannot_support_a_habit(app: Any, basis: str) -> None:
    _service, clock = app
    episodes = tuple(episode(i, clock) for i in range(3))
    payload = response(
        [{"episode_id": e.episode_id, "quote": e.text, "basis": basis} for e in episodes]
    )
    batch = SchemaBoundHabitSensor(lambda *args: json.dumps(payload)).analyze(
        episodes, context="The required incident template determines the response format."
    )
    assert not batch.proposals and not batch.contradictions


def test_single_discretionary_request_is_weak_not_trial_evidence(app: Any) -> None:
    service, clock = app
    e = episode(0, clock)
    payload = response([{"episode_id": e.episode_id, "quote": e.text, "basis": "personal_choice"}])
    service.ingest_episode(e)
    batch = SchemaBoundHabitSensor(lambda *args: json.dumps(payload)).analyze((e,), context="")
    habit = service.record_proposal(batch.proposals[0])
    assert habit.state is HabitState.PROVISIONAL
    assert habit.support_episode_ids == (e.episode_id,)
    assert habit.origin == "inferred"


@pytest.mark.parametrize("origin", [InputOrigin.AGENT, InputOrigin.UNKNOWN, InputOrigin.COPIED])
def test_semantic_personal_label_cannot_override_source_attribution(app: Any, origin: Any) -> None:
    _service, clock = app
    e = episode(0, clock, origin=origin)
    payload = response([{"episode_id": e.episode_id, "quote": e.text, "basis": "personal_choice"}])
    assert (
        not SchemaBoundHabitSensor(lambda *args: json.dumps(payload))
        .analyze((e,), context="")
        .proposals
    )


@pytest.mark.parametrize("verdict", ["personal_change", "task_exception"])
def test_changed_style_pauses_but_temporary_task_exception_does_not(app: Any, verdict: str) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    e = episode(10, clock, text="Give the reasoning in these updates; the short ones lose the why.")
    service.ingest_episode(e)
    payload = {
        "evaluation_version": EVALUATION_VERSION,
        "candidates": [],
        "known_habit_assessments": [
            {
                "habit_id": habit_id,
                "verdict": verdict,
                "evidence": [
                    {"episode_id": e.episode_id, "quote": e.text, "basis": "personal_choice"}
                ],
            }
        ],
    }
    batch = SchemaBoundHabitSensor(lambda *args: json.dumps(payload)).analyze(
        (e,), context="", existing_habits=service.hypotheses()
    )
    for change in batch.contradictions:
        service.record_contradiction(change)
    assert (service.hypotheses()[0].state is HabitState.PAUSED) == (verdict == "personal_change")


def test_every_known_target_must_be_assessed_and_quotes_must_be_real(app: Any) -> None:
    service, clock = app
    trial(service, clock)
    e = episode(10, clock)
    payload = response(
        [{"episode_id": e.episode_id, "quote": "invented", "basis": "personal_choice"}]
    )
    sensor = SchemaBoundHabitSensor(lambda *args: json.dumps(payload))
    with pytest.raises(ValueError, match="omitted or invented contradiction"):
        sensor.analyze((e,), context="", existing_habits=service.hypotheses())
    with pytest.raises(ValueError, match="evidence quotes"):
        sensor.analyze((e,), context="")
