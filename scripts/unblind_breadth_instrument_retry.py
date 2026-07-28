"""Deterministically unblind the smoke-validated v3 retry."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentJudgeDecision,
    BreadthInstrumentPublicPlan,
    BreadthInstrumentResult,
    build_breadth_instrument_plan,
    load_breadth_instrument_contract,
    load_breadth_instrument_design,
)
from adaptation_compiler_lab.benchmark.breadth_instrument_retry import (
    load_breadth_instrument_retry_contract,
    load_breadth_instrument_retry_design,
)
from adaptation_compiler_lab.benchmark.breadth_replication import BreadthTaskPairOutcome
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairComparisonTrialReceipt,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json
from scripts.unblind_breadth_instrument import (
    _canonical_bytes,
    _exclusive_write,
    _markdown,
    _trial_total,
    _trial_winner,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_instrument_repair"
    results = root / "results-v2"
    base_design = load_breadth_instrument_design(root)
    base_contract = load_breadth_instrument_contract(root, design=base_design)
    retry_design = load_breadth_instrument_retry_design(
        root,
        base_design=base_design,
        base_contract=base_contract,
    )
    contract = load_breadth_instrument_retry_contract(root, retry_design=retry_design)
    result_path = results / "unblinded-result.json"
    markdown_path = results / "MILESTONE_6A4_V3_RETRY_RESULT.md"
    if result_path.exists() or markdown_path.exists():
        raise RuntimeError("v3 breadth retry is already unblinded")
    seed_path = arguments.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("v3 retry unblinding seed boundary is invalid")
    public, private = build_breadth_instrument_plan(
        design_digest=retry_design.content_digest,
        tasks=base_design.tasks,
        seed=seed_path.read_bytes(),
    )
    frozen_public = BreadthInstrumentPublicPlan.model_validate_json(
        (root / "RETRY_PUBLIC_PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("v3 retry seed does not reproduce the public plan")
    report_path = results / "blind-report.json"
    completion = json.loads((results / "completion.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    judge_path = results / "judge-receipt.json"
    judge = json.loads(judge_path.read_text(encoding="utf-8"))
    if (
        not isinstance(completion, dict)
        or completion.get("blind_report_digest") != sha256_file(report_path)
        or not isinstance(report, dict)
        or report.get("condition_mapping_withheld") is not True
        or not isinstance(judge, dict)
        or judge.get("blind_report_digest") != sha256_file(report_path)
        or judge.get("condition_mapping_access") is not False
    ):
        raise RuntimeError("v3 retry unblinding prerequisites are invalid")
    raw_trials = report.get("trials")
    if not isinstance(raw_trials, list):
        raise RuntimeError("v3 retry blind trials are malformed")
    trials = tuple(
        FairComparisonTrialReceipt.model_validate_json(canonical_json(item)) for item in raw_trials
    )
    assignments = cast(list[dict[str, object]], private["condition_assignments"])
    condition_by_blind = {
        str(item["blind_condition_id"]): BenchmarkCondition(str(item["condition"]))
        for item in assignments
    }
    by_task: dict[str, dict[BenchmarkCondition, FairComparisonTrialReceipt]] = defaultdict(dict)
    output_to_condition: dict[str, BenchmarkCondition] = {}
    for trial in trials:
        condition = condition_by_blind[trial.observation.blind_condition_id]
        by_task[trial.observation.task_id][condition] = trial
        output_to_condition[trial.observation.blind_output_id] = condition
    pairs = []
    no_family_regression = True
    for wrapped in base_design.tasks:
        cells = by_task[wrapped.task_id]
        compiled = cells[BenchmarkCondition.COMPILED_ADAPTATION]
        profile = cells[BenchmarkCondition.STRONG_STATIC_PROFILE]
        compiled_metrics = (
            compiled.observation.objective_checks_passed,
            compiled.observation.diagnostic_checks_passed,
            compiled.observation.neutral_checks_passed,
            int(compiled.behavior_conformant),
        )
        profile_metrics = (
            profile.observation.objective_checks_passed,
            profile.observation.diagnostic_checks_passed,
            profile.observation.neutral_checks_passed,
            int(profile.behavior_conformant),
        )
        no_family_regression &= all(
            compiled_value >= profile_value
            for compiled_value, profile_value in zip(
                compiled_metrics,
                profile_metrics,
                strict=True,
            )
        )
        pairs.append(
            BreadthTaskPairOutcome(
                task_id=wrapped.task_id,
                family=wrapped.task.family,
                stage=3,
                compiled_output_id=compiled.observation.blind_output_id,
                profile_output_id=profile.observation.blind_output_id,
                automated_winner=_trial_winner(compiled, profile),
                compiled_total_passed=_trial_total(compiled),
                profile_total_passed=_trial_total(profile),
                compiled_behavior_conformant=compiled.behavior_conformant,
                profile_behavior_conformant=profile.behavior_conformant,
            )
        )
    compiled_trials = tuple(
        trial
        for trial in trials
        if condition_by_blind[trial.observation.blind_condition_id]
        is BenchmarkCondition.COMPILED_ADAPTATION
    )
    compiled_objective_perfect = all(
        item.observation.objective_checks_passed == item.observation.objective_checks_total
        for item in compiled_trials
    )
    compiled_neutral_perfect = all(
        item.observation.neutral_checks_passed == item.observation.neutral_checks_total
        for item in compiled_trials
    )
    instrument_valid = all(item.integrity_valid for item in trials)
    compactness = base_design.compiled_material_bytes < base_design.profile_material_bytes
    primary_gate = (
        instrument_valid
        and compiled_objective_perfect
        and compiled_neutral_perfect
        and no_family_regression
        and compactness
    )
    decision = BreadthInstrumentJudgeDecision.model_validate_json(canonical_json(judge["decision"]))
    judge_counts: dict[BenchmarkCondition | None, int] = {
        BenchmarkCondition.COMPILED_ADAPTATION: 0,
        BenchmarkCondition.STRONG_STATIC_PROFILE: 0,
        None: 0,
    }
    for rating in decision.pair_ratings:
        condition = (
            None
            if rating.preferred_output_id is None
            else output_to_condition[rating.preferred_output_id]
        )
        judge_counts[condition] += 1
    if not instrument_valid:
        claim = "breadth_instrument_repair_instrumentation_failure"
    elif not primary_gate:
        claim = "breadth_instrument_repair_gate_failed"
    else:
        claim = (
            "compiled_matched_or_outperformed_profile_across_four_families_"
            "with_lifecycle_advantages"
        )
    result = BreadthInstrumentResult(
        design_digest=retry_design.content_digest,
        contract_digest=contract.content_digest,
        public_plan_digest=public.content_digest,
        source_commit=str(report["source_commit"]),
        trials=trials,
        task_pairs=tuple(sorted(pairs, key=lambda item: item.task_id)),
        instrument_valid=instrument_valid,
        compiled_objective_perfect=compiled_objective_perfect,
        compiled_neutral_perfect=compiled_neutral_perfect,
        no_family_regression=no_family_regression,
        compactness_gate_passed=compactness,
        primary_gate_passed=primary_gate,
        judge_compiled_wins=judge_counts[BenchmarkCondition.COMPILED_ADAPTATION],
        judge_profile_wins=judge_counts[BenchmarkCondition.STRONG_STATIC_PROFILE],
        judge_ties=judge_counts[None],
        permitted_claim=claim,
    )
    _exclusive_write(result_path, _canonical_bytes(result))
    report_text = _markdown(
        result,
        compiled_bytes=base_design.compiled_material_bytes,
        profile_bytes=base_design.profile_material_bytes,
    ).replace(
        "# Milestone 6A.4 Clean Breadth Result",
        "# Milestone 6A.4 v3 Runner Retry Result",
        1,
    )
    _exclusive_write(markdown_path, report_text.encode())


if __name__ == "__main__":
    main()
