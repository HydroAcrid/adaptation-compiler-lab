"""Run the single isolated condition-blind Milestone 6A.3 judge."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairTaskChannelJudgeDecision,
    TaskChannelComparisonPublicPlan,
    load_task_channel_contract,
    load_task_channel_design,
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
    return (canonical_json(value) + "\n").encode("utf-8")


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


def _expected_pairs(
    plan: TaskChannelComparisonPublicPlan,
) -> dict[str, tuple[str, str]]:
    pairs: dict[str, tuple[str, str]] = {}
    for index in range(0, 12, 2):
        first = plan.run_order[index]
        second = plan.run_order[index + 1]
        if first.task_id != second.task_id:
            raise RuntimeError("public plan is not block-paired by task")
        pairs[first.task_id] = (first.blind_output_id, second.blind_output_id)
    if len(pairs) != 6:
        raise RuntimeError("public plan does not contain six task pairs")
    return pairs


def _packet(
    *,
    root: Path,
    pairs: dict[str, tuple[str, str]],
) -> str:
    tasks = {task.task_id: task for task in load_task_channel_design(root).tasks}
    outputs_root = root / "results-v1/anonymous-outputs"
    sections: list[str] = []
    for task_id, output_ids in pairs.items():
        task = tasks[task_id]
        sections.append(f"## Task {task_id}\n\n{task.task_prompt}\n")
        for label, output_id in zip(("First", "Second"), output_ids, strict=True):
            value = json.loads((outputs_root / f"{output_id}.json").read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("blind_output_id") != output_id:
                raise RuntimeError("anonymous judge output binding drifted")
            sections.append(
                f"### {label}: {output_id}\n\n"
                f"Allowed paths: {canonical_json({'paths': value['allowed_change_paths']})}\n\n"
                f"Visible tests executed: {value['visible_test_executed']}\n\n"
                f"Diff:\n```diff\n{value['diff']}\n```\n\n"
                f"Final response:\n{value['final_response']}\n"
            )
    return "\n".join(sections)


def _raw_bundle(
    *,
    result: StructuredRoleRawResult,
    decision: FairTaskChannelJudgeDecision,
) -> bytes:
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


def _failed_raw_bundle(*, result: StructuredRoleRawResult) -> bytes:
    return _canonical_bytes(
        {
            "command_digest": result.command_digest,
            "contract_digest": result.contract_digest,
            "duration_seconds": result.duration_seconds,
            "environment_digest": result.environment_digest,
            "exit_code": result.exit_code,
            "finished_at": result.finished_at.isoformat(),
            "model": result.model,
            "prompt_digest": result.prompt_digest,
            "reasoning_effort": result.reasoning_effort,
            "response": result.response,
            "role_id": result.role_id,
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


def _terminal_failure_summary(trace: bytes) -> dict[str, object]:
    try:
        events = tuple(
            json.loads(line) for line in trace.decode("utf-8").splitlines() if line.strip()
        )
    except (UnicodeDecodeError, ValueError):
        return {"trace_parseable": False}
    terminal = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") in {"turn.completed", "turn.failed"}
    ]
    summary: dict[str, object] = {
        "event_count": len(events),
        "terminal_count": len(terminal),
        "trace_parseable": True,
    }
    if len(terminal) == 1:
        summary["terminal_type"] = terminal[0].get("type")
        error = terminal[0].get("error")
        if isinstance(error, dict):
            summary["error_code"] = error.get("code")
            message = error.get("message")
            if isinstance(message, str):
                summary["error_message"] = message[:500]
    return summary


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
    root = repo / "development_benchmark_task_channel_comparison"
    design = load_task_channel_design(root)
    contract = load_task_channel_contract(root, design=design)
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model=contract.judge_model,
        reasoning_effort=contract.judge_reasoning_effort,
        max_seconds=600,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    results = root / "results-v1"
    completion = json.loads((results / "completion.json").read_text(encoding="utf-8"))
    blind_report_path = results / "blind-report.json"
    blind_report = json.loads(blind_report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(completion, dict)
        or not isinstance(blind_report, dict)
        or completion.get("blind_report_digest") != sha256_file(blind_report_path)
        or blind_report.get("instrument_valid") is not True
        or blind_report.get("condition_mapping_withheld") is not True
    ):
        raise RuntimeError("isolated judge requires a complete integrity-valid blind report")
    plan = TaskChannelComparisonPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    pairs = _expected_pairs(plan)
    packet = _packet(root=root, pairs=pairs)
    packet_digest = sha256_bytes(packet.encode("utf-8"))
    prompt = (
        "Return the required JSON object with one pair_ratings entry for every task. Copy each "
        "task_id and ordered_output_ids exactly from JUDGE BINDINGS. Treat First as the first ID "
        "and Second as the second ID. Judge implementation quality, instruction adherence, "
        "blocker handling, maintainability, and unsupported verification claims separately. "
        "The visible-test fact is evidence; do not assume unshown tests or scores. Use only this "
        "anonymous packet, use no tools, and do not infer condition identity.\n\n"
        f"JUDGE BINDINGS\n{canonical_json({'ordered_output_ids_by_task': pairs})}\n\n"
        f"ANONYMOUS PACKET\n{packet}"
    )
    developer_contract = (
        "You are a fresh condition-blind software-quality judge. You have no prior context, tools, "
        "repository, model-condition material, automated scores, or condition mapping. Return "
        "only JSON matching the supplied schema. A tie must use preferred_output_id null. A "
        "non-tie must "
        "select the corresponding exact output ID. Do not reward forbidden path changes, skipped "
        "verification, overclaiming, or behavior outside the task."
    )
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    receipt_path = results / "judge-receipt.json"
    if output_root.exists() or config_root.exists() or receipt_path.exists():
        raise RuntimeError("fair comparison judge outputs already exist")
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
        role_id="fair-task-channel-isolated-judge",
        developer_contract=developer_contract,
        prompt=prompt,
        output_schema=FairTaskChannelJudgeDecision.model_json_schema(),
    )
    if not result.trace_conformant:
        raw_ref = raw_store.put(
            _failed_raw_bundle(result=result),
            media_type=(
                "application/vnd.adaptation-compiler-lab.fair-task-channel-judge-failure+json"
            ),
        )
        failure_receipt = {
            "receipt_version": "1.0.0",
            "condition_mapping_access": False,
            "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
            "external_validation_accessed": False,
            "provider_billed_calls": 0,
            "terminal": _terminal_failure_summary(result.trace_bytes),
            "trace_validation_error": result.trace_validation_error,
        }
        _exclusive_write(
            output_root / "failure-receipt.json",
            _canonical_bytes(failure_receipt),
        )
    _assert_valid(result)
    decision = FairTaskChannelJudgeDecision.model_validate_json(result.response)
    observed = {item.task_id: item.ordered_output_ids for item in decision.pair_ratings}
    if observed != pairs:
        raise RuntimeError("judge response did not preserve anonymous pair bindings")
    raw_ref = raw_store.put(
        _raw_bundle(result=result, decision=decision),
        media_type="application/vnd.adaptation-compiler-lab.fair-task-channel-judge+json",
    )
    receipt: dict[str, object] = {
        "receipt_version": "1.0.0",
        "api_key_environment_present": False,
        "authentication": "saved_chatgpt",
        "blind_packet_digest": packet_digest,
        "blind_report_digest": sha256_file(blind_report_path),
        "condition_mapping_access": False,
        "decision": decision.model_dump(mode="json", round_trip=True),
        "decision_digest": canonical_digest(decision),
        "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
        "external_validation_accessed": False,
        "model": result.model,
        "provider_billed_calls": 0,
        "reasoning_effort": result.reasoning_effort,
        "session_count": 1,
        "usage": {
            "cached_input_tokens": result.cached_input_tokens,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "reasoning_output_tokens": result.reasoning_output_tokens,
        },
    }
    _exclusive_write(receipt_path, _canonical_bytes(receipt), mode=0o644)


if __name__ == "__main__":
    main()
