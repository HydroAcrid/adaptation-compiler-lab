"""Freeze the Mode evaluation v3.1 judge-only repair before its trace smoke."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.modes.evaluation import load_mode_evaluation_contract
from adaptation_compiler_lab.runners.codex_mode_judge_v31 import CODE_MODE_DISABLED_NOTICE
from adaptation_compiler_lab.serialization import canonical_digest
from scripts.mode_evaluation_v31_judge_common import (
    load_object,
    repair_source_digests,
    write_new,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    protocol = load_object(benchmark / "JUDGE_REPAIR_PROTOCOL-v3.1.json")
    if (
        protocol.get("accepted_notice") != CODE_MODE_DISABLED_NOTICE
        or protocol.get("blind_report_digest")
        != "sha256:09218344b7f8c12aab6eb07defa53c70f843a97fe826477177ebe3d271fdf097"
        or protocol.get("condition_mapping_revealed") is not False
        or protocol.get("target_grid_reexecution_allowed") is not False
        or protocol.get("tool_events_remain_forbidden") is not True
        or protocol.get("trace_smoke_required") is not True
        or protocol.get("judge_sessions_required") != 3
    ):
        raise RuntimeError("Mode judge v3.1 repair protocol is invalid")
    target_contract = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v3.json")
    blind_report = load_object(benchmark / "results-v3/blind-trial-report.json")
    completion = load_object(benchmark / "results-v3/completion.json")
    if (
        completion.get("report_digest") != protocol["blind_report_digest"]
        or completion.get("report_digest") != canonical_digest(blind_report)
        or blind_report.get("unblinded") is not False
    ):
        raise RuntimeError("Mode judge v3.1 requires the exact blinded v3 target report")
    path = benchmark / "JUDGE_EXECUTION_CONTRACT-v3.1.json"
    if path.exists():
        raise RuntimeError("Mode judge v3.1 repair is already frozen")
    payload: dict[str, object] = {
        "contract_version": "3.1.0",
        "repair_protocol_digest": canonical_digest(protocol),
        "blind_report_digest": protocol["blind_report_digest"],
        "target_contract_digest": target_contract.content_digest,
        "target_grid_reexecution_allowed": False,
        "accepted_notice": CODE_MODE_DISABLED_NOTICE,
        "judge_model": target_contract.judge_model,
        "judge_reasoning_effort": target_contract.judge_reasoning_effort,
        "judge_sessions_required": 3,
        "trace_smoke_required": True,
        "condition_mapping_revealed": False,
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
        **repair_source_digests(repo),
    }
    write_new(path, payload)


if __name__ == "__main__":
    main()
