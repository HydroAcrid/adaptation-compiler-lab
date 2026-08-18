from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32FinalizationAmendment,
    PersonaV32FinalizationInstrumentIncident,
    PersonaV32FinalReportV11,
    PersonaV32FinalReportV141,
    PersonaV32FrozenRescoreReport,
    PersonaV32ScoringAmendment,
    PersonaV32ScoringInstrumentIncident,
    strict_v32_scorer_failures,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "development_benchmark_persona_v32/tasks/tide-ledger-incident-transfer"
SCORER = ROOT / "scripts/score_compact_projection_task_v12.py"

_COMPILED_STYLE = """
def plan_transfer(destination_exists, retention_class, recovery_requested=False):
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError("unsupported retention class")
    if not destination_exists:
        return ("begin_capture", "confirm_result")
    if retention_class == "rebuildable_cache":
        return ("rebuild_cache", "confirm_result")
    recovery_step = ("save_recovery_point",) if recovery_requested else ()
    return recovery_step + (
        "inspect_api_health",
        "inspect_deployed_revision",
        "inspect_backlog_pressure",
        "replace_retained_tree",
        "confirm_result",
    )
"""

_STATIC_STYLE = """
def plan_transfer(destination_exists, retention_class, recovery_requested=False):
    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:
        raise ValueError("unsupported retention class")
    if not destination_exists:
        return ("begin_capture", "confirm_result")
    if retention_class == "rebuildable_cache":
        return ("rebuild_cache", "confirm_result")
    actions = []
    if recovery_requested:
        actions.append("save_recovery_point")
    actions.extend((
        "inspect_api_health",
        "inspect_deployed_revision",
        "inspect_backlog_pressure",
    ))
    actions.extend(("replace_retained_tree", "confirm_result"))
    return tuple(actions)
"""


def _score_source(tmp_path: Path, source: str) -> dict[str, object]:
    workspace = tmp_path / "workspace"
    shutil.copytree(TASK / "fixture", workspace)
    (workspace / "src/transfer_policy.py").write_text(source, encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCORER),
            "--task-manifest",
            str(TASK / "task.json"),
            "--workspace",
            str(workspace),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


def test_v32_repaired_observer_accepts_both_frozen_capability_free_styles(
    tmp_path: Path,
) -> None:
    for index, source in enumerate((_COMPILED_STYLE, _STATIC_STYLE)):
        score = _score_source(tmp_path / str(index), source)

        assert strict_v32_scorer_failures(score) == ()
        checks = cast(Mapping[str, Mapping[str, bool]], score["checks"])
        assert all(
            passed is True for group_checks in checks.values() for passed in group_checks.values()
        )


def test_v32_repaired_observer_still_detects_wrong_behavior(tmp_path: Path) -> None:
    wrong = _COMPILED_STYLE.replace(
        '"inspect_deployed_revision",\n        "inspect_backlog_pressure",',
        '"inspect_backlog_pressure",\n        "inspect_deployed_revision",',
    )
    score = _score_source(tmp_path, wrong)

    assert strict_v32_scorer_failures(score)
    checks = cast(Mapping[str, Mapping[str, bool]], score["checks"])
    assert any(
        passed is False for group_checks in checks.values() for passed in group_checks.values()
    )


def test_v32_repaired_observer_still_rejects_host_capabilities(tmp_path: Path) -> None:
    hostile = """
def plan_transfer(destination_exists, retention_class, recovery_requested=False):
    open("/etc/passwd")
    return ("begin_capture", "confirm_result")
"""
    score = _score_source(tmp_path, hostile)

    assert strict_v32_scorer_failures(score)
    checks = cast(Mapping[str, Mapping[str, bool]], score["checks"])
    assert all(
        passed is False for group_checks in checks.values() for passed in group_checks.values()
    )


def test_v32_strict_gate_rejects_false_checks_even_when_receipts_succeed() -> None:
    score: dict[str, object] = {
        "checks": {
            "objective": {"scenario": False},
            "diagnostic": {"scenario": True},
            "neutral": {"scenario": True},
        },
        "receipts": {"scenario": {"status": "succeeded"}},
    }

    assert strict_v32_scorer_failures(score) == ("automated check failed for objective/scenario",)


def test_v32_corrected_final_report_binds_json_shaped_lists_strictly() -> None:
    original = PersonaV32FinalReportV11.model_validate_json(
        (ROOT / "development_benchmark_persona_v32/FINAL-REPORT-v1.json").read_bytes()
    )
    values = original.model_dump(mode="json", round_trip=True)
    digest = "sha256:" + "0" * 64
    values.update(
        {
            "amendment_version": "1.4.1",
            "finalization_amendment_digest": digest,
            "finalization_incident_digest": digest,
            "frozen_rescore_report_digest": digest,
            "invalidated_final_report_digest": digest,
            "original_final_report_invalidated": True,
            "post_unblind_instrument_repair": True,
            "scoring_amendment_digest": digest,
            "scoring_incident_digest": digest,
        }
    )

    report = PersonaV32FinalReportV141.model_validate_json(canonical_json(values))

    assert report.amendment_version == "1.4.1"
    assert isinstance(report.task_outcomes, tuple)


def test_v32_actual_scoring_repair_chain_is_bound_and_complete() -> None:
    benchmark = ROOT / "development_benchmark_persona_v32"
    incident = PersonaV32ScoringInstrumentIncident.model_validate_json(
        (benchmark / "SCORING-INSTRUMENT-INCIDENT-002.json").read_bytes()
    )
    amendment = PersonaV32ScoringAmendment.model_validate_json(
        (benchmark / "SCORING-AMENDMENT-v1.4.json").read_bytes()
    )
    rescore_path = benchmark / "FROZEN-RESCORE-v1.4.json"
    rescore = PersonaV32FrozenRescoreReport.model_validate_json(rescore_path.read_bytes())
    finalization_incident = PersonaV32FinalizationInstrumentIncident.model_validate_json(
        (benchmark / "FINALIZATION-INSTRUMENT-INCIDENT-003.json").read_bytes()
    )
    finalization_amendment = PersonaV32FinalizationAmendment.model_validate_json(
        (benchmark / "FINALIZATION-AMENDMENT-v1.4.1.json").read_bytes()
    )
    final = PersonaV32FinalReportV141.model_validate_json(
        (benchmark / "FINAL-REPORT-v1.4.1.json").read_bytes()
    )

    assert amendment.incident_digest == canonical_digest(incident)
    assert rescore.scoring_amendment_digest == canonical_digest(amendment)
    assert finalization_incident.frozen_rescore_report_digest == sha256_file(rescore_path)
    assert finalization_amendment.incident_digest == canonical_digest(finalization_incident)
    assert final.finalization_amendment_digest == canonical_digest(finalization_amendment)
    assert rescore.all_check_totals_passed is True
    assert final.behavioral_gate_passed is True
    assert final.permitted_claim == "fresh_canary_compiled_matched_static"
    assert all(
        outcome.compiled_checks_passed == outcome.static_checks_passed == outcome.checks_total == 8
        for outcome in final.task_outcomes
    )
