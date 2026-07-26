"""Reveal a completed Claude development mapping only after a durable blind rating."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.claude_development import (
    ClaudeDevelopmentBlindReport,
    ClaudeDevelopmentPrivatePlan,
    ClaudeDevelopmentPublicPlan,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)


def _file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _raw_ref(value: dict[str, Any]) -> RawPayloadRef:
    return RawPayloadRef(
        sha256=value["sha256"],
        size_bytes=value["size_bytes"],
        media_type=value["media_type"],
        relative_path=value["relative_path"],
    )


def _counts(passed: int, total: int) -> dict[str, int]:
    return {"passed": passed, "total": total}


def _objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for nested in value.values():
            found.extend(_objects(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_objects(nested))
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--rating", type=Path, required=True)
    parser.add_argument("--rating-checksum", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument(
        "--result-id",
        default="claude-haiku-compiler-v2-development-comparison",
    )
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    output_root = arguments.output_root.resolve()
    rating_path = arguments.rating.resolve()
    rating_checksum = arguments.rating_checksum.resolve()
    packet_path = arguments.packet.resolve()
    if not all(path.is_relative_to(repo) for path in (rating_path, rating_checksum, packet_path)):
        raise RuntimeError("rating, checksum, and packet must be durable repository files")
    rating = json.loads(rating_path.read_text(encoding="utf-8"))
    expected_rating_hex = rating_checksum.read_text(encoding="ascii").split()[0]
    if _file_digest(rating_path) != f"sha256:{expected_rating_hex}":
        raise RuntimeError("blind rating checksum failed")
    if rating["condition_mapping_seen"] or rating["objective_scores_seen"]:
        raise RuntimeError("rating was not recorded blind")

    completion = json.loads((output_root / "completion.json").read_text(encoding="utf-8"))
    if (
        rating["presentation_sha256"] != _file_digest(packet_path)
        or rating["blind_report_digest"] != completion["blind_report_digest"]
    ):
        raise RuntimeError("rating does not bind the completed blind packet and report")

    key = RawEncryptionKey.from_file(
        arguments.config_root.resolve() / "development-encryption.key",
        workspace_root=repo,
    )
    store = LocalRawPayloadStore(output_root / "encrypted", encryption_key=key)
    private_plan = ClaudeDevelopmentPrivatePlan.model_validate_json(
        store.read(_raw_ref(completion["private_plan_ref"]))
    )
    blind_report = ClaudeDevelopmentBlindReport.model_validate_json(
        store.read(_raw_ref(completion["blind_report_ref"]))
    )
    public_plan = ClaudeDevelopmentPublicPlan.model_validate_json(
        (output_root / "public-plan.json").read_bytes()
    )
    if (
        private_plan.content_digest != public_plan.private_plan_digest
        or blind_report.content_digest != completion["blind_report_digest"]
        or blind_report.design_digest != public_plan.design_digest
    ):
        raise RuntimeError("private plan or blind report failed its public commitments")

    condition_by_blind = {
        item.blind_condition_id: item.condition for item in private_plan.condition_assignments
    }
    observation_by_output = {item.blind_output_id: item for item in blind_report.observations}
    if len(observation_by_output) != 16:
        raise RuntimeError("unblinding requires all sixteen observations")
    progress = tuple(
        json.loads(line)
        for line in (output_root / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    )
    if len(progress) != 16:
        raise RuntimeError("unblinding requires all sixteen encrypted bundle references")
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
        bash_calls = []
        for item in _objects(bundle["events"]):
            if item.get("type") == "tool_use" and item.get("name") == "Bash":
                input_value = item.get("input")
                if isinstance(input_value, dict):
                    bash_calls.append(
                        {
                            "command": input_value.get("command"),
                            "description": input_value.get("description"),
                            "timeout": input_value.get("timeout"),
                        }
                    )
        tool_errors = []
        for item in _objects(bundle["events"]):
            if item.get("type") != "tool_result" or not item.get("is_error"):
                continue
            content = item.get("content")
            if isinstance(content, str):
                tool_errors.append(content[:500])
        visible_test = bundle["visible_test"]
        bundle_details[entry["blind_output_id"]] = {
            "bash_attempt_count": len(bash_calls),
            "bash_permission_denial_observed": any(
                "Permission to use Bash has been denied" in value for value in tool_errors
            ),
            "failed_checks": sorted(failed_checks),
            "target_visible_test_returncode": visible_test["returncode"],
        }

    preference_wins: dict[BenchmarkCondition, int] = defaultdict(int)
    preference_ties: dict[BenchmarkCondition, int] = defaultdict(int)
    pair_results = []
    for preference in rating["pair_preferences"]:
        output_ids = preference["ordered_output_ids"]
        observations = [observation_by_output[output_id] for output_id in output_ids]
        if any(
            item.task_id != preference["task_id"] or item.repetition != preference["repetition"]
            for item in observations
        ):
            raise RuntimeError("blind rating output pair does not match its frozen cell")
        conditions = [condition_by_blind[item.blind_condition_id] for item in observations]
        if set(conditions) != {
            BenchmarkCondition.STRONG_STATIC_PROFILE,
            BenchmarkCondition.COMPILED_ADAPTATION,
        }:
            raise RuntimeError("blind rating pair does not compare both conditions")
        preferred_condition = None
        if preference["preference"] == "tie":
            for condition in conditions:
                preference_ties[condition] += 1
        else:
            preferred_output_id = preference["preferred_output_id"]
            preferred_observation = observation_by_output[preferred_output_id]
            preferred_condition = condition_by_blind[preferred_observation.blind_condition_id]
            preference_wins[preferred_condition] += 1
        pair_results.append(
            {
                "task_id": preference["task_id"],
                "repetition": preference["repetition"],
                "preference": preference["preference"],
                "preferred_condition": (
                    preferred_condition.value if preferred_condition is not None else None
                ),
                "rationale": preference["rationale"],
                "outputs": [
                    {
                        "presentation_position": ("first" if index == 0 else "second"),
                        "blind_output_id": observation.blind_output_id,
                        "condition": condition.value,
                        "valid": observation.valid,
                        "invalid_reason": observation.invalid_reason,
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
                        "cache_creation_input_tokens": (observation.cache_creation_input_tokens),
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

    aggregates: list[dict[str, Any]] = []
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
    all_visible_tests_executed = all(
        details["target_visible_test_returncode"] == 0 for details in bundle_details.values()
    )
    benchmark_limitation = rating.get(
        "benchmark_limitation",
        rating.get("instrument_limitation"),
    )
    result = {
        "result_version": "1.1.0",
        "benchmark_id": arguments.result_id,
        "design_digest": public_plan.design_digest,
        "private_plan_digest": private_plan.content_digest,
        "blind_report_digest": blind_report.content_digest,
        "preference_rating_digest": _file_digest(rating_path),
        "pair_results": pair_results,
        "condition_aggregates": aggregates,
        "total_cost_usd": sum(item.total_cost_usd for item in blind_report.observations),
        "instrument_status": {
            "all_sixteen_runs_valid": all(item.valid for item in blind_report.observations),
            "all_visible_tests_executed_successfully": all_visible_tests_executed,
            "runner_test_execution_repaired": all_visible_tests_executed,
        },
        "benchmark_sensitivity_limitation": benchmark_limitation,
        "descriptive_comparison": {
            "compiled_preference_wins": compiled["preference_wins"],
            "strong_profile_preference_wins": strong["preference_wins"],
            "preference_ties": compiled["preference_ties"],
            "compiled_beats_or_ties_strong_on_preference": (
                compiled["preference_wins"] >= strong["preference_wins"]
            ),
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
        "decision": "benchmark_limited_descriptive_comparison",
        "decision_reason": (
            "The corrected runner executed the bounded tests for every valid run. The comparison "
            "is descriptive because the scorer found meaningful edge-case differences that the "
            "two-test visible suites did not expose, so this run alone cannot establish a durable "
            "compiled-pack advantage."
        ),
        "compiled_product_advantage_established": False,
        "cross_agent_comparison_executed": True,
        "cross_agent_claim_allowed": False,
        "milestone_6_custody_accessed": False,
    }
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
