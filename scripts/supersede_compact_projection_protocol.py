"""Issue an immutable pre-execution scorer amendment for Milestone 6A.1."""

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
    historical_path = root / "PREREGISTRATION-v1.0.json"
    historical_checksum = root / "PREREGISTRATION-v1.0.sha256"
    fields = historical_checksum.read_text(encoding="ascii").split()
    if (
        len(fields) != 2
        or fields[1] != historical_path.name
        or sha256_file(historical_path) != f"sha256:{fields[0]}"
    ):
        raise ValueError("refusing to amend a drifted v1.0 preregistration")
    historical = CompactProjectionComparisonDesign.model_validate_json(historical_path.read_bytes())
    if historical.design_version != "1.0.0":
        raise ValueError("expected compact projection preregistration v1.0")
    if (
        historical.target_sessions_started
        or historical.profile_sessions_started
        or historical.judge_sessions_started
    ):
        raise ValueError("cannot amend a protocol after any registered session starts")

    replacement = CompactProjectionComparisonDesign.model_validate(
        {
            **historical.model_dump(
                exclude_none=True,
                round_trip=True,
            ),
            "design_version": "1.1.0",
            "independent_scorer_digest": sha256_file(
                repo / "scripts" / "score_compact_projection_task.py"
            ),
            "supersedes_design_digest": historical.content_digest,
            "superseded_scorer_digest": historical.independent_scorer_digest,
            "amendment_reason": "strict_tuple_return_contract",
        }
    )
    preregistration = (
        canonical_json(
            replacement.model_dump(
                mode="json",
                exclude_none=True,
                round_trip=True,
            )
        )
        + "\n"
    )
    preregistration_path = root / "PREREGISTRATION-v1.1.json"
    checksum_path = root / "PREREGISTRATION-v1.1.sha256"
    if preregistration_path.exists() or checksum_path.exists():
        raise ValueError("compact projection scorer amendment is already frozen")
    _exclusive_write(preregistration_path, preregistration)
    digest = hashlib.sha256(preregistration.encode("utf-8")).hexdigest()
    _exclusive_write(
        checksum_path,
        f"{digest}  PREREGISTRATION-v1.1.json\n",
    )
    print(
        canonical_json(
            {
                "design_digest": replacement.content_digest,
                "sessions": replacement.maximum_subscription_sessions,
                "supersedes_design_digest": historical.content_digest,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
