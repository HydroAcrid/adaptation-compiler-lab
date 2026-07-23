from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from adaptation_compiler_lab.connectors.codex_app_server import (
    CodexAppServerProcess,
    CodexProtocolError,
    CodexSchemaSet,
    CodexSourceConnector,
)
from adaptation_compiler_lab.connectors.models import JsonObject, JsonValue
from adaptation_compiler_lab.connectors.pins import VerifiedCodexRuntime

SCHEMA_DIGEST = f"sha256:{'a' * 64}"


def _thread(
    task_id: str,
    *,
    status: str = "idle",
    ephemeral: bool = False,
    turns: list[JsonObject] | None = None,
) -> JsonObject:
    status_payload: JsonObject = {"type": status}
    if status == "active":
        status_payload["activeFlags"] = []
    return {
        "id": task_id,
        "sessionId": f"session-{task_id}",
        "source": "cli",
        "modelProvider": "openai",
        "createdAt": 10,
        "updatedAt": 20,
        "status": status_payload,
        "cwd": "/private/source/project",
        "cliVersion": "0.145.0",
        "name": f"Name {task_id}",
        "preview": "private first user message",
        "ephemeral": ephemeral,
        "turns": cast(JsonValue, [] if turns is None else turns),
    }


@dataclass
class FakeRpc:
    responses: dict[str, JsonObject]
    calls: list[tuple[str, JsonObject]] = field(default_factory=list)

    def request(self, method: str, params: JsonObject) -> JsonObject:
        self.calls.append((method, params))
        return self.responses[method]


def _connector(rpc: FakeRpc) -> CodexSourceConnector:
    return CodexSourceConnector(
        rpc,
        source_version="0.145.0",
        source_schema_digest=SCHEMA_DIGEST,
        schemas=CodexSchemaSet(),
    )


def test_list_uses_state_database_and_withholds_raw_metadata() -> None:
    rpc = FakeRpc(
        {
            "thread/list": {
                "data": [
                    _thread("thread-idle"),
                    _thread("thread-active", status="active"),
                    _thread("thread-ephemeral", ephemeral=True),
                ],
                "nextCursor": "opaque-next",
            }
        }
    )

    page = _connector(rpc).list_completed_tasks(cursor="opaque-current", limit=25)

    assert [item.task_id for item in page.tasks] == ["thread-idle"]
    assert page.next_cursor == "opaque-next"
    assert "preview" not in page.tasks[0].model_dump()
    assert "cwd" not in page.tasks[0].model_dump()
    method, params = rpc.calls[0]
    assert method == "thread/list"
    assert params["useStateDbOnly"] is True
    assert params["cursor"] == "opaque-current"


def test_read_requires_full_terminal_turns_and_preserves_canonical_payload() -> None:
    turn: JsonObject = {
        "id": "turn-1",
        "items": [],
        "itemsView": "full",
        "status": "failed",
    }
    rpc = FakeRpc({"thread/read": {"thread": _thread("thread-1", turns=[turn])}})

    snapshot = _connector(rpc).read_completed_task("thread-1")

    assert snapshot.task_id == "thread-1"
    assert snapshot.turns[0].status.value == "failed"
    assert json.loads(snapshot.raw_payload)["cwd"] == "/private/source/project"
    assert snapshot.untrusted_context is True
    assert rpc.calls == [("thread/read", {"threadId": "thread-1", "includeTurns": True})]


@pytest.mark.parametrize(
    "turn",
    [
        {"id": "turn-1", "items": [], "itemsView": "full", "status": "inProgress"},
        {"id": "turn-1", "items": [], "itemsView": "summary", "status": "completed"},
    ],
)
def test_read_rejects_nonterminal_or_partial_history(turn: JsonObject) -> None:
    rpc = FakeRpc({"thread/read": {"thread": _thread("thread-1", turns=[turn])}})

    with pytest.raises(CodexProtocolError):
        _connector(rpc).read_completed_task("thread-1")


def test_generated_schema_rejects_substituted_response() -> None:
    rpc = FakeRpc({"thread/list": {"nextCursor": None}})

    with pytest.raises(CodexProtocolError, match="pinned thread_list_response"):
        _connector(rpc).list_completed_tasks()


def test_fake_stdio_app_server_conforms_and_tears_down(tmp_path: Path) -> None:
    executable = tmp_path / "fake-codex"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message["method"]
    if method == "initialize":
        result = {
            "codexHome": "/synthetic",
            "platformFamily": "unix",
            "platformOs": "linux",
            "userAgent": "fake-codex",
        }
    elif method == "thread/list":
        result = {"data": [], "nextCursor": None}
    else:
        result = {}
    print(json.dumps({"id": message["id"], "result": result}), flush=True)
""",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    runtime = VerifiedCodexRuntime(
        executable=executable,
        version="0.145.0",
        schema_bundle_digest=SCHEMA_DIGEST,
    )
    schemas = CodexSchemaSet()

    with CodexAppServerProcess(
        runtime,
        codex_home=codex_home,
        schemas=schemas,
    ) as rpc:
        connector = CodexSourceConnector(
            rpc,
            source_version=runtime.version,
            source_schema_digest=runtime.schema_bundle_digest,
            schemas=schemas,
        )
        assert connector.list_completed_tasks(limit=1).tasks == ()
