from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from adaptation_compiler_lab.autonomy.evaluation import COUNTS, load_frozen_scenarios
from adaptation_compiler_lab.autonomy.styles import StyleKey, style_contract
from scripts.prepare_habit_calibration_v14 import build

ROOT = Path(__file__).parents[2] / "fixtures/autonomy"


def test_current_calibration_is_frozen_fresh_and_has_opaque_observation_ids() -> None:
    data = load_frozen_scenarios(
        ROOT / "habit_eval_v14_prospective.json",
        ROOT / "habit_eval_v14_prospective.manifest.json",
    )
    assert data == build()
    assert data["purpose"] == "prospective_shadow_detection"
    assert Counter(case["group"] for case in data["cases"]) == Counter(COUNTS)
    ids = []
    for case in data["cases"]:
        for episode in case["episodes"]:
            ids.append(episode["task_id"])
            assert episode["task_id"].startswith("episode-")
            assert not any(group in episode["task_id"] for group in COUNTS)
        for key in case["expected"]["style_keys"]:
            assert all(
                episode["task_class"] == style_contract(StyleKey(key))[1]
                for episode in case["episodes"]
            )
    assert len(ids) == len(set(ids))
    old = {
        text
        for path in ROOT.glob("habit_eval_*.json")
        if not path.name.endswith(".manifest.json")
        and path.name != "habit_eval_v14_prospective.json"
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]
        for episode in case["episodes"]
        for text in episode["user_messages"]
    }
    new = {
        text
        for case in data["cases"]
        for episode in case["episodes"]
        for text in episode["user_messages"]
    }
    assert not old & new
    untrusted = [case for case in data["cases"] if case["group"] == "untrusted"]
    assert all(not case["expected"]["style_keys"] for case in untrusted)
    assert any(
        episode["origin"] == "owner_authorized_chat"
        for case in untrusted
        for episode in case["episodes"]
    )
