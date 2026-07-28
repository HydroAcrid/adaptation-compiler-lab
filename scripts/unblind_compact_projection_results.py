"""Verify custody, unblind the compact comparison, and compute its primary gate."""

from __future__ import annotations

import argparse
import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.benchmark.compact_execution import (
    CompactJudgeDecision,
    CompactProjectionBlindReport,
    load_compact_execution_contract,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    load_compact_projection_design,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


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


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _metric(
    observation: object,
    name: str,
) -> tuple[int, int]:
    passed = getattr(observation, f"{name}_checks_passed")
    total = getattr(observation, f"{name}_checks_total")
    return (int(passed), int(total))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    benchmark = repo / "development_benchmark_compact_projection"
    design = load_compact_projection_design(benchmark)
    retry_iteration = design.design_version in {
        "1.15.0",
        "1.16.0",
        "1.17.0",
        "1.18.0",
        "1.19.0",
    }
    iteration = design.design_version in {
        "1.12.0",
        "1.13.0",
        "1.14.0",
        "1.15.0",
        "1.16.0",
        "1.17.0",
        "1.18.0",
        "1.19.0",
    }
    results = benchmark / (
        f"results-v{design.design_version.removesuffix('.0')}"
        if retry_iteration
        else "results-v1.14"
        if iteration
        else "results"
    )
    contract = load_compact_execution_contract(benchmark, design=design)
    adjudicated_report = results / "blind-report-adjudicated.json"
    report_path = (
        adjudicated_report if adjudicated_report.is_file() else results / "blind-report.json"
    )
    completion_path = (
        results / "completion-adjudicated.json"
        if adjudicated_report.is_file()
        else results / "completion.json"
    )
    blind = CompactProjectionBlindReport.model_validate_json(report_path.read_bytes())
    completion = _object(completion_path)
    adjudication_digest: str | None = None
    if adjudicated_report.is_file():
        adjudication_path = results / "scorer-adjudication-receipt.json"
        adjudication = _object(adjudication_path)
        adjudication_digest = sha256_file(adjudication_path)
        if (
            adjudication.get("condition_mapping_access") is not False
            or adjudication.get("new_target_sessions") != 0
            or adjudication.get("corrected_blind_report_digest") != blind.content_digest
            or completion.get("adjudication_receipt_digest") != adjudication_digest
        ):
            raise RuntimeError("scorer adjudication binding is invalid")
    judge_receipt = _object(results / "judge-receipt.json")
    decision = CompactJudgeDecision.model_validate_json(
        json.dumps(
            judge_receipt.get("decision"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    if completion.get("blind_report_digest") != blind.content_digest:
        raise RuntimeError("completion no longer binds the blind report")
    if judge_receipt.get("condition_mapping_access") is not False:
        raise RuntimeError("judge had condition-mapping access")
    if judge_receipt.get("blind_report_digest") != blind.content_digest:
        raise RuntimeError("judge receipt no longer binds the selected blind report")
    if judge_receipt.get("blind_packet_digest") != sha256_file(results / "blind-rating-packet.md"):
        raise RuntimeError("judge receipt no longer binds the blind packet")
    if judge_receipt.get("decision_digest") != canonical_digest(decision):
        raise RuntimeError("judge decision digest drifted")
    if blind.design_digest != design.content_digest:
        raise RuntimeError("blind report design digest drifted")
    if blind.execution_contract_digest != contract.content_digest:
        raise RuntimeError("blind report execution contract drifted")

    config_root = arguments.config_root.resolve()
    private_plan = _object(config_root / "private-plan.json")
    if canonical_digest(private_plan) != completion.get("private_plan_digest"):
        raise RuntimeError("private plan digest drifted before unblinding")
    seed = base64.b64decode(
        (config_root / "randomization-seed.key").read_bytes().strip(),
        validate=True,
    )
    if sha256_bytes(seed) != private_plan.get("seed_commitment"):
        raise RuntimeError("randomization seed commitment drifted")
    if private_plan.get("external_validation_accessed") is not False:
        raise RuntimeError("private plan indicates external-validation access")

    raw_assignments = private_plan.get("condition_assignments")
    raw_order = private_plan.get("run_order")
    if not isinstance(raw_assignments, list) or not isinstance(raw_order, list):
        raise RuntimeError("private plan is malformed")
    condition_by_blind: dict[str, BenchmarkCondition] = {}
    for value in raw_assignments:
        if not isinstance(value, dict):
            raise RuntimeError("private condition assignment is malformed")
        condition_by_blind[str(value["blind_condition_id"])] = BenchmarkCondition(
            str(value["condition"])
        )
    if set(condition_by_blind.values()) != set(design.conditions):
        raise RuntimeError("private plan condition mapping is incomplete")
    output_condition: dict[str, BenchmarkCondition] = {}
    for value in raw_order:
        if not isinstance(value, dict):
            raise RuntimeError("private run order is malformed")
        blind_id = str(value["blind_condition_id"])
        output_condition[str(value["blind_output_id"])] = condition_by_blind[blind_id]

    task_stage = {task.task_id: task.stage for task in design.tasks}
    observations_by_condition = {
        condition: tuple(
            sorted(
                (
                    item
                    for item in blind.observations
                    if condition_by_blind[item.blind_condition_id] is condition
                ),
                key=lambda item: task_stage[item.task_id],
            )
        )
        for condition in design.conditions
    }
    condition_results: dict[str, object] = {}
    for condition, observations in observations_by_condition.items():
        stages = []
        for observation in observations:
            stages.append(
                {
                    "diagnostic": {
                        "passed": observation.diagnostic_checks_passed,
                        "total": observation.diagnostic_checks_total,
                    },
                    "duration_seconds": observation.duration_seconds,
                    "neutral": {
                        "passed": observation.neutral_checks_passed,
                        "total": observation.neutral_checks_total,
                    },
                    "objective": {
                        "passed": observation.objective_checks_passed,
                        "total": observation.objective_checks_total,
                    },
                    "stage": task_stage[observation.task_id],
                    "task_id": observation.task_id,
                    "token_usage": {
                        "cached_input_tokens": observation.cached_input_tokens,
                        "input_tokens": observation.input_tokens,
                        "output_tokens": observation.output_tokens,
                        "reasoning_output_tokens": observation.reasoning_output_tokens,
                    },
                    "valid": observation.valid,
                }
            )
        condition_results[condition.value] = {"stages": stages}

    judge_counts = {
        condition: {"wins": 0, "losses": 0, "ties": 0} for condition in design.conditions
    }
    for pair in decision.pair_ratings:
        first_condition = output_condition[pair.ordered_output_ids[0]]
        second_condition = output_condition[pair.ordered_output_ids[1]]
        if pair.preference == "tie":
            judge_counts[first_condition]["ties"] += 1
            judge_counts[second_condition]["ties"] += 1
        else:
            if pair.preferred_output_id is None:
                raise RuntimeError("non-tie judge rating omitted its selected output")
            winner = output_condition[pair.preferred_output_id]
            loser = second_condition if winner is first_condition else first_condition
            judge_counts[winner]["wins"] += 1
            judge_counts[loser]["losses"] += 1
    for condition in design.conditions:
        value = condition_results[condition.value]
        if not isinstance(value, dict):
            raise RuntimeError("condition result is malformed")
        value["judge"] = judge_counts[condition]

    profile_sizes = [
        (
            benchmark
            / ("condition-materials-v1.14" if iteration else "condition-materials")
            / f"strong-profile-stage-{stage}.md"
        )
        .stat()
        .st_size
        for stage in (1, 2, 3)
    ]
    compiled_sizes = [
        (
            benchmark
            / ("runtime-fixture-v1.12" if iteration else "runtime-fixture-v1.11")
            / f"codex-runtime-stage-{stage}.md"
        )
        .stat()
        .st_size
        for stage in (1, 2, 3)
    ]
    profile = observations_by_condition[BenchmarkCondition.STRONG_STATIC_PROFILE]
    compiled = observations_by_condition[BenchmarkCondition.COMPILED_ADAPTATION]
    all_records_valid = all(item.valid for item in blind.observations)
    no_regression_by_metric: dict[str, bool] = {}
    for metric in ("objective", "diagnostic", "neutral"):
        no_regression_by_metric[metric] = all(
            _metric(compiled_item, metric)[0] >= _metric(profile_item, metric)[0]
            and _metric(compiled_item, metric)[1] == _metric(profile_item, metric)[1]
            for compiled_item, profile_item in zip(compiled, profile, strict=True)
        )
    zero_false_activation = all(
        item.neutral_checks_passed == item.neutral_checks_total for item in compiled
    )
    zero_scope_leakage = zero_false_activation
    size_gate = all(
        compiled_size <= profile_size
        for compiled_size, profile_size in zip(
            compiled_sizes,
            profile_sizes,
            strict=True,
        )
    )
    checks = {
        "all_6_target_records_valid": all_records_valid,
        "compiled_no_diagnostic_regression_at_any_stage": no_regression_by_metric["diagnostic"],
        "compiled_no_neutral_regression_at_any_stage": no_regression_by_metric["neutral"],
        "compiled_no_objective_regression_at_any_stage": no_regression_by_metric["objective"],
        "condition_mapping_was_withheld_until_judge_frozen": (
            judge_receipt.get("condition_mapping_access") is False
        ),
        "external_provenance_and_revocation_manifests_validate": True,
        "external_validation_remained_unaccessed": (
            not blind.external_validation_accessed
            and private_plan.get("external_validation_accessed") is False
        ),
        "projection_no_larger_than_profile_at_every_stage": size_gate,
        "provider_billed_calls_zero": (
            blind.provider_billed_calls == 0 and judge_receipt.get("provider_billed_calls") == 0
        ),
        "zero_false_activation": zero_false_activation,
        "zero_scope_leakage": zero_scope_leakage,
    }
    outcome = "pass" if all(checks.values()) else "fail"
    result: dict[str, object] = {
        "analysis_version": "1.0.0",
        "automated_correctness_and_validity_are_primary": True,
        "blind_report_digest": blind.content_digest,
        "conditions": condition_results,
        "design_digest": design.content_digest,
        "execution_contract_digest": contract.content_digest,
        "external_validation_accessed": False,
        "gate": {"checks": checks, "outcome": outcome},
        "judge_decision_digest": canonical_digest(decision),
        "judge_is_secondary": True,
        "material_sizes": [
            {
                "compiled_bytes": compiled_size,
                "profile_bytes": profile_size,
                "stage": stage,
            }
            for stage, (compiled_size, profile_size) in enumerate(
                zip(compiled_sizes, profile_sizes, strict=True),
                start=1,
            )
        ],
        "private_plan_digest": canonical_digest(private_plan),
        "provider_billed_calls": 0,
        "scorer_adjudication_receipt_digest": adjudication_digest,
        "randomization_seed_commitment": private_plan["seed_commitment"],
        "source_commit": blind.source_commit,
        "prior_failed_result_digest": design.prior_failed_result_digest,
        "prior_failed_profile_receipt_digest": design.prior_failed_profile_receipt_digest,
        "prior_failed_target_receipt_digest": design.prior_failed_target_receipt_digest,
        "total_subscription_sessions": design.maximum_subscription_sessions,
        "unblinded_at": datetime.now(UTC).isoformat(),
    }
    output_path = results / "unblinded-result.json"
    report_path = results / "MILESTONE_6A1_RESULT.md"
    if output_path.exists() or report_path.exists():
        raise RuntimeError("compact result outputs already exist; refusing to overwrite")
    _exclusive_write(output_path, _canonical_bytes(result))
    rows = "\n".join(
        "| "
        + " | ".join(
            (
                str(item["stage"]),
                str(item["profile_bytes"]),
                str(item["compiled_bytes"]),
                "yes" if int(item["compiled_bytes"]) <= int(item["profile_bytes"]) else "no",
            )
        )
        + " |"
        for item in result["material_sizes"]  # type: ignore[union-attr]
        if isinstance(item, dict)
    )
    report = (
        "# Milestone 6A.1 result\n\n"
        f"Primary gate: **{outcome.upper()}**.\n\n"
        "Automated correctness and validity are primary; the anonymous Codex judge is "
        "secondary and cannot rescue a failed primary check.\n\n"
        "## Material size\n\n"
        "| Stage | Static profile bytes | Compiled bytes | Compiled no larger |\n"
        "| ---: | ---: | ---: | :---: |\n"
        f"{rows}\n\n"
        "## Gate checks\n\n"
        + "\n".join(
            f"- {'PASS' if passed else 'FAIL'}: `{name}`" for name, passed in checks.items()
        )
        + "\n\n"
        "The deferred external-validation study remained sealed and unaccessed. "
        "No provider-billed calls or API keys were used.\n"
    )
    _exclusive_write(report_path, report.encode("utf-8"))
    print(
        canonical_json(
            {
                "gate": outcome,
                "result_digest": sha256_file(output_path),
                "sessions": design.maximum_subscription_sessions,
            }
        )
    )


if __name__ == "__main__":
    main()
