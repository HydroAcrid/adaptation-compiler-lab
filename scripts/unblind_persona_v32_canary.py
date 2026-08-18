"""Unblind completed v3.2 evidence and emit the bounded final claim."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32ConstructionReport,
    PersonaV32Fixture,
    PersonaV32JudgeDecision,
    PersonaV32Oracle,
    PersonaV32TaskOutcome,
    PersonaV32TrialReceipt,
    build_v32_plan,
)
from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32ConstructionAdjudication,
    PersonaV32FinalReportV11,
    PersonaV32MaterialsFreezeV11,
    PersonaV321Protocol,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _winner(
    compiled: PersonaV32TrialReceipt, static: PersonaV32TrialReceipt
) -> Literal["compiled_adaptation", "strong_static_profile", "tie"]:
    if compiled.behavior_conformant != static.behavior_conformant:
        return "compiled_adaptation" if compiled.behavior_conformant else "strong_static_profile"
    compiled_checks = _checks(compiled)
    static_checks = _checks(static)
    if compiled_checks == static_checks:
        return "tie"
    return "compiled_adaptation" if compiled_checks > static_checks else "strong_static_profile"


def _checks(receipt: PersonaV32TrialReceipt) -> int:
    value = receipt.observation
    return (
        value.objective_checks_passed + value.diagnostic_checks_passed + value.neutral_checks_passed
    )


def _total(receipt: PersonaV32TrialReceipt) -> int:
    value = receipt.observation
    return value.objective_checks_total + value.diagnostic_checks_total + value.neutral_checks_total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_v32"
    seed_path = args.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("v3.2 unblind seed location or permissions are unsafe")
    original_protocol_digest = canonical_digest(
        json.loads((root / "PROTOCOL-v3.2.json").read_text(encoding="utf-8"))
    )
    original_freeze_digest = canonical_digest(
        json.loads((root / "FREEZE-v1.json").read_text(encoding="utf-8"))
    )
    protocol = PersonaV321Protocol.model_validate_json((root / "PROTOCOL-v3.2.1.json").read_bytes())
    fixture = PersonaV32Fixture.model_validate_json((root / "FIXTURE-v1.json").read_bytes())
    oracle = PersonaV32Oracle.model_validate_json((root / "ORACLE-v1.1.json").read_bytes())
    construction = PersonaV32ConstructionReport.model_validate_json(
        (root / "construction-results-v1/CONSTRUCTION-REPORT-v1.json").read_bytes()
    )
    adjudication = PersonaV32ConstructionAdjudication.model_validate_json(
        (root / "CONSTRUCTION-ADJUDICATION-v1.1.json").read_bytes()
    )
    materials = PersonaV32MaterialsFreezeV11.model_validate_json(
        (root / "MATERIALS-FREEZE-v1.1.json").read_bytes()
    )
    if materials.successor_protocol_digest != canonical_digest(protocol):
        raise RuntimeError("v3.2 successor protocol drifted before unblinding")
    if materials.construction_adjudication_digest != canonical_digest(adjudication):
        raise RuntimeError("v3.2 adjudication drifted before unblinding")
    if materials.unblinder_digest != sha256_file(Path(__file__)):
        raise RuntimeError("v3.2 unblinder drifted after material freeze")
    public, private = build_v32_plan(fixture=fixture, seed=seed_path.read_bytes())
    blind_path = root / "target-results-v1/BLIND-REPORT-v1.json"
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    trials = tuple(
        PersonaV32TrialReceipt.model_validate(item)
        for item in cast(list[dict[str, object]], blind["trials"])
    )
    trial_by_output = {item.observation.blind_output_id: item for item in trials}
    condition_by_output = {
        str(cell["blind_output_id"]): str(cell["condition"])
        for cell in cast(list[dict[str, object]], private["run_order"])
    }
    tasks = {item.task_id: item for item in fixture.tasks}
    outcomes = []
    judge_digests = []
    for task_id in sorted(tasks):
        pair = tuple(cell.blind_output_id for cell in public.run_order if cell.task_id == task_id)
        by_condition = {
            condition_by_output[output_id]: trial_by_output[output_id] for output_id in pair
        }
        compiled = by_condition["compiled_adaptation"]
        static = by_condition["strong_static_profile"]
        judge_path = root / f"judge-results-v1/JUDGE-{task_id}-v1.json"
        judge_value = json.loads(judge_path.read_text(encoding="utf-8"))
        decision = PersonaV32JudgeDecision.model_validate(judge_value["decision"])
        preferred = decision.rating.preferred_output_id
        judge_winner = cast(
            Literal["compiled_adaptation", "strong_static_profile", "tie"],
            "tie" if preferred is None else condition_by_output[preferred],
        )
        outcomes.append(
            PersonaV32TaskOutcome(
                task_id=task_id,
                applicable_adaptation=tasks[task_id].applicable_adaptation,
                compiled_output_id=compiled.observation.blind_output_id,
                static_output_id=static.observation.blind_output_id,
                compiled_behavior_conformant=compiled.behavior_conformant,
                static_behavior_conformant=static.behavior_conformant,
                compiled_checks_passed=_checks(compiled),
                static_checks_passed=_checks(static),
                checks_total=_total(compiled),
                automated_winner=_winner(compiled, static),
                judge_winner=judge_winner,
            )
        )
        judge_digests.append(sha256_file(judge_path))
    outcomes_tuple = tuple(outcomes)
    instrument_valid = bool(blind["instrument_valid"]) and all(
        item.integrity_valid for item in trials
    )
    construction_exact = adjudication.corrected_construction_exact
    compiled_trials = tuple(
        item
        for item in trials
        if condition_by_output[item.observation.blind_output_id] == "compiled_adaptation"
    )
    compiled_not_worse = all(
        item.automated_winner != "strong_static_profile" for item in outcomes_tuple
    )
    compiled_false_activation = sum(
        not item.behavior_conformant
        for item in compiled_trials
        if not tasks[item.observation.task_id].applicable_adaptation
    )
    static_false_activation = sum(
        not item.behavior_conformant
        for item in trials
        if condition_by_output[item.observation.blind_output_id] == "strong_static_profile"
        and not tasks[item.observation.task_id].applicable_adaptation
    )
    gate = (
        instrument_valid
        and construction_exact
        and all(item.behavior_conformant for item in compiled_trials)
        and compiled_not_worse
        and compiled_false_activation == 0
    )
    claim: Literal[
        "fresh_canary_compiled_outperformed",
        "fresh_canary_compiled_matched_static",
        "product_gate_failed",
        "instrumentation_failure",
    ]
    if not instrument_valid:
        claim = "instrumentation_failure"
    elif not gate:
        claim = "product_gate_failed"
    elif any(item.automated_winner == "compiled_adaptation" for item in outcomes_tuple):
        claim = "fresh_canary_compiled_outperformed"
    else:
        claim = "fresh_canary_compiled_matched_static"
    report = PersonaV32FinalReportV11(
        protocol_digest=canonical_digest(protocol),
        original_protocol_digest=original_protocol_digest,
        original_freeze_digest=original_freeze_digest,
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        corrected_oracle_digest=canonical_digest(oracle),
        construction_adjudication_digest=canonical_digest(adjudication),
        construction_report_digest=canonical_digest(construction),
        materials_freeze_digest=canonical_digest(materials),
        public_plan_digest=public.content_digest,
        target_blind_report_digest=sha256_file(blind_path),
        judge_receipt_digests=(judge_digests[0], judge_digests[1]),
        task_outcomes=(outcomes_tuple[0], outcomes_tuple[1]),
        instrument_valid=instrument_valid,
        construction_exact=construction_exact,
        compiled_false_activation_count=compiled_false_activation,
        static_false_activation_count=static_false_activation,
        behavioral_gate_passed=gate,
        permitted_claim=claim,
    )
    path = root / "FINAL-REPORT-v1.json"
    payload = (canonical_json(report.model_dump(mode="json", round_trip=True)) + "\n").encode()
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError("v3.2 final report drifted")
    else:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    print(canonical_json(report.model_dump(mode="json", round_trip=True)))


if __name__ == "__main__":
    main()
