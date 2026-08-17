from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaCondition,
    PersonaJudgeDecision,
    PersonaPreference,
    PersonaTrack,
    PersonaTrackDecision,
    build_judge_packet,
    persona_judge_output_schema,
    resolve_track_votes,
    validate_judge_decision,
)
from adaptation_compiler_lab.benchmark.persona_fixture import (
    build_persona_benchmark_plan,
    build_reference_materials,
)


def test_frozen_persona_plan_is_balanced() -> None:
    plan = build_persona_benchmark_plan()
    assert len(plan.personas) == 6
    assert len(plan.histories) == 6
    assert len(plan.cases) == 24
    assert sum(item.sentinel for item in plan.cases) == 6
    assert len({item.content_digest for item in (plan,)}) == 1


def test_packet_reverses_both_candidate_and_track_order() -> None:
    plan = build_persona_benchmark_plan()
    materials = build_reference_materials(plan)
    case = plan.cases[0]
    persona = plan.personas[0]
    selected = [item for item in materials if item.case_id == case.case_id]
    first, mapping_1 = build_judge_packet(
        seed=b"p" * 32,
        persona=persona,
        case=case,
        compiled=selected[0],
        comparator=selected[1],
        replicate=1,
    )
    second, mapping_2 = build_judge_packet(
        seed=b"p" * 32,
        persona=persona,
        case=case,
        compiled=selected[0],
        comparator=selected[1],
        replicate=2,
    )
    assert first.track_pairs[0].track is PersonaTrack.LEARNING_STATE
    assert second.track_pairs[0].track is PersonaTrack.TARGET_GUIDANCE
    for track in PersonaTrack:
        left = next(item for item in first.track_pairs if item.track is track)
        right = next(item for item in second.track_pairs if item.track is track)
        assert left.alternatives == tuple(reversed(right.alternatives))
    assert mapping_1 == mapping_2


def test_sentinel_refuses_static_comparator() -> None:
    plan = build_persona_benchmark_plan()
    materials = build_reference_materials(plan)
    case = next(item for item in plan.cases if item.sentinel)
    persona = next(item for item in plan.personas if item.persona_id == case.persona_id)
    compiled, sentinel = [item for item in materials if item.case_id == case.case_id]
    invalid = sentinel.model_copy(
        update={
            "condition": PersonaCondition.STRONG_STATIC,
            "independently_maintained": True,
        }
    )
    with pytest.raises(ValueError, match="controlled sentinel"):
        build_judge_packet(
            seed=b"s" * 32,
            persona=persona,
            case=case,
            compiled=compiled,
            comparator=invalid,
            replicate=1,
        )


def test_judge_binding_rejects_substitution() -> None:
    plan = build_persona_benchmark_plan()
    materials = build_reference_materials(plan)
    case = plan.cases[0]
    persona = plan.personas[0]
    compiled, comparator = [item for item in materials if item.case_id == case.case_id]
    packet, _ = build_judge_packet(
        seed=b"b" * 32,
        persona=persona,
        case=case,
        compiled=compiled,
        comparator=comparator,
        replicate=1,
    )
    decisions = tuple(
        PersonaTrackDecision(
            track=pair.track,
            ordered_alternative_ids=tuple(item.alternative_id for item in pair.alternatives),
            preference=PersonaPreference.FIRST,
            rationale="The first alternative follows the supplied persona and current scenario.",
        )
        for pair in packet.track_pairs
    )
    decision = PersonaJudgeDecision(
        packet_id=packet.packet_id,
        case_id=packet.case_id,
        persona_id=packet.persona_id,
        decisions=decisions,
        limitations=("This is a synthetic persona judgment.",),
    )
    assert validate_judge_decision(packet, decision) is decision
    with pytest.raises(ValueError, match="packet identity"):
        validate_judge_decision(packet, decision.model_copy(update={"persona_id": "other"}))


def test_vote_resolution_requires_majority() -> None:
    outcome = resolve_track_votes(
        case_id="case-1",
        track=PersonaTrack.TARGET_GUIDANCE,
        first=PersonaCondition.COMPILED,
        second=PersonaCondition.STRONG_STATIC,
        adjudicator=PersonaCondition.COMPILED,
    )
    assert outcome.adjudicated
    assert outcome.winning_condition is PersonaCondition.COMPILED
    unresolved = resolve_track_votes(
        case_id="case-2",
        track=PersonaTrack.TARGET_GUIDANCE,
        first=PersonaCondition.COMPILED,
        second=PersonaCondition.STRONG_STATIC,
    )
    assert unresolved.winning_condition is None


def test_schema_is_closed() -> None:
    schema = persona_judge_output_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["decisions", "limitations"]
    assert "packet_id" not in cast(dict[str, object], schema["properties"])


def test_material_rejects_oversized_projection() -> None:
    plan = build_persona_benchmark_plan()
    material = build_reference_materials(plan)[0]
    with pytest.raises(ValidationError, match="byte ceiling"):
        material.__class__(
            **{
                **material.model_dump(mode="python"),
                "target_guidance": "x" * 3001,
            }
        )
