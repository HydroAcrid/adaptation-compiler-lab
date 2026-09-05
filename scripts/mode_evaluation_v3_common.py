"""Shared custody checks for the smoke-gated Mode evaluation v3 repair."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.modes.evaluation import ModeEvaluationExecutionContractV1
from adaptation_compiler_lab.serialization import canonical_digest

_REPAIR_PROTOCOL = "development_benchmark_mode_evaluation/REPAIR_PROTOCOL-v3.json"


def load_object(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"invalid Mode evaluation v3 file: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"Mode evaluation v3 file is not an object: {path.name}")
    return cast(JsonObject, value)


def _bundle_digest(repo: Path, paths: tuple[str, ...]) -> str:
    return canonical_digest({path: sha256_file(repo / path) for path in paths})


def instrument_source_digests(repo: Path) -> dict[str, str]:
    """Bind every mutable source used by the repaired execution and decision chain."""

    common = "scripts/mode_evaluation_v3_common.py"
    return {
        "runner_source_digest": _bundle_digest(
            repo,
            (
                _REPAIR_PROTOCOL,
                common,
                "scripts/run_mode_evaluation.py",
                "scripts/run_mode_evaluation_v3.py",
                "scripts/run_mode_evaluation_smoke_v3.py",
                "scripts/run_durable_progress_comparison.py",
                "src/adaptation_compiler_lab/runners/codex_mode_target.py",
                "src/adaptation_compiler_lab/runners/codex_subscription.py",
            ),
        ),
        "scorer_source_digest": _bundle_digest(
            repo,
            (
                common,
                "scripts/score_mode_evaluation_task.py",
                "scripts/observe_mode_evaluation_policy.py",
                "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
                "src/adaptation_compiler_lab/modes/evaluation.py",
                "uv.lock",
            ),
        ),
        "observer_source_digest": sha256_file(repo / "scripts/observe_mode_evaluation_policy.py"),
        "judge_role_runner_source_digest": _bundle_digest(
            repo,
            (
                common,
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
                "scripts/judge_mode_evaluation_v3.py",
            ),
        ),
        "unblind_source_digest": _bundle_digest(
            repo,
            (
                common,
                "scripts/unblind_mode_evaluation.py",
                "scripts/unblind_mode_evaluation_v3.py",
            ),
        ),
    }


def validate_instrument_sources(
    repo: Path,
    contract: ModeEvaluationExecutionContractV1,
) -> None:
    for field, observed in instrument_source_digests(repo).items():
        if getattr(contract, field) != observed:
            raise RuntimeError(f"Mode evaluation v3 {field} drifted")


def code_mode_host_digest(repo: Path) -> str:
    value = load_object(repo / _REPAIR_PROTOCOL).get("code_mode_host_digest")
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise RuntimeError("Mode evaluation v3 execution-host digest is invalid")
    return value


def verify_scorer_runtime(*, repo: Path, python: Path) -> JsonObject:
    """Fail before inference unless the isolated scorer has the frozen dependencies."""

    invocation = Path(os.path.abspath(python.expanduser()))
    resolved = invocation.resolve()
    if invocation.is_relative_to(repo) or resolved.is_relative_to(repo) or not invocation.is_file():
        raise RuntimeError("Mode evaluation v3 scorer Python must be external and executable")
    protocol = load_object(repo / _REPAIR_PROTOCOL)
    expected_python = protocol.get("scorer_python_version")
    expected_pydantic = protocol.get("scorer_pydantic_version")
    expected_lock = protocol.get("scorer_lock_digest")
    if sha256_file(repo / "uv.lock") != expected_lock:
        raise RuntimeError("Mode evaluation v3 scorer lock drifted")
    probe = subprocess.run(
        [
            str(invocation),
            "-c",
            (
                "import json,platform,pydantic; "
                "print(json.dumps({'pydantic':pydantic.__version__,"
                "'python':platform.python_version()},sort_keys=True))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=10,
    )
    try:
        observed = json.loads(probe.stdout)
    except ValueError as error:
        raise RuntimeError("Mode evaluation v3 scorer probe was malformed") from error
    if (
        probe.returncode != 0
        or not isinstance(observed, dict)
        or observed.get("python") != expected_python
        or observed.get("pydantic") != expected_pydantic
    ):
        raise RuntimeError("Mode evaluation v3 scorer runtime drifted")
    return cast(JsonObject, observed)


def require_valid_smoke(
    *,
    benchmark: Path,
    contract: ModeEvaluationExecutionContractV1,
) -> JsonObject:
    smoke = load_object(benchmark / "smoke-v3/smoke-receipt.json")
    completion = load_object(benchmark / "smoke-v3/completion.json")
    if (
        completion.get("smoke_receipt_digest") != canonical_digest(smoke)
        or smoke.get("contract_digest") != contract.content_digest
        or smoke.get("valid") is not True
        or smoke.get("edit_observed") is not True
        or smoke.get("visible_tests_passed") is not True
        or smoke.get("hidden_scorer_passed") is not True
        or smoke.get("workspace_destroyed") is not True
        or smoke.get("provider_billed_calls") != 0
        or smoke.get("external_validation_accessed") is not False
    ):
        raise RuntimeError("Mode evaluation v3 requires its exact passing smoke receipt")
    return smoke


def write_new(path: Path, value: JsonObject) -> None:
    from adaptation_compiler_lab.serialization import canonical_json

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (canonical_json(value) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
