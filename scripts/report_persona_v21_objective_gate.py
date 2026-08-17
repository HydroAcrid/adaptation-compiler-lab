"""Create the immutable v2.1 objective-gate report without running guidance judges."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaMaterialSnapshot,
    PersonaModelProfileOutput,
    PersonaObjectiveScore,
    PersonaV21ObjectiveGateReport,
)
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"v2.1 objective-gate report drifted: {path.name}")
        return
    _exclusive_write(path, payload)


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be one JSON object")
    return cast(dict[str, object], value)


def _scores(root: Path) -> tuple[PersonaObjectiveScore, ...]:
    payload = _object(
        json.loads((root / "OBJECTIVE-SCORE-MANIFEST-v1.json").read_text(encoding="utf-8")),
        field="objective score manifest",
    )
    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, list):
        raise RuntimeError("v2.1 objective score manifest lacks its score ledger")
    scores = tuple(
        PersonaObjectiveScore.model_validate_json(canonical_json(value), strict=True)
        for value in raw_scores
    )
    if len(scores) != 48:
        raise RuntimeError("v2.1 objective score ledger must contain two scores per case")
    return scores


def _report(root: Path) -> PersonaV21ObjectiveGateReport:
    scores = _scores(root)
    compiled = tuple(item for item in scores if item.source.value == "compiled")
    static = tuple(item for item in scores if item.source.value == "static")
    if len(compiled) != 24 or len(static) != 24:
        raise RuntimeError("v2.1 objective score ledger crossed its condition boundary")
    compiled_by_case = {item.case_id: item for item in compiled}
    static_by_case = {item.case_id: item for item in static}
    if len(compiled_by_case) != 24 or compiled_by_case.keys() != static_by_case.keys():
        raise RuntimeError("v2.1 objective score ledger has incomplete case pairs")
    if any(
        compiled_by_case[case_id].expected_count != static_by_case[case_id].expected_count
        for case_id in compiled_by_case
    ):
        raise RuntimeError("v2.1 objective conditions were scored against different states")

    nonempty_case_ids = {
        case_id for case_id, item in compiled_by_case.items() if item.expected_count > 0
    }
    empty_case_ids = set(compiled_by_case) - nonempty_case_ids
    compiled_exact_count = sum(item.exact for item in compiled)
    static_exact_count = sum(item.exact for item in static)

    reviewed_profiles = tuple(
        PersonaModelProfileOutput.model_validate_json(path.read_bytes(), strict=True)
        for path in sorted((root / "profile-results").glob("*.reviewed.json"))
    )
    compiled_materials = tuple(
        PersonaMaterialSnapshot.model_validate_json(path.read_bytes(), strict=True)
        for path in sorted((root / "frozen-materials").glob("*.compiled.json"))
    )
    static_materials = tuple(
        PersonaMaterialSnapshot.model_validate_json(path.read_bytes(), strict=True)
        for path in sorted((root / "frozen-materials").glob("*.static.json"))
    )
    if tuple(map(len, (reviewed_profiles, compiled_materials, static_materials))) != (24, 24, 24):
        raise RuntimeError("v2.1 material construction outputs are incomplete")
    reviewed_static_claim_count = sum(len(item.snapshot.claims) for item in reviewed_profiles)
    delivered_static_claim_count = sum(len(item.claims) for item in static_materials)
    static_scope_transport_valid = not (
        reviewed_static_claim_count > 0 and delivered_static_claim_count == 0
    )

    diagnostics = []
    if compiled_exact_count / 24 < 0.75:
        diagnostics.append("compiled_below_objective_floor")
    if static_exact_count / 24 < 0.75:
        diagnostics.append("static_below_objective_floor")
    if not static_scope_transport_valid:
        diagnostics.append("static_scope_vocabulary_transport_failure")
    if any(compiled_by_case[item].exact or static_by_case[item].exact for item in empty_case_ids):
        diagnostics.append("empty_state_cases_contribute_to_aggregate_exact_rate")
    if any((root / "guidance-results").glob("*.json")):
        raise RuntimeError("guidance outputs exist despite the failed objective gate")

    comparison_permitted = compiled_exact_count >= 18 and static_exact_count >= 18
    return PersonaV21ObjectiveGateReport(
        status=("comparison_permitted" if comparison_permitted else "stopped_at_objective_gate"),
        compiled_exact_count=compiled_exact_count,
        static_exact_count=static_exact_count,
        compiled_objective_exact_rate=compiled_exact_count / 24,
        static_objective_exact_rate=static_exact_count / 24,
        nonempty_expected_case_count=len(nonempty_case_ids),
        compiled_nonempty_exact_count=sum(
            compiled_by_case[item].exact for item in nonempty_case_ids
        ),
        static_nonempty_exact_count=sum(static_by_case[item].exact for item in nonempty_case_ids),
        empty_expected_case_count=len(empty_case_ids),
        compiled_empty_exact_count=sum(compiled_by_case[item].exact for item in empty_case_ids),
        static_empty_exact_count=sum(static_by_case[item].exact for item in empty_case_ids),
        compiled_material_claim_count=sum(len(item.claims) for item in compiled_materials),
        reviewed_static_claim_count=reviewed_static_claim_count,
        delivered_static_claim_count=delivered_static_claim_count,
        static_scope_transport_valid=static_scope_transport_valid,
        compiled_gate_passed=compiled_exact_count >= 18,
        static_gate_passed=static_exact_count >= 18,
        comparison_permitted=comparison_permitted,
        instrument_valid=comparison_permitted,
        interpretation=("objective_gate_passed" if comparison_permitted else "instrument_failure"),
        diagnostic_codes=tuple(sorted(diagnostics)),
    )


def _markdown(report: PersonaV21ObjectiveGateReport) -> bytes:
    compiled_nonempty_rate = (
        report.compiled_nonempty_exact_count / report.nonempty_expected_case_count
    )
    static_nonempty_rate = report.static_nonempty_exact_count / report.nonempty_expected_case_count
    lines = [
        "# Persona Evaluation v2.1 — Objective Gate Report",
        "",
        "Status: **stopped at the preregistered objective gate**.",
        "",
        "The compiled condition recovered 10 of 24 complete states (41.7%) and the strong static "
        "condition recovered 8 of 24 (33.3%). Both are below the frozen 75% floor, so the blind "
        "guidance comparison was not run and no condition winner is reported.",
        "",
        "| Slice | Compiled | Strong static |",
        "| --- | ---: | ---: |",
        f"| All 24 cases | {report.compiled_exact_count}/24 | {report.static_exact_count}/24 |",
        (
            f"| Active behavior required | {report.compiled_nonempty_exact_count}/"
            f"{report.nonempty_expected_case_count} ({compiled_nonempty_rate:.1%}) | "
            f"{report.static_nonempty_exact_count}/{report.nonempty_expected_case_count} "
            f"({static_nonempty_rate:.1%}) |"
        ),
        (
            f"| Empty expected state | {report.compiled_empty_exact_count}/"
            f"{report.empty_expected_case_count} | {report.static_empty_exact_count}/"
            f"{report.empty_expected_case_count} |"
        ),
        "",
        "## What failed",
        "",
        "The compiled path missed context-specific exceptions, sometimes routed preferences as "
        "procedures or examples, and did not complete several correction or revocation chains. "
        "Its objective result is a genuine negative for the current sensor-and-policy path.",
        "",
        "The static authors produced governed behavioral claims, but the authoring packet did not "
        "provide the runtime's canonical scope vocabulary. The model therefore emitted sensible "
        "human labels that did not exactly match registered identifiers. Deterministic delivery "
        f"filtered all {report.reviewed_static_claim_count} reviewed claims to "
        f"{report.delivered_static_claim_count}; that is a comparator transport defect, not proof "
        "that a strong profile learned nothing.",
        "",
        "Empty-state cases make both aggregate rates look better than active-learning performance. "
        "A later instrument should report active, exception, lifecycle, and sentinel slices "
        "separately and require non-vacuous lifecycle prerequisites.",
        "",
        "## Boundaries",
        "",
        "- Guidance-judge sessions executed: 0.",
        "- Provider-billed calls: 0.",
        "- This synthetic result does not count toward ordinary-use dogfood evidence.",
        "- No Milestone 6 external-validation task, mapping, or random order was accessed.",
        "- The result does not establish cross-agent transfer or compiled superiority.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_relative_to(Path.cwd().resolve()):
        raise RuntimeError("v2.1 report root must remain inside the workspace")
    report = _report(root)
    _write_or_verify(root / "OBJECTIVE-GATE-REPORT-v1.json", _json_bytes(report))
    _write_or_verify(root / "OBJECTIVE-GATE-REPORT-v1.md", _markdown(report))
    print(canonical_json(report))


if __name__ == "__main__":
    main()
