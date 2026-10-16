from __future__ import annotations

from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from scripts.run_owner_habit_evaluation import OwnerRequestedEvaluationRunner
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_evaluation_run import BINDING, DATASET, MANIFEST, Sensor, runner


def owner_runner(
    app: Any, sensor: Sensor, capacity: Any = lambda: 50
) -> OwnerRequestedEvaluationRunner:
    service, clock = app
    return OwnerRequestedEvaluationRunner(
        dataset=DATASET,
        manifest=MANIFEST,
        store=service.store,
        sensor=sensor,
        remaining_capacity=capacity,
        runtime_binding=BINDING,
        clock=clock,
    )


def test_explicit_owner_check_runs_immediately_without_background_budget_or_publication(
    app: Any,
) -> None:
    service, _clock = app
    sensor = Sensor()
    before = (service.publisher.home / "AGENTS.md").read_bytes()
    value = owner_runner(app, sensor)
    for _ in range(13):
        assert value.advance()["status"] == "advanced"
    assert len(sensor.calls) == 13
    assert not any(event["type"] == "analysis" for event in service.store.events())
    assert value.report()["execution_policy"] == "owner_requested_foreground_v1"
    assert value.report()["background_budget_consumed"] == 0
    assert not value.report()["automatic_serving_gate_passed"]
    assert not service.hypotheses()
    assert (service.publisher.home / "AGENTS.md").read_bytes() == before
    resumed = owner_runner(app, sensor)
    assert resumed.run_id == value.run_id
    assert resumed.advance()["phases_completed"] == 14


def test_explicit_screening_selection_is_bound_and_reports_only_selected_cases(app: Any) -> None:
    service, clock = app
    selected = ("stable-00", "changing-00")
    value = OwnerRequestedEvaluationRunner(
        dataset=DATASET,
        manifest=MANIFEST,
        store=service.store,
        sensor=Sensor(),
        remaining_capacity=lambda: 50,
        runtime_binding=BINDING,
        clock=clock,
        case_ids=selected,
    )
    assert value.report()["cases_total"] == 2 and value.report()["phases_total"] == 3
    assert value.report()["screening_only"] is True
    for _ in range(3):
        value.advance()
    assert value.report()["complete"] is True
    assert value.report()["automatic_serving_gate_passed"] is False
    with pytest.raises(AutonomyIntegrityError, match="execution binding changed"):
        OwnerRequestedEvaluationRunner(
            dataset=DATASET,
            manifest=MANIFEST,
            store=service.store,
            sensor=Sensor(),
            remaining_capacity=lambda: 50,
            runtime_binding=BINDING,
            clock=clock,
            case_ids=("stable-00",),
        )


@pytest.mark.parametrize("capacity", [None, 19.9, True, float("nan"), 101])
def test_owner_check_still_requires_known_sufficient_subscription_capacity(
    app: Any, capacity: Any
) -> None:
    sensor = Sensor()
    value = owner_runner(app, sensor, capacity=lambda: capacity)
    assert value.advance()["status"] == "subscription_capacity_deferred"
    assert not sensor.calls


def test_owner_check_never_relabels_an_old_run_and_preserves_interrupted_reservations(
    app: Any,
) -> None:
    sensor = Sensor()
    background = runner(app, sensor)
    before = background.store.head_digest
    with pytest.raises(AutonomyIntegrityError, match="cannot change"):
        owner_runner(app, sensor)
    assert background.store.head_digest == before


def test_owner_check_does_not_retry_interrupted_model_session(app: Any) -> None:
    sensor = Sensor()
    value = owner_runner(app, sensor)
    value.store.append(
        "evaluation-analysis-" + value.run_id + "-" + value.phases[0].key,
        "owner_evaluation_analysis",
        {"started_at": value.clock().isoformat(), "sessions": 1},
        at=value.clock(),
    )
    assert value.advance()["status"] == "interrupted_analysis_needs_attention"
    assert not sensor.calls


def test_failed_owner_phase_does_not_start_another_model_on_resume(app: Any) -> None:
    sensor = Sensor()
    value = owner_runner(app, sensor)
    phase = value.phases[0]
    value.store.append(
        "failed-fictional-phase",
        "evaluation_phase",
        {"phase": phase.key, "case_id": phase.case_id, "stage": phase.stage, "status": "failed"},
        at=value.clock(),
    )
    assert value.advance()["status"] == "failed_phase_needs_attention"
    assert not sensor.calls


def test_owner_execution_policy_changes_are_rejected_before_resume(
    app: Any, monkeypatch: Any
) -> None:
    sensor = Sensor()
    value = owner_runner(app, sensor)
    before = value.store.head_digest
    monkeypatch.setattr("scripts.run_owner_habit_evaluation.sha256_file", lambda path: "changed")
    with pytest.raises(AutonomyIntegrityError, match="execution binding changed"):
        owner_runner(app, sensor)
    assert value.store.head_digest == before
