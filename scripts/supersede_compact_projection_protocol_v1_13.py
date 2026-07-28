"""Freeze pre-live source bindings and target sandbox requirements as v1.13."""

from __future__ import annotations

import argparse
import hashlib
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
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    root = arguments.benchmark_root.resolve()
    historical_path = root / "PREREGISTRATION-v1.12.json"
    historical_checksum = root / "PREREGISTRATION-v1.12.sha256"
    fields = historical_checksum.read_text(encoding="ascii").split()
    if (
        len(fields) != 2
        or fields[1] != historical_path.name
        or sha256_file(historical_path) != f"sha256:{fields[0]}"
    ):
        raise ValueError("refusing to supersede a drifted v1.12 preregistration")
    historical = CompactProjectionComparisonDesign.model_validate_json(historical_path.read_bytes())
    if historical.design_version != "1.12.0":
        raise ValueError("expected compact projection preregistration v1.12")
    if (root / "condition-materials-v1.12").exists() or (root / "results-v1.12").exists():
        raise ValueError("v1.12 live material exists; a pre-live amendment is forbidden")

    replacement = CompactProjectionComparisonDesign.model_validate(
        {
            **historical.model_dump(exclude_none=True, round_trip=True),
            "amendment_reason": "prelive_source_binding_and_target_sandbox_freeze",
            "design_version": "1.13.0",
            "renderer_source_digest": sha256_file(
                repo / "src/adaptation_compiler_lab/targets/codex_runtime_v2.py"
            ),
            "superseded_scorer_digest": historical.independent_scorer_digest,
            "supersedes_design_digest": historical.content_digest,
        }
    )
    preregistration = (
        canonical_json(replacement.model_dump(mode="json", exclude_none=True, round_trip=True))
        + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.13.json"
    checksum_path = root / "PREREGISTRATION-v1.13.sha256"
    if preregistration_path.exists() or checksum_path.exists():
        raise ValueError("compact projection v1.13 is already frozen")
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(checksum_path, f"{digest}  PREREGISTRATION-v1.13.json\n")
    print(
        canonical_json(
            {
                "design_digest": replacement.content_digest,
                "prior_failed_result_digest": replacement.prior_failed_result_digest,
                "sessions": replacement.maximum_subscription_sessions,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
