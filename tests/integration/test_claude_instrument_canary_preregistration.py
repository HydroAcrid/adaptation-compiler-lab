from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.connectors.models import TargetCommandAuditEntry


def test_canary_v10_preregistration_matches_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).parents[2]
    monkeypatch.syspath_prepend(str(repository / "scripts"))
    coordinator: Any = importlib.import_module("run_claude_instrument_canary")
    preregistration = (
        repository / "development_benchmark_claude" / "INSTRUMENT_CANARY_PREREGISTRATION-v10.json"
    )

    loaded = coordinator._load_preregistration(
        preregistration,
        repo=repository,
        source_commit="synthetic-clean-commit",
    )

    assert loaded["canary_id"] == "claude-haiku-instrument-canary-v10"
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
        "claude_sandbox_exclusions": [],
        "alias_sandbox_backend": "claude_code_pinned_bubblewrap",
        "alias_sandbox_network": "denied_by_inner_sandbox",
        "alias_sandbox_host_filesystem": "outer_minimal_mounts_plus_inner_policy",
        "alias_sandbox_workspace": "disposable_workspace_only",
        "outer_process_boundary": "pinned_bubblewrap_minimal_mount_manifest",
        "outer_read_only_mounts": [
            "/usr",
            "/etc",
            "pinned_claude",
            "pinned_bubblewrap",
            "pinned_socat",
            "pinned_sandbox_library",
        ],
        "outer_writable_mounts": [
            "disposable_workspace",
            "ephemeral_config",
        ],
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
