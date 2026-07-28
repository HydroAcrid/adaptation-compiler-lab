"""Freeze the nested-sandbox repair and one-session live instrument smoke gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.compact_execution import (
    CompactExecutionContract,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionComparisonDesign,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, required=True)
    arguments = parser.parse_args()

    root = arguments.benchmark_root.resolve()
    repo = root.parent
    historical_path = root / "PREREGISTRATION-v1.15.json"
    historical_checksum = root / "PREREGISTRATION-v1.15.sha256"
    fields = historical_checksum.read_text(encoding="ascii").split()
    if (
        len(fields) != 2
        or fields[1] != historical_path.name
        or sha256_file(historical_path) != f"sha256:{fields[0]}"
    ):
        raise ValueError("refusing to supersede a drifted v1.15 preregistration")
    historical = CompactProjectionComparisonDesign.model_validate_json(historical_path.read_bytes())
    if historical.design_version != "1.15.0":
        raise ValueError("expected compact projection preregistration v1.15")

    failure = root / "TARGET_EXECUTION_FAILURE-v1.15.json"
    blind_report = root / "results-v1.15" / "blind-report.json"
    if not failure.is_file() or not blind_report.is_file():
        raise ValueError("v1.16 requires the durable v1.15 target-failure records")
    failure_value = json.loads(failure.read_text(encoding="utf-8"))
    report_value = json.loads(blind_report.read_text(encoding="utf-8"))
    observations = report_value.get("observations")
    if (
        failure_value.get("failure_class") != "instrument"
        or failure_value.get("subscription_sessions_consumed") != 6
        or failure_value.get("judge_executed") is not False
        or not isinstance(observations, list)
        or len(observations) != 6
        or any(item.get("valid") is not False for item in observations)
    ):
        raise ValueError("v1.15 was not an exact six-cell instrument failure")
    if (root / "results-v1.15" / "judge-receipt.json").exists():
        raise ValueError("v1.15 was judged; instrument retry is no longer applicable")

    replacement = CompactProjectionComparisonDesign.model_validate(
        {
            **historical.model_dump(exclude_none=True, round_trip=True),
            "amendment_reason": "nested_target_sandbox_runtime_and_live_smoke_gate",
            "design_version": "1.16.0",
            "instrument_smoke_sessions": 1,
            "maximum_subscription_sessions": 8,
            "prior_failed_target_receipt_digest": sha256_file(failure),
            "superseded_scorer_digest": historical.independent_scorer_digest,
            "supersedes_design_digest": historical.content_digest,
        }
    )
    preregistration = (
        canonical_json(replacement.model_dump(mode="json", exclude_none=True, round_trip=True))
        + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.16.json"
    checksum_path = root / "PREREGISTRATION-v1.16.sha256"
    contract_path = root / "EXECUTION_CONTRACT-v1.4.json"
    if preregistration_path.exists() or checksum_path.exists() or contract_path.exists():
        raise ValueError("compact projection v1.16 is already frozen")

    contract = CompactExecutionContract(
        contract_version="1.4.0",
        design_digest=replacement.content_digest,
        execution_protocol_digest=sha256_file(root / "EXECUTION_PROTOCOL.md"),
        maximum_subscription_sessions=8,
        profile_author_sessions=0,
        profile_review_sessions=0,
        instrument_smoke_sessions=1,
        target_sandbox="workspace-write-inside-read-only-outer-mount-namespace",
        target_outer_sandbox_digest=(
            "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
        ),
        target_workspace_policy="workspace-read-only-except-registered-source-file",
        target_runner_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_subscription.py"
        ),
        inherited_profile_receipt_digest=sha256_file(
            root / "profile-remediation-receipt-v1.14.json"
        ),
    )
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(checksum_path, f"{digest}  PREREGISTRATION-v1.16.json\n")
    _exclusive_write(
        contract_path,
        canonical_json(contract.model_dump(mode="json", round_trip=True)) + "\n",
    )
    print(
        canonical_json(
            {
                "contract_digest": contract.content_digest,
                "design_digest": replacement.content_digest,
                "instrument_smoke_sessions": replacement.instrument_smoke_sessions,
                "sessions": replacement.maximum_subscription_sessions,
                "target_failure_digest": replacement.prior_failed_target_receipt_digest,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
