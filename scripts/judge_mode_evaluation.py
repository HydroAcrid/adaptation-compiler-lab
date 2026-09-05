"""Run three fresh condition-blind quality judges over frozen Mode outputs."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationFixtureV1,
    ModeEvaluationPublicPlanV1,
    ModeJudgeDecisionV1,
    load_mode_evaluation_contract,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    require_external_raw_root,
)
from adaptation_compiler_lab.runners.codex_mode_judge import CodexModeJudgeRunner
from adaptation_compiler_lab.runners.codex_structured_role import StructuredRoleRawResult
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _write_new(path: Path, value: dict[str, object], *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (canonical_json(value) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _load_object(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"invalid Mode evaluation file: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"Mode evaluation file is not an object: {path.name}")
    return cast(JsonObject, value)


def _strict_schema() -> dict[str, object]:
    schema = ModeJudgeDecisionV1.model_json_schema()

    def normalize(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            prefix = node.get("prefixItems")
            if isinstance(prefix, list) and prefix and "items" not in node:
                if not all(item == prefix[0] for item in prefix):
                    raise RuntimeError("Mode judge tuple has heterogeneous item schemas")
                node["items"] = prefix[0]
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


def _pairs_for_mode(
    plan: ModeEvaluationPublicPlanV1,
    *,
    task_ids: tuple[str, ...],
) -> dict[str, tuple[str, str]]:
    pairs: dict[str, tuple[str, str]] = {}
    for task_id in task_ids:
        cells = tuple(item for item in plan.run_order if item.task_id == task_id)
        if len(cells) != 2:
            raise RuntimeError("Mode judge requires exactly two outputs per task")
        ordered = tuple(
            item.blind_output_id for item in sorted(cells, key=lambda item: item.sequence)
        )
        pairs[task_id] = cast(tuple[str, str], ordered)
    return pairs


def _packet(
    *,
    mode_id: str,
    fixtures: dict[str, ModeEvaluationFixtureV1],
    pairs: dict[str, tuple[str, str]],
    output_root: Path,
) -> str:
    sections: list[str] = []
    for task_id, output_ids in pairs.items():
        fixture = fixtures[task_id]
        prompt = fixture.prompt
        kind = fixture.kind
        sections.append(f"## Task {task_id} ({kind})\n\n{prompt}\n")
        for label, output_id in zip(("First", "Second"), output_ids, strict=True):
            value = _load_object(output_root / "anonymous-outputs" / f"{output_id}.json")
            if value.get("blind_output_id") != output_id or value.get("task_id") != task_id:
                raise RuntimeError("anonymous Mode output binding drifted")
            sections.append(
                f"### {label}: {output_id}\n\n"
                f"Visible tests passed: {value.get('visible_tests_passed') is True}\n\n"
                f"Diff:\n```diff\n{value.get('diff', '')}\n```\n\n"
                f"Final response:\n{value.get('final_response', '')}\n"
            )
    return f"# Condition-blind quality packet for {mode_id}\n\n" + "\n".join(sections)


def _assert_valid(result: StructuredRoleRawResult) -> None:
    if not result.trace_conformant:
        raise RuntimeError(
            "Mode judge failed its trace contract: "
            f"{result.trace_validation_error or 'unknown error'}"
        )
    if result.tool_use_observed or result.model_reroute_observed:
        raise RuntimeError("Mode judge used a tool or rerouted")
    if result.session_files_persisted:
        raise RuntimeError("Mode judge persisted session files")
    if not result.config_destroyed or not result.workspace_destroyed:
        raise RuntimeError("Mode judge did not destroy temporary state")


def _raw_bundle(result: StructuredRoleRawResult, decision: ModeJudgeDecisionV1) -> bytes:
    value = {
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
    return (canonical_json(value) + "\n").encode("utf-8")


def _validate_instrument_sources(repo: Path, contract: object) -> None:
    expected = {
        "runner_source_digest": sha256_file(repo / "scripts/run_mode_evaluation.py"),
        "scorer_source_digest": sha256_file(repo / "scripts/score_mode_evaluation_task.py"),
        "observer_source_digest": sha256_file(repo / "scripts/observe_mode_evaluation_policy.py"),
        "judge_role_runner_source_digest": sha256_file(
            repo / "src/adaptation_compiler_lab/runners/codex_mode_judge.py"
        ),
        "judge_source_digest": sha256_file(repo / "scripts/judge_mode_evaluation.py"),
        "unblind_source_digest": sha256_file(repo / "scripts/unblind_mode_evaluation.py"),
    }
    for field, observed in expected.items():
        if getattr(contract, field) != observed:
            raise RuntimeError(f"Mode evaluation {field} drifted")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--raw-key-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for Mode evaluation judges")
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    output_root = arguments.output_root.expanduser().resolve()
    if output_root != benchmark / "results-v1":
        raise RuntimeError("Mode judge output must use the frozen results-v1 directory")
    contract = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v1.json")
    _validate_instrument_sources(repo, contract)
    execution_contract = CodexExecutionContract(
        cli_version=contract.target_cli_version,
        cli_digest=contract.target_cli_digest,
        model=contract.judge_model,
        reasoning_effort=contract.judge_reasoning_effort,
        service_mode="standard",
        max_seconds=contract.judge_timeout_seconds,
    )
    runner = CodexModeJudgeRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        contract=execution_contract,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    report = _load_object(output_root / "blind-trial-report.json")
    completion = _load_object(output_root / "completion.json")
    trials = report.get("trials")
    if (
        report.get("unblinded") is not False
        or not isinstance(trials, list)
        or len(trials) != contract.target_runs
        or completion.get("report_digest") != canonical_digest(report)
    ):
        raise RuntimeError("Mode judge requires the complete frozen blind trial report")
    if any(
        not isinstance(item, dict) or item.get("integrity_valid") is not True for item in trials
    ):
        raise RuntimeError("Mode judge will not rate an integrity-invalid target grid")
    plan = ModeEvaluationPublicPlanV1.model_validate_json(
        (benchmark / "PUBLIC_PLAN-v1.json").read_text(encoding="utf-8"), strict=True
    )
    if plan.contract_digest != contract.content_digest:
        raise RuntimeError("Mode judge plan is bound to another contract")
    judge_root = output_root / "judges"
    if judge_root.exists():
        raise RuntimeError("Mode judge receipts already exist")
    raw_root = require_external_raw_root(arguments.raw_root, workspace_root=repo)
    raw_key = RawEncryptionKey.from_file(arguments.raw_key_file, workspace_root=repo)
    raw_store = LocalRawPayloadStore(raw_root, encryption_key=raw_key)
    fixtures = {item.task_id: item for item in contract.fixtures}
    pending: list[tuple[str, dict[str, object]]] = []
    schema = _strict_schema()
    for mode_id in sorted({item.mode_id for item in contract.fixtures}):
        task_ids = tuple(
            sorted(item.task_id for item in contract.fixtures if item.mode_id == mode_id)
        )
        pairs = _pairs_for_mode(plan, task_ids=task_ids)
        packet = _packet(
            mode_id=mode_id,
            fixtures=fixtures,
            pairs=pairs,
            output_root=output_root,
        )
        prompt = (
            "Return one pair_ratings entry for every task, sorted by task_id. Copy mode_id, "
            "task_id, and ordered_output_ids exactly from JUDGE BINDINGS. Judge the actual patch "
            "before the self-report. Compare implementation quality, instruction adherence, "
            "blocker handling, maintainability, and unsupported verification claims. The hidden "
            "automated scores and condition identities are unavailable. A tie uses null. Use no "
            f"tools and do not infer condition identity.\n\nJUDGE BINDINGS\n"
            f"{canonical_json({'mode_id': mode_id, 'pairs': pairs})}\n\n{packet}"
        )
        print(f"running fresh blind judge for {mode_id}", flush=True)
        result = runner.run(
            role_id=f"mode-evaluation-blind-judge-{mode_id}",
            developer_contract=(
                "You are a fresh condition-blind software-quality judge with no prior context, "
                "tools, repository, automated scores, condition material, condition mapping, or "
                "external study access. Return only strict JSON matching the supplied schema."
            ),
            prompt=prompt,
            output_schema=schema,
        )
        _assert_valid(result)
        decision = ModeJudgeDecisionV1.model_validate_json(result.response, strict=True)
        if decision.mode_id != mode_id:
            raise RuntimeError("Mode judge returned a different Mode ID")
        observed = {item.task_id: item.ordered_output_ids for item in decision.pair_ratings}
        if observed != pairs:
            raise RuntimeError("Mode judge changed anonymous pair bindings")
        raw_ref = raw_store.put(
            _raw_bundle(result, decision),
            media_type="application/vnd.temper.mode-evaluation-judge+json",
        )
        receipt: dict[str, object] = {
            "receipt_version": "1.0.0",
            "api_key_environment_present": False,
            "authentication": "saved_chatgpt",
            "blind_packet_digest": sha256_bytes(packet.encode("utf-8")),
            "blind_report_digest": canonical_digest(report),
            "condition_mapping_access": False,
            "decision": decision.model_dump(mode="json", round_trip=True),
            "decision_digest": decision.content_digest,
            "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
            "external_validation_accessed": False,
            "model": result.model,
            "provider_billed_calls": 0,
            "reasoning_effort": result.reasoning_effort,
            "session_count": 1,
        }
        pending.append((mode_id, receipt))
    judge_root.mkdir(parents=True, exist_ok=False)
    for mode_id, receipt in pending:
        _write_new(judge_root / f"{mode_id}.json", receipt)
    _write_new(
        judge_root / "completion.json",
        {
            "judge_receipt_digests": {
                mode_id: canonical_digest(receipt) for mode_id, receipt in pending
            },
            "session_count": len(pending),
        },
    )


if __name__ == "__main__":
    main()
