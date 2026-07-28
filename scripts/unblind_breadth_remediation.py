"""Unblind and combine the Milestone 6A.4 repair replication."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.benchmark.breadth_adjudication import (
    BreadthScoringAdjudicationResult,
    BreadthScoringCorrection,
)
from adaptation_compiler_lab.benchmark.breadth_remediation import (
    BreadthRemediationJudgeDecision,
    BreadthRemediationPublicPlan,
    BreadthRemediationResult,
    BreadthTaskPairOutcome,
    build_breadth_remediation_plan,
    load_breadth_remediation_contract,
    load_breadth_remediation_design,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
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
        raise TypeError("remediation result must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


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


def _metrics_from_trial(trial: FairComparisonTrialReceipt) -> dict[str, int]:
    value = trial.observation
    return {
        "objective_passed": value.objective_checks_passed,
        "objective_total": value.objective_checks_total,
        "diagnostic_passed": value.diagnostic_checks_passed,
        "diagnostic_total": value.diagnostic_checks_total,
        "neutral_passed": value.neutral_checks_passed,
        "neutral_total": value.neutral_checks_total,
        "behavior_conformant": int(trial.behavior_conformant),
        "records": 1,
    }


def _metrics_from_correction(item: BreadthScoringCorrection) -> dict[str, int]:
    return {
        "objective_passed": item.objective_passed,
        "objective_total": item.objective_total,
        "diagnostic_passed": item.diagnostic_passed,
        "diagnostic_total": item.diagnostic_total,
        "neutral_passed": item.neutral_passed,
        "neutral_total": item.neutral_total,
        "behavior_conformant": int(item.behavior_conformant),
        "records": 1,
    }


def _add_metrics(target: dict[str, int], value: dict[str, int]) -> None:
    for key, count in value.items():
        target[key] += count


def _empty_metrics() -> dict[str, int]:
    return {
        "objective_passed": 0,
        "objective_total": 0,
        "diagnostic_passed": 0,
        "diagnostic_total": 0,
        "neutral_passed": 0,
        "neutral_total": 0,
        "behavior_conformant": 0,
        "records": 0,
    }


def _markdown(
    *,
    result: BreadthRemediationResult,
    family_summary: dict[str, dict[ApprovedSourceFamily, dict[str, int]]],
    compiled_bytes: tuple[int, int, int],
    profile_bytes: tuple[int, int, int],
) -> str:
    lines = [
        "# Milestone 6A.4 Oracle-Contract Remediation Result",
        "",
        f"Primary gate: **{'PASS' if result.primary_gate_passed else 'FAIL'}**.",
        "",
        f"Permitted claim: `{result.permitted_claim}`.",
        "",
        "The combined matrix retains three valid v1 task pairs and substitutes five fresh, "
        "oracle-audited replacements for the slots whose hidden checks required undisclosed "
        "vocabulary.",
        "",
        "## Combined task matrix",
        "",
        "| Task | Family | Stage | Winner | Compiled checks | Profile checks |",
        "| --- | --- | ---: | --- | ---: | ---: |",
    ]
    for pair in result.combined_task_pairs:
        lines.append(
            f"| {pair.task_id} | {pair.family.value} | {pair.stage} | "
            f"{pair.automated_winner} | {pair.compiled_total_passed} | "
            f"{pair.profile_total_passed} |"
        )
    lines.extend(
        [
            "",
            "## Combined family aggregates",
            "",
            "| Condition | Family | Objective | Diagnostic | Neutral | Conformant |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for condition in ("compiled_adaptation", "strong_static_profile"):
        for family in ApprovedSourceFamily:
            value = family_summary[condition][family]
            lines.append(
                f"| {condition} | {family.value} | "
                f"{value['objective_passed']}/{value['objective_total']} | "
                f"{value['diagnostic_passed']}/{value['diagnostic_total']} | "
                f"{value['neutral_passed']}/{value['neutral_total']} | "
                f"{value['behavior_conformant']}/{value['records']} |"
            )
    lines.extend(
        [
            "",
            "## Material size",
            "",
            "| Stage | Compiled bytes | Strong-profile bytes |",
            "| ---: | ---: | ---: |",
            *[
                f"| {stage} | {compiled_bytes[stage - 1]} | {profile_bytes[stage - 1]} |"
                for stage in range(1, 4)
            ],
            "",
            "## Fresh secondary judge",
            "",
            f"- Compiled wins: {result.judge_compiled_wins}",
            f"- Strong-profile wins: {result.judge_profile_wins}",
            f"- Ties: {result.judge_ties}",
            "",
            "The original failed scoring result and its valid v1.1 adjudication remain "
            "preserved. The deferred external-validation study was not accessed. No API key "
            "or provider-billed call was used.",
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
    root = repo / "development_benchmark_breadth_remediation"
    results = root / "results-v1"
    design = load_breadth_remediation_design(root)
    contract = load_breadth_remediation_contract(root, design=design)
    result_path = results / "unblinded-result.json"
    markdown_path = results / "MILESTONE_6A4_REMEDIATION_RESULT.md"
    if result_path.exists() or markdown_path.exists():
        raise RuntimeError("breadth remediation is already unblinded")
    seed_path = arguments.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("remediation unblinding seed boundary is invalid")
    public, private = build_breadth_remediation_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed_path.read_bytes(),
    )
    frozen_public = BreadthRemediationPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("remediation seed does not reproduce the public plan")
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
        raise RuntimeError("remediation unblinding prerequisites are invalid")
    raw_trials = report.get("trials")
    if not isinstance(raw_trials, list):
        raise RuntimeError("remediation blind trials are malformed")
    trials = tuple(
        FairComparisonTrialReceipt.model_validate_json(canonical_json(item)) for item in raw_trials
    )
    assignments = cast(list[dict[str, object]], private["condition_assignments"])
    condition_by_blind = {
        str(item["blind_condition_id"]): BenchmarkCondition(str(item["condition"]))
        for item in assignments
    }
    by_task: dict[str, dict[BenchmarkCondition, FairComparisonTrialReceipt]] = defaultdict(dict)
    for trial in trials:
        condition = condition_by_blind[trial.observation.blind_condition_id]
        by_task[trial.observation.task_id][condition] = trial
    replacement_pairs = []
    for wrapped in design.tasks:
        cells = by_task[wrapped.task_id]
        compiled = cells[BenchmarkCondition.COMPILED_ADAPTATION]
        profile = cells[BenchmarkCondition.STRONG_STATIC_PROFILE]
        replacement_pairs.append(
            BreadthTaskPairOutcome(
                task_id=wrapped.task_id,
                family=wrapped.task.family,
                stage=wrapped.stage,
                compiled_output_id=compiled.observation.blind_output_id,
                profile_output_id=profile.observation.blind_output_id,
                automated_winner=_trial_winner(compiled, profile),
                compiled_total_passed=_trial_total(compiled),
                profile_total_passed=_trial_total(profile),
                compiled_behavior_conformant=compiled.behavior_conformant,
                profile_behavior_conformant=profile.behavior_conformant,
            )
        )
    inherited_path = (
        repo
        / "development_benchmark_breadth_replication/results-v1.1"
        / "SCORING_ADJUDICATION-v1.json"
    )
    inherited = BreadthScoringAdjudicationResult.model_validate_json(inherited_path.read_bytes())
    inherited_pairs = tuple(
        pair for pair in inherited.task_pairs if pair.task_id in design.inherited_task_ids
    )
    if len(inherited_pairs) != 3:
        raise RuntimeError("remediation inherited task pairs drifted")
    combined_pairs = tuple(
        sorted((*inherited_pairs, *replacement_pairs), key=lambda item: item.task_id)
    )
    correction_by_output = {item.blind_output_id: item for item in inherited.corrections}
    family_summary = {
        "compiled_adaptation": {family: _empty_metrics() for family in ApprovedSourceFamily},
        "strong_static_profile": {family: _empty_metrics() for family in ApprovedSourceFamily},
    }
    for pair in inherited_pairs:
        _add_metrics(
            family_summary["compiled_adaptation"][pair.family],
            _metrics_from_correction(correction_by_output[pair.compiled_output_id]),
        )
        _add_metrics(
            family_summary["strong_static_profile"][pair.family],
            _metrics_from_correction(correction_by_output[pair.profile_output_id]),
        )
    family_by_new_task = {item.task_id: item.task.family for item in design.tasks}
    for trial in trials:
        condition = condition_by_blind[trial.observation.blind_condition_id].value
        _add_metrics(
            family_summary[condition][family_by_new_task[trial.observation.task_id]],
            _metrics_from_trial(trial),
        )
    family_gates = 0
    for family in ApprovedSourceFamily:
        compiled_value = family_summary["compiled_adaptation"][family]
        profile_value = family_summary["strong_static_profile"][family]
        metrics_hold = all(
            compiled_value[metric] >= profile_value[metric]
            for metric in (
                "objective_passed",
                "diagnostic_passed",
                "neutral_passed",
                "behavior_conformant",
            )
        )
        compiled_perfect = (
            all(
                compiled_value[f"{group}_passed"] == compiled_value[f"{group}_total"]
                for group in ("objective", "diagnostic", "neutral")
            )
            and compiled_value["behavior_conformant"] == compiled_value["records"]
        )
        family_gates += int(metrics_hold and compiled_perfect)
    instrument_valid = all(item.integrity_valid for item in trials)
    size_gate = all(
        compiled < profile
        for compiled, profile in zip(
            design.compiled_material_bytes,
            design.profile_material_bytes,
            strict=True,
        )
    )
    primary_gate = instrument_valid and family_gates == 4 and size_gate
    compiled_total = sum(item.compiled_total_passed for item in combined_pairs)
    profile_total = sum(item.profile_total_passed for item in combined_pairs)
    claim: Literal[
        "compiled_matched_profile_across_all_approved_families_with_lifecycle_advantages",
        "compiled_outperformed_on_combined_multifamily_suite",
        "breadth_remediation_gate_failed",
        "breadth_remediation_instrumentation_failure",
    ]
    if not instrument_valid:
        claim = "breadth_remediation_instrumentation_failure"
    elif not primary_gate:
        claim = "breadth_remediation_gate_failed"
    elif compiled_total > profile_total:
        claim = "compiled_outperformed_on_combined_multifamily_suite"
    else:
        claim = "compiled_matched_profile_across_all_approved_families_with_lifecycle_advantages"
    decision = BreadthRemediationJudgeDecision.model_validate_json(
        canonical_json(judge["decision"])
    )
    output_to_condition = {
        trial.observation.blind_output_id: condition_by_blind[trial.observation.blind_condition_id]
        for trial in trials
    }
    judge_counts: dict[BenchmarkCondition | None, int] = {
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
    result = BreadthRemediationResult(
        design_digest=design.content_digest,
        contract_digest=contract.content_digest,
        public_plan_digest=public.content_digest,
        source_commit=str(report["source_commit"]),
        new_trials=trials,
        inherited_task_pairs=inherited_pairs,
        replacement_task_pairs=tuple(replacement_pairs),
        combined_task_pairs=combined_pairs,
        instrument_valid=instrument_valid,
        primary_gate_passed=primary_gate,
        family_gates_passed=family_gates,
        judge_compiled_wins=judge_counts[BenchmarkCondition.COMPILED_ADAPTATION],
        judge_profile_wins=judge_counts[BenchmarkCondition.STRONG_STATIC_PROFILE],
        judge_ties=judge_counts[None],
        permitted_claim=claim,
    )
    _exclusive_write(result_path, _canonical_bytes(result))
    _exclusive_write(
        markdown_path,
        _markdown(
            result=result,
            family_summary=family_summary,
            compiled_bytes=design.compiled_material_bytes,
            profile_bytes=design.profile_material_bytes,
        ).encode("utf-8"),
    )


if __name__ == "__main__":
    main()
