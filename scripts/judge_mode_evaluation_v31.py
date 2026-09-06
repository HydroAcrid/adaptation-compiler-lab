"""Run condition-blind judges through the judge-only v3.1 trace repair."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationPublicPlanV1,
    ModeJudgeDecisionV1,
    load_mode_evaluation_contract,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    require_external_raw_root,
)
from adaptation_compiler_lab.runners.codex_mode_judge_v31 import CodexModeJudgeV31Runner
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from scripts.judge_mode_evaluation import (
    _assert_valid,
    _load_object,
    _packet,
    _pairs_for_mode,
    _raw_bundle,
    _strict_schema,
    _write_new,
)
from scripts.mode_evaluation_v3_common import validate_instrument_sources
from scripts.mode_evaluation_v31_judge_common import (
    require_valid_trace_smoke,
    validate_repair_sources,
)

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


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
        raise RuntimeError("API keys are forbidden for Mode evaluation v3.1 judges")
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    output_root = arguments.output_root.expanduser().resolve()
    if output_root != benchmark / "results-v3":
        raise RuntimeError("Mode v3.1 judge output must use the frozen results-v3 directory")
    contract = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v3.json")
    validate_instrument_sources(repo, contract)
    repair_contract = validate_repair_sources(repo)
    execution_contract = CodexExecutionContract(
        cli_version=contract.target_cli_version,
        cli_digest=contract.target_cli_digest,
        model=contract.judge_model,
        reasoning_effort=contract.judge_reasoning_effort,
        service_mode="standard",
        max_seconds=contract.judge_timeout_seconds,
    )
    runner = CodexModeJudgeV31Runner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        contract=execution_contract,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    smoke = require_valid_trace_smoke(repo, repair_contract=repair_contract)
    report = _load_object(output_root / "blind-trial-report.json")
    completion = _load_object(output_root / "completion.json")
    trials = report.get("trials")
    if (
        report.get("unblinded") is not False
        or report.get("contract_digest") != contract.content_digest
        or not isinstance(trials, list)
        or len(trials) != contract.target_runs
        or completion.get("report_digest") != canonical_digest(report)
    ):
        raise RuntimeError("Mode v3.1 judge requires the complete frozen blind trial report")
    if any(
        not isinstance(item, dict) or item.get("integrity_valid") is not True for item in trials
    ):
        raise RuntimeError("Mode v3.1 judge will not rate an integrity-invalid target grid")
    plan = ModeEvaluationPublicPlanV1.model_validate_json(
        (benchmark / "PUBLIC_PLAN-v3.json").read_text(encoding="utf-8"), strict=True
    )
    if plan.contract_digest != contract.content_digest:
        raise RuntimeError("Mode v3.1 judge plan is bound to another contract")
    judge_root = output_root / "judges-v31"
    if judge_root.exists():
        raise RuntimeError("Mode v3.1 judge receipts already exist")
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
            role_id=f"mode-evaluation-v31-blind-judge-{mode_id}",
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
            raise RuntimeError("Mode v3.1 judge returned a different Mode ID")
        observed = {item.task_id: item.ordered_output_ids for item in decision.pair_ratings}
        if observed != pairs:
            raise RuntimeError("Mode v3.1 judge changed anonymous pair bindings")
        raw_ref = raw_store.put(
            _raw_bundle(result, decision),
            media_type="application/vnd.temper.mode-evaluation-v31-judge+json",
        )
        receipt: dict[str, object] = {
            "receipt_version": "3.1.0",
            "repair_contract_digest": canonical_digest(repair_contract),
            "trace_smoke_receipt_digest": canonical_digest(smoke),
            "api_key_environment_present": False,
            "authentication": "saved_chatgpt",
            "blind_packet_digest": canonical_digest({"packet": packet}),
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
