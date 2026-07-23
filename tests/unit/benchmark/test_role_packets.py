"""Internally blinded role-packet and preference-scoring tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.role_packets import (
    BlindOutputDescriptor,
    BlindPreferenceScoringPacket,
    InternalStudyRole,
    IsolatedRolePacket,
    PreferenceRating,
)

NOW = datetime(2026, 7, 23, 18, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def test_profile_author_packet_forbids_compiled_holdout_mapping_and_results() -> None:
    packet = IsolatedRolePacket(
        packet_id="profile-author-packet-1",
        benchmark_id="benchmark-internal-feasibility-1",
        role=InternalStudyRole.PROFILE_AUTHOR,
        eligible_input_digests=(DIGEST,),
        allowed_outputs=("profile_draft",),
        held_out_content_allowed=False,
        compiled_adaptation_allowed=False,
        condition_mapping_allowed=False,
        trial_results_allowed=False,
        created_at=NOW,
    )

    assert packet.content_digest.startswith("sha256:")


def test_profile_packet_cannot_broaden_knowledge() -> None:
    with pytest.raises(ValidationError, match="outside the frozen role boundary"):
        IsolatedRolePacket(
            packet_id="profile-author-packet-1",
            benchmark_id="benchmark-internal-feasibility-1",
            role=InternalStudyRole.PROFILE_AUTHOR,
            eligible_input_digests=(DIGEST,),
            allowed_outputs=("profile_draft",),
            held_out_content_allowed=True,
            compiled_adaptation_allowed=False,
            condition_mapping_allowed=False,
            trial_results_allowed=False,
            created_at=NOW,
        )


def test_blind_scoring_packet_and_rating_contain_no_condition_label() -> None:
    outputs = tuple(
        BlindOutputDescriptor(
            blind_output_id=f"output-{index}",
            trial_id=f"trial-{index}",
            diff_digest=DIGEST,
            independent_test_digest=DIGEST,
            rubric_digest=DIGEST,
            presentation_digest=DIGEST,
        )
        for index in range(8)
    )
    packet = BlindPreferenceScoringPacket(
        packet_id="scoring-packet-1",
        benchmark_id="benchmark-internal-feasibility-1",
        blind_task_id="task-000000000001",
        outputs=outputs,
        output_order_commitment=DIGEST,
        created_at=NOW,
    )
    rating = PreferenceRating(
        rating_id="rating-1",
        scoring_packet_digest=packet.content_digest,
        blind_output_id="output-1",
        requirement_and_preference_fit=4,
        change_discipline_and_maintainability=3,
        severe_behavioral_violation=False,
        rated_at=NOW,
    )

    assert "condition" not in rating.model_dump(mode="json")
    assert packet.condition_mapping_withheld
