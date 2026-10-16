from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, HabitBatchV1
from adaptation_compiler_lab.autonomy.models import HabitContradictionProposalV1, HabitState
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker, CapturePage
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import episode, trial


@pytest.mark.parametrize("cached_support", [True, False])
def test_replayed_context_cannot_become_a_new_preference_change(
    app: Any, cached_support: bool
) -> None:
    service, clock = app
    old = episode(7, clock, text="This earlier task needed more explanation.")
    service.ingest_episode(old)
    habit_id = trial(service, clock)
    service.store.append(
        "prior-analysis",
        "analysis_completed",
        {
            "episode_ids": [old.episode_id, "task-0", "task-1", "task-2"],
            "raw_ref": asdict(service.store.save_raw(b"{}")),
            "completed_at": clock.value.isoformat(),
        },
        at=clock.value,
    )
    clock.value += timedelta(days=1)
    fresh = episode(8, clock, text="The next task is ready.")

    class Sensor:
        def analyze(self, episodes: Any, **kwargs: Any) -> HabitBatchV1:
            return HabitBatchV1(
                proposals=(),
                contradictions=(
                    HabitContradictionProposalV1(
                        habit_id=habit_id,
                        evidence_episode_ids=("task-0" if cached_support else old.episode_id,),
                        evaluation_version=EVALUATION_VERSION,
                    ),
                ),
            )

    worker = BackgroundHabitWorker(
        service,
        read_completed=lambda *args: CapturePage("next", (fresh,)),
        sensor=Sensor(),
        remaining_capacity=lambda: 50,
        context=lambda project: "",
    )
    assert worker.poll()["status"] == "shadow"
    assert service.hypotheses()[0].state is HabitState.TRIAL
    assert not service.hypotheses()[0].contradiction_episode_ids


def test_mixed_cached_and_fresh_citations_keep_only_the_new_correction(app: Any) -> None:
    service, clock = app
    old = episode(7, clock, text="This earlier task needed more explanation.")
    service.ingest_episode(old)
    habit_id = trial(service, clock)
    service.store.append(
        "prior-analysis",
        "analysis_completed",
        {
            "episode_ids": [old.episode_id, "task-0", "task-1", "task-2"],
            "raw_ref": asdict(service.store.save_raw(b"{}")),
            "completed_at": clock.value.isoformat(),
        },
        at=clock.value,
    )
    clock.value += timedelta(days=1)
    fresh = episode(
        8, clock, text="The terse updates are no longer helping. Include the reasoning."
    )

    class Sensor:
        def analyze(self, episodes: Any, **kwargs: Any) -> HabitBatchV1:
            return HabitBatchV1(
                proposals=(),
                contradictions=(
                    HabitContradictionProposalV1(
                        habit_id=habit_id,
                        evidence_episode_ids=(old.episode_id, fresh.episode_id),
                        evaluation_version=EVALUATION_VERSION,
                    ),
                ),
            )

    worker = BackgroundHabitWorker(
        service,
        read_completed=lambda *args: CapturePage("next", (fresh,)),
        sensor=Sensor(),
        remaining_capacity=lambda: 50,
        context=lambda project: "",
    )
    assert worker.poll()["status"] == "shadow"
    assert service.hypotheses()[0].state is HabitState.PAUSED
    assert service.hypotheses()[0].contradiction_episode_ids == (fresh.episode_id,)


def test_freshness_filter_does_not_hide_an_invented_counterevidence_reference(app: Any) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    clock.value += timedelta(days=1)
    fresh = episode(8, clock)

    class Sensor:
        def analyze(self, episodes: Any, **kwargs: Any) -> HabitBatchV1:
            return HabitBatchV1(
                proposals=(),
                contradictions=(
                    HabitContradictionProposalV1(
                        habit_id=habit_id,
                        evidence_episode_ids=("invented-task",),
                        evaluation_version=EVALUATION_VERSION,
                    ),
                ),
            )

    worker = BackgroundHabitWorker(
        service,
        read_completed=lambda *args: CapturePage("next", (fresh,)),
        sensor=Sensor(),
        remaining_capacity=lambda: 50,
        context=lambda project: "",
    )
    with pytest.raises(AutonomyIntegrityError, match="outside the current batch"):
        worker.poll()
    assert service.hypotheses()[0].state is HabitState.TRIAL
