from __future__ import annotations

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.breadth_adjudication import (
    BreadthScoringCorrection,
    direct_check_counts,
    validate_direct_score,
)

_DIGEST = "sha256:" + "1" * 64


def test_direct_score_contract_counts_boolean_maps_without_legacy_wrapper() -> None:
    value = {
        "objective": {"one": True, "two": False},
        "diagnostic": {"three": True},
        "neutral": {"four": True, "five": True},
    }

    validated = validate_direct_score(value)

    assert direct_check_counts(validated["objective"]) == (1, 2)
    assert direct_check_counts(validated["diagnostic"]) == (1, 1)
    assert direct_check_counts(validated["neutral"]) == (2, 2)


@pytest.mark.parametrize(
    "value",
    (
        {"checks": {}, "receipts": {}},
        {"objective": {}, "diagnostic": {"one": True}, "neutral": {"two": True}},
        {"objective": {"one": 1}, "diagnostic": {"two": True}, "neutral": {"three": True}},
    ),
)
def test_direct_score_contract_rejects_legacy_or_malformed_shapes(value: object) -> None:
    with pytest.raises(ValueError):
        validate_direct_score(value)


def test_scoring_correction_requires_counts_and_failures_to_match_maps() -> None:
    correction = BreadthScoringCorrection(
        task_id="task-one",
        blind_output_id="output-one",
        original_trial_digest=_DIGEST,
        public_output_digest=_DIGEST,
        scorer_output_digest=_DIGEST,
        objective={"objective_pass": True},
        diagnostic={"diagnostic_miss": False},
        neutral={"neutral_pass": True},
        objective_passed=1,
        objective_total=1,
        diagnostic_passed=0,
        diagnostic_total=1,
        neutral_passed=1,
        neutral_total=1,
        behavior_conformant=False,
        behavior_failures=("diagnostic.diagnostic_miss",),
    )

    assert correction.total_passed == 2

    invalid = correction.model_dump()
    invalid["behavior_conformant"] = True
    with pytest.raises(ValidationError):
        BreadthScoringCorrection.model_validate(invalid)
