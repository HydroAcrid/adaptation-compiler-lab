from pathlib import Path

import pytest

from scripts.persistent_hub_effort import Effort


def test_unobserved_and_unfinished_attention_remain_unknown(tmp_path: Path) -> None:
    effort = Effort(tmp_path)
    assert effort.summary()["active_seconds"] is None
    value = effort.transition("one", "persistent_hub", "setup", clock=100)
    assert value["active_seconds"] is None
    assert not value["participant_attention_recorded"]
    assert value["open_interval"]["category"] == "setup"


def test_waiting_and_measurement_overhead_are_separate(tmp_path: Path) -> None:
    effort = Effort(tmp_path)
    effort.transition("one", "native_managers", "setup", clock=100)
    effort.transition("one", "native_managers", "waiting", clock=112)
    effort.transition("one", "native_managers", "measurement", clock=150)
    value = effort.transition("one", "native_managers", None, clock=153)
    assert value["active_seconds"] == 15
    assert value["waiting_seconds"] == 38
    assert value["by_arm"]["skillkit"]["active_seconds"] is None
    assert value["by_arm"]["native_managers"]["active_seconds"] == 15


def test_restart_preserves_closed_intervals_and_discards_unknown_open_time(tmp_path: Path) -> None:
    Effort(tmp_path).transition("one", "skillkit", "research", clock=10)
    Effort(tmp_path).transition("one", "skillkit", "review", clock=20)
    value = Effort(tmp_path).abandon()
    assert value["active_seconds"] == 10
    assert value["open_interval"] is None
    assert value["participant_events"] == 3


def test_invalid_condition_does_not_create_evidence(tmp_path: Path) -> None:
    effort = Effort(tmp_path)
    with pytest.raises(ValueError):
        effort.transition("one", "invented", "review", clock=10)
    assert effort.summary()["participant_events"] == 0
