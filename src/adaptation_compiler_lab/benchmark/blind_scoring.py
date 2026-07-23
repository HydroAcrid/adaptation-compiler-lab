"""Deterministic condition-blind presentation and rating-completeness checks."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator

from adaptation_compiler_lab.benchmark.models import BlindTaskId
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed
from adaptation_compiler_lab.benchmark.role_packets import (
    BlindOutputDescriptor,
    BlindPreferenceScoringPacket,
    PreferenceRating,
)
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.serialization import canonical_digest


class BlindTrialPresentationSource(FrozenModel):
    """Condition-free result metadata eligible for Kevin's scoring packet."""

    trial_id: Identifier
    diff_digest: Sha256Digest
    independent_test_digest: Sha256Digest
    rubric_digest: Sha256Digest


class CompletedPreferenceRatings(FrozenModel):
    """Exactly one Kevin rating for every anonymous packet output."""

    scoring_packet_digest: Sha256Digest
    ratings: Annotated[tuple[PreferenceRating, ...], Field(min_length=8, max_length=8)]

    @field_validator("ratings")
    @classmethod
    def ratings_are_unique(
        cls,
        value: tuple[PreferenceRating, ...],
    ) -> tuple[PreferenceRating, ...]:
        output_ids = tuple(item.blind_output_id for item in value)
        rating_ids = tuple(item.rating_id for item in value)
        if len(output_ids) != len(set(output_ids)) or len(rating_ids) != len(set(rating_ids)):
            raise ValueError("preference ratings must be unique by output and rating ID")
        return value


def build_blind_preference_scoring_packet(
    *,
    seed: RandomizationSeed,
    benchmark_id: str,
    blind_task_id: BlindTaskId,
    sources: tuple[BlindTrialPresentationSource, ...],
    created_at: UtcDateTime,
) -> BlindPreferenceScoringPacket:
    """Assign unrelated output labels and a secret-seed order without condition metadata."""

    if len(sources) != 8 or len({item.trial_id for item in sources}) != 8:
        raise ValueError("blind preference packet requires eight unique trial outputs")
    descriptors = tuple(
        BlindOutputDescriptor(
            blind_output_id=seed.blind_id(
                prefix="output",
                domain=f"{benchmark_id}/{blind_task_id}/preference-output",
                stable_key=source.trial_id,
            ),
            trial_id=source.trial_id,
            diff_digest=source.diff_digest,
            independent_test_digest=source.independent_test_digest,
            rubric_digest=source.rubric_digest,
            presentation_digest=canonical_digest(
                {
                    "blind_output_id": seed.blind_id(
                        prefix="output",
                        domain=f"{benchmark_id}/{blind_task_id}/preference-output",
                        stable_key=source.trial_id,
                    ),
                    "diff_digest": source.diff_digest,
                    "independent_test_digest": source.independent_test_digest,
                    "rubric_digest": source.rubric_digest,
                }
            ),
        )
        for source in sources
    )
    randomized = seed.shuffled(
        descriptors,
        domain=f"{benchmark_id}/{blind_task_id}/preference-presentation-order",
    )
    commitment = canonical_digest(
        {"blind_output_ids": [item.blind_output_id for item in randomized]}
    )
    return BlindPreferenceScoringPacket(
        packet_id=f"preference-packet-{blind_task_id.removeprefix('task-')}",
        benchmark_id=benchmark_id,
        blind_task_id=blind_task_id,
        outputs=randomized,
        output_order_commitment=commitment,
        created_at=created_at,
    )


def validate_complete_preference_ratings(
    packet: BlindPreferenceScoringPacket,
    ratings: tuple[PreferenceRating, ...],
) -> CompletedPreferenceRatings:
    """Require complete condition-blind Kevin ratings before unblinding."""

    packet_digest = packet.content_digest
    expected_outputs = {item.blind_output_id for item in packet.outputs}
    if {item.blind_output_id for item in ratings} != expected_outputs:
        raise ValueError("preference ratings do not exactly cover the scoring packet")
    if any(item.scoring_packet_digest != packet_digest for item in ratings):
        raise ValueError("preference rating substituted its scoring packet")
    return CompletedPreferenceRatings(
        scoring_packet_digest=packet_digest,
        ratings=tuple(sorted(ratings, key=lambda item: item.blind_output_id)),
    )
