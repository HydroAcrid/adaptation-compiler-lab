from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.benchmark.claude_repair import load_claude_repair_design
from adaptation_compiler_lab.benchmark.isolated_rating import (
    IsolatedAIRatingReceipt,
    isolated_rating_output_schema,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.runners.codex_blind_rating import (
    CODEX_BLIND_RATING_CONTRACT,
)


def test_repair_preregistration_binds_the_new_tasks_and_frozen_materials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_repair_gate")
    preregistration_path = (
        repository / "development_benchmark_claude_repair" / "PREREGISTRATION-v1.0.json"
    )
    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    design = load_claude_repair_design(
        repository / "development_benchmark_claude_repair",
        frozen_at=datetime.fromisoformat(preregistration["frozen_at"]),
    )

    manifests = coordinator._validate_preregistration(
        preregistration=preregistration,
        repo=repository,
        design=design,
        runtime_lock_digest=sha256_file(coordinator.DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK),
        source_commit=preregistration["implementation_commit"],
    )

    assert design.content_digest == preregistration["design_digest"]
    assert design.planned_runs == 4
    assert design.max_usd_total == 1.0
    assert set(manifests) == {task.task_id for task in design.tasks}
    assert set(manifests.values()) == {("python3 -m unittest -v",)}
    assert preregistration["conditions"] == [
        "strong_static_profile",
        "compiled_adaptation",
    ]
    assert preregistration["materials"] == {
        "compiled_v2": coordinator.EXPECTED_COMPILED_V2_TEXT_DIGEST,
        "compiled_lineage": coordinator.EXPECTED_COMPILED_V2_MATERIAL_DIGEST,
        "strong_static_profile": coordinator.EXPECTED_STRONG_TEXT_DIGEST,
    }
    assert preregistration["boundaries"]["milestone_6_custody_accessed"] is False
    assert preregistration["boundaries"]["milestone_6_materials_modified"] is False
    assert preregistration["decision_policy"]["stop_for_kevin_ratings_before_unblinding"]


def test_repair_preregistration_preserves_prior_v2_9_evidence() -> None:
    repository = Path(__file__).parents[2]
    repair = json.loads(
        (
            repository / "development_benchmark_claude_repair" / "PREREGISTRATION-v1.0.json"
        ).read_text(encoding="utf-8")
    )

    assert repair["prior_evidence"] == {
        "v2_9_rating_digest": sha256_file(
            repository / "development_benchmark_claude" / "results" / "kevin-blind-rating-v2.9.json"
        ),
        "v2_9_result_digest": sha256_file(
            repository / "development_benchmark_claude" / "results" / "unblinded-result-v2.9.json"
        ),
        "v2_9_analysis_digest": sha256_file(repository / "CLAUDE_CORRECTED_COMPARISON.md"),
    }


def test_repair_blind_packet_is_digest_bound_and_condition_safe() -> None:
    repository = Path(__file__).parents[2]
    results = repository / "development_benchmark_claude_repair" / "results"
    packet = results / "blind-rating-packet-v1.0.md"
    receipt = json.loads((results / "blind-run-receipt-v1.0.json").read_text(encoding="utf-8"))

    assert sha256_file(packet) == receipt["blind_packet_digest"]
    assert receipt["completed_runs"] == receipt["valid_runs"] == receipt["planned_runs"] == 4
    assert receipt["condition_mapping_withheld"] is True
    assert receipt["objective_scores_withheld"] is True
    assert receipt["token_and_cost_data_withheld"] is True
    assert receipt["milestone_6_custody_accessed"] is False
    serialized = packet.read_text(encoding="utf-8")
    for forbidden in (
        "strong_static_profile",
        "compiled_adaptation",
        "compiled_v2",
        "blind_condition_id",
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "sk-ant-",
        "/home/kevin_dotel",
        ".acl-condition",
        "total_cost_usd",
        "input_tokens",
        "output_tokens",
    ):
        assert forbidden not in serialized


def test_isolated_rating_is_frozen_before_condition_reveal() -> None:
    repository = Path(__file__).parents[2]
    root = repository / "development_benchmark_claude_repair"
    preregistration = json.loads(
        (root / "ISOLATED_RATING_PREREGISTRATION-v1.4.json").read_text(encoding="utf-8")
    )
    blind_receipt = json.loads(
        (root / "results" / "blind-run-receipt-v1.0.json").read_text(encoding="utf-8")
    )
    schema_bytes = (
        json.dumps(
            isolated_rating_output_schema(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")

    assert preregistration["packet_digest"] == sha256_file(
        root / "results" / "blind-rating-packet-v1.0.md"
    )
    assert (
        preregistration["completion_receipt_digest"] == blind_receipt["completion_receipt_digest"]
    )
    assert preregistration["blind_report_digest"].startswith("sha256:")
    assert preregistration["rating_contract_digest"] == sha256_bytes(
        CODEX_BLIND_RATING_CONTRACT.encode()
    )
    assert preregistration["output_schema_digest"] == sha256_bytes(schema_bytes)
    assert preregistration["scorer"]["model"] == "gpt-5.6-sol"
    assert preregistration["scorer"]["reasoning_effort"] == "xhigh"
    assert preregistration["supersedes_failed_preregistration"].endswith("v1.3.json")
    assert preregistration["rating_policy"]["kevin_specific_preference_measured"] is False
    assert preregistration["boundaries"]["milestone_6_custody_accessed"] is False


def test_isolated_rating_preregistration_json_pairs_enter_strict_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_isolated_codex_blind_rating")
    preregistration = json.loads(
        (
            repository
            / "development_benchmark_claude_repair"
            / "ISOLATED_RATING_PREREGISTRATION-v1.4.json"
        ).read_text(encoding="utf-8")
    )

    pairs = coordinator._pair_bindings(preregistration["pairs"])

    assert len(pairs) == 2
    assert all(isinstance(item.ordered_output_ids, tuple) for item in pairs)


def test_isolated_rating_raw_bundle_normalizes_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_isolated_codex_blind_rating")

    encoded = coordinator._canonical_bytes(
        {"finished_at": datetime(2026, 7, 26, 14, 20, tzinfo=UTC)}
    )

    assert json.loads(encoded) == {"finished_at": "2026-07-26T14:20:00Z"}


def test_isolated_ai_rating_is_durable_and_still_blind() -> None:
    repository = Path(__file__).parents[2]
    results = repository / "development_benchmark_claude_repair" / "results"
    rating_path = results / "isolated-ai-rating-v1.0.json"
    checksum = (results / "isolated-ai-rating-v1.0.sha256").read_text(encoding="ascii").split()[0]
    rating = IsolatedAIRatingReceipt.model_validate_json(rating_path.read_bytes())

    assert sha256_file(rating_path) == f"sha256:{checksum}"
    assert rating.presentation_sha256 == sha256_file(results / "blind-rating-packet-v1.0.md")
    assert rating.scorer_model == "gpt-5.6-sol"
    assert rating.scorer_reasoning_effort == "xhigh"
    assert rating.context_inputs == "rating_contract_and_anonymous_packet_only"
    assert not rating.condition_mapping_seen
    assert not rating.objective_scores_seen
    assert not rating.project_repository_visible
    assert not rating.host_home_visible
    assert not rating.tool_use_observed
    assert not rating.milestone_6_custody_accessed
    assert len(rating.decision.pair_ratings) == 2


def test_unblinded_repair_result_binds_rating_and_preserves_boundaries() -> None:
    repository = Path(__file__).parents[2]
    results = repository / "development_benchmark_claude_repair" / "results"
    result_path = results / "unblinded-result-v1.0.json"
    checksum = (results / "unblinded-result-v1.0.sha256").read_text(encoding="ascii").split()[0]
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert sha256_file(result_path) == f"sha256:{checksum}"
    assert result["isolated_rating_digest"] == sha256_file(results / "isolated-ai-rating-v1.0.json")
    assert result["descriptive_comparison"] == {
        "classification": "compiled_descriptively_above_strong",
        "compiled_beats_or_ties_strong_on_diagnostic_checks": True,
        "compiled_beats_or_ties_strong_on_neutral_checks": True,
        "compiled_beats_or_ties_strong_on_objective_checks": True,
        "compiled_preference_wins": 1,
        "preference_ties": 1,
        "strong_profile_preference_wins": 0,
    }
    assert result["total_cost_usd"] == pytest.approx(0.33626555)
    assert result["instrument_status"] == {
        "all_four_runs_valid": True,
        "all_visible_tests_executed_successfully": True,
        "all_workspaces_and_configurations_destroyed": True,
    }
    assert result["rating_method"] == {
        "context_inputs": "rating_contract_and_anonymous_packet_only",
        "kevin_preference_measured": False,
        "kind": "isolated_ai",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "tool_use_observed": False,
    }
    assert result["compiled_product_advantage_established"] is False
    assert result["general_cross_agent_claim_allowed"] is False
    assert result["kevin_specific_preference_claim_allowed"] is False
    assert result["milestone_6_custody_accessed"] is False
