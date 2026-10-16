from __future__ import annotations

import io
import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from adaptation_compiler_lab.autonomy.agent_bridge import TemperAgentBridge, serve_bridge
from adaptation_compiler_lab.autonomy.models import StyleCategory
from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import trial


def context_for(service: AutonomyApplicationService, tmp_path: Path) -> dict[str, Any]:
    config = tmp_path / "bridge-config.json"
    config.write_text("{}", encoding="utf-8")
    with patch(
        "adaptation_compiler_lab.autonomy.native.native_autonomy_service", return_value=service
    ):
        return TemperAgentBridge(config_path=config, agent_id="test").call(
            "temper_context", {"project_id": "project", "task_class": "progress_update"}
        )


def test_context_obeys_replacement_grant_categories(
    app: tuple[AutonomyApplicationService, Any], tmp_path: Path
) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    service.set_switch("personalization", True, key="personalize")
    assert context_for(service, tmp_path)["habit_ids"] == (habit_id,)
    service.revoke_grant(key="revoke")
    preview = service.preview_grant(("project",), (StyleCategory.PRESENTATION_STYLE,))
    service.confirm_grant(preview["preview_token"], confirmed=True, idempotency_key="narrow")
    service.set_switch("personalization", True, key="narrow-personalize")
    before = service.store.head_digest
    result = context_for(service, tmp_path)
    assert result["habit_ids"] == ()
    assert result["profile"] == ""
    assert service.store.head_digest == before


def test_context_excludes_expired_trial_without_mutating_learning_state(
    app: tuple[AutonomyApplicationService, Any], tmp_path: Path
) -> None:
    service, clock = app
    habit_id = trial(service, clock)
    service.set_switch("personalization", True, key="personalize")
    assert context_for(service, tmp_path)["habit_ids"] == (habit_id,)
    habit = service.hypotheses()[0]
    assert habit.trial_expires_at is not None
    clock.value = habit.trial_expires_at - timedelta(microseconds=1)
    assert context_for(service, tmp_path)["habit_ids"] == (habit_id,)
    clock.value = habit.trial_expires_at
    before = service.store.head_digest
    result = context_for(service, tmp_path)
    assert result["habit_ids"] == ()
    assert result["profile"] == ""
    assert service.store.head_digest == before


def test_bridge_is_connected_without_fabricating_runtime_or_personal_consent(
    tmp_path: Path,
) -> None:
    bridge = TemperAgentBridge(config_path=tmp_path / "absent", agent_id="agent")
    status = bridge.call("temper_status", {})
    assert status["connection"] == "read_only_context"
    assert not status["status"]["runtime_configured"]
    assert status["independent_human_evidence"] is False
    context = bridge.call("temper_context", {"project_id": "ffg", "task_class": "summary"})
    assert context["profile"] == ""
    assert context["habit_ids"] == ()
    for method in ("observe_human", "approve", "publish", "enable_learning"):
        with pytest.raises(ValueError, match="unsupported"):
            bridge.call(method, {})


def test_mcp_protocol_exposes_only_closed_read_only_tools(tmp_path: Path) -> None:
    bridge = TemperAgentBridge(config_path=None, agent_id="agent")
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "temper_status", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "temper_status", "arguments": {"origin": "human"}},
        },
    ]
    out = io.StringIO()
    serve_bridge(
        bridge, stdin=io.StringIO("\n".join(json.dumps(value) for value in requests)), stdout=out
    )
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert {tool["name"] for tool in replies[1]["result"]["tools"]} == {
        "temper_status",
        "temper_context",
    }
    assert all(tool["annotations"]["readOnlyHint"] for tool in replies[1]["result"]["tools"])
    assert replies[2]["result"]["isError"] is False
    assert "error" in replies[3]


@pytest.mark.parametrize(
    "arguments",
    [
        {"project_id": [], "task_class": "summary"},
        {"project_id": "", "task_class": "summary"},
        {"project_id": "project", "task_class": "invented"},
    ],
)
def test_unconfigured_bridge_still_validates_closed_context_arguments(arguments):
    with pytest.raises((ValueError, TypeError)):
        TemperAgentBridge(config_path=None, agent_id="agent").call("temper_context", arguments)
