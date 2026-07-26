"""Unblind the four-cell Claude repair only after a durable isolated-AI rating."""

from __future__ import annotations

import argparse
import base64
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.claude_repair import (
    ClaudeRepairBlindReport,
    ClaudeRepairPrivatePlan,
    ClaudeRepairPublicPlan,
)
from adaptation_compiler_lab.benchmark.isolated_rating import IsolatedAIRatingReceipt
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from adaptation_compiler_lab.serialization import canonical_json


def _canonical_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _raw_ref(value: dict[str, Any]) -> RawPayloadRef:
    return RawPayloadRef(
        sha256=value["sha256"],
        size_bytes=value["size_bytes"],
        media_type=value["media_type"],
        relative_path=value["relative_path"],
    )


def _counts(passed: int, total: int) -> dict[str, int]:
    return {"passed": passed, "total": total}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--benchmark-output-root", type=Path, required=True)
    parser.add_argument("--benchmark-config-root", type=Path, required=True)
    parser.add_argument("--rating", type=Path, required=True)
    parser.add_argument("--rating-checksum", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    benchmark_output_root = arguments.benchmark_output_root.resolve()
    rating_path = arguments.rating.resolve()
    rating_checksum = arguments.rating_checksum.resolve()
    packet_path = arguments.packet.resolve()
    result_output = arguments.result_output.resolve()
    if not all(path.is_relative_to(repo) for path in (rating_path, rating_checksum, packet_path)):
        raise RuntimeError("rating, checksum, and packet must be durable repository files")
    if result_output.is_relative_to(repo) or result_output.exists():
        raise RuntimeError("unblinded result output must be a new external file")
    rating_hex = rating_checksum.read_text(encoding="ascii").split()[0]
    if sha256_file(rating_path) != f"sha256:{rating_hex}":
        raise RuntimeError("isolated blind rating checksum failed")
    rating = IsolatedAIRatingReceipt.model_validate_json(rating_path.read_bytes())
    completion = json.loads((benchmark_output_root / "completion.json").read_text(encoding="utf-8"))
    if (
        rating.presentation_sha256 != sha256_file(packet_path)
        or rating.blind_report_digest != completion["blind_report_digest"]
        or rating.completion_receipt_digest
        != sha256_file(benchmark_output_root / "completion.json")
    ):
        raise RuntimeError("isolated rating does not bind the completed blind run")

    key = RawEncryptionKey.from_file(
        arguments.benchmark_config_root.resolve() / "development-encryption.key",
        workspace_root=repo,
    )
    store = LocalRawPayloadStore(
        benchmark_output_root / "encrypted",
        encryption_key=key,
    )
    private_plan = ClaudeRepairPrivatePlan.model_validate_json(
        store.read(_raw_ref(completion["private_plan_ref"]))
    )
    blind_report = ClaudeRepairBlindReport.model_validate_json(
        store.read(_raw_ref(completion["blind_report_ref"]))
    )
    public_plan = ClaudeRepairPublicPlan.model_validate_json(
        (benchmark_output_root / "public-plan.json").read_bytes()
    )
    if (
        private_plan.content_digest != public_plan.private_plan_digest
        or blind_report.content_digest != completion["blind_report_digest"]
        or blind_report.design_digest != public_plan.design_digest
    ):
        raise RuntimeError("repair plan or report failed its public commitments")
    condition_by_blind = {
        item.blind_condition_id: item.condition for item in private_plan.condition_assignments
    }
    observation_by_output = {item.blind_output_id: item for item in blind_report.observations}
    if len(observation_by_output) != 4:
        raise RuntimeError("repair unblinding requires all four observations")

    progress = tuple(
        json.loads(line)
        for line in (benchmark_output_root / "progress.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    if len(progress) != 4:
        raise RuntimeError("repair unblinding requires four encrypted bundles")
    bundle_details: dict[str, dict[str, Any]] = {}
    for entry in progress:
        bundle = json.loads(store.read(_raw_ref(entry["bundle_ref"])))
        scorer = json.loads(base64.b64decode(bundle["scorer_output_base64"], validate=True))
        failed_checks = [
            f"{group}:{name}"
            for group, checks in scorer.items()
            for name, passed in checks.items()
            if not passed
        ]
        bundle_details[entry["blind_output_id"]] = {
            "failed_checks": sorted(failed_checks),
            "target_visible_test_returncode": bundle["visible_test"]["returncode"],
        }

    preference_wins: dict[BenchmarkCondition, int] = defaultdict(int)
    preference_ties: dict[BenchmarkCondition, int] = defaultdict(int)
    pair_results = []
    for preference in rating.decision.pair_ratings:
        observations = [
            observation_by_output[output_id] for output_id in preference.ordered_output_ids
        ]
        if any(item.task_id != preference.task_id for item in observations):
            raise RuntimeError("isolated rating pair does not match its frozen task")
        conditions = [condition_by_blind[item.blind_condition_id] for item in observations]
        if set(conditions) != {
            BenchmarkCondition.STRONG_STATIC_PROFILE,
            BenchmarkCondition.COMPILED_ADAPTATION,
        }:
            raise RuntimeError("isolated rating pair does not compare both conditions")
        preferred_condition = None
        if preference.preference == "tie":
            for condition in conditions:
                preference_ties[condition] += 1
        else:
            if preference.preferred_output_id is None:
                raise RuntimeError("non-tie isolated rating lacks a preferred output")
            preferred = observation_by_output[preference.preferred_output_id]
            preferred_condition = condition_by_blind[preferred.blind_condition_id]
            preference_wins[preferred_condition] += 1
        pair_results.append(
            {
                "task_id": preference.task_id,
                "preference": preference.preference,
                "preferred_condition": (
                    preferred_condition.value if preferred_condition is not None else None
                ),
                "rationale": preference.rationale,
                "outputs": [
                    {
                        "presentation_position": "first" if index == 0 else "second",
                        "blind_output_id": observation.blind_output_id,
                        "condition": condition.value,
                        "valid": observation.valid,
                        "objective": _counts(
                            observation.objective_checks_passed,
                            observation.objective_checks_total,
                        ),
                        "diagnostic": _counts(
                            observation.diagnostic_checks_passed,
                            observation.diagnostic_checks_total,
                        ),
                        "neutral": _counts(
                            observation.neutral_checks_passed,
                            observation.neutral_checks_total,
                        ),
                        "input_tokens": observation.input_tokens,
                        "cache_creation_input_tokens": observation.cache_creation_input_tokens,
                        "cache_read_input_tokens": observation.cache_read_input_tokens,
                        "output_tokens": observation.output_tokens,
                        "cost_usd": observation.total_cost_usd,
                        "duration_seconds": observation.duration_seconds,
                        **bundle_details[observation.blind_output_id],
                    }
                    for index, (observation, condition) in enumerate(
                        zip(observations, conditions, strict=True)
                    )
                ],
            }
        )

    aggregates = []
    for condition in (
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    ):
        observations = [
            item
            for item in blind_report.observations
            if condition_by_blind[item.blind_condition_id] is condition
        ]
        valid = [item for item in observations if item.valid]
        aggregates.append(
            {
                "condition": condition.value,
                "preference_wins": preference_wins[condition],
                "preference_ties": preference_ties[condition],
                "valid_runs": len(valid),
                "invalid_runs": len(observations) - len(valid),
                "objective": _counts(
                    sum(item.objective_checks_passed for item in valid),
                    sum(item.objective_checks_total for item in valid),
                ),
                "diagnostic": _counts(
                    sum(item.diagnostic_checks_passed for item in valid),
                    sum(item.diagnostic_checks_total for item in valid),
                ),
                "neutral": _counts(
                    sum(item.neutral_checks_passed for item in valid),
                    sum(item.neutral_checks_total for item in valid),
                ),
                "input_tokens": sum(item.input_tokens for item in observations),
                "cache_creation_input_tokens": sum(
                    item.cache_creation_input_tokens for item in observations
                ),
                "cache_read_input_tokens": sum(
                    item.cache_read_input_tokens for item in observations
                ),
                "output_tokens": sum(item.output_tokens for item in observations),
                "cost_usd": sum(item.total_cost_usd for item in observations),
            }
        )
    aggregate_by_condition = {item["condition"]: item for item in aggregates}
    strong = aggregate_by_condition[BenchmarkCondition.STRONG_STATIC_PROFILE.value]
    compiled = aggregate_by_condition[BenchmarkCondition.COMPILED_ADAPTATION.value]
    if compiled["preference_wins"] > strong["preference_wins"]:
        comparison = "compiled_descriptively_above_strong"
    elif compiled["preference_wins"] < strong["preference_wins"]:
        comparison = "compiled_descriptively_below_strong"
    else:
        comparison = "preference_tie"
    result = {
        "result_version": "1.0.0",
        "benchmark_id": rating.benchmark_id,
        "design_digest": public_plan.design_digest,
        "private_plan_digest": private_plan.content_digest,
        "blind_report_digest": blind_report.content_digest,
        "isolated_rating_digest": sha256_file(rating_path),
        "rating_method": {
            "kind": "isolated_ai",
            "model": rating.scorer_model,
            "reasoning_effort": rating.scorer_reasoning_effort,
            "context_inputs": rating.context_inputs,
            "tool_use_observed": rating.tool_use_observed,
            "kevin_preference_measured": False,
        },
        "pair_results": pair_results,
        "condition_aggregates": aggregates,
        "total_cost_usd": sum(item.total_cost_usd for item in blind_report.observations),
        "instrument_status": {
            "all_four_runs_valid": all(item.valid for item in blind_report.observations),
            "all_visible_tests_executed_successfully": all(
                item.visible_test_returncode == 0 for item in blind_report.observations
            ),
            "all_workspaces_and_configurations_destroyed": all(
                item.workspace_destroyed and item.config_destroyed
                for item in blind_report.observations
            ),
        },
        "descriptive_comparison": {
            "classification": comparison,
            "compiled_preference_wins": compiled["preference_wins"],
            "strong_profile_preference_wins": strong["preference_wins"],
            "preference_ties": compiled["preference_ties"],
            "compiled_beats_or_ties_strong_on_objective_checks": (
                compiled["objective"]["passed"] >= strong["objective"]["passed"]
            ),
            "compiled_beats_or_ties_strong_on_diagnostic_checks": (
                compiled["diagnostic"]["passed"] >= strong["diagnostic"]["passed"]
            ),
            "compiled_beats_or_ties_strong_on_neutral_checks": (
                compiled["neutral"]["passed"] >= strong["neutral"]["passed"]
            ),
        },
        "decision": "small_public_ai_judged_development_comparison",
        "decision_reason": (
            "The repaired public tasks and isolated scorer provide descriptive general-quality "
            "evidence. Two tasks, one run per condition, and a non-Kevin AI preference scorer "
            "cannot establish durable product superiority or Kevin-specific adaptation."
        ),
        "compiled_product_advantage_established": False,
        "kevin_specific_preference_claim_allowed": False,
        "general_cross_agent_claim_allowed": False,
        "milestone_6_custody_accessed": False,
    }
    result_output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    _exclusive_write(result_output, _canonical_bytes(result), mode=0o600)


if __name__ == "__main__":
    main()
