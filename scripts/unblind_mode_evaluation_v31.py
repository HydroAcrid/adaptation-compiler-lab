"""Unblind the v3 targets only after all repaired v3.1 judges are recorded."""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationPublicPlanV1,
    ModeEvaluationResultV1,
    ModeJudgeDecisionV1,
    build_mode_evaluation_plan,
    load_mode_evaluation_contract,
)
from adaptation_compiler_lab.serialization import canonical_digest
from scripts.mode_evaluation_v3_common import (
    require_valid_smoke,
    validate_instrument_sources,
)
from scripts.mode_evaluation_v31_judge_common import (
    require_valid_trace_smoke,
    validate_repair_sources,
)
from scripts.unblind_mode_evaluation import (
    Condition,
    _load_object,
    _markdown,
    _write_new,
    build_mode_outcome,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    results = benchmark / "results-v3"
    result_path = results / "unblinded-result-v31.json"
    markdown_path = results / "MODE_EVALUATION_RESULT-v31.md"
    if result_path.exists() or markdown_path.exists():
        raise RuntimeError("Mode evaluation v3.1 has already been unblinded")
    contract = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v3.json")
    validate_instrument_sources(repo, contract)
    smoke = require_valid_smoke(benchmark=benchmark, contract=contract)
    repair_contract = validate_repair_sources(repo)
    judge_smoke = require_valid_trace_smoke(repo, repair_contract=repair_contract)
    seed_path = arguments.seed_file.expanduser().resolve()
    if seed_path.is_relative_to(repo) or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("Mode evaluation v3.1 seed boundary is invalid")
    public, private = build_mode_evaluation_plan(contract, seed=seed_path.read_bytes())
    frozen_public = ModeEvaluationPublicPlanV1.model_validate_json(
        (benchmark / "PUBLIC_PLAN-v3.json").read_text(encoding="utf-8"), strict=True
    )
    if public != frozen_public:
        raise RuntimeError("Mode evaluation v3.1 seed does not reproduce the public plan")
    report = _load_object(results / "blind-trial-report.json")
    completion = _load_object(results / "completion.json")
    raw_trials = report.get("trials")
    if (
        report.get("contract_digest") != contract.content_digest
        or report.get("public_plan_digest") != public.content_digest
        or report.get("smoke_receipt_digest") != canonical_digest(smoke)
        or report.get("unblinded") is not False
        or not isinstance(raw_trials, list)
        or len(raw_trials) != 30
        or completion.get("report_digest") != canonical_digest(report)
    ):
        raise RuntimeError("Mode evaluation v3.1 blind report is incomplete or drifted")
    public_cells = {item.run_id: item for item in public.run_order}
    if {cast(str, item.get("run_id")) for item in raw_trials if isinstance(item, dict)} != set(
        public_cells
    ):
        raise RuntimeError("Mode evaluation v3.1 trial coverage does not match its public plan")
    assignments = cast(list[dict[str, object]], private["condition_assignments"])
    condition_by_blind = {
        str(item["blind_condition_id"]): cast(Condition, item["condition"]) for item in assignments
    }
    trials_by_task: dict[str, dict[Condition, JsonObject]] = defaultdict(dict)
    output_conditions: dict[str, Condition] = {}
    for raw in raw_trials:
        if not isinstance(raw, dict):
            raise RuntimeError("Mode evaluation v3.1 trial is not an object")
        trial = raw
        run_id = cast(str, trial["run_id"])
        cell = public_cells[run_id]
        if (
            trial.get("task_id") != cell.task_id
            or trial.get("blind_condition_id") != cell.blind_condition_id
            or trial.get("blind_output_id") != cell.blind_output_id
        ):
            raise RuntimeError("Mode evaluation v3.1 trial changed its public binding")
        condition = condition_by_blind[cell.blind_condition_id]
        if condition in trials_by_task[cell.task_id]:
            raise RuntimeError("Mode evaluation v3.1 repeated a task-condition cell")
        trials_by_task[cell.task_id][condition] = trial
        output_conditions[cell.blind_output_id] = condition
    judge_completion = _load_object(results / "judges-v31/completion.json")
    receipt_digests = judge_completion.get("judge_receipt_digests")
    if not isinstance(receipt_digests, dict) or judge_completion.get("session_count") != 3:
        raise RuntimeError("Mode evaluation v3.1 judge completion receipt is invalid")
    decisions: dict[str, ModeJudgeDecisionV1] = {}
    for mode_id in sorted({item.mode_id for item in contract.fixtures}):
        receipt = _load_object(results / "judges-v31" / f"{mode_id}.json")
        if (
            receipt_digests.get(mode_id) != canonical_digest(receipt)
            or receipt.get("blind_report_digest") != canonical_digest(report)
            or receipt.get("condition_mapping_access") is not False
            or receipt.get("provider_billed_calls") != 0
            or receipt.get("model") != contract.judge_model
            or receipt.get("reasoning_effort") != contract.judge_reasoning_effort
            or receipt.get("repair_contract_digest") != canonical_digest(repair_contract)
            or receipt.get("trace_smoke_receipt_digest") != canonical_digest(judge_smoke)
        ):
            raise RuntimeError("Mode evaluation v3.1 judge receipt is invalid or unblinded")
        decision = ModeJudgeDecisionV1.model_validate(receipt.get("decision"), strict=True)
        if decision.mode_id != mode_id or receipt.get("decision_digest") != decision.content_digest:
            raise RuntimeError("Mode evaluation v3.1 judge decision binding drifted")
        decisions[mode_id] = decision
    outcomes = tuple(
        build_mode_outcome(
            mode_id=mode_id,
            fixtures=tuple(item for item in contract.fixtures if item.mode_id == mode_id),
            trials_by_task=trials_by_task,
            decision=decisions[mode_id],
            output_conditions=output_conditions,
        )
        for mode_id in sorted(decisions)
    )
    result = ModeEvaluationResultV1(
        contract_digest=contract.content_digest,
        public_plan_digest=public.content_digest,
        source_commit=cast(str, report["source_commit"]),
        mode_outcomes=outcomes,
        all_instrument_valid=all(item.instrument_valid for item in outcomes),
        passed_mode_count=sum(item.gate_passed for item in outcomes),
    )
    _write_new(result_path, result)
    descriptor = os.open(markdown_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(_markdown(result))
    _write_new(
        results / "unblind-completion-v31.json",
        {
            "result_digest": result.content_digest,
            "repair_contract_digest": canonical_digest(repair_contract),
            "judge_completion_digest": canonical_digest(judge_completion),
            "target_grid_reexecuted": False,
        },
    )


if __name__ == "__main__":
    main()
