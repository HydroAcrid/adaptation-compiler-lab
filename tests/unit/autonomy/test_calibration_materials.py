from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from adaptation_compiler_lab.autonomy.analyzer import (
    EVALUATION_VERSION,
    HabitAnalysisV1,
    HabitReviewV1,
)
from adaptation_compiler_lab.autonomy.calibration import DISQUALIFIED_DATASETS
from adaptation_compiler_lab.autonomy.evaluation import COUNTS, load_frozen_scenarios
from adaptation_compiler_lab.autonomy.styles import StyleKey, style_contract
from adaptation_compiler_lab.serialization import canonical_digest
from scripts.prepare_habit_calibration_v15 import CHOICES, REQUIRED, build

ROOT = Path(__file__).parents[2] / "fixtures/autonomy"


def test_wire_versions_match_the_current_frozen_evaluation() -> None:
    for model in (HabitAnalysisV1, HabitReviewV1):
        version = model.model_json_schema()["properties"]["evaluation_version"]
        assert version["const"] == EVALUATION_VERSION
        assert version["default"] == EVALUATION_VERSION


def test_current_calibration_is_frozen_fresh_and_has_opaque_observation_ids() -> None:
    data = load_frozen_scenarios(
        ROOT / "habit_eval_v15_prospective.json",
        ROOT / "habit_eval_v15_prospective.manifest.json",
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
        and path.name != "habit_eval_v15_prospective.json"
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


def test_exposed_v14_material_is_preserved_and_disqualified() -> None:
    data = json.loads((ROOT / "habit_eval_v14_prospective.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (ROOT / "habit_eval_v14_prospective.manifest.json").read_text(encoding="utf-8")
    )
    assert canonical_digest(data) == manifest["dataset_digest"]
    assert manifest["dataset_digest"] in DISQUALIFIED_DATASETS
    assert Counter(case["group"] for case in data["cases"]) == Counter(COUNTS)


def test_negative_tasks_and_corrections_share_the_required_artifact() -> None:
    data = build()
    positive_corrections = {text for choices in CHOICES.values() for text in choices}
    for case in data["cases"]:
        if case["group"] != "context_constraint":
            continue
        family = next(value for value in REQUIRED.values() if value[0] in case["context"])
        artifact, requirement, corrections = family
        assert requirement in case["context"]
        assert not case["expected"]["style_keys"]
        assert len({episode["task_id"] for episode in case["episodes"]}) == 3
        assert len({episode["date"] for episode in case["episodes"]}) == 2
        for episode in case["episodes"]:
            task, correction = episode["user_messages"]
            assert artifact in task
            assert correction in corrections
            assert correction not in positive_corrections
