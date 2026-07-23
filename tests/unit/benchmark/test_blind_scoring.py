"""Condition-blind preference presentation tests."""

from datetime import UTC, datetime, timedelta

import pytest

from adaptation_compiler_lab.benchmark.blind_scoring import (
    BlindTrialPresentationSource,
    build_blind_preference_scoring_packet,
    validate_complete_preference_ratings,
)
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed
from adaptation_compiler_lab.benchmark.role_packets import PreferenceRating

NOW = datetime(2026, 7, 23, 18, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
TASK_ID = "task-000000000001"


def _sources() -> tuple[BlindTrialPresentationSource, ...]:
    return tuple(
        BlindTrialPresentationSource(
            trial_id=f"trial-{index:04d}",
            diff_digest=DIGEST,
            independent_test_digest="sha256:" + "b" * 64,
            rubric_digest="sha256:" + "c" * 64,
        )
        for index in range(1, 9)
    )


def test_packet_is_deterministic_randomized_and_contains_no_condition_mapping() -> None:
    seed = RandomizationSeed(b"s" * 32)

    packet = build_blind_preference_scoring_packet(
        seed=seed,
        benchmark_id="benchmark-internal-feasibility-1",
        blind_task_id=TASK_ID,
        sources=_sources(),
        created_at=NOW,
    )

    assert packet == build_blind_preference_scoring_packet(
        seed=seed,
        benchmark_id="benchmark-internal-feasibility-1",
        blind_task_id=TASK_ID,
        sources=_sources(),
        created_at=NOW,
    )
    payload = packet.model_dump(mode="json")
    assert "condition" not in payload
    assert "condition_mapping" not in payload
    assert payload["condition_mapping_withheld"] is True
    assert tuple(item.trial_id for item in packet.outputs) != tuple(
        item.trial_id for item in _sources()
    )


def test_kevin_ratings_must_cover_every_anonymous_output_before_unblinding() -> None:
    packet = build_blind_preference_scoring_packet(
        seed=RandomizationSeed(b"s" * 32),
        benchmark_id="benchmark-internal-feasibility-1",
        blind_task_id=TASK_ID,
        sources=_sources(),
        created_at=NOW,
    )
    ratings = tuple(
        PreferenceRating(
            rating_id=f"rating-{index:04d}",
            scoring_packet_digest=packet.content_digest,
            blind_output_id=output.blind_output_id,
            requirement_and_preference_fit=3,
            change_discipline_and_maintainability=3,
            severe_behavioral_violation=False,
            rated_at=NOW + timedelta(minutes=index),
        )
        for index, output in enumerate(packet.outputs, start=1)
    )

    completed = validate_complete_preference_ratings(packet, ratings)
    assert len(completed.ratings) == 8
    with pytest.raises(ValueError, match="exactly cover"):
        validate_complete_preference_ratings(packet, ratings[:-1])
