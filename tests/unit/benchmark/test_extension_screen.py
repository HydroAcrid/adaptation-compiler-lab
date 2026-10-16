from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.benchmark.extension_screen import (
    CONDITIONS,
    TASK_IDS,
    clauses,
    compile_selection,
    prompt,
    summarize,
    validate_patch,
)


def fixture_cases() -> list[dict[str, Any]]:
    root = Path(__file__).parents[3]
    result: list[dict[str, Any]] = json.loads(
        (root / "development_benchmark_extensions/rapid-v1/cases.json").read_text()
    )
    return result


def complete_trials() -> list[dict[str, Any]]:
    trials = []
    for task in sorted(TASK_IDS):
        for condition in CONDITIONS:
            for repeat in (0, 1):
                trials.append(
                    {
                        "task_id": task,
                        "condition": condition,
                        "repeat": repeat,
                        "score": {"instrument_valid": True, "passed": ["a", "b"], "complete": True},
                    }
                )
    return trials


def selectors() -> list[dict[str, Any]]:
    return [{"task_id": task, "clause_ids": []} for task in sorted(TASK_IDS)]


def test_targets_cannot_see_hidden_scorers_or_known_repairs() -> None:
    for case in fixture_cases():
        shown = json.loads(prompt(case))
        assert set(shown) == {"task", "project_policy", "files", "allowed_paths"}
        assert "hidden_checks" not in shown and "oracle" not in shown


def test_selection_cannot_add_unattributed_or_oversized_instructions() -> None:
    catalog = clauses([{"id": "upstream", "text": "---\nname: sample\n---\nOne.\n\nTwo."}])
    assert compile_selection(catalog, ["upstream:000"]) == "One."
    for ids in (["invented"], ["upstream:000", "upstream:000"]):
        with pytest.raises(ValueError):
            compile_selection(catalog, ids)
    with pytest.raises(ValueError, match="4000-byte"):
        compile_selection({"large": "ü" * 2001}, ["large"])


def test_patch_cannot_modify_hidden_checks_or_another_path() -> None:
    case = fixture_cases()[0]
    for path in ("hidden_checks.py", "../secret", "C:/outside", "normalizer.py"):
        with pytest.raises(ValueError):
            validate_patch(case, {"files": [{"path": path, "content": "bad"}]})


def test_ties_do_not_become_evidence_of_added_value() -> None:
    result = summarize(complete_trials(), selectors())
    assert result["verdict"] == "no_incremental_quality_signal"
    assert not result["general_effectiveness_proven"]


def test_incomplete_cases_and_missing_neutral_selection_cannot_pass() -> None:
    trials = complete_trials()
    with pytest.raises(ValueError):
        summarize([t for t in trials if t["task_id"] != "copy-only"], selectors())
    with pytest.raises(ValueError):
        summarize(trials, selectors()[:-1])


def test_regression_or_inappropriate_neutral_guidance_blocks_candidate() -> None:
    trials = complete_trials()
    target = next(t for t in trials if t["condition"] == "temper_selected")
    target["score"]["passed"] = []
    assert summarize(trials, selectors())["verdict"] == "candidate_regression"
    selected = selectors()
    next(s for s in selected if s["task_id"] == "copy-only")["clause_ids"] = ["coding"]
    assert summarize(complete_trials(), selected)["verdict"] == "candidate_regression"


def test_one_lucky_gain_does_not_pass_the_repeated_gain_rule() -> None:
    trials = complete_trials()
    for t in trials:
        if t["task_id"] == "archive-preview" and t["condition"] == "direct_sources":
            t["score"]["passed"] = [] if t["repeat"] == 0 else ["a", "b"]
    assert summarize(trials, selectors())["verdict"] == "no_incremental_quality_signal"
    repeated = deepcopy(trials)
    for t in repeated:
        if t["task_id"] == "archive-preview" and t["condition"] == "direct_sources":
            t["score"]["passed"] = []
    assert summarize(repeated, selectors())["verdict"] == "promising_repeated_objective_signal"
