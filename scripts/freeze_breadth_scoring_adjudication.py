"""Freeze the zero-session Milestone 6A.4 score adjudication."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_adjudication import (
    BreadthAdjudicationInput,
    BreadthScoringAdjudicationDesign,
)
from adaptation_compiler_lab.benchmark.breadth_adjudication_schema_export import (
    breadth_adjudication_schemas,
)
from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthReplicationResult,
    load_breadth_contract,
    load_breadth_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_LEGACY_FAILURE = "independent scorer returned no receipts"


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("frozen adjudication artifacts must be JSON objects")
    return (canonical_json(value) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_replication"
    target = root / "SCORING_ADJUDICATION_PREREGISTRATION-v1.json"
    checksum = root / "SCORING_ADJUDICATION_PREREGISTRATION-v1.sha256"
    schema_root = repo / "schemas/breadth_replication/v1_1"
    if target.exists() or checksum.exists() or schema_root.exists():
        raise RuntimeError("breadth score adjudication is already frozen")
    original_design = load_breadth_design(root)
    original_contract = load_breadth_contract(root, design=original_design)
    original_path = root / "results-v1/unblinded-result.json"
    original = BreadthReplicationResult.model_validate_json(original_path.read_bytes())
    if (
        not original.instrument_valid
        or original.permitted_claim != "breadth_gate_failed"
        or original.design_digest != original_design.content_digest
        or original.contract_digest != original_contract.content_digest
    ):
        raise RuntimeError("original breadth result is outside the registered correction")
    inputs = []
    for trial in original.trials:
        if trial.behavior_failures != (_LEGACY_FAILURE,):
            raise RuntimeError("breadth result does not have the uniform registered adapter defect")
        output_id = trial.observation.blind_output_id
        output_path = root / f"results-v1/anonymous-outputs/{output_id}.json"
        public = json.loads(output_path.read_text(encoding="utf-8"))
        if (
            not isinstance(public, dict)
            or public.get("blind_output_id") != output_id
            or public.get("task_id") != trial.observation.task_id
            or not isinstance(public.get("diff"), str)
            or not isinstance(public.get("final_response"), str)
            or public.get("visible_test_executed") is not True
        ):
            raise RuntimeError("breadth anonymous output is malformed")
        if (
            sha256_bytes(str(public["diff"]).encode("utf-8")) != trial.observation.diff_digest
            or sha256_bytes(str(public["final_response"]).encode("utf-8"))
            != trial.observation.final_response_digest
        ):
            raise RuntimeError("breadth public output and original receipt disagree")
        inputs.append(
            BreadthAdjudicationInput(
                task_id=trial.observation.task_id,
                blind_output_id=output_id,
                public_output_digest=sha256_file(output_path),
                original_trial_digest=canonical_digest(trial),
                diff_digest=trial.observation.diff_digest,
                final_response_digest=trial.observation.final_response_digest,
            )
        )
    design = BreadthScoringAdjudicationDesign(
        original_design_digest=original_design.content_digest,
        original_contract_digest=original_contract.content_digest,
        original_result_file_digest=sha256_file(original_path),
        blind_report_file_digest=sha256_file(root / "results-v1/blind-report.json"),
        completion_file_digest=sha256_file(root / "results-v1/completion.json"),
        judge_receipt_file_digest=sha256_file(root / "results-v1/judge-receipt.json"),
        inputs=tuple(sorted(inputs, key=lambda item: item.blind_output_id)),
        protocol_digest=sha256_file(root / "SCORING_ADJUDICATION_PROTOCOL-v1.md"),
        scorer_source_digest=sha256_file(repo / "scripts/score_breadth_replication_task.py"),
        adjudicator_source_digest=sha256_file(repo / "scripts/adjudicate_breadth_scoring.py"),
        adjudication_model_source_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/breadth_adjudication.py"
        ),
    )
    _exclusive_write(target, _canonical_bytes(design))
    digest = sha256_file(target).removeprefix("sha256:")
    _exclusive_write(checksum, f"{digest}  {target.name}\n".encode("ascii"))
    schema_root.mkdir(parents=True, exist_ok=False)
    for name, schema in breadth_adjudication_schemas().items():
        _exclusive_write(schema_root / name, _canonical_bytes(schema))


if __name__ == "__main__":
    main()
