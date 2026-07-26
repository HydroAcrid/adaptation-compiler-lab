from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.isolated_rating import (
    BlindPairBinding,
    IsolatedBlindRatingDecision,
    IsolatedPairRating,
    PairPreference,
    isolated_rating_output_schema,
    validate_blind_pair_coverage,
)


def _pair(
    task: str,
    first: str,
    second: str,
    preference: PairPreference,
) -> IsolatedPairRating:
    preferred = {
        "first_better": first,
        "second_better": second,
        "tie": None,
    }[preference]
    return IsolatedPairRating(
        task_id=task,
        ordered_output_ids=(first, second),
        preference=preference,
        preferred_output_id=preferred,
        rationale="The selected patch handles a material edge case more safely.",
    )


def test_isolated_rating_requires_exact_blind_pair_coverage() -> None:
    expected = (
        BlindPairBinding(task_id="task-a", ordered_output_ids=("output-a1", "output-a2")),
        BlindPairBinding(task_id="task-b", ordered_output_ids=("output-b1", "output-b2")),
    )
    decision = IsolatedBlindRatingDecision(
        pair_ratings=(
            _pair("task-b", "output-b1", "output-b2", "tie"),
            _pair("task-a", "output-a1", "output-a2", "second_better"),
        ),
        overall_assessment="One pair is equivalent while the other has a meaningful safety edge.",
        evaluator_limitations=("Only the supplied patches and final responses were available.",),
    )

    assert validate_blind_pair_coverage(decision, expected) is decision


def test_isolated_rating_rejects_preference_output_mismatch() -> None:
    with pytest.raises(ValidationError, match="preferred output"):
        IsolatedPairRating(
            task_id="task-a",
            ordered_output_ids=("output-a1", "output-a2"),
            preference="first_better",
            preferred_output_id="output-a2",
            rationale="The first output is materially safer than the second implementation.",
        )


def test_isolated_rating_rejects_substituted_output() -> None:
    expected = (
        BlindPairBinding(task_id="task-a", ordered_output_ids=("output-a1", "output-a2")),
        BlindPairBinding(task_id="task-b", ordered_output_ids=("output-b1", "output-b2")),
    )
    decision = IsolatedBlindRatingDecision(
        pair_ratings=(
            _pair("task-a", "output-a1", "output-substituted", "first_better"),
            _pair("task-b", "output-b1", "output-b2", "tie"),
        ),
        overall_assessment="The supplied candidate set contains one materially stronger patch.",
        evaluator_limitations=("Only anonymous packet content was considered.",),
    )

    with pytest.raises(ValueError, match="substituted"):
        validate_blind_pair_coverage(decision, expected)


def test_isolated_rating_output_schema_is_provider_strict_and_locally_minimal() -> None:
    schema = isolated_rating_output_schema()

    assert schema["additionalProperties"] is False
    required = schema["required"]
    properties = schema["properties"]
    assert isinstance(required, list)
    assert isinstance(properties, dict)
    assert set(required) == set(properties)
    pair_ratings = properties["pair_ratings"]
    assert isinstance(pair_ratings, dict)
    pair_schema = pair_ratings["items"]
    assert isinstance(pair_schema, dict)
    assert pair_schema["additionalProperties"] is False
    pair_required = pair_schema["required"]
    pair_properties = pair_schema["properties"]
    assert isinstance(pair_required, list)
    assert isinstance(pair_properties, dict)
    assert set(pair_required) == set(pair_properties)
    assert "prefixItems" not in json.dumps(schema)
