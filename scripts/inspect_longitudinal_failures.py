"""Read and summarize only invalid Milestone 6A target bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    LongitudinalBlindReport,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from adaptation_compiler_lab.serialization import canonical_json

_MEDIA_TYPE = "application/vnd.adaptation-compiler-lab.longitudinal-target-run+json"
_MAGIC = b"ACLAB-RAW-1\n"


def _envelope_size(path: Path) -> int:
    raw = path.read_bytes()
    value = json.loads(raw.removeprefix(_MAGIC))
    if not isinstance(value, dict) or not isinstance(value.get("plaintext_size"), int):
        raise RuntimeError("encrypted target bundle envelope is malformed")
    return value["plaintext_size"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    output = arguments.output_root.resolve()
    report = LongitudinalBlindReport.model_validate_json(
        (repo / "development_benchmark_longitudinal" / "results" / "blind-report.json").read_bytes()
    )
    progress = {
        value["blind_output_id"]: value
        for value in (
            json.loads(line)
            for line in (output / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    store = LocalRawPayloadStore(
        output / "encrypted",
        encryption_key=RawEncryptionKey.from_file(arguments.key, workspace_root=repo),
    )
    summaries: list[dict[str, object]] = []
    for observation in report.observations:
        if observation.valid:
            continue
        progress_value = progress[observation.blind_output_id]
        digest_value = progress_value["raw_trace_ref_digest"]
        if not isinstance(digest_value, str) or not digest_value.startswith("sha256:"):
            raise RuntimeError("progress receipt omitted raw target digest")
        digest = digest_value.removeprefix("sha256:")
        relative = f"sha256/{digest[:2]}/{digest}"
        path = output / "encrypted" / relative
        reference = RawPayloadRef(
            sha256=digest,
            size_bytes=_envelope_size(path),
            media_type=_MEDIA_TYPE,
            relative_path=relative,
        )
        bundle = json.loads(store.read(reference))
        if not isinstance(bundle, dict):
            raise RuntimeError("target bundle is not a JSON object")
        summaries.append(
            {
                "blind_output_id": observation.blind_output_id,
                "command_audit": bundle.get("command_audit"),
                "diff_digest": observation.diff_digest,
                "invalid_reason": observation.invalid_reason,
                "status": bundle.get("status"),
                "task_id": observation.task_id,
                "visible_test_returncode": (
                    bundle.get("visible_test", {}).get("returncode")
                    if isinstance(bundle.get("visible_test"), dict)
                    else None
                ),
            }
        )
    print(canonical_json({"invalid_runs": summaries}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
