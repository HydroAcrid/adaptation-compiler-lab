"""Custody checks for the judge-only Mode evaluation v3.1 repair."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_BENCHMARK = "development_benchmark_mode_evaluation"
_PROTOCOL = f"{_BENCHMARK}/JUDGE_REPAIR_PROTOCOL-v3.1.json"
_CONTRACT = f"{_BENCHMARK}/JUDGE_EXECUTION_CONTRACT-v3.1.json"


def load_object(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"invalid Mode judge v3.1 file: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"Mode judge v3.1 file is not an object: {path.name}")
    return cast(JsonObject, value)


def _bundle_digest(repo: Path, paths: tuple[str, ...]) -> str:
    return canonical_digest({path: sha256_file(repo / path) for path in paths})


def repair_source_digests(repo: Path) -> dict[str, str]:
    common = "scripts/mode_evaluation_v31_judge_common.py"
    return {
        "judge_runner_source_digest": _bundle_digest(
            repo,
            (
                _PROTOCOL,
                "scripts/run_mode_evaluation_judge_smoke_v31.py",
                "src/adaptation_compiler_lab/runners/codex_mode_judge_v31.py",
                "src/adaptation_compiler_lab/runners/codex_mode_judge.py",
                "src/adaptation_compiler_lab/runners/codex_structured_role.py",
                "src/adaptation_compiler_lab/runners/codex_subscription.py",
            ),
        ),
        "judge_source_digest": _bundle_digest(
            repo,
            (
                common,
                "scripts/judge_mode_evaluation.py",
                "scripts/judge_mode_evaluation_v31.py",
                "src/adaptation_compiler_lab/modes/evaluation.py",
            ),
        ),
        "unblind_source_digest": _bundle_digest(
            repo,
            (
                common,
                "scripts/unblind_mode_evaluation.py",
                "scripts/unblind_mode_evaluation_v31.py",
                "src/adaptation_compiler_lab/modes/evaluation.py",
            ),
        ),
    }


def validate_repair_sources(repo: Path) -> JsonObject:
    contract = load_object(repo / _CONTRACT)
    for field, observed in repair_source_digests(repo).items():
        if contract.get(field) != observed:
            raise RuntimeError(f"Mode judge v3.1 {field} drifted")
    protocol = load_object(repo / _PROTOCOL)
    if contract.get("repair_protocol_digest") != canonical_digest(protocol):
        raise RuntimeError("Mode judge v3.1 repair protocol drifted")
    report = load_object(repo / _BENCHMARK / "results-v3/blind-trial-report.json")
    completion = load_object(repo / _BENCHMARK / "results-v3/completion.json")
    if (
        completion.get("report_digest") != contract.get("blind_report_digest")
        or completion.get("report_digest") != canonical_digest(report)
        or report.get("unblinded") is not False
    ):
        raise RuntimeError("Mode judge v3.1 blind target report drifted")
    return contract


def require_valid_trace_smoke(repo: Path, *, repair_contract: JsonObject) -> JsonObject:
    root = repo / _BENCHMARK / "judge-smoke-v31"
    receipt = load_object(root / "smoke-receipt.json")
    completion = load_object(root / "completion.json")
    if (
        completion.get("smoke_receipt_digest") != canonical_digest(receipt)
        or receipt.get("repair_contract_digest") != canonical_digest(repair_contract)
        or receipt.get("valid") is not True
        or receipt.get("exact_notice_normalized") is not True
        or receipt.get("genuine_tool_rejection_tested") is not True
        or receipt.get("workspace_destroyed") is not True
        or receipt.get("provider_billed_calls") != 0
    ):
        raise RuntimeError("Mode judge v3.1 requires its exact passing trace smoke")
    return receipt


def write_new(path: Path, value: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (canonical_json(value) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
