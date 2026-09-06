"""Exact-boundary tests for the Mode v3.1 judge trace repair."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from adaptation_compiler_lab.runners.codex_mode_judge_v31 import (
    CODE_MODE_DISABLED_NOTICE,
    reconcile_disabled_host_notice,
)
from adaptation_compiler_lab.runners.codex_structured_role import StructuredRoleRawResult


def _trace(*items: dict[str, object]) -> bytes:
    events: list[dict[str, object]] = [{"type": "thread.started"}]
    events.extend({"type": "item.completed", "item": item} for item in items)
    events.extend(
        [
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": '{"ok":true}'},
            },
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 4,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 1,
                },
            },
        ]
    )
    return ("\n".join(json.dumps(event) for event in events) + "\n").encode()


def _result(trace: bytes) -> StructuredRoleRawResult:
    now = datetime.now(UTC)
    return StructuredRoleRawResult(
        role_id="judge-smoke",
        command_digest="sha256:command",
        environment_digest="sha256:environment",
        contract_digest="sha256:contract",
        prompt_digest="sha256:prompt",
        output_schema_digest="sha256:schema",
        started_at=now,
        finished_at=now,
        duration_seconds=1.0,
        exit_code=0,
        timed_out=False,
        trace_bytes=trace,
        stderr="",
        response="",
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
        reasoning_output_tokens=0,
        trace_conformant=False,
        trace_validation_error="structured role used a tool",
        tool_use_observed=True,
        model_reroute_observed=False,
        config_destroyed=True,
        workspace_destroyed=True,
        session_files_persisted=False,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        service_mode="standard",
    )


def test_exact_disabled_host_notice_is_not_treated_as_tool_use() -> None:
    original = _result(_trace({"type": "error", "message": CODE_MODE_DISABLED_NOTICE}))

    repaired = reconcile_disabled_host_notice(original)

    assert repaired.trace_conformant is True
    assert repaired.trace_validation_error is None
    assert repaired.tool_use_observed is False
    assert repaired.response == '{"ok":true}'
    assert (
        repaired.input_tokens,
        repaired.cached_input_tokens,
        repaired.output_tokens,
        repaired.reasoning_output_tokens,
    ) == (10, 4, 2, 1)


def test_any_other_error_notice_remains_invalid() -> None:
    original = _result(_trace({"type": "error", "message": "another error"}))

    assert reconcile_disabled_host_notice(original) == original


def test_actual_tool_item_remains_invalid_even_with_the_exact_notice() -> None:
    original = _result(
        _trace(
            {"type": "error", "message": CODE_MODE_DISABLED_NOTICE},
            {"type": "command_execution", "command": "true"},
        )
    )

    assert reconcile_disabled_host_notice(original) == original
