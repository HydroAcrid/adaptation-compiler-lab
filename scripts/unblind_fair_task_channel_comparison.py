"""Unblind and analyze Milestone 6A.3 only after the judge is frozen."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairComparisonResult,
    FairComparisonTrialReceipt,
    FairTaskChannelJudgeDecision,
    FairTaskPairOutcome,
    TaskChannelComparisonPublicPlan,
    build_task_channel_plan,
    load_task_channel_contract,
    load_task_channel_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("unblinded comparison artifacts must be JSON objects")
    return (canonical_json(value) + "\n").encode("utf-8")


def _score_total(receipt: FairComparisonTrialReceipt) -> int:
    observation = receipt.observation
    return (
        observation.objective_checks_passed
        + observation.diagnostic_checks_passed
        + observation.neutral_checks_passed
    )


def _winner(
    compiled: FairComparisonTrialReceipt,
    profile: FairComparisonTrialReceipt,
) -> Literal["compiled_adaptation", "strong_static_profile", "tie"]:
    if compiled.behavior_conformant != profile.behavior_conformant:
        return "compiled_adaptation" if compiled.behavior_conformant else "strong_static_profile"
    compiled_total = _score_total(compiled)
    profile_total = _score_total(profile)
    if compiled_total > profile_total:
        return "compiled_adaptation"
    if profile_total > compiled_total:
        return "strong_static_profile"
    return "tie"


def _stage_counts(
    receipts: list[FairComparisonTrialReceipt],
    tasks: dict[str, int],
) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "objective_passed": 0,
            "objective_total": 0,
            "diagnostic_passed": 0,
            "diagnostic_total": 0,
            "neutral_passed": 0,
            "neutral_total": 0,
            "behavior_conformant": 0,
            "records": 0,
        }
    )
    for receipt in receipts:
        stage = tasks[receipt.observation.task_id]
        observation = receipt.observation
        counts = result[stage]
        counts["objective_passed"] += observation.objective_checks_passed
        counts["objective_total"] += observation.objective_checks_total
        counts["diagnostic_passed"] += observation.diagnostic_checks_passed
        counts["diagnostic_total"] += observation.diagnostic_checks_total
        counts["neutral_passed"] += observation.neutral_checks_passed
        counts["neutral_total"] += observation.neutral_checks_total
        counts["behavior_conformant"] += int(receipt.behavior_conformant)
        counts["records"] += 1
    return dict(result)


def _markdown(
    *,
    result: FairComparisonResult,
    stage_summary: dict[str, dict[int, dict[str, int]]],
) -> str:
    lines = [
        "# Milestone 6A.3 Fair Task-Channel Comparison Result",
        "",
        f"Primary gate: **{'PASS' if result.primary_gate_passed else 'FAIL'}**.",
        "",
        f"Permitted claim: `{result.permitted_claim}`.",
        "",
        "## Task-level matrix",
        "",
        "| Task | Stage | Automated winner | Compiled checks | Profile checks |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for pair in result.task_pairs:
        lines.append(
            f"| {pair.task_id} | {pair.stage} | {pair.automated_winner} | "
            f"{pair.compiled_total_passed} | {pair.profile_total_passed} |"
        )
    lines.extend(
        [
            "",
            "## Stage aggregates",
            "",
            "| Condition | Stage | Objective | Diagnostic | Neutral | Behaviorally conformant |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for condition in ("compiled_adaptation", "strong_static_profile"):
        for stage in range(1, 4):
            value = stage_summary[condition][stage]
            lines.append(
                f"| {condition} | {stage} | "
                f"{value['objective_passed']}/{value['objective_total']} | "
                f"{value['diagnostic_passed']}/{value['diagnostic_total']} | "
                f"{value['neutral_passed']}/{value['neutral_total']} | "
                f"{value['behavior_conformant']}/{value['records']} |"
            )
    lines.extend(
        [
            "",
            "## Secondary judge",
            "",
            f"- Compiled wins: {result.judge_compiled_wins}",
            f"- Strong-profile wins: {result.judge_profile_wins}",
            f"- Ties: {result.judge_ties}",
            "",
            "Automated correctness and safety are primary. The judge cannot rescue a failed gate.",
            "",
            "The deferred Milestone 6 external-validation study remained sealed and unaccessed. "
            "No API key or provider-billed call was used.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_task_channel_comparison"
    results = root / "results-v1"
    design = load_task_channel_design(root)
    contract = load_task_channel_contract(root, design=design)
    result_path = results / "unblinded-result.json"
    markdown_path = results / "MILESTONE_6A3_RESULT.md"
    if result_path.exists() or markdown_path.exists():
        raise RuntimeError("fair comparison has already been unblinded")
    seed_path = arguments.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("fair comparison seed boundary is invalid")
    public, private = build_task_channel_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed_path.read_bytes(),
    )
    frozen_public = TaskChannelComparisonPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("unblinding seed does not reproduce the frozen public plan")
    blind_report_path = results / "blind-report.json"
    completion = json.loads((results / "completion.json").read_text(encoding="utf-8"))
    blind_report = json.loads(blind_report_path.read_text(encoding="utf-8"))
    judge_path = results / "judge-receipt.json"
    judge = json.loads(judge_path.read_text(encoding="utf-8"))
    if (
        not isinstance(completion, dict)
        or completion.get("blind_report_digest") != sha256_file(blind_report_path)
        or not isinstance(blind_report, dict)
        or blind_report.get("condition_mapping_withheld") is not True
        or not isinstance(judge, dict)
        or judge.get("blind_report_digest") != sha256_file(blind_report_path)
        or judge.get("condition_mapping_access") is not False
    ):
        raise RuntimeError("fair comparison unblinding prerequisites are invalid")
    raw_trials = blind_report.get("trials")
    if not isinstance(raw_trials, list):
        raise RuntimeError("fair comparison blind trials are malformed")
    trials = tuple(FairComparisonTrialReceipt.model_validate(item) for item in raw_trials)
    assignments = cast(list[dict[str, object]], private["condition_assignments"])
    condition_by_blind = {
        str(item["blind_condition_id"]): BenchmarkCondition(str(item["condition"]))
        for item in assignments
    }
    by_task: dict[str, dict[BenchmarkCondition, FairComparisonTrialReceipt]] = defaultdict(dict)
    for trial in trials:
        by_task[trial.observation.task_id][
            condition_by_blind[trial.observation.blind_condition_id]
        ] = trial
    task_stage = {task.task_id: task.stage for task in design.tasks}
    pairs = []
    for task in design.tasks:
        cells = by_task[task.task_id]
        compiled = cells[BenchmarkCondition.COMPILED_ADAPTATION]
        profile = cells[BenchmarkCondition.STRONG_STATIC_PROFILE]
        pairs.append(
            FairTaskPairOutcome(
                task_id=task.task_id,
                stage=task.stage,
                compiled_output_id=compiled.observation.blind_output_id,
                profile_output_id=profile.observation.blind_output_id,
                automated_winner=_winner(compiled, profile),
                compiled_behavior_conformant=compiled.behavior_conformant,
                profile_behavior_conformant=profile.behavior_conformant,
                compiled_total_passed=_score_total(compiled),
                profile_total_passed=_score_total(profile),
            )
        )
    compiled_trials = [
        trial
        for trial in trials
        if condition_by_blind[trial.observation.blind_condition_id]
        is BenchmarkCondition.COMPILED_ADAPTATION
    ]
    profile_trials = [
        trial
        for trial in trials
        if condition_by_blind[trial.observation.blind_condition_id]
        is BenchmarkCondition.STRONG_STATIC_PROFILE
    ]
    compiled_stages = _stage_counts(compiled_trials, task_stage)
    profile_stages = _stage_counts(profile_trials, task_stage)
    no_stage_regression = all(
        compiled_stages[stage][metric] >= profile_stages[stage][metric]
        for stage in range(1, 4)
        for metric in (
            "objective_passed",
            "diagnostic_passed",
            "neutral_passed",
            "behavior_conformant",
        )
    )
    compiled_complete = all(
        trial.behavior_conformant
        and trial.observation.objective_checks_passed == trial.observation.objective_checks_total
        and trial.observation.diagnostic_checks_passed == trial.observation.diagnostic_checks_total
        and trial.observation.neutral_checks_passed == trial.observation.neutral_checks_total
        for trial in compiled_trials
    )
    instrument_valid = all(trial.integrity_valid for trial in trials)
    primary_gate = instrument_valid and compiled_complete and no_stage_regression
    compiled_total = sum(_score_total(trial) for trial in compiled_trials)
    profile_total = sum(_score_total(trial) for trial in profile_trials)
    claim: Literal[
        "compiled_outperformed_on_fresh_suite",
        "compiled_matched_with_lifecycle_advantages",
        "product_gate_failed",
        "instrumentation_failure",
    ]
    if not instrument_valid:
        claim = "instrumentation_failure"
    elif not primary_gate:
        claim = "product_gate_failed"
    elif compiled_total > profile_total:
        claim = "compiled_outperformed_on_fresh_suite"
    else:
        claim = "compiled_matched_with_lifecycle_advantages"
    decision = FairTaskChannelJudgeDecision.model_validate(judge["decision"])
    output_to_condition = {
        trial.observation.blind_output_id: condition_by_blind[trial.observation.blind_condition_id]
        for trial in trials
    }
    judge_counts = {
        BenchmarkCondition.COMPILED_ADAPTATION: 0,
        BenchmarkCondition.STRONG_STATIC_PROFILE: 0,
        None: 0,
    }
    for rating in decision.pair_ratings:
        selected = (
            None
            if rating.preferred_output_id is None
            else output_to_condition[rating.preferred_output_id]
        )
        judge_counts[selected] += 1
    result = FairComparisonResult(
        design_digest=design.content_digest,
        contract_digest=contract.content_digest,
        public_plan_digest=public.content_digest,
        source_commit=str(blind_report["source_commit"]),
        trials=trials,
        task_pairs=tuple(pairs),
        instrument_valid=instrument_valid,
        primary_gate_passed=primary_gate,
        judge_receipt_digest=sha256_file(judge_path),
        judge_compiled_wins=judge_counts[BenchmarkCondition.COMPILED_ADAPTATION],
        judge_profile_wins=judge_counts[BenchmarkCondition.STRONG_STATIC_PROFILE],
        judge_ties=judge_counts[None],
        permitted_claim=claim,
    )
    _exclusive_write(result_path, _canonical_bytes(result))
    stage_summary = {
        "compiled_adaptation": compiled_stages,
        "strong_static_profile": profile_stages,
    }
    _exclusive_write(
        markdown_path,
        _markdown(result=result, stage_summary=stage_summary).encode("utf-8"),
    )


if __name__ == "__main__":
    main()
