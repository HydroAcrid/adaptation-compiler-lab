from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.connectors.models import TargetCommandAuditEntry


def test_canary_v5_preregistration_matches_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_instrument_canary")
    preregistration = (
        repository / "development_benchmark_claude" / "INSTRUMENT_CANARY_PREREGISTRATION-v5.json"
    )

    loaded = coordinator._load_preregistration(
        preregistration,
        repo=repository,
        source_commit="synthetic-clean-commit",
    )

    assert loaded["canary_id"] == "claude-haiku-instrument-canary-v5"
    assert loaded["command_interface"] == {
        "full_test_alias": "acl-test-full",
        "focused_test_alias": "acl-test-focused",
        "command_implementations_visible_to_target": False,
        "out_of_manifest_behavior": "deny_and_persist_encrypted_failure_evidence",
        "task_file_manifest_visible_to_target": True,
    }
    assert loaded["success_gate"]["post_execution_rejections_preserve_usage_and_command_digest"]

    completion_bytes = coordinator._canonical_bytes(
        {"completed_at": coordinator._utc_text(datetime(2026, 7, 25, 5, 34, 39, tzinfo=UTC))}
    )
    assert json.loads(completion_bytes) == {"completed_at": "2026-07-25T05:34:39Z"}

    audit = (
        TargetCommandAuditEntry(
            sequence=1,
            alias="acl-test-full",
            approved_command_digest="sha256:" + ("0" * 64),
            requested_timeout_ms=5000,
        ),
    )
    digest = coordinator._command_audit_digest(audit)
    assert digest.startswith("sha256:")
    assert digest == coordinator._command_audit_digest(audit)

    boundary_source = (
        repository
        / "development_benchmark_claude"
        / "instrument_canary"
        / "fixture"
        / "test_instrument_boundary.py"
    ).read_text(encoding="utf-8")
    assert str(coordinator.HOST_PROBE) in boundary_source
