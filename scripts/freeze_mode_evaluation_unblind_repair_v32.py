"""Freeze the deterministic Mode evaluation v3.2 unblind repair."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.serialization import canonical_digest
from scripts.mode_evaluation_v31_judge_common import write_new
from scripts.mode_evaluation_v32_unblind_common import load_object, unblind_source_digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    protocol = load_object(benchmark / "UNBLIND_REPAIR_PROTOCOL-v3.2.json")
    if (
        protocol.get("condition_reveal_eligible") is not True
        or protocol.get("target_grid_reexecution_allowed") is not False
        or protocol.get("judge_reexecution_allowed") is not False
        or protocol.get("judge_completion_digest")
        != "sha256:8361e8fb2321b4eb5bf9a09cc0ead3392d52a25bbcd36d120451fe326284fa6f"
    ):
        raise RuntimeError("Mode unblind v3.2 repair protocol is invalid")
    path = benchmark / "UNBLIND_EXECUTION_CONTRACT-v3.2.json"
    if path.exists():
        raise RuntimeError("Mode unblind v3.2 repair is already frozen")
    write_new(
        path,
        {
            "contract_version": "3.2.0",
            "repair_protocol_digest": canonical_digest(protocol),
            "blind_report_digest": protocol["blind_report_digest"],
            "judge_completion_digest": protocol["judge_completion_digest"],
            "judge_repair_contract_digest": protocol["judge_repair_contract_digest"],
            "target_grid_reexecution_allowed": False,
            "judge_reexecution_allowed": False,
            "provider_billed_calls": 0,
            "unblind_source_digest": unblind_source_digest(repo),
        },
    )


if __name__ == "__main__":
    main()
