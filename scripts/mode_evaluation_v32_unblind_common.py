"""Deterministic source binding for the Mode evaluation v3.2 unblinder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest

_BENCHMARK = "development_benchmark_mode_evaluation"
_PROTOCOL = f"{_BENCHMARK}/UNBLIND_REPAIR_PROTOCOL-v3.2.json"
_CONTRACT = f"{_BENCHMARK}/UNBLIND_EXECUTION_CONTRACT-v3.2.json"


def load_object(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"invalid Mode unblind v3.2 file: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"Mode unblind v3.2 file is not an object: {path.name}")
    return cast(JsonObject, value)


def unblind_source_digest(repo: Path) -> str:
    paths = (
        _PROTOCOL,
        "scripts/mode_evaluation_v32_unblind_common.py",
        "scripts/unblind_mode_evaluation.py",
        "scripts/unblind_mode_evaluation_v32.py",
        "src/adaptation_compiler_lab/modes/evaluation.py",
    )
    return canonical_digest({path: sha256_file(repo / path) for path in paths})


def validate_unblind_repair(repo: Path) -> JsonObject:
    contract = load_object(repo / _CONTRACT)
    protocol = load_object(repo / _PROTOCOL)
    if contract.get("repair_protocol_digest") != canonical_digest(protocol):
        raise RuntimeError("Mode unblind v3.2 protocol drifted")
    if contract.get("unblind_source_digest") != unblind_source_digest(repo):
        raise RuntimeError("Mode unblind v3.2 source drifted")
    judge_completion = load_object(repo / _BENCHMARK / "results-v3/judges-v31/completion.json")
    if contract.get("judge_completion_digest") != canonical_digest(judge_completion):
        raise RuntimeError("Mode unblind v3.2 judge completion drifted")
    return contract
