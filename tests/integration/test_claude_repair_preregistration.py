from __future__ import annotations

import importlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.benchmark.claude_repair import load_claude_repair_design
from adaptation_compiler_lab.benchmark.isolated_rating import IsolatedBlindRatingDecision
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
        (root / "ISOLATED_RATING_PREREGISTRATION-v1.0.json").read_text(encoding="utf-8")
    )
    blind_receipt = json.loads(
        (root / "results" / "blind-run-receipt-v1.0.json").read_text(encoding="utf-8")
    )
    schema_bytes = (
        json.dumps(
            IsolatedBlindRatingDecision.model_json_schema(),
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
    assert preregistration["rating_policy"]["kevin_specific_preference_measured"] is False
    assert preregistration["boundaries"]["milestone_6_custody_accessed"] is False
