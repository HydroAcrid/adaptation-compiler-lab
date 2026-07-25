from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.connectors.models import TargetCommandAuditEntry


def test_canary_v9_preregistration_matches_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_instrument_canary")
    preregistration = (
        repository / "development_benchmark_claude" / "INSTRUMENT_CANARY_PREREGISTRATION-v9.json"
    )

    loaded = coordinator._load_preregistration(
        preregistration,
        repo=repository,
        source_commit="synthetic-clean-commit",
    )

    assert loaded["canary_id"] == "claude-haiku-instrument-canary-v9"
    assert loaded["command_interface"] == {
        "full_test_alias": "acl-test-full",
        "focused_test_alias": "acl-test-focused",
        "command_implementations_visible_to_target": False,
        "out_of_manifest_behavior": "deny_and_persist_encrypted_failure_evidence",
        "task_file_manifest_visible_to_target": True,
        "target_host_platform": "linux",
        "managed_settings_source": "isolated_ephemeral_directory_with_strict_policy",
        "managed_bwrap_path_pinned": True,
        "inherited_path_visible_to_target": False,
        "claude_unsandboxed_escape_allowed": False,
        "claude_sandbox_exclusions": [
            "acl-test-full",
            "acl-test-focused",
        ],
        "alias_sandbox_backend": "pinned_bubblewrap",
        "alias_sandbox_network": "unshared",
        "alias_sandbox_host_filesystem": "not_mounted",
        "alias_sandbox_workspace": "disposable_workspace_only",
        "outer_compatibility_namespace": "pinned_bubblewrap_mnt_mask",
        "windows_mount_visible_to_target": False,
        "provider_network_retained_outside_command_sandbox": True,
        "inner_claude_sandbox_retained": True,
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
