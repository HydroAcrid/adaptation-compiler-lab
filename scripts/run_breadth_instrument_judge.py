"""Run the isolated blind judge for the clean four-family breadth gate."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentJudgeDecision,
    BreadthInstrumentPublicPlan,
    load_breadth_instrument_contract,
    load_breadth_instrument_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    StructuredRoleRawResult,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from scripts.run_durable_progress_comparison import _create_key

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return (canonical_json(value) + "\n").encode()


def _strict_schema() -> dict[str, object]:
    schema = BreadthInstrumentJudgeDecision.model_json_schema()

    def normalize(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            prefix = node.get("prefixItems")
            if isinstance(prefix, list) and prefix and "items" not in node:
                if not all(item == prefix[0] for item in prefix):
                    raise RuntimeError("clean breadth judge tuple has heterogeneous schemas")
                node["items"] = prefix[0]
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


def _assert_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            "clean breadth judge failed its trace contract: "
            f"{result.trace_validation_error or 'unknown error'}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError("clean breadth judge used a tool or rerouted")
    if result.session_files_persisted:
        raise RuntimeError("clean breadth judge persisted session files")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError("clean breadth judge did not destroy temporary state")


def _pairs(plan: BreadthInstrumentPublicPlan) -> dict[str, tuple[str, str]]:
    pairs: dict[str, tuple[str, str]] = {}
    for index in range(0, 8, 2):
        first = plan.run_order[index]
        second = plan.run_order[index + 1]
        if first.task_id != second.task_id:
            raise RuntimeError("clean breadth plan is not paired by task")
        pairs[first.task_id] = (first.blind_output_id, second.blind_output_id)
    if len(pairs) != 4:
        raise RuntimeError("clean breadth plan does not contain four pairs")
    return pairs


def _packet(root: Path, pairs: dict[str, tuple[str, str]]) -> str:
    tasks = {item.task_id: item.task for item in load_breadth_instrument_design(root).tasks}
    outputs = root / "results-v1/anonymous-outputs"
    sections = []
    for task_id, output_ids in pairs.items():
        task = tasks[task_id]
        sections.append(f"## Task {task_id}\n\n{task.prompt}\n")
        for label, output_id in zip(("First", "Second"), output_ids, strict=True):
            value = json.loads((outputs / f"{output_id}.json").read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("blind_output_id") != output_id:
                raise RuntimeError("clean breadth anonymous output binding drifted")
            sections.append(
                f"### {label}: {output_id}\n\n"
                f"Allowed paths: {canonical_json({'paths': value['allowed_change_paths']})}\n\n"
                f"Visible tests executed: {value['visible_test_executed']}\n\n"
                f"Diff:\n```diff\n{value['diff']}\n```\n\n"
                f"Final response:\n{value['final_response']}\n"
            )
    return "\n".join(sections)


def _raw_bundle(
    result: StructuredRoleRawResult,
    decision: BreadthInstrumentJudgeDecision,
) -> bytes:
    return _canonical_bytes(
        {
            "command_digest": result.command_digest,
            "decision": decision.model_dump(mode="json", round_trip=True),
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
            "timed_out": result.timed_out,
            "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
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
        raise RuntimeError("API keys are forbidden for the clean breadth judge")
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_instrument_repair"
    design = load_breadth_instrument_design(root)
    contract = load_breadth_instrument_contract(root, design=design)
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model=contract.judge_model,
        reasoning_effort=contract.judge_reasoning_effort,
        max_seconds=contract.max_seconds_per_session,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    results = root / "results-v1"
    report_path = results / "blind-report.json"
    completion = json.loads((results / "completion.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(completion, dict)
        or not isinstance(report, dict)
        or completion.get("blind_report_digest") != sha256_file(report_path)
        or report.get("instrument_valid") is not True
        or report.get("condition_mapping_withheld") is not True
    ):
        raise RuntimeError("clean breadth judge requires a complete valid blind report")
    public = BreadthInstrumentPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    pairs = _pairs(public)
    packet = _packet(root, pairs)
    prompt = (
        "Return one pair_ratings entry for every task. Copy task_id and ordered_output_ids exactly "
        "from JUDGE BINDINGS. Judge implementation quality, instruction adherence, blocker "
        "handling, maintainability, and unsupported verification claims. Visible-test execution "
        "is evidence, but no unshown score is available. Use no tools and do not infer condition "
        f"identity.\n\nJUDGE BINDINGS\n{canonical_json({'pairs': pairs})}\n\n{packet}"
    )
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    receipt_path = results / "judge-receipt.json"
    if output_root.exists() or config_root.exists() or receipt_path.exists():
        raise RuntimeError("clean breadth judge output already exists")
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
        role_id="breadth-instrument-condition-blind-judge",
        developer_contract=(
            "You are a fresh condition-blind software-quality judge. You have no tools, "
            "repository, model-condition material, automated scores, condition mapping, external "
            "study, or prior context. Return only JSON matching the schema. A tie uses null; a "
            "non-tie selects the exact corresponding output ID."
        ),
        prompt=prompt,
        output_schema=_strict_schema(),
    )
    _assert_valid(result)
    decision = BreadthInstrumentJudgeDecision.model_validate_json(result.response)
    observed = {item.task_id: item.ordered_output_ids for item in decision.pair_ratings}
    if observed != pairs:
        raise RuntimeError("clean breadth judge changed anonymous pair bindings")
    raw_ref = raw_store.put(
        _raw_bundle(result, decision),
        media_type="application/vnd.adaptation-compiler-lab.breadth-instrument-judge+json",
    )
    receipt: dict[str, object] = {
        "receipt_version": "1.0.0",
        "api_key_environment_present": False,
        "authentication": "saved_chatgpt",
        "blind_packet_digest": sha256_bytes(packet.encode()),
        "blind_report_digest": sha256_file(report_path),
        "condition_mapping_access": False,
        "decision": decision.model_dump(mode="json", round_trip=True),
        "decision_digest": canonical_digest(decision),
        "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
        "external_validation_accessed": False,
        "model": result.model,
        "provider_billed_calls": 0,
        "reasoning_effort": result.reasoning_effort,
    }
    _exclusive_write(receipt_path, _canonical_bytes(receipt), mode=0o644)


if __name__ == "__main__":
    main()
