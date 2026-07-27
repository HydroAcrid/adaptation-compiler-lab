"""Unblind the frozen longitudinal comparison and evaluate its preregistered gate."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
)
from adaptation_compiler_lab.benchmark.longitudinal import (
    LongitudinalDevelopmentTask,
    load_longitudinal_comparison,
)
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    LongitudinalBlindReport,
    LongitudinalJudgeDecision,
    load_compiled_materials,
    load_execution_amendment,
    load_execution_protocol,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} is not a JSON object")
    return value


def _object_list(value: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError(f"{label} must be a list of objects")
    return value


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed")
    return completed.stdout.strip()


def _load_key(path: Path) -> bytes:
    try:
        value = base64.b64decode(path.read_bytes().strip(), validate=True)
    except ValueError as error:
        raise RuntimeError("randomization key is not valid base64") from error
    if len(value) != 32:
        raise RuntimeError("randomization key must contain exactly 32 bytes")
    return value


def _metric(pass_count: int, total: int) -> dict[str, int | float]:
    return {
        "passed": pass_count,
        "rate": pass_count / total if total else 0.0,
        "total": total,
    }


def _integer(value: object, *, label: str) -> int:
    if not isinstance(value, int):
        raise RuntimeError(f"{label} must be an integer")
    return value


def _stage_summary(
    observations: list[CodexDevelopmentRunObservation],
    *,
    tasks: dict[str, LongitudinalDevelopmentTask],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for stage in (1, 2, 3):
        selected = [item for item in observations if tasks[item.task_id].stage == stage]
        result.append(
            {
                "diagnostic": _metric(
                    sum(item.diagnostic_checks_passed for item in selected),
                    sum(item.diagnostic_checks_total for item in selected),
                ),
                "neutral": _metric(
                    sum(item.neutral_checks_passed for item in selected),
                    sum(item.neutral_checks_total for item in selected),
                ),
                "objective": _metric(
                    sum(item.objective_checks_passed for item in selected),
                    sum(item.objective_checks_total for item in selected),
                ),
                "stage": stage,
                "task_ids": sorted(item.task_id for item in selected),
                "valid_runs": sum(item.valid for item in selected),
            }
        )
    return result


def _totals(observations: list[CodexDevelopmentRunObservation]) -> dict[str, object]:
    return {
        "diagnostic": _metric(
            sum(item.diagnostic_checks_passed for item in observations),
            sum(item.diagnostic_checks_total for item in observations),
        ),
        "duration_seconds": sum(item.duration_seconds for item in observations),
        "neutral": _metric(
            sum(item.neutral_checks_passed for item in observations),
            sum(item.neutral_checks_total for item in observations),
        ),
        "objective": _metric(
            sum(item.objective_checks_passed for item in observations),
            sum(item.objective_checks_total for item in observations),
        ),
        "runs": len(observations),
        "token_usage": {
            "cached_input_tokens": sum(item.cached_input_tokens for item in observations),
            "input_tokens": sum(item.input_tokens for item in observations),
            "output_tokens": sum(item.output_tokens for item in observations),
            "reasoning_output_tokens": sum(item.reasoning_output_tokens for item in observations),
        },
        "valid_runs": sum(item.valid for item in observations),
    }


def _profile_maintenance(
    receipt: dict[str, object],
    strong_materials: tuple[str, str, str],
) -> list[dict[str, object]]:
    stages = _object_list(receipt.get("stages"), label="profile receipt stages")
    if len(stages) != 3:
        raise RuntimeError("profile receipt must contain three stages")
    result: list[dict[str, object]] = []
    for expected_stage, (stage, material) in enumerate(
        zip(stages, strong_materials, strict=True),
        start=1,
    ):
        if stage.get("stage") != expected_stage:
            raise RuntimeError("profile receipt stage order drifted")
        author = stage.get("author")
        review = stage.get("review")
        if not isinstance(author, dict) or not isinstance(review, dict):
            raise RuntimeError("profile receipt is missing a role receipt")
        author_actions = stage.get("author_intentional_edit_operations")
        review_actions = stage.get("review_intentional_edit_operations")
        if not isinstance(author_actions, int) or not isinstance(review_actions, int):
            raise RuntimeError("profile receipt maintenance actions are malformed")
        if stage.get("profile_digest") != sha256_bytes(material.encode("utf-8")):
            raise RuntimeError("profile receipt no longer binds the exact material")
        result.append(
            {
                "author_edit_operations": author_actions,
                "maintenance_actions": author_actions + review_actions,
                "maintenance_seconds": float(author.get("duration_seconds", 0))
                + float(review.get("duration_seconds", 0)),
                "material_bytes": len(material.encode("utf-8")),
                "material_digest": sha256_bytes(material.encode("utf-8")),
                "review_edit_operations": review_actions,
                "stage": expected_stage,
            }
        )
    return result


def _condition_assignments(
    private_plan: dict[str, object],
) -> tuple[dict[str, BenchmarkCondition], dict[str, BenchmarkCondition]]:
    assignments = _object_list(
        private_plan.get("condition_assignments"),
        label="condition assignments",
    )
    run_order = _object_list(private_plan.get("run_order"), label="run order")
    by_blind_condition: dict[str, BenchmarkCondition] = {}
    for item in assignments:
        blind_id = item.get("blind_condition_id")
        raw_condition = item.get("condition")
        if not isinstance(blind_id, str) or not isinstance(raw_condition, str):
            raise RuntimeError("condition assignment contains invalid values")
        by_blind_condition[blind_id] = BenchmarkCondition(raw_condition)
    if set(by_blind_condition.values()) != set(_CONDITIONS):
        raise RuntimeError("private plan does not contain the exact two conditions")
    by_output: dict[str, BenchmarkCondition] = {}
    for item in run_order:
        blind_condition = item.get("blind_condition_id")
        blind_output = item.get("blind_output_id")
        if not isinstance(blind_condition, str) or not isinstance(blind_output, str):
            raise RuntimeError("private run order contains invalid values")
        by_output[blind_output] = by_blind_condition[blind_condition]
    if len(by_output) != 12:
        raise RuntimeError("private plan does not bind exactly 12 outputs")
    return by_blind_condition, by_output


def _judge_counts(
    decision: LongitudinalJudgeDecision,
    output_conditions: dict[str, BenchmarkCondition],
) -> dict[BenchmarkCondition, dict[str, int]]:
    result = {condition: {"losses": 0, "ties": 0, "wins": 0} for condition in _CONDITIONS}
    for pair in decision.pair_ratings:
        conditions = tuple(output_conditions[item] for item in pair.ordered_output_ids)
        if set(conditions) != set(_CONDITIONS):
            raise RuntimeError("judge pair does not compare the two registered conditions")
        if pair.preferred_output_id is None:
            for condition in _CONDITIONS:
                result[condition]["ties"] += 1
            continue
        winner = output_conditions[pair.preferred_output_id]
        loser = next(condition for condition in _CONDITIONS if condition is not winner)
        result[winner]["wins"] += 1
        result[loser]["losses"] += 1
    return result


def _render_markdown(report: dict[str, object]) -> str:
    conditions = report["conditions"]
    if not isinstance(conditions, dict):
        raise RuntimeError("unblinded condition summary is malformed")
    compiled = conditions[BenchmarkCondition.COMPILED_ADAPTATION.value]
    profile = conditions[BenchmarkCondition.STRONG_STATIC_PROFILE.value]
    if not isinstance(compiled, dict) or not isinstance(profile, dict):
        raise RuntimeError("unblinded condition metrics are malformed")
    gate = report["gate"]
    if not isinstance(gate, dict):
        raise RuntimeError("unblinded gate is malformed")

    def total(condition: dict[str, object], name: str) -> str:
        totals = condition["totals"]
        assert isinstance(totals, dict)
        metric = totals[name]
        assert isinstance(metric, dict)
        return f"{metric['passed']}/{metric['total']}"

    lines = [
        "# Milestone 6A longitudinal dogfood result",
        "",
        f"Outcome: **{str(gate['outcome']).upper()}**",
        "",
        "This is a public, one-run-per-cell Codex development comparison. Automated scenario "
        "checks are primary; the isolated blind AI judge is secondary. It is not a powered "
        "research result and does not establish cross-model transfer.",
        "",
        "## Condition totals",
        "",
        "| Condition | Valid runs | Objective | Diagnostic | Neutral | Judge W-L-T |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, value in (("Compiled adaptation", compiled), ("Strong static profile", profile)):
        totals = value["totals"]
        judge = value["judge"]
        assert isinstance(totals, dict) and isinstance(judge, dict)
        lines.append(
            f"| {label} | {totals['valid_runs']}/{totals['runs']} | "
            f"{total(value, 'objective')} | {total(value, 'diagnostic')} | "
            f"{total(value, 'neutral')} | "
            f"{judge['wins']}-{judge['losses']}-{judge['ties']} |"
        )
    lines.extend(
        (
            "",
            "## Frozen gate",
            "",
        )
    )
    checks = gate["checks"]
    assert isinstance(checks, dict)
    for name, passed in checks.items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — {name.replace('_', ' ')}")
    lines.extend(
        (
            "",
            "## Interpretation limits",
            "",
            "- One fresh execution per condition and task measures development behavior, not "
            "stable population performance.",
            "- Both conditions ran on Codex, so this tests longitudinal packaging and maintenance "
            "inside one target family—not cross-agent or Claude transfer.",
            "- The static profile was created by isolated Codex author/reviewer roles from the "
            "same evidence; its role timings and self-reported edit operations are maintenance "
            "proxies.",
            "- No provider-billed API call or sealed Milestone 6 material was used.",
            "",
        )
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--comparison-config-root", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    if _git(repo, "status", "--porcelain"):
        raise RuntimeError("unblinding requires a clean repository")
    benchmark = repo / "development_benchmark_longitudinal"
    results = benchmark / "results"
    output_path = results / "unblinded-result.json"
    markdown_path = results / "MILESTONE_6A_RESULT.md"
    if output_path.exists() or markdown_path.exists():
        raise RuntimeError("unblinded outputs already exist; refusing to overwrite")
    design = load_longitudinal_comparison(benchmark)
    protocol = load_execution_protocol(benchmark)
    amendment = load_execution_amendment(benchmark)
    dogfood_metrics = _object(benchmark / "DOGFOOD_METRICS-v1.0.json")
    if protocol.dogfood_metrics_digest != sha256_file(benchmark / "DOGFOOD_METRICS-v1.0.json"):
        raise RuntimeError("frozen dogfood metrics binding drifted")
    report = LongitudinalBlindReport.model_validate_json(
        (results / "blind-report.json").read_bytes()
    )
    completion = _object(results / "completion.json")
    judge_receipt = _object(results / "judge-receipt.json")
    judge = LongitudinalJudgeDecision.model_validate(judge_receipt.get("decision"))
    if completion.get("blind_report_digest") != report.content_digest:
        raise RuntimeError("completion no longer binds the blind report")
    if judge_receipt.get("decision_digest") != canonical_digest(judge):
        raise RuntimeError("judge receipt no longer binds its decision")
    if report.execution_amendment_digest != amendment.content_digest:
        raise RuntimeError("blind report execution-amendment binding drifted")
    if judge_receipt.get("execution_amendment_digest") != amendment.content_digest:
        raise RuntimeError("judge receipt execution-amendment binding drifted")

    config_root = arguments.comparison_config_root.resolve()
    seed = _load_key(config_root / "randomization-seed.key")
    private_plan_path = config_root / "private-plan.json"
    private_plan = _object(private_plan_path)
    if private_plan.get("seed_commitment") != sha256_bytes(seed):
        raise RuntimeError("private plan does not match the committed randomization seed")
    if private_plan.get("external_validation_accessed") is not False:
        raise RuntimeError("private plan claims external-validation access")
    blind_conditions, output_conditions = _condition_assignments(private_plan)

    task_by_id = {task.task_id: task for task in design.tasks}
    grouped: dict[BenchmarkCondition, list[CodexDevelopmentRunObservation]] = defaultdict(list)
    for observation in report.observations:
        condition = blind_conditions.get(observation.blind_condition_id)
        if condition is None:
            raise RuntimeError("blind report contains an unmapped condition ID")
        if output_conditions.get(observation.blind_output_id) is not condition:
            raise RuntimeError("blind report output mapping disagrees with the private plan")
        grouped[condition].append(observation)
    if any(len(grouped[condition]) != 6 for condition in _CONDITIONS):
        raise RuntimeError("unblinded report does not contain six runs per condition")

    compiled_materials = load_compiled_materials(benchmark)
    strong_materials = tuple(
        (benchmark / "condition-materials" / f"strong-profile-stage-{stage}.md").read_text(
            encoding="utf-8"
        )
        for stage in (1, 2, 3)
    )
    profile_maintenance = _profile_maintenance(
        _object(benchmark / "profile-construction-receipt.json"),
        strong_materials,
    )
    compiled_maintenance = [
        {
            "maintenance_actions": protocol.compiled_stage_maintenance_actions[stage - 1],
            "maintenance_seconds": protocol.compiled_stage_maintenance_seconds[stage - 1],
            "material_bytes": len(compiled_materials[stage - 1].encode("utf-8")),
            "material_digest": sha256_bytes(compiled_materials[stage - 1].encode("utf-8")),
            "stage": stage,
            "update_latency_seconds": (protocol.compiled_stage_update_latency_seconds[stage - 1]),
        }
        for stage in (1, 2, 3)
    ]
    judge_counts = _judge_counts(judge, output_conditions)
    condition_results: dict[str, object] = {}
    for condition in _CONDITIONS:
        observations = grouped[condition]
        condition_results[condition.value] = {
            "judge": judge_counts[condition],
            "maintenance": (
                profile_maintenance
                if condition is BenchmarkCondition.STRONG_STATIC_PROFILE
                else compiled_maintenance
            ),
            "stages": _stage_summary(observations, tasks=task_by_id),
            "totals": _totals(observations),
        }

    compiled_stages = condition_results[BenchmarkCondition.COMPILED_ADAPTATION.value]
    profile_stages = condition_results[BenchmarkCondition.STRONG_STATIC_PROFILE.value]
    assert isinstance(compiled_stages, dict) and isinstance(profile_stages, dict)
    compiled_stage_values = compiled_stages["stages"]
    profile_stage_values = profile_stages["stages"]
    assert isinstance(compiled_stage_values, list) and isinstance(profile_stage_values, list)

    def no_regression(metric: str) -> bool:
        for compiled_stage, profile_stage in zip(
            compiled_stage_values,
            profile_stage_values,
            strict=True,
        ):
            assert isinstance(compiled_stage, dict) and isinstance(profile_stage, dict)
            compiled_metric = compiled_stage[metric]
            profile_metric = profile_stage[metric]
            assert isinstance(compiled_metric, dict) and isinstance(profile_metric, dict)
            if int(compiled_metric["passed"]) < int(profile_metric["passed"]):
                return False
        return True

    compiled_final_bytes = _integer(
        compiled_maintenance[-1]["material_bytes"],
        label="compiled final material bytes",
    )
    profile_final_bytes = _integer(
        profile_maintenance[-1]["material_bytes"],
        label="profile final material bytes",
    )
    compiled_final_actions = _integer(
        compiled_maintenance[-1]["maintenance_actions"],
        label="compiled final maintenance actions",
    )
    profile_final_actions = _integer(
        profile_maintenance[-1]["maintenance_actions"],
        label="profile final maintenance actions",
    )
    checks = {
        "all_12_target_records_valid": all(item.valid for item in report.observations),
        "compiled_no_diagnostic_regression_at_any_stage": no_regression("diagnostic"),
        "compiled_no_objective_regression_at_any_stage": no_regression("objective"),
        "compiled_final_material_no_larger_than_profile": (
            compiled_final_bytes <= profile_final_bytes
        ),
        "compiled_final_update_no_more_actions_than_profile": (
            compiled_final_actions <= profile_final_actions
        ),
        "condition_mapping_was_withheld_until_judge_frozen": (
            judge_receipt.get("condition_mapping_access") is False
        ),
        "external_validation_remained_unaccessed": (
            report.external_validation_accessed is False
            and judge_receipt.get("external_validation_accessed") is False
        ),
        "provider_billed_calls_zero": (
            report.provider_billed_calls == 0 and judge_receipt.get("provider_billed_calls") == 0
        ),
    }
    unblinded = {
        "analysis_version": "1.0.0",
        "automated_correctness_is_primary": True,
        "blind_report_digest": report.content_digest,
        "conditions": condition_results,
        "design_digest": design.content_digest,
        "dogfood_instrumentation_metrics": dogfood_metrics,
        "external_validation_accessed": False,
        "execution_amendment_digest": amendment.content_digest,
        "gate": {
            "checks": checks,
            "outcome": "pass" if all(checks.values()) else "fail",
        },
        "judge_decision_digest": canonical_digest(judge),
        "judge_is_secondary": True,
        "private_plan_digest": sha256_file(private_plan_path),
        "provider_billed_calls": 0,
        "randomization_seed_commitment": private_plan["seed_commitment"],
        "source_commit": report.source_commit,
        "total_attempted_subscription_sessions": amendment.maximum_attempted_sessions,
    }
    gate_outcome = "pass" if all(checks.values()) else "fail"
    _exclusive_write(
        output_path,
        (canonical_json(unblinded) + "\n").encode("utf-8"),
    )
    _exclusive_write(markdown_path, _render_markdown(unblinded).encode("utf-8"))
    print(
        canonical_json(
            {
                "gate_outcome": gate_outcome,
                "result_digest": sha256_file(output_path),
            }
        )
    )


if __name__ == "__main__":
    main()
