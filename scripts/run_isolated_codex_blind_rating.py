"""Run one blank-context Codex rating and preserve its trace encrypted outside Git."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter

from adaptation_compiler_lab.benchmark.isolated_rating import (
    BlindPairBinding,
    IsolatedAIRatingReceipt,
    isolated_rating_output_schema,
    validate_blind_pair_coverage,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_blind_rating import (
    CODEX_BLIND_RATING_CONTRACT,
    IsolatedCodexBlindRatingRunner,
)
from adaptation_compiler_lab.serialization import canonical_json

_JSON_ADAPTER = TypeAdapter(Any)


def _canonical_bytes(value: Any) -> bytes:
    payload = _JSON_ADAPTER.dump_python(value, mode="json")
    if not isinstance(payload, dict):
        raise TypeError("canonical isolated-rating payload must be a JSON object")
    return (canonical_json(cast(dict[str, object], payload)) + "\n").encode("utf-8")


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _create_secret(path: Path) -> None:
    _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")


def _git(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *command],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _pair_bindings(raw_pairs: Any) -> tuple[BlindPairBinding, BlindPairBinding]:
    if not isinstance(raw_pairs, list) or len(raw_pairs) != 2:
        raise RuntimeError("isolated rating pair bindings are incomplete")
    pair_values = []
    for value in raw_pairs:
        if not isinstance(value, dict):
            raise RuntimeError("isolated rating pair binding is not an object")
        normalized = dict(value)
        output_ids = normalized.get("ordered_output_ids")
        if not isinstance(output_ids, list):
            raise RuntimeError("isolated rating output binding is not a JSON array")
        normalized["ordered_output_ids"] = tuple(output_ids)
        pair_values.append(BlindPairBinding.model_validate(normalized))
    pairs = tuple(pair_values)
    if len({item.task_id for item in pairs}) != 2:
        raise RuntimeError("isolated rating tasks are not unique")
    return cast(tuple[BlindPairBinding, BlindPairBinding], pairs)


def _validate_preregistration(
    *,
    preregistration: dict[str, Any],
    repo: Path,
    packet_path: Path,
    benchmark_output_root: Path,
    source_commit: str,
) -> tuple[BlindPairBinding, BlindPairBinding]:
    if preregistration.get("schema_version") != "1.0.0":
        raise RuntimeError("isolated rating preregistration schema drifted")
    if preregistration.get("benchmark_id") != "claude-haiku-compiler-v2-public-repair":
        raise RuntimeError("isolated rating benchmark identity drifted")
    implementation_commit = preregistration.get("implementation_commit")
    if not isinstance(implementation_commit, str) or len(implementation_commit) != 40:
        raise RuntimeError("isolated rating implementation commit is invalid")
    ancestor = _git(["merge-base", "--is-ancestor", implementation_commit, source_commit], cwd=repo)
    if ancestor.returncode != 0:
        raise RuntimeError("isolated rating implementation commit is not an ancestor")
    if preregistration.get("packet_digest") != sha256_file(packet_path):
        raise RuntimeError("isolated rating packet changed")
    completion_path = benchmark_output_root / "completion.json"
    if preregistration.get("completion_receipt_digest") != sha256_file(completion_path):
        raise RuntimeError("isolated rating completion receipt changed")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if preregistration.get("blind_report_digest") != completion.get("blind_report_digest"):
        raise RuntimeError("isolated rating blind-report binding drifted")
    if preregistration.get("rating_contract_digest") != sha256_bytes(
        CODEX_BLIND_RATING_CONTRACT.encode("utf-8")
    ):
        raise RuntimeError("isolated rating contract drifted")
    schema_bytes = (
        json.dumps(
            isolated_rating_output_schema(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if preregistration.get("output_schema_digest") != sha256_bytes(schema_bytes):
        raise RuntimeError("isolated rating output schema drifted")
    if preregistration.get("scorer") != {
        "cli_digest": "sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14",
        "cli_version": "codex-cli 0.145.0",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "service_mode": "standard",
        "saved_chatgpt_authentication": True,
    }:
        raise RuntimeError("isolated rating scorer identity drifted")
    if preregistration.get("isolation") != {
        "api_key_environment_forbidden": True,
        "context_inputs": "rating_contract_and_anonymous_packet_only",
        "empty_workspace": True,
        "ephemeral_session": True,
        "host_home_visible": False,
        "memories_plugins_skills_mcp_disabled": True,
        "network_search_disabled": True,
        "no_retry": True,
        "outer_minimal_mount_namespace": True,
        "project_repository_visible": False,
        "read_only_inner_sandbox": True,
        "tool_use_forbidden": True,
        "user_config_and_rules_ignored": True,
    }:
        raise RuntimeError("isolated rating boundary drifted")
    return _pair_bindings(preregistration.get("pairs"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--benchmark-output-root", type=Path, required=True)
    parser.add_argument("--rating-output-root", type=Path, required=True)
    parser.add_argument("--rating-config-root", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    packet_path = arguments.packet.resolve()
    benchmark_output_root = arguments.benchmark_output_root.resolve()
    rating_output_root = arguments.rating_output_root.resolve()
    rating_config_root = arguments.rating_config_root.resolve()
    preregistration_path = arguments.preregistration.resolve()
    if not packet_path.is_relative_to(repo) or not preregistration_path.is_relative_to(repo):
        raise RuntimeError("rating packet and preregistration must be repository files")
    if rating_output_root.exists() or rating_config_root.exists():
        raise RuntimeError("isolated rating roots already exist; refusing to overwrite")
    source_status = _git(["status", "--porcelain"], cwd=repo)
    if source_status.returncode != 0 or source_status.stdout:
        raise RuntimeError("isolated rating requires a clean repository")
    source_commit_result = _git(["rev-parse", "HEAD"], cwd=repo)
    if source_commit_result.returncode != 0:
        raise RuntimeError("unable to resolve isolated rating source commit")
    source_commit = source_commit_result.stdout.strip()
    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    expected_pairs = _validate_preregistration(
        preregistration=preregistration,
        repo=repo,
        packet_path=packet_path,
        benchmark_output_root=benchmark_output_root,
        source_commit=source_commit,
    )

    rating_output_root.mkdir(parents=True, mode=0o700)
    rating_config_root.mkdir(parents=True, mode=0o700)
    os.chmod(rating_output_root, 0o700)
    os.chmod(rating_config_root, 0o700)
    key_path = rating_config_root / "rating-encryption.key"
    _create_secret(key_path)
    encryption_key = RawEncryptionKey.from_file(key_path, workspace_root=repo)
    store = LocalRawPayloadStore(
        rating_output_root / "encrypted",
        encryption_key=encryption_key,
    )
    runner = IsolatedCodexBlindRatingRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
    )
    preconditions = runner.verify_preconditions()
    try:
        result = runner.run(
            packet=packet_path.read_text(encoding="utf-8"),
            output_schema=isolated_rating_output_schema(),
        )
    except BaseException as error:
        _exclusive_write(
            rating_output_root / "failure.json",
            _canonical_bytes(
                {
                    "benchmark_id": preregistration["benchmark_id"],
                    "condition_mapping_seen": False,
                    "exception_message": str(error),
                    "exception_type": type(error).__name__,
                    "milestone_6_custody_accessed": False,
                    "objective_scores_seen": False,
                    "rating_created": False,
                    "retry_allowed": False,
                    "status": "isolated_rating_coordinator_failure",
                }
            ),
            mode=0o600,
        )
        raise
    raw_bundle = _canonical_bytes(
        {
            "command_digest": result.command_digest,
            "decision": (
                result.decision.model_dump(mode="json") if result.decision is not None else None
            ),
            "duration_seconds": result.duration_seconds,
            "environment_digest": result.environment_digest,
            "exit_code": result.exit_code,
            "finished_at": result.finished_at,
            "model": result.model,
            "preconditions": preconditions,
            "rating_contract_digest": result.rating_contract_digest,
            "reasoning_effort": result.reasoning_effort,
            "service_mode": result.service_mode,
            "started_at": result.started_at,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
            "trace_conformant": result.trace_conformant,
            "trace_validation_error": result.trace_validation_error,
            "usage": {
                "cached_input_tokens": result.cached_input_tokens,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "reasoning_output_tokens": result.reasoning_output_tokens,
            },
        }
    )
    trace_ref = store.put(
        raw_bundle,
        media_type="application/vnd.adaptation-compiler-lab.isolated-rating+json",
    )
    if not result.trace_conformant or result.decision is None:
        _exclusive_write(
            rating_output_root / "failure.json",
            _canonical_bytes(
                {
                    "benchmark_id": preregistration["benchmark_id"],
                    "milestone_6_custody_accessed": False,
                    "retry_allowed": False,
                    "status": "isolated_rating_instrument_failure",
                    "trace_ref_digest": f"sha256:{trace_ref.sha256}",
                    "trace_validation_error": result.trace_validation_error,
                }
            ),
            mode=0o644,
        )
        raise SystemExit(2)
    decision = validate_blind_pair_coverage(result.decision, expected_pairs)
    completion = json.loads((benchmark_output_root / "completion.json").read_text(encoding="utf-8"))
    receipt = IsolatedAIRatingReceipt(
        rating_id="isolated-rating-claude-repair-v1",
        benchmark_id=preregistration["benchmark_id"],
        presentation_sha256=sha256_file(packet_path),
        blind_report_digest=completion["blind_report_digest"],
        completion_receipt_digest=sha256_file(benchmark_output_root / "completion.json"),
        rating_contract_digest=result.rating_contract_digest,
        output_schema_digest=result.output_schema_digest,
        decision=decision,
        codex_cli_digest=preregistration["scorer"]["cli_digest"],
        execution_environment_digest=result.environment_digest,
        command_digest=result.command_digest,
        trace_digest=result.trace_digest,
        trace_ref_digest=f"sha256:{trace_ref.sha256}",
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
        reasoning_output_tokens=result.reasoning_output_tokens,
        rated_at=result.finished_at,
    )
    _exclusive_write(
        rating_output_root / "rating.json",
        _canonical_bytes(receipt),
        mode=0o644,
    )
    _exclusive_write(
        rating_output_root / "completion.json",
        _canonical_bytes(
            {
                "benchmark_id": preregistration["benchmark_id"],
                "condition_mapping_seen": False,
                "milestone_6_custody_accessed": False,
                "objective_scores_seen": False,
                "rated_at": result.finished_at,
                "rating_digest": sha256_file(rating_output_root / "rating.json"),
                "raw_retention_deadline": datetime.now(UTC) + timedelta(days=30),
                "status": "isolated_rating_complete",
                "trace_ref_digest": f"sha256:{trace_ref.sha256}",
            }
        ),
        mode=0o644,
    )


if __name__ == "__main__":
    main()
