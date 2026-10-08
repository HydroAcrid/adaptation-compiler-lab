from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from adaptation_compiler_lab.autonomy.agent_bridge import TemperAgentBridge, serve_bridge


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
