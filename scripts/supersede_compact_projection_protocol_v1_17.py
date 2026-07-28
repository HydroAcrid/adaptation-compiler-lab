"""Bind the live-smoke source after the zero-session v1.16 coordinator failure."""

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
    historical_path = root / "PREREGISTRATION-v1.16.json"
    historical_checksum = root / "PREREGISTRATION-v1.16.sha256"
    fields = historical_checksum.read_text(encoding="ascii").split()
    if (
        len(fields) != 2
        or fields[1] != historical_path.name
        or sha256_file(historical_path) != f"sha256:{fields[0]}"
    ):
        raise ValueError("refusing to supersede a drifted v1.16 preregistration")
    historical = CompactProjectionComparisonDesign.model_validate_json(historical_path.read_bytes())
    if historical.design_version != "1.16.0":
        raise ValueError("expected compact projection preregistration v1.16")

    failure = root / "INSTRUMENT_SMOKE_FAILURE-v1.16.json"
    failure_value = json.loads(failure.read_text(encoding="utf-8"))
    if (
        failure_value.get("failure_class") != "pre_session_instrument"
        or failure_value.get("subscription_sessions_consumed") != 0
        or failure_value.get("target_sessions_started") != 0
        or failure_value.get("trace_created") is not False
    ):
        raise ValueError("v1.16 was not an exact zero-session smoke-coordinator failure")
    if (root / "INSTRUMENT_SMOKE-v1.16.json").exists():
        raise ValueError("v1.16 produced a smoke receipt and cannot be retried")

    replacement = CompactProjectionComparisonDesign.model_validate(
        {
            **historical.model_dump(exclude_none=True, round_trip=True),
            "amendment_reason": "smoke_role_binding_and_source_family_fix",
            "design_version": "1.17.0",
            "prior_failed_smoke_receipt_digest": sha256_file(failure),
            "superseded_scorer_digest": historical.independent_scorer_digest,
            "supersedes_design_digest": historical.content_digest,
        }
    )
    preregistration = (
        canonical_json(replacement.model_dump(mode="json", exclude_none=True, round_trip=True))
        + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.17.json"
    checksum_path = root / "PREREGISTRATION-v1.17.sha256"
    contract_path = root / "EXECUTION_CONTRACT-v1.5.json"
    if preregistration_path.exists() or checksum_path.exists() or contract_path.exists():
        raise ValueError("compact projection v1.17 is already frozen")

    contract = CompactExecutionContract(
        contract_version="1.5.0",
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
        instrument_smoke_source_digest=sha256_file(
            repo / "scripts/run_compact_projection_live_smoke.py"
        ),
        inherited_profile_receipt_digest=sha256_file(
            root / "profile-remediation-receipt-v1.14.json"
        ),
    )
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(checksum_path, f"{digest}  PREREGISTRATION-v1.17.json\n")
    _exclusive_write(
        contract_path,
        canonical_json(contract.model_dump(mode="json", round_trip=True)) + "\n",
    )
    print(
        canonical_json(
            {
                "contract_digest": contract.content_digest,
                "design_digest": replacement.content_digest,
                "sessions": replacement.maximum_subscription_sessions,
                "smoke_failure_digest": replacement.prior_failed_smoke_receipt_digest,
                "smoke_source_digest": contract.instrument_smoke_source_digest,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
