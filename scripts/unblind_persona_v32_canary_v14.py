"""Issue a corrected v3.2 final report from exact frozen-output rescoring."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.benchmark.persona_v32 import PersonaV32TaskOutcome
from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32FinalizationAmendment,
    PersonaV32FinalizationInstrumentIncident,
    PersonaV32FinalReportV11,
    PersonaV32FinalReportV141,
    PersonaV32FrozenRescoreReport,
    PersonaV32ScoringAmendment,
    PersonaV32ScoringInstrumentIncident,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _winner(
    compiled_passed: int,
    static_passed: int,
) -> Literal["compiled_adaptation", "strong_static_profile", "tie"]:
    if compiled_passed == static_passed:
        return "tie"
    return "compiled_adaptation" if compiled_passed > static_passed else "strong_static_profile"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_v32"
    original_path = root / "FINAL-REPORT-v1.json"
    incident_path = root / "SCORING-INSTRUMENT-INCIDENT-002.json"
    amendment_path = root / "SCORING-AMENDMENT-v1.4.json"
    rescore_path = root / "FROZEN-RESCORE-v1.4.json"
    finalization_incident_path = root / "FINALIZATION-INSTRUMENT-INCIDENT-003.json"
    finalization_amendment_path = root / "FINALIZATION-AMENDMENT-v1.4.1.json"
    original = PersonaV32FinalReportV11.model_validate_json(original_path.read_bytes())
    incident = PersonaV32ScoringInstrumentIncident.model_validate_json(incident_path.read_bytes())
    amendment = PersonaV32ScoringAmendment.model_validate_json(amendment_path.read_bytes())
    rescore = PersonaV32FrozenRescoreReport.model_validate_json(rescore_path.read_bytes())
    finalization_incident = PersonaV32FinalizationInstrumentIncident.model_validate_json(
        finalization_incident_path.read_bytes()
    )
    finalization_amendment = PersonaV32FinalizationAmendment.model_validate_json(
        finalization_amendment_path.read_bytes()
    )
    if finalization_amendment.amended_unblinder_digest != sha256_file(Path(__file__)):
        raise RuntimeError("v3.2 corrected unblinder drifted after amendment")
    if incident.original_final_report_digest != canonical_digest(original):
        raise RuntimeError("v3.2 incident is not bound to the invalid report")
    if amendment.incident_digest != canonical_digest(incident):
        raise RuntimeError("v3.2 scoring amendment is not bound to its incident")
    if rescore.scoring_amendment_digest != canonical_digest(amendment):
        raise RuntimeError("v3.2 rescore is not bound to the scoring amendment")
    if finalization_incident.frozen_rescore_report_digest != sha256_file(rescore_path):
        raise RuntimeError("v3.2 finalization incident is not bound to the frozen rescore")
    if finalization_amendment.incident_digest != canonical_digest(finalization_incident):
        raise RuntimeError("v3.2 finalization amendment is not bound to its incident")
    rescored = {item.blind_output_id: item for item in rescore.trials}
    outcomes = []
    for outcome in original.task_outcomes:
        compiled = rescored[outcome.compiled_output_id]
        static = rescored[outcome.static_output_id]
        compiled_passed = (
            compiled.objective_checks_passed
            + compiled.diagnostic_checks_passed
            + compiled.neutral_checks_passed
        )
        static_passed = (
            static.objective_checks_passed
            + static.diagnostic_checks_passed
            + static.neutral_checks_passed
        )
        total = (
            compiled.objective_checks_total
            + compiled.diagnostic_checks_total
            + compiled.neutral_checks_total
        )
        outcomes.append(
            PersonaV32TaskOutcome(
                task_id=outcome.task_id,
                applicable_adaptation=outcome.applicable_adaptation,
                compiled_output_id=outcome.compiled_output_id,
                static_output_id=outcome.static_output_id,
                compiled_behavior_conformant=compiled.behavior_conformant,
                static_behavior_conformant=static.behavior_conformant,
                compiled_checks_passed=compiled_passed,
                static_checks_passed=static_passed,
                checks_total=total,
                automated_winner=_winner(compiled_passed, static_passed),
                judge_winner=outcome.judge_winner,
            )
        )
    compiled_false_activation = sum(
        not item.compiled_behavior_conformant for item in outcomes if not item.applicable_adaptation
    )
    static_false_activation = sum(
        not item.static_behavior_conformant for item in outcomes if not item.applicable_adaptation
    )
    instrument_valid = rescore.all_observer_receipts_succeeded
    compiled_complete = all(
        item.compiled_behavior_conformant and item.compiled_checks_passed == item.checks_total
        for item in outcomes
    )
    compiled_not_worse = all(item.automated_winner != "strong_static_profile" for item in outcomes)
    gate = (
        instrument_valid
        and original.construction_exact
        and compiled_complete
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
    elif any(item.automated_winner == "compiled_adaptation" for item in outcomes):
        claim = "fresh_canary_compiled_outperformed"
    else:
        claim = "fresh_canary_compiled_matched_static"
    values = original.model_dump(mode="json", round_trip=True)
    values.update(
        {
            "amendment_version": "1.4.1",
            "behavioral_gate_passed": gate,
            "compiled_false_activation_count": compiled_false_activation,
            "frozen_rescore_report_digest": sha256_file(rescore_path),
            "finalization_amendment_digest": canonical_digest(finalization_amendment),
            "finalization_incident_digest": canonical_digest(finalization_incident),
            "instrument_valid": instrument_valid,
            "invalidated_final_report_digest": canonical_digest(original),
            "original_final_report_invalidated": True,
            "permitted_claim": claim,
            "post_unblind_instrument_repair": True,
            "scoring_amendment_digest": canonical_digest(amendment),
            "scoring_incident_digest": canonical_digest(incident),
            "static_false_activation_count": static_false_activation,
            "task_outcomes": [item.model_dump(mode="json", round_trip=True) for item in outcomes],
        }
    )
    report = PersonaV32FinalReportV141.model_validate_json(canonical_json(values))
    path = root / "FINAL-REPORT-v1.4.1.json"
    payload = (canonical_json(report.model_dump(mode="json", round_trip=True)) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    print(canonical_json(report.model_dump(mode="json", round_trip=True)))


if __name__ == "__main__":
    main()
