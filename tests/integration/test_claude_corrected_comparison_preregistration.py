from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.benchmark.claude_development import (
    load_claude_development_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import RawPayloadRef


def test_corrected_comparison_is_frozen_to_public_tasks_and_passing_instrument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_development_gate")
    path = repository / "development_benchmark_claude" / "PREREGISTRATION-v2.3.json"
    preregistration = json.loads(path.read_text(encoding="utf-8"))
    design = load_claude_development_design(
        repository / "development_benchmark_claude",
        frozen_at=datetime.fromisoformat(preregistration["frozen_at"]),
    )

    execution, manifests = coordinator._corrected_execution_contract(
        preregistration,
        task_ids={task.task_id for task in design.tasks},
    )

    assert design.content_digest == preregistration["design_digest"]
    assert execution["planned_runs"] == 16
    assert execution["max_usd_per_run"] == 0.25
    assert execution["max_usd_total"] == 4.0
    assert len(manifests["claude-development-debugging-verification"]) == 2
    assert all(commands[0] == "python3 -m unittest -v" for commands in manifests.values())
    assert preregistration["boundaries"] == {
        "held_out": False,
        "reuses_previously_executed_public_tasks": True,
        "prior_outputs_and_scores_are_known_to_the_construction_context": True,
        "condition_materials_unchanged_after_prior_results": True,
        "milestone_6_custody_accessed": False,
        "milestone_6_materials_modified": False,
        "full_paid_milestone_6_pilot_authorized": False,
        "general_thesis_claim_allowed": False,
    }
    assert preregistration["prior_evidence"]["instrument_success_receipt_digest"] == sha256_file(
        repository
        / "development_benchmark_claude"
        / "results"
        / "instrument-canary-success-v12.json"
    )
    prior_paths = {
        "corrected_comparison_v2_0_failure_digest": (
            "results/corrected-comparison-instrument-failure-v2.0.json"
        ),
        "corrected_comparison_v2_1_failure_digest": (
            "results/corrected-comparison-instrument-failure-v2.1.json"
        ),
        "corrected_comparison_v2_2_failure_digest": (
            "results/corrected-comparison-instrument-failure-v2.2.json"
        ),
        "instrument_success_receipt_digest": "results/instrument-canary-success-v12.json",
        "v1_2_blind_rating_digest": "results/kevin-blind-rating-v1.2.json",
        "v1_2_unblinded_result_digest": "results/unblinded-result-v1.2.json",
        "v1_2_analysis_digest": "UNBLINDED_ANALYSIS-v1.2.md",
    }
    benchmark_root = repository / "development_benchmark_claude"
    assert preregistration["prior_evidence"] == {
        name: sha256_file(benchmark_root / relative_path)
        for name, relative_path in prior_paths.items()
    }


def test_corrected_comparison_validity_does_not_require_a_perfect_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_development_gate")

    assert (
        coordinator._comparison_invalid_reasons(
            terminal_reasons=[],
            runner_failure_reason=None,
            timed_out=False,
            exit_code=0,
            config_destroyed=True,
            condition_leakage_observed=False,
        )
        == []
    )


def test_successful_alias_receipt_excludes_out_of_manifest_trace_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_development_gate")
    events = (
        {
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "approved-use",
                        "name": "Bash",
                        "input": {"command": "acl-test-full"},
                    },
                    {
                        "type": "tool_use",
                        "id": "rejected-use",
                        "name": "Bash",
                        "input": {"command": "python3 -m unittest -v"},
                    },
                ]
            }
        },
        {
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "approved-use",
                        "is_error": False,
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "rejected-use",
                        "is_error": False,
                    },
                ]
            }
        },
    )

    assert coordinator._successful_audited_aliases(
        events,
        accepted_aliases={"acl-test-full"},
    ) == {"acl-test-full"}


def test_failure_receipt_serializes_encrypted_reference_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_development_gate")
    reference = RawPayloadRef(
        sha256="0" * 64,
        size_bytes=1,
        media_type="application/json",
        relative_path="sha256/00/" + "0" * 64,
    )

    value = {
        "private_plan_ref": coordinator._encrypted_ref(reference),
        "raw_retention_deadline": datetime(2026, 8, 24, tzinfo=UTC),
    }

    assert json.loads(coordinator._canonical_bytes(value)) == {
        "private_plan_ref": coordinator._encrypted_ref(reference).model_dump(mode="json"),
        "raw_retention_deadline": "2026-08-24T00:00:00Z",
    }
