"""Deterministically unblind the scoped breadth expression validation."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.benchmark.breadth_expression_validation import (
    BreadthExpressionJudgeDecision,
    BreadthExpressionPublicPlan,
    BreadthExpressionResult,
    build_breadth_expression_plan,
    load_breadth_expression_contract,
    load_breadth_expression_design,
    noncommunication_rules_are_identical,
)
from adaptation_compiler_lab.benchmark.breadth_replication import BreadthTaskPairOutcome
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairComparisonTrialReceipt,
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
        raise TypeError("expression-validation result must be a JSON object")
    return (canonical_json(value) + "\n").encode()


def _trial_total(trial: FairComparisonTrialReceipt) -> int:
    value = trial.observation
    return (
        value.objective_checks_passed + value.diagnostic_checks_passed + value.neutral_checks_passed
    )


def _trial_winner(
    compiled: FairComparisonTrialReceipt,
    profile: FairComparisonTrialReceipt,
) -> Literal["compiled_adaptation", "strong_static_profile", "tie"]:
    if compiled.behavior_conformant != profile.behavior_conformant:
        return "compiled_adaptation" if compiled.behavior_conformant else "strong_static_profile"
    if _trial_total(compiled) > _trial_total(profile):
        return "compiled_adaptation"
    if _trial_total(profile) > _trial_total(compiled):
        return "strong_static_profile"
    return "tie"


def _prior_noncommunication_pairs_remain_ties(repo: Path) -> bool:
    prior = json.loads(
        (
            repo / "development_benchmark_breadth_instrument_repair/results-v2/"
            "unblinded-result.json"
        ).read_text(encoding="utf-8")
    )
    if not isinstance(prior, dict) or prior.get("instrument_valid") is not True:
        return False
    pairs = prior.get("task_pairs")
    if not isinstance(pairs, list):
        return False
    expected = {
        "debugging-deployment-state",
        "environment-migration-plan",
        "research-cutoff-report",
    }
    selected = {
        str(item.get("task_id")): item
        for item in pairs
        if isinstance(item, dict) and item.get("task_id") in expected
    }
    return set(selected) == expected and all(
        item.get("automated_winner") == "tie" for item in selected.values()
    )


def _markdown(
    result: BreadthExpressionResult,
    *,
    compiled_bytes: int,
    profile_bytes: int,
) -> str:
    lines = [
        "# Milestone 6A.4 Scoped Expression-Validation Result",
        "",
        f"Primary gate: **{'PASS' if result.primary_gate_passed else 'FAIL'}**.",
        "",
        f"Permitted claim: `{result.permitted_claim}`.",
        "",
        "This validation changed only the compiled communication rule. It used one fresh "
        "communication task and one fresh unrelated research-integrity control, while binding "
        "the valid prior debugging, environment-safety, and research-integrity ties.",
        "",
        "## Fresh task matrix",
        "",
        "| Task | Role/family | Winner | Compiled checks | Profile checks |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for pair in result.task_pairs:
        lines.append(
            f"| {pair.task_id} | {pair.family.value} | {pair.automated_winner} | "
            f"{pair.compiled_total_passed} | {pair.profile_total_passed} |"
        )
    lines.extend(
        [
            "",
            "## Primary gates",
            "",
            f"- Instrument valid: {str(result.instrument_valid).lower()}",
            f"- Compiled objective checks perfect: "
            f"{str(result.compiled_objective_perfect).lower()}",
            f"- Compiled diagnostic checks perfect: "
            f"{str(result.compiled_diagnostic_perfect).lower()}",
            f"- Compiled neutral checks perfect: {str(result.compiled_neutral_perfect).lower()}",
            f"- Compiled bounded-command behavior conformant: "
            f"{str(result.compiled_behavior_conformant).lower()}",
            f"- No fresh-task regression: {str(result.no_new_task_regression).lower()}",
            f"- Prior non-communication pairs remain ties: "
            f"{str(result.prior_noncommunication_pairs_remain_ties).lower()}",
            f"- Non-communication material byte-identical: "
            f"{str(result.noncommunication_material_byte_identical).lower()}",
            f"- Compactness: {compiled_bytes} compiled bytes vs {profile_bytes} profile bytes",
            "",
            "## Secondary blind judge",
            "",
            f"- Compiled wins: {result.judge_compiled_wins}",
            f"- Strong-profile wins: {result.judge_profile_wins}",
            f"- Ties: {result.judge_ties}",
            "",
            "The valid earlier failure and all instrument failures remain immutable. The "
            "deferred external-validation study was not accessed. No API key or provider-billed "
            "call was used.",
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
    root = repo / "development_benchmark_breadth_expression_validation"
    results = root / "results-v1"
    design = load_breadth_expression_design(root)
    contract = load_breadth_expression_contract(root, design=design)
    result_path = results / "unblinded-result.json"
    markdown_path = results / "MILESTONE_6A4_EXPRESSION_RESULT.md"
    if result_path.exists() or markdown_path.exists():
        raise RuntimeError("expression validation is already unblinded")
    seed_path = arguments.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("expression-validation unblinding seed boundary is invalid")
    public, private = build_breadth_expression_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed_path.read_bytes(),
    )
    frozen_public = BreadthExpressionPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("expression-validation seed does not reproduce the public plan")
    report_path = results / "blind-report.json"
    completion = json.loads((results / "completion.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    judge = json.loads((results / "judge-receipt.json").read_text(encoding="utf-8"))
    if (
        not isinstance(completion, dict)
        or completion.get("blind_report_digest") != sha256_file(report_path)
        or not isinstance(report, dict)
        or report.get("condition_mapping_withheld") is not True
        or not isinstance(judge, dict)
        or judge.get("blind_report_digest") != sha256_file(report_path)
        or judge.get("condition_mapping_access") is not False
    ):
        raise RuntimeError("expression-validation unblinding prerequisites are invalid")
    raw_trials = report.get("trials")
    if not isinstance(raw_trials, list):
        raise RuntimeError("expression-validation blind trials are malformed")
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
    no_new_task_regression = True
    for wrapped in design.tasks:
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
        no_new_task_regression &= all(
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
    compiled_diagnostic_perfect = all(
        item.observation.diagnostic_checks_passed == item.observation.diagnostic_checks_total
        for item in compiled_trials
    )
    compiled_neutral_perfect = all(
        item.observation.neutral_checks_passed == item.observation.neutral_checks_total
        for item in compiled_trials
    )
    compiled_behavior_conformant = all(item.behavior_conformant for item in compiled_trials)
    instrument_valid = all(item.integrity_valid for item in trials)
    old_material = (
        repo / "development_benchmark_breadth_instrument_repair/condition-materials/"
        "compiled-final.md"
    )
    repaired_material = (
        repo / "development_benchmark_breadth_instrument_repair/condition-materials/"
        "compiled-final-v4.md"
    )
    noncommunication_identical = noncommunication_rules_are_identical(
        old_material,
        repaired_material,
    )
    prior_ties = _prior_noncommunication_pairs_remain_ties(repo)
    compactness = design.repaired_compiled_material_bytes < design.profile_material_bytes
    primary_gate = (
        instrument_valid
        and compiled_objective_perfect
        and compiled_diagnostic_perfect
        and compiled_neutral_perfect
        and compiled_behavior_conformant
        and no_new_task_regression
        and prior_ties
        and noncommunication_identical
        and compactness
    )
    decision = BreadthExpressionJudgeDecision.model_validate_json(canonical_json(judge["decision"]))
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
        claim = "scoped_expression_validation_instrumentation_failure"
    elif not primary_gate:
        claim = "scoped_expression_validation_failed"
    else:
        claim = (
            "compiled_matched_or_outperformed_profile_across_four_families_"
            "with_lifecycle_advantages"
        )
    result = BreadthExpressionResult(
        design_digest=design.content_digest,
        contract_digest=contract.content_digest,
        public_plan_digest=public.content_digest,
        source_commit=str(report["source_commit"]),
        trials=trials,
        task_pairs=tuple(sorted(pairs, key=lambda item: item.task_id)),
        instrument_valid=instrument_valid,
        compiled_objective_perfect=compiled_objective_perfect,
        compiled_diagnostic_perfect=compiled_diagnostic_perfect,
        compiled_neutral_perfect=compiled_neutral_perfect,
        compiled_behavior_conformant=compiled_behavior_conformant,
        no_new_task_regression=no_new_task_regression,
        prior_noncommunication_pairs_remain_ties=prior_ties,
        noncommunication_material_byte_identical=noncommunication_identical,
        compactness_gate_passed=compactness,
        primary_gate_passed=primary_gate,
        judge_compiled_wins=judge_counts[BenchmarkCondition.COMPILED_ADAPTATION],
        judge_profile_wins=judge_counts[BenchmarkCondition.STRONG_STATIC_PROFILE],
        judge_ties=judge_counts[None],
        permitted_claim=claim,
    )
    _exclusive_write(result_path, _canonical_bytes(result))
    _exclusive_write(
        markdown_path,
        _markdown(
            result,
            compiled_bytes=design.repaired_compiled_material_bytes,
            profile_bytes=design.profile_material_bytes,
        ).encode(),
    )


if __name__ == "__main__":
    main()
