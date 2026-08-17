"""Unblind completed persona judgments and emit the raw-free development report."""

from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaCondition,
    PersonaConditionMaterial,
    PersonaEvaluationReport,
    PersonaJudgeDecision,
    PersonaTrack,
    resolve_track_votes,
)
from adaptation_compiler_lab.benchmark.persona_fixture import build_persona_benchmark_plan
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _decision(path: Path) -> PersonaJudgeDecision:
    return PersonaJudgeDecision.model_validate_json(path.read_bytes())


def _preferred(decision: PersonaJudgeDecision, track: PersonaTrack) -> str | None:
    return next(item for item in decision.decisions if item.track is track).preferred_alternative_id


def _vote(
    decision: PersonaJudgeDecision,
    track: PersonaTrack,
    mapping: dict[str, str],
) -> PersonaCondition | None:
    preferred = _preferred(decision, track)
    return None if preferred is None else PersonaCondition(mapping[preferred])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--private-mapping", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_evaluation"
    output = root / "RESULT-v1.json"
    if output.exists():
        raise RuntimeError("persona result already exists")
    private = json.loads(args.private_mapping.read_text(encoding="utf-8"))
    mappings: dict[str, dict[str, str]] = private["mappings"]
    plan = build_persona_benchmark_plan()
    materials_document = json.loads((root / "MATERIALS-v1.json").read_text(encoding="utf-8"))
    materials = tuple(
        PersonaConditionMaterial.model_validate_json(json.dumps(item))
        for item in materials_document["materials"]
    )
    outcomes = []
    agreement = {track: 0 for track in PersonaTrack}
    adjudicated_cases = 0
    sentinel_correct = {track: 0 for track in PersonaTrack}
    wins = {
        track: {PersonaCondition.COMPILED: 0, PersonaCondition.STRONG_STATIC: 0}
        for track in PersonaTrack
    }
    for case in plan.cases:
        first_path = root / f"judge-results/{case.case_id}-r1.decision.json"
        second_path = root / f"judge-results/{case.case_id}-r2.decision.json"
        first = _decision(first_path)
        second = _decision(second_path)
        mapping = mappings[f"{case.case_id}-r1.json"]
        needs_adjudication = any(
            _preferred(first, track) != _preferred(second, track) for track in PersonaTrack
        )
        adjudicator = None
        if needs_adjudication:
            adjudicated_cases += 1
            adjudicator = _decision(root / f"adjudicator-results/{case.case_id}.decision.json")
        for track in PersonaTrack:
            first_vote = _vote(first, track, mapping)
            second_vote = _vote(second, track, mapping)
            if first_vote == second_vote:
                agreement[track] += 1
            third_vote = None if adjudicator is None else _vote(adjudicator, track, mapping)
            outcome = resolve_track_votes(
                case_id=case.case_id,
                track=track,
                first=first_vote,
                second=second_vote,
                adjudicator=third_vote,
            )
            outcomes.append(outcome)
            if case.sentinel and outcome.winning_condition is PersonaCondition.COMPILED:
                sentinel_correct[track] += 1
            if not case.sentinel and outcome.winning_condition in wins[track]:
                wins[track][outcome.winning_condition] += 1
    agreement_rates = {track: agreement[track] / 24 for track in PersonaTrack}
    adjudication_rate = adjudicated_cases / 24
    instrument_valid = (
        all(sentinel_correct[track] == 6 for track in PersonaTrack)
        and all(agreement_rates[track] >= 0.75 for track in PersonaTrack)
        and adjudication_rate <= 0.25
    )
    compiled = tuple(item for item in materials if item.condition is PersonaCondition.COMPILED)
    static = tuple(item for item in materials if item.condition is PersonaCondition.STRONG_STATIC)
    case_by_id = {item.case_id: item for item in plan.cases}
    false_activations = sum(
        bool(item.active_trait_ids) for item in compiled if case_by_id[item.case_id].sentinel
    )
    lifecycle_leaks = sum(
        bool(set(item.active_trait_ids) & set(case_by_id[item.case_id].forbidden_trait_ids))
        for item in compiled
    )
    compiled_bytes = tuple(len(item.target_guidance.encode("utf-8")) for item in compiled)
    static_bytes = tuple(len(item.target_guidance.encode("utf-8")) for item in static)
    lineage_complete = all(
        item.evidence_digest.startswith("sha256:")
        and item.active_trait_ids == case_by_id[item.case_id].expected_active_trait_ids
        for item in compiled
    )
    if not instrument_valid:
        interpretation: Literal[
            "instrument_failure",
            "compiled_negative",
            "compiled_directional_tie",
            "compiled_directional_positive",
        ] = "instrument_failure"
    elif all(
        wins[track][PersonaCondition.COMPILED] > wins[track][PersonaCondition.STRONG_STATIC]
        for track in PersonaTrack
    ):
        interpretation = "compiled_directional_positive"
    elif all(
        wins[track][PersonaCondition.COMPILED] >= wins[track][PersonaCondition.STRONG_STATIC]
        for track in PersonaTrack
    ):
        interpretation = "compiled_directional_tie"
    else:
        interpretation = "compiled_negative"
    report = PersonaEvaluationReport(
        benchmark_id=plan.benchmark_id,
        plan_digest=plan.content_digest,
        xhigh_session_count=54,
        max_session_count=adjudicated_cases,
        luna_session_count=0,
        total_session_count=54 + adjudicated_cases,
        outcomes=tuple(outcomes),
        sentinel_learning_correct=sentinel_correct[PersonaTrack.LEARNING_STATE],
        sentinel_guidance_correct=sentinel_correct[PersonaTrack.TARGET_GUIDANCE],
        learning_agreement_rate=agreement_rates[PersonaTrack.LEARNING_STATE],
        guidance_agreement_rate=agreement_rates[PersonaTrack.TARGET_GUIDANCE],
        adjudication_rate=adjudication_rate,
        instrument_valid=instrument_valid,
        compiled_lineage_complete=lineage_complete,
        false_activation_count=false_activations,
        revoked_or_superseded_leak_count=lifecycle_leaks,
        compiled_max_bytes=max(compiled_bytes),
        compiled_median_bytes=statistics.median(compiled_bytes),
        static_median_bytes=statistics.median(static_bytes),
        interpretation=interpretation,
    )
    _exclusive_write(output, (canonical_json(report) + "\n").encode("utf-8"))
    _exclusive_write(
        root / "CONDITION-SUMMARY-v1.json",
        (
            canonical_json(
                {
                    "adjudicated_case_count": adjudicated_cases,
                    "comparison_case_count": 18,
                    "guidance_wins": {
                        key.value: value
                        for key, value in wins[PersonaTrack.TARGET_GUIDANCE].items()
                    },
                    "learning_wins": {
                        key.value: value for key, value in wins[PersonaTrack.LEARNING_STATE].items()
                    },
                    "ties_or_unresolved_are_not_counted_as_wins": True,
                }
            )
            + "\n"
        ).encode("utf-8"),
    )
    print(canonical_json(report))


if __name__ == "__main__":
    main()
