"""Unblind and analyze Milestone 6A.4 after the blind judge is frozen."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthJudgeDecision,
    BreadthReplicationPublicPlan,
    BreadthReplicationResult,
    BreadthTaskPairOutcome,
    build_breadth_plan,
    load_breadth_contract,
    load_breadth_design,
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
        raise TypeError("breadth result must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _score(trial: FairComparisonTrialReceipt) -> int:
    observation = trial.observation
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
    if _score(compiled) > _score(profile):
        return "compiled_adaptation"
    if _score(profile) > _score(compiled):
        return "strong_static_profile"
    return "tie"


def _family_totals(
    trials: list[FairComparisonTrialReceipt],
    families: dict[str, ApprovedSourceFamily],
) -> dict[ApprovedSourceFamily, dict[str, int]]:
    totals: dict[ApprovedSourceFamily, dict[str, int]] = defaultdict(
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
    for trial in trials:
        target = totals[families[trial.observation.task_id]]
        observation = trial.observation
        for group in ("objective", "diagnostic", "neutral"):
            target[f"{group}_passed"] += getattr(observation, f"{group}_checks_passed")
            target[f"{group}_total"] += getattr(observation, f"{group}_checks_total")
        target["behavior_conformant"] += int(trial.behavior_conformant)
        target["records"] += 1
    return dict(totals)


def _markdown(
    *,
    result: BreadthReplicationResult,
    family_summary: dict[str, dict[ApprovedSourceFamily, dict[str, int]]],
    compiled_bytes: tuple[int, int, int],
    profile_bytes: tuple[int, int, int],
) -> str:
    lines = [
        "# Milestone 6A.4 Breadth Replication Result",
        "",
        f"Primary gate: **{'PASS' if result.primary_gate_passed else 'FAIL'}**.",
        "",
        f"Permitted claim: `{result.permitted_claim}`.",
        "",
        "## Task matrix",
        "",
        "| Task | Family | Stage | Winner | Compiled checks | Profile checks |",
        "| --- | --- | ---: | --- | ---: | ---: |",
    ]
    for pair in result.task_pairs:
        lines.append(
            f"| {pair.task_id} | {pair.family.value} | {pair.stage} | "
            f"{pair.automated_winner} | {pair.compiled_total_passed} | "
            f"{pair.profile_total_passed} |"
        )
    lines.extend(
        [
            "",
            "## Family aggregates",
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
            "## Secondary judge",
            "",
            f"- Compiled wins: {result.judge_compiled_wins}",
            f"- Strong-profile wins: {result.judge_profile_wins}",
            f"- Ties: {result.judge_ties}",
            "",
            "Automated behavior and scope isolation remain primary.",
            "",
            "The deferred external-validation study remained sealed and unaccessed. "
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
    root = repo / "development_benchmark_breadth_replication"
    results = root / "results-v1"
    design = load_breadth_design(root)
    contract = load_breadth_contract(root, design=design)
    result_path = results / "unblinded-result.json"
    markdown_path = results / "MILESTONE_6A4_RESULT.md"
    if result_path.exists() or markdown_path.exists():
        raise RuntimeError("breadth comparison has already been unblinded")
    seed_path = arguments.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("breadth unblinding seed boundary is invalid")
    public, private = build_breadth_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed_path.read_bytes(),
    )
    frozen_public = BreadthReplicationPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("breadth seed does not reproduce the public plan")
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
        raise RuntimeError("breadth unblinding prerequisites are invalid")
    raw_trials = report.get("trials")
    if not isinstance(raw_trials, list):
        raise RuntimeError("breadth blind trials are malformed")
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
        by_task[trial.observation.task_id][
            condition_by_blind[trial.observation.blind_condition_id]
        ] = trial
    metadata = {wrapped.task_id: wrapped for wrapped in design.tasks}
    pairs: list[BreadthTaskPairOutcome] = []
    for wrapped in design.tasks:
        cells = by_task[wrapped.task_id]
        compiled = cells[BenchmarkCondition.COMPILED_ADAPTATION]
        profile = cells[BenchmarkCondition.STRONG_STATIC_PROFILE]
        pairs.append(
            BreadthTaskPairOutcome(
                task_id=wrapped.task_id,
                family=wrapped.task.family,
                stage=wrapped.stage,
                compiled_output_id=compiled.observation.blind_output_id,
                profile_output_id=profile.observation.blind_output_id,
                automated_winner=_winner(compiled, profile),
                compiled_total_passed=_score(compiled),
                profile_total_passed=_score(profile),
                compiled_behavior_conformant=compiled.behavior_conformant,
                profile_behavior_conformant=profile.behavior_conformant,
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
    families = {task_id: wrapped.task.family for task_id, wrapped in metadata.items()}
    compiled_families = _family_totals(compiled_trials, families)
    profile_families = _family_totals(profile_trials, families)
    family_gates = 0
    for family in ApprovedSourceFamily:
        compiled_value = compiled_families[family]
        profile_value = profile_families[family]
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
    instrument_valid = all(trial.integrity_valid for trial in trials)
    size_gate = all(
        compiled <= profile
        for compiled, profile in zip(
            design.compiled_material_bytes,
            design.profile_material_bytes,
            strict=True,
        )
    )
    primary_gate = instrument_valid and family_gates == 4 and size_gate
    compiled_total = sum(_score(trial) for trial in compiled_trials)
    profile_total = sum(_score(trial) for trial in profile_trials)
    claim: Literal[
        "compiled_outperformed_on_multifamily_suite_without_family_regression",
        "compiled_matched_profile_across_all_approved_families",
        "breadth_gate_failed",
        "instrumentation_failure",
    ]
    if not instrument_valid:
        claim = "instrumentation_failure"
    elif not primary_gate:
        claim = "breadth_gate_failed"
    elif compiled_total > profile_total:
        claim = "compiled_outperformed_on_multifamily_suite_without_family_regression"
    else:
        claim = "compiled_matched_profile_across_all_approved_families"
    decision = BreadthJudgeDecision.model_validate_json(canonical_json(judge["decision"]))
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
    result = BreadthReplicationResult(
        design_digest=design.content_digest,
        contract_digest=contract.content_digest,
        public_plan_digest=public.content_digest,
        source_commit=str(report["source_commit"]),
        trials=trials,
        task_pairs=tuple(pairs),
        instrument_valid=instrument_valid,
        primary_gate_passed=primary_gate,
        family_gates_passed=family_gates,
        judge_receipt_digest=sha256_file(judge_path),
        judge_compiled_wins=judge_counts[BenchmarkCondition.COMPILED_ADAPTATION],
        judge_profile_wins=judge_counts[BenchmarkCondition.STRONG_STATIC_PROFILE],
        judge_ties=judge_counts[None],
        permitted_claim=claim,
    )
    _exclusive_write(result_path, _canonical_bytes(result))
    summary = {
        "compiled_adaptation": compiled_families,
        "strong_static_profile": profile_families,
    }
    _exclusive_write(
        markdown_path,
        _markdown(
            result=result,
            family_summary=summary,
            compiled_bytes=design.compiled_material_bytes,
            profile_bytes=design.profile_material_bytes,
        ).encode("utf-8"),
    )


if __name__ == "__main__":
    main()
