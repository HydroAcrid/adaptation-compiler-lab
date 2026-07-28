"""Run the single condition-blind, tool-free compact-comparison judge."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.compact_execution import (
    CompactJudgeDecision,
    CompactProjectionBlindReport,
    compact_judge_schema,
    load_compact_execution_contract,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    load_compact_projection_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("judge payload must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def _create_key(path: Path) -> None:
    _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} is not a JSON object")
    return value


def _bindings(value: object) -> dict[str, tuple[str, str]]:
    if not isinstance(value, dict):
        raise RuntimeError("judge task bindings are malformed")
    result: dict[str, tuple[str, str]] = {}
    for task_id, raw_ids in value.items():
        if (
            not isinstance(task_id, str)
            or not isinstance(raw_ids, list)
            or len(raw_ids) != 2
            or not all(isinstance(item, str) for item in raw_ids)
            or len(set(raw_ids)) != 2
        ):
            raise RuntimeError("judge task bindings contain a malformed pair")
        result[task_id] = (raw_ids[0], raw_ids[1])
    return result


def _assert_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            "isolated judge failed its trace contract: "
            f"{result.trace_validation_error or 'unknown error'}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError("isolated judge used a tool or rerouted")
    if result.session_files_persisted:
        raise RuntimeError("isolated judge persisted session files")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError("isolated judge did not destroy temporary state")


def _validate_decision(
    decision: CompactJudgeDecision,
    expected: dict[str, tuple[str, str]],
) -> None:
    observed = {item.task_id: item.ordered_output_ids for item in decision.pair_ratings}
    if observed != expected:
        raise RuntimeError("judge response did not preserve the anonymous pair bindings")


def _raw_bundle(result: StructuredRoleRawResult, decision: CompactJudgeDecision) -> bytes:
    return _canonical_bytes(
        {
            "command_digest": result.command_digest,
            "contract_digest": result.contract_digest,
            "decision": decision.model_dump(mode="json", round_trip=True),
            "duration_seconds": result.duration_seconds,
            "environment_digest": result.environment_digest,
            "exit_code": result.exit_code,
            "finished_at": result.finished_at.isoformat(),
            "model": result.model,
            "prompt_digest": result.prompt_digest,
            "reasoning_effort": result.reasoning_effort,
            "response": result.response,
            "role_id": result.role_id,
            "service_mode": result.service_mode,
            "started_at": result.started_at.isoformat(),
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
            "trace_validation_error": result.trace_validation_error,
            "usage": {
                "cached_input_tokens": result.cached_input_tokens,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "reasoning_output_tokens": result.reasoning_output_tokens,
            },
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()

    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("Codex/OpenAI API keys are forbidden for the isolated judge")
    repo = arguments.repo.resolve()
    benchmark = repo / "development_benchmark_compact_projection"
    results = benchmark / "results"
    design = load_compact_projection_design(benchmark)
    contract = load_compact_execution_contract(benchmark, design=design)
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model=contract.model,
        reasoning_effort=contract.reasoning_effort,
        max_seconds=contract.max_seconds,
    )
    if arguments.preflight_only:
        print(
            canonical_json(
                {
                    "execution_contract_digest": contract.content_digest,
                    **runner.verify_preconditions(),
                }
            )
        )
        return

    blind_report = CompactProjectionBlindReport.model_validate_json(
        (results / "blind-report.json").read_bytes()
    )
    completion = _load_object(results / "completion.json")
    binding_document = _load_object(results / "judge-input-bindings.json")
    packet_path = results / "blind-rating-packet.md"
    packet_digest = sha256_file(packet_path)
    expected = _bindings(binding_document.get("ordered_output_ids_by_task"))
    if set(expected) != {task.task_id for task in design.tasks}:
        raise RuntimeError("judge bindings do not cover the frozen task set")
    if binding_document.get("blind_packet_digest") != packet_digest:
        raise RuntimeError("judge binding packet digest drifted")
    if binding_document.get("condition_mapping_withheld") is not True:
        raise RuntimeError("judge bindings did not preserve condition blinding")
    if completion.get("blind_report_digest") != blind_report.content_digest:
        raise RuntimeError("target completion no longer binds the blind report")
    if completion.get("judge_input_bindings_digest") != sha256_file(
        results / "judge-input-bindings.json"
    ):
        raise RuntimeError("target completion no longer binds the judge input")
    if blind_report.design_digest != design.content_digest:
        raise RuntimeError("blind report design binding drifted")
    if blind_report.execution_contract_digest != contract.content_digest:
        raise RuntimeError("blind report execution-contract binding drifted")
    if _git(repo, "status", "--porcelain"):
        raise RuntimeError("isolated judging requires a clean repository")

    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    public_receipt = results / "judge-receipt.json"
    if output_root.exists() or config_root.exists() or public_receipt.exists():
        raise RuntimeError("judge outputs already exist; refusing to overwrite")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    os.chmod(output_root, 0o700)
    os.chmod(config_root, 0o700)
    key_path = config_root / "judge-trace-encryption.key"
    _create_key(key_path)
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(key_path, workspace_root=repo),
    )
    developer_contract = (benchmark / "JUDGE_PACKET.md").read_text(encoding="utf-8")
    prompt = (
        "Return the required JSON object with one pair_ratings entry for every task. "
        "Copy each task_id and ordered_output_ids exactly from JUDGE BINDINGS. Treat First as "
        "the first ID and Second as the second ID. Analyze implementation quality, instruction "
        "adherence, blocker handling, and unsupported verification claims separately. Judge "
        "only the anonymous packet. Do not use tools and do not infer condition identity.\n\n"
        f"JUDGE BINDINGS\n{canonical_json({'ordered_output_ids_by_task': expected})}\n\n"
        f"ANONYMOUS PACKET\n{packet_path.read_text(encoding='utf-8')}"
    )
    print("Starting isolated blind quality judge (session 1/1).", flush=True)
    try:
        result = runner.run(
            role_id="compact-isolated-blind-judge",
            developer_contract=developer_contract,
            prompt=prompt,
            output_schema=compact_judge_schema(),
        )
        _assert_valid(result)
        decision = CompactJudgeDecision.model_validate_json(result.response)
        _validate_decision(decision, expected)
        raw_ref = raw_store.put(
            _raw_bundle(result, decision),
            media_type=("application/vnd.adaptation-compiler-lab.compact-judge+json"),
        )
    except BaseException as error:
        _exclusive_write(
            output_root / "failure.json",
            _canonical_bytes(
                {
                    "exception_message": str(error),
                    "exception_type": type(error).__name__,
                    "external_validation_accessed": False,
                    "provider_billed_calls": 0,
                    "retry_allowed": False,
                    "sessions_completed": 0,
                }
            ),
        )
        raise

    receipt = {
        "api_key_environment_present": False,
        "authentication": "saved_chatgpt",
        "blind_packet_digest": packet_digest,
        "condition_mapping_access": False,
        "decision": decision.model_dump(mode="json", round_trip=True),
        "decision_digest": canonical_digest(decision),
        "design_digest": design.content_digest,
        "execution_contract_digest": contract.content_digest,
        "external_validation_accessed": False,
        "judge_input_bindings_digest": sha256_file(results / "judge-input-bindings.json"),
        "model": result.model,
        "provider_billed_calls": 0,
        "reasoning_effort": result.reasoning_effort,
        "retry_allowed": False,
        "service_mode": result.service_mode,
        "session_files_persisted": result.session_files_persisted,
        "sessions": 1,
        "tool_use_observed": result.tool_use_observed,
        "trace_conformant": result.trace_conformant,
        "trace_digest": sha256_bytes(result.trace_bytes),
        "trace_ref_digest": f"sha256:{raw_ref.sha256}",
        "usage": {
            "cached_input_tokens": result.cached_input_tokens,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "reasoning_output_tokens": result.reasoning_output_tokens,
        },
    }
    _exclusive_write(public_receipt, _canonical_bytes(receipt), mode=0o644)
    _exclusive_write(
        output_root / "completion.json",
        _canonical_bytes(
            {
                "decision_digest": canonical_digest(decision),
                "external_validation_accessed": False,
                "judge_receipt_digest": sha256_file(public_receipt),
                "provider_billed_calls": 0,
                "sessions": 1,
            }
        ),
    )
    print("Isolated blind quality judge completed and frozen.", flush=True)


if __name__ == "__main__":
    main()
