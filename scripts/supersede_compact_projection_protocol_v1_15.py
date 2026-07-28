"""Authorize an exact pre-action retry after freezing the v1.14 resolver failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

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
    historical_path = root / "PREREGISTRATION-v1.14.json"
    historical_checksum = root / "PREREGISTRATION-v1.14.sha256"
    fields = historical_checksum.read_text(encoding="ascii").split()
    if (
        len(fields) != 2
        or fields[1] != historical_path.name
        or sha256_file(historical_path) != f"sha256:{fields[0]}"
    ):
        raise ValueError("refusing to supersede a drifted v1.14 preregistration")
    historical = CompactProjectionComparisonDesign.model_validate_json(historical_path.read_bytes())
    if historical.design_version != "1.14.0":
        raise ValueError("expected compact projection preregistration v1.14")
    failure = root / "TARGET_EXECUTION_FAILURE-v1.14.json"
    blind_report = root / "results-v1.14" / "blind-report.json"
    if not failure.is_file() or not blind_report.is_file():
        raise ValueError("v1.15 requires the durable v1.14 target-failure records")
    failure_value = json.loads(failure.read_text(encoding="utf-8"))
    report_value = json.loads(blind_report.read_text(encoding="utf-8"))
    observations = report_value.get("observations")
    if (
        failure_value.get("sessions_attempted") != 6
        or failure_value.get("target_actions_observed") != 0
        or not isinstance(observations, list)
        or len(observations) != 6
        or any(item.get("valid") is not False for item in observations)
    ):
        raise ValueError("v1.14 was not an exact six-cell pre-action failure")
    if (root / "results-v1.14" / "judge-receipt.json").exists():
        raise ValueError("v1.14 was judged; pre-action retry is no longer applicable")

    replacement = CompactProjectionComparisonDesign.model_validate(
        {
            **historical.model_dump(exclude_none=True, round_trip=True),
            "amendment_reason": "target_resolver_mount_and_preact_retry",
            "design_version": "1.15.0",
            "maximum_subscription_sessions": 7,
            "prior_failed_target_receipt_digest": sha256_file(failure),
            "profile_review_sessions": 0,
            "superseded_scorer_digest": historical.independent_scorer_digest,
            "supersedes_design_digest": historical.content_digest,
        }
    )
    preregistration = (
        canonical_json(replacement.model_dump(mode="json", exclude_none=True, round_trip=True))
        + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.15.json"
    checksum_path = root / "PREREGISTRATION-v1.15.sha256"
    if preregistration_path.exists() or checksum_path.exists():
        raise ValueError("compact projection v1.15 is already frozen")
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(checksum_path, f"{digest}  PREREGISTRATION-v1.15.json\n")
    print(
        canonical_json(
            {
                "design_digest": replacement.content_digest,
                "sessions": replacement.maximum_subscription_sessions,
                "target_failure_digest": replacement.prior_failed_target_receipt_digest,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
