"""Reproducible, sanitized Milestone 4 live-smoke procedure."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import Field

from adaptation_compiler_lab.connectors.models import JsonObject, JsonValue, TargetRunRequest
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_RUNTIME_LOCK,
    RuntimeConformanceError,
    sha256_bytes,
    sha256_file,
)
from adaptation_compiler_lab.connectors.ports import TargetRunner
from adaptation_compiler_lab.domain.base import FrozenModel, NonEmptyStr, Sha256Digest, UtcDateTime

_CONDITION: Final = """Milestone 4 synthetic conformance condition.
Use only the supplied synthetic fixture. Read fixture.txt, then use an allowed file-mutation tool
(Write or Edit) to create smoke-output.txt containing exactly this UTF-8 text with no trailing
newline:
synthetic-smoke-ok
Use exactly those two tool calls. Do not re-read or otherwise verify the output; finish
immediately after the file mutation.
Do not use Bash, network access, agents, web tools, plugins, skills, memory, or external files.
"""
_TASK: Final = """M4_LIVE_SMOKE_TASK
Complete the synthetic conformance operation described in the injected condition. The workspace
contains no user or repository data.
"""
_EXPECTED_OUTPUT: Final = b"synthetic-smoke-ok"


class LiveSmokeError(RuntimeConformanceError):
    """The authenticated no-user-data smoke did not satisfy its exact contract."""


class LiveSmokeReceipt(FrozenModel):
    """Sanitized receipt; it contains no prompt, path, credential, or raw trace."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    milestone: Literal[4] = 4
    run_id: Literal["run-444444444444"] = "run-444444444444"
    executed_at: UtcDateTime
    runtime_lock_digest: Sha256Digest
    runner_version: NonEmptyStr
    model_id: Literal["claude-sonnet-5", "claude-haiku-4-5-20251001"]
    condition_digest: Sha256Digest
    command_digest: Sha256Digest
    trace_digest: Sha256Digest
    output_digest: Sha256Digest
    total_cost_usd: float = Field(ge=0.0, le=0.25, allow_inf_nan=False)
    tools: tuple[NonEmptyStr, ...]
    workspace_destroyed: Literal[True] = True
    raw_trace_persisted: Literal[False] = False
    user_data_used: Literal[False] = False
    source_data_used: Literal[False] = False
    held_out_data_used: Literal[False] = False


def _objects(value: JsonValue) -> list[JsonObject]:
    found: list[JsonObject] = []
    if isinstance(value, dict):
        found.append(value)
        for nested in value.values():
            found.extend(_objects(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_objects(nested))
    return found


def run_live_no_user_data_smoke(
    runner: TargetRunner,
    *,
    runtime_lock: Path = DEFAULT_RUNTIME_LOCK,
    model_id: Literal["claude-sonnet-5", "claude-haiku-4-5-20251001"] = "claude-sonnet-5",
) -> LiveSmokeReceipt:
    """Run one USD $0.25 synthetic task and return only a minimized receipt."""

    with tempfile.TemporaryDirectory(prefix="acl-m4-live-smoke-") as temporary:
        workspace = Path(temporary)
        fixture = workspace / "fixture.txt"
        condition = workspace / "condition.md"
        output = workspace / "smoke-output.txt"
        fixture.write_text("synthetic fixture only\n", encoding="utf-8")
        condition.write_text(_CONDITION, encoding="utf-8")
        result = runner.run(
            TargetRunRequest(
                run_id="run-444444444444",
                workspace_root=workspace,
                prompt=_TASK,
                condition_file=condition,
                condition_digest=sha256_file(condition),
                allowed_bash_commands=(),
                max_seconds=300,
                max_turns=4,
                max_usd=0.25,
                model_id=model_id,
            )
        )
        if result.timed_out or result.exit_code != 0:
            result_metadata = sorted(
                {
                    (
                        str(event.get("subtype", "none")),
                        str(event.get("is_error", "none")),
                    )
                    for event in result.events
                    if event.get("type") == "result"
                }
            )
            raise LiveSmokeError(
                "live smoke did not complete successfully; "
                f"exit_code={result.exit_code}; timed_out={result.timed_out}; "
                f"result_metadata={result_metadata}"
            )
        if not output.is_file() or output.read_bytes() != _EXPECTED_OUTPUT:
            raise LiveSmokeError("live smoke output failed independent verification")
        init_events = [
            event
            for event in result.events
            if event.get("type") == "system" and event.get("subtype") == "init"
        ]
        result_events = [event for event in result.events if event.get("type") == "result"]
        if len(init_events) != 1 or len(result_events) != 1:
            raise LiveSmokeError("live smoke trace is missing init or result evidence")
        tools_value = init_events[0].get("tools")
        if not isinstance(tools_value, list) or any(
            not isinstance(item, str) for item in tools_value
        ):
            raise LiveSmokeError("live smoke tool inventory is malformed")
        observed_tool_uses = {
            name
            for event in result.events
            for item in _objects(event)
            if item.get("type") in {"tool_use", "tool_result"}
            for name in (item.get("name"), item.get("tool_name"))
            if isinstance(name, str)
        }
        if "Read" not in observed_tool_uses or not observed_tool_uses.intersection(
            {"Edit", "Write"}
        ):
            observed = ", ".join(sorted(observed_tool_uses)) or "none"
            event_types = sorted(
                {
                    item_type
                    for event in result.events
                    for item in _objects(event)
                    if isinstance((item_type := item.get("type")), str)
                }
            )
            raise LiveSmokeError(
                "live smoke did not capture required Read and file-mutation tool uses; "
                f"observed tool names: {observed}; event types: {', '.join(event_types)}"
            )
        cost = result_events[0].get("total_cost_usd")
        if (
            not isinstance(cost, int | float)
            or isinstance(cost, bool)
            or not 0.0 <= float(cost) <= 0.25
        ):
            raise LiveSmokeError("live smoke cost evidence is absent or out of bounds")
        trace_bytes = json.dumps(
            result.events,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        receipt_values = {
            "executed_at": result.finished_at,
            "runtime_lock_digest": sha256_file(runtime_lock),
            "runner_version": result.runner_version,
            "model_id": result.model_id,
            "condition_digest": result.condition_digest,
            "command_digest": result.command_digest,
            "trace_digest": sha256_bytes(trace_bytes),
            "output_digest": sha256_file(output),
            "total_cost_usd": float(cost),
            "tools": tuple(sorted(cast(list[str], tools_value))),
        }
    return LiveSmokeReceipt.model_validate(receipt_values, strict=True)
