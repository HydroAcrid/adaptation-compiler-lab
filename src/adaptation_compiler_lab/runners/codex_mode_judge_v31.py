"""Judge-only adapter for Codex 0.153.1's deterministic disabled-host notice."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.runners.codex_mode_judge import CodexModeJudgeRunner
from adaptation_compiler_lab.runners.codex_structured_role import StructuredRoleRawResult

CODE_MODE_DISABLED_NOTICE = (
    "Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; "
    "enable `features.code_mode_host` and install `codex-code-mode-host`."
)
_ALLOWED_ITEM_TYPES = frozenset({"agent_message", "error", "reasoning"})


def _events(trace: bytes) -> tuple[JsonObject, ...] | None:
    try:
        lines = trace.decode("utf-8").splitlines()
        values = tuple(json.loads(line) for line in lines if line.strip())
    except (UnicodeDecodeError, ValueError):
        return None
    if not all(isinstance(value, dict) for value in values):
        return None
    return cast(tuple[JsonObject, ...], values)


def reconcile_disabled_host_notice(result: StructuredRoleRawResult) -> StructuredRoleRawResult:
    """Accept only the exact nonfatal notice while retaining the no-tool boundary."""

    if result.trace_conformant:
        return result
    if (
        result.trace_validation_error != "structured role used a tool"
        or not result.tool_use_observed
        or result.model_reroute_observed
        or result.exit_code != 0
        or result.timed_out
        or not result.config_destroyed
        or not result.workspace_destroyed
        or result.session_files_persisted
    ):
        return result
    events = _events(result.trace_bytes)
    if events is None:
        return result
    if (
        sum(event.get("type") == "thread.started" for event in events) != 1
        or sum(event.get("type") == "turn.started" for event in events) != 1
        or sum(event.get("type") == "turn.completed" for event in events) != 1
        or any(event.get("type") == "turn.failed" for event in events)
        or any("fromModel" in event or "toModel" in event for event in events)
    ):
        return result

    item_types: list[str] = []
    notices: list[str] = []
    responses: list[str] = []
    for event in events:
        item = event.get("item")
        if item is None:
            continue
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            return result
        item_type = cast(str, item["type"])
        item_types.append(item_type)
        if item_type not in _ALLOWED_ITEM_TYPES:
            return result
        if item_type == "error":
            message = item.get("message")
            if not isinstance(message, str):
                return result
            notices.append(message)
        elif item_type == "agent_message":
            text = item.get("text")
            if not isinstance(text, str):
                return result
            responses.append(text)
    if notices != [CODE_MODE_DISABLED_NOTICE] or len(responses) != 1:
        return result
    try:
        parsed_response = json.loads(responses[0])
    except ValueError:
        return result
    if not isinstance(parsed_response, dict):
        return result

    terminal = next(event for event in events if event.get("type") == "turn.completed")
    usage_value = terminal.get("usage")
    usage = usage_value if isinstance(usage_value, dict) else {}

    def token(name: str) -> int:
        value = usage.get(name, 0)
        return value if isinstance(value, int) and value >= 0 else 0

    return replace(
        result,
        response=responses[0],
        input_tokens=token("input_tokens"),
        cached_input_tokens=token("cached_input_tokens"),
        output_tokens=token("output_tokens"),
        reasoning_output_tokens=token("reasoning_output_tokens"),
        trace_conformant=True,
        trace_validation_error=None,
        tool_use_observed=False,
    )


class CodexModeJudgeV31Runner(CodexModeJudgeRunner):
    """Normalize one exact CLI notice after the historical strict parser runs."""

    def run(
        self,
        *,
        role_id: str,
        developer_contract: str,
        prompt: str,
        output_schema: dict[str, object],
    ) -> StructuredRoleRawResult:
        result = super().run(
            role_id=role_id,
            developer_contract=developer_contract,
            prompt=prompt,
            output_schema=output_schema,
        )
        return reconcile_disabled_host_notice(result)
