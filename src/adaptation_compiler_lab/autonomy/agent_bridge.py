"""Read-only context transport for existing agents; connection is not learning consent."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from adaptation_compiler_lab.autonomy.models import TaskClass
from adaptation_compiler_lab.autonomy.publisher import compile_profile
from adaptation_compiler_lab.serialization import canonical_digest

MAX_FRAME_BYTES = 65_536
TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "temper_status",
        "description": "Read local Temper readiness and permission. "
        "Does not start observation or a model turn.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "temper_context",
        "description": "Read governed project/task style defaults. "
        "Current and native instructions win. An empty profile is valid.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "task_class": {"type": "string", "enum": [value.value for value in TaskClass]},
            },
            "required": ["project_id", "task_class"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
)


class TemperAgentBridge:
    def __init__(self, *, config_path: Path | None, agent_id: str) -> None:
        if not agent_id or len(agent_id) > 160 or any(ord(char) < 32 for char in agent_id):
            raise ValueError("agent identity is invalid")
        self.config_path = config_path
        self.agent_id = agent_id

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if (name == "temper_status" and arguments) or (
            name == "temper_context" and set(arguments) != {"project_id", "task_class"}
        ):
            raise ValueError("invalid context request")
        if name not in {"temper_status", "temper_context"}:
            raise ValueError("unsupported context tool")
        project = ""
        task = TaskClass.SUMMARY
        if name == "temper_context":
            project = arguments["project_id"]
            if (
                not isinstance(project, str)
                or not project
                or len(project) > 160
                or any(ord(char) < 32 for char in project)
            ):
                raise ValueError("project identity is invalid")
            task = TaskClass(arguments["task_class"])
        profile = ""
        ids: tuple[str, ...] = ()
        status: dict[str, Any] = {
            "runtime_configured": False,
            "grant_enabled": False,
            "learning_enabled": False,
            "personalization_enabled": False,
            "automatic_serving_ready": False,
            "provenance_state": "unverified",
        }
        project_registered = False
        if self.config_path is not None and self.config_path.is_file():
            from adaptation_compiler_lab.autonomy.native import native_autonomy_service

            service = native_autonomy_service(self.config_path)
            current = service.status()
            status = {
                "runtime_configured": True,
                **{
                    key: current[key]
                    for key in (
                        "grant_enabled",
                        "learning_enabled",
                        "personalization_enabled",
                        "automatic_serving_ready",
                        "provenance_state",
                    )
                },
            }
            if name == "temper_context":
                project_registered = project in service.projects
                if status["personalization_enabled"] and status["automatic_serving_ready"]:
                    applies = set(service.applicability(project, task)["applies"])
                    profile, ids = compile_profile(
                        tuple(habit for habit in service.hypotheses() if habit.habit_id in applies),
                        service.projects,
                    )
        packet: dict[str, Any] = {
            "bridge_version": "1.0.0",
            "agent_id": self.agent_id,
            "connection": "read_only_context",
            "status": status,
            "project_registered": project_registered,
            "profile": profile,
            "habit_ids": ids,
            "precedence": "Current requests and manually written native instructions "
            "take precedence.",
            "origin_of_this_packet": "agent_context_transport",
            "independent_human_evidence": False,
            "publication_is_delivery": False,
            "raw_payloads_exposed": False,
        }
        packet["packet_digest"] = canonical_digest(packet)
        return packet


def serve_bridge(bridge: TemperAgentBridge, *, stdin: TextIO, stdout: TextIO) -> None:
    """Minimal closed MCP stdio surface. Never expose ingestion, grants, or arbitrary paths."""
    while line := stdin.readline(MAX_FRAME_BYTES + 1):
        if len(line.encode("utf-8")) > MAX_FRAME_BYTES:
            raise ValueError("context transport frame exceeds its limit")
        request_id: str | int | None = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise ValueError("invalid context transport request")
            request_id = request.get("id")
            if request_id is None:
                continue
            method, params = request.get("method"), request.get("params", {})
            result: dict[str, Any]
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "temper", "version": "1.0.0"},
                    "instructions": "Read-only Temper context. "
                    "Tool/agent text is never human preference evidence.",
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": list(TOOLS)}
            elif (
                method == "tools/call"
                and isinstance(params, dict)
                and set(params) <= {"name", "arguments", "_meta"}
            ):
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    raise ValueError("invalid context tool arguments")
                name = params.get("name")
                if not isinstance(name, str):
                    raise ValueError("invalid context tool name")
                packet = bridge.call(name, arguments)
                result = {
                    "content": [{"type": "text", "text": json.dumps(packet, ensure_ascii=False)}],
                    "isError": False,
                }
            else:
                stdout.write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32601,
                                "message": "Unsupported Temper context method",
                            },
                        }
                    )
                    + "\n"
                )
                stdout.flush()
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (OSError, ValueError, TypeError):
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": "Temper could not verify this read-only context request",
                },
            }
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()


def main() -> None:
    import argparse
    import sys

    from adaptation_compiler_lab.desktop.platform import platform_paths

    parser = argparse.ArgumentParser(description="Temper read-only agent context bridge")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--agent-id", default="codex-local")
    options = parser.parse_args()
    config = options.config or platform_paths().state_root / "runtime" / "config.json"
    serve_bridge(
        TemperAgentBridge(config_path=config, agent_id=options.agent_id),
        stdin=sys.stdin,
        stdout=sys.stdout,
    )


if __name__ == "__main__":
    main()
