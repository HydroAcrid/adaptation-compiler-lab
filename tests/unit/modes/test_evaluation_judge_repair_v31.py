"""Custody tests for the judge-only Mode evaluation v3.1 repair."""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptation_compiler_lab.serialization import canonical_digest
from scripts.mode_evaluation_v31_judge_common import (
    load_object,
    require_valid_trace_smoke,
    validate_repair_sources,
)

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "development_benchmark_mode_evaluation"


def test_v31_repair_binds_the_unchanged_blind_target_report() -> None:
    repair = validate_repair_sources(ROOT)
    report = load_object(BENCHMARK / "results-v3/blind-trial-report.json")
    completion = load_object(BENCHMARK / "results-v3/completion.json")

    assert repair["blind_report_digest"] == completion["report_digest"]
    assert completion["report_digest"] == canonical_digest(report)
    assert report["unblinded"] is False
    assert repair["target_grid_reexecution_allowed"] is False


def test_v31_repair_accepts_only_one_notice_and_still_forbids_tools() -> None:
    protocol = load_object(BENCHMARK / "JUDGE_REPAIR_PROTOCOL-v3.1.json")
    notice = protocol["accepted_notice"]

    assert isinstance(notice, str) and notice.startswith("Code Mode is unavailable")
    assert protocol["tool_events_remain_forbidden"] is True
    assert protocol["trace_smoke_required"] is True
    assert protocol["judge_sessions_required"] == 3


def test_v31_judging_fails_closed_without_its_trace_smoke(tmp_path: Path) -> None:
    repair = validate_repair_sources(ROOT)

    with pytest.raises(RuntimeError, match=r"invalid Mode judge v3\.1 file"):
        require_valid_trace_smoke(tmp_path, repair_contract=repair)


def test_v31_has_not_unblinded_before_judging() -> None:
    assert not (BENCHMARK / "results-v3/unblinded-result-v31.json").exists()
    assert not (BENCHMARK / "results-v3/MODE_EVALUATION_RESULT-v31.md").exists()
