"""Run one fresh tool-free condition-blind judge for Milestone 6A.5."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import cast

import jsonschema

from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.serialization import canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _create_key(path: Path) -> None:
    _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")


def _schema(output_ids: tuple[str, str]) -> dict[str, object]:
    rating = {
        "type": "object",
        "properties": {
            "turn": {"type": "integer", "minimum": 1, "maximum": 15},
            "task_id": {"type": "string", "minLength": 1},
            "ordered_output_ids": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "string", "minLength": 1},
            },
            "winner": {"enum": ["first", "second", "tie"]},
            "confidence": {"enum": ["low", "medium", "high"]},
            "rationale": {"type": "string", "minLength": 1},
        },
        "required": [
            "turn",
            "task_id",
            "ordered_output_ids",
            "winner",
            "confidence",
            "rationale",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "judge_version": {"const": "1.0.0"},
            "task_ratings": {
                "type": "array",
                "minItems": 13,
                "maxItems": 13,
                "items": rating,
            },
            "overall_winner_output_id": {"enum": [*output_ids, "tie"]},
            "overall_rationale": {"type": "string", "minLength": 1},
        },
        "required": [
            "judge_version",
            "task_ratings",
            "overall_winner_output_id",
            "overall_rationale",
        ],
        "additionalProperties": False,
    }


def _assert_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            f"long-horizon judge trace failed: {result.trace_validation_error or 'unknown error'}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError("long-horizon judge used a tool or rerouted")
    if result.session_files_persisted:
        raise RuntimeError("long-horizon judge persisted session files")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError("long-horizon judge did not destroy temporary state")


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
        raise RuntimeError("API keys are forbidden for the long-horizon judge")
    repo = arguments.repo.expanduser().resolve()
    root = repo / "development_benchmark_long_horizon"
    results = root / "results-v1"
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        max_seconds=1200,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    completion = json.loads((results / "BLIND_COMPLETION-v1.json").read_text())
    bindings = json.loads((results / "JUDGE_BINDINGS-v1.json").read_text())
    packet_path = results / "JUDGE_PACKET-v1.md"
    if (
        completion.get("condition_mapping_withheld") is not True
        or completion.get("instrument_valid") is not True
        or completion.get("judge_packet_digest") != sha256_file(packet_path)
        or bindings.get("condition_mapping_withheld") is not True
        or bindings.get("automated_scores_included") is not False
    ):
        raise RuntimeError("long-horizon judge requires a complete blind packet")
    output_ids = tuple(
        sorted(
            {
                output_id
                for item in cast(list[dict[str, object]], bindings["task_ratings"])
                for output_id in cast(list[str], item["ordered_output_ids"])
            }
        )
    )
    if len(output_ids) != 2:
        raise RuntimeError("long-horizon judge bindings must contain two output IDs")
    prompt = (
        "Return exactly 13 task_ratings in the JUDGE BINDINGS order. Copy each turn, task_id, "
        "and ordered_output_ids exactly. Set winner to first, second, or tie relative to each "
        "task's ordered_output_ids. Set overall_winner_output_id to one exact anonymous output ID "
        "or tie. Select an overall winner only if one anonymous episode is meaningfully stronger "
        "across the sequence. You have no tools and no other context."
        f"\n\nJUDGE BINDINGS\n{canonical_json(bindings)}\n\n"
        f"{packet_path.read_text(encoding='utf-8')}"
    )
    output_root = arguments.output_root.expanduser().resolve()
    config_root = arguments.config_root.expanduser().resolve()
    receipt_path = results / "JUDGE_RECEIPT-v1.json"
    if output_root.exists() or config_root.exists() or receipt_path.exists():
        raise RuntimeError("long-horizon judge outputs already exist")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    _create_key(config_root / "trace-encryption.key")
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key",
            workspace_root=repo,
        ),
    )
    result = runner.run(
        role_id="long-horizon-condition-blind-judge",
        developer_contract=(
            "You are a fresh condition-blind software-quality judge with no tools, repository, "
            "automated scores, condition material, condition mapping, external study, or prior "
            "context. Judge only the packet. Return only JSON matching the supplied schema."
        ),
        prompt=prompt,
        output_schema=_schema(output_ids),
    )
    _assert_valid(result)
    decision = json.loads(result.response)
    jsonschema.validate(decision, _schema(output_ids))
    expected: tuple[tuple[object, object, tuple[str, ...]], ...] = tuple(
        (
            item["turn"],
            item["task_id"],
            tuple(cast(list[str], item["ordered_output_ids"])),
        )
        for item in cast(list[dict[str, object]], bindings["task_ratings"])
    )
    observed: tuple[tuple[object, object, tuple[str, ...]], ...] = tuple(
        (
            item["turn"],
            item["task_id"],
            tuple(cast(list[str], item["ordered_output_ids"])),
        )
        for item in cast(list[dict[str, object]], decision["task_ratings"])
    )
    if observed != expected:
        raise RuntimeError("long-horizon judge changed anonymous bindings")
    raw_payload = {
        "command_digest": result.command_digest,
        "decision": decision,
        "duration_seconds": result.duration_seconds,
        "environment_digest": result.environment_digest,
        "exit_code": result.exit_code,
        "finished_at": result.finished_at.isoformat(),
        "model": result.model,
        "prompt_digest": result.prompt_digest,
        "reasoning_effort": result.reasoning_effort,
        "response": result.response,
        "started_at": result.started_at.isoformat(),
        "stderr": result.stderr,
        "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
        "usage": {
            "cached_input_tokens": result.cached_input_tokens,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "reasoning_output_tokens": result.reasoning_output_tokens,
        },
    }
    raw_ref = raw_store.put(
        (canonical_json(raw_payload) + "\n").encode("utf-8"),
        media_type="application/vnd.acl.long-horizon-judge+json",
    )
    receipt = {
        "receipt_version": "1.0.0",
        "authentication": "saved_chatgpt",
        "model": result.model,
        "reasoning_effort": result.reasoning_effort,
        "blind_packet_digest": sha256_file(packet_path),
        "condition_mapping_accessed": False,
        "automated_scores_accessed": False,
        "decision": decision,
        "decision_digest": sha256_bytes((canonical_json(decision) + "\n").encode("utf-8")),
        "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
    }
    _exclusive_write(
        receipt_path,
        (canonical_json(receipt) + "\n").encode("utf-8"),
        mode=0o644,
    )
    print(
        canonical_json(
            {
                "condition_mapping_accessed": False,
                "decision_digest": receipt["decision_digest"],
                "provider_billed_calls": 0,
                "task_ratings": 13,
            }
        )
    )


if __name__ == "__main__":
    main()
