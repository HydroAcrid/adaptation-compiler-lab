from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest


def test_canary_v2_preregistration_matches_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_instrument_canary")
    preregistration = (
        repository / "development_benchmark_claude" / "INSTRUMENT_CANARY_PREREGISTRATION-v2.json"
    )

    loaded = coordinator._load_preregistration(
        preregistration,
        repo=repository,
        source_commit="synthetic-clean-commit",
    )

    assert loaded["canary_id"] == "claude-haiku-instrument-canary-v2"
    assert loaded["command_interface"] == {
        "full_test_alias": "acl-test-full",
        "focused_test_alias": "acl-test-focused",
        "command_implementations_visible_to_target": False,
        "out_of_manifest_behavior": "deny_and_persist_encrypted_failure_evidence",
    }
    assert loaded["success_gate"]["post_execution_rejections_preserve_usage_and_command_digest"]
