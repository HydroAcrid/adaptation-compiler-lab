from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.runners import codex_structured_role
from adaptation_compiler_lab.runners.codex_structured_role import (
    CodexStructuredRoleRunner,
    _trace_result,
)


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _fake_codex(path: Path) -> Path:
    response = json.dumps({"answer": "A schema-bound result."})
    path.write_text(
        f"""#!/usr/bin/python3
import json
import os
import pathlib
import sys

if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.145.0")
    raise SystemExit(0)
if sys.argv[1:] == ["login", "status"]:
    assert "CODEX_API_KEY" not in os.environ
    assert "OPENAI_API_KEY" not in os.environ
    assert pathlib.Path(os.environ["CODEX_HOME"], "auth.json").is_file()
    print("Logged in using ChatGPT")
    raise SystemExit(0)
if sys.argv[1] == "app-server":
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("method") == "initialize":
            response = {{"id": request["id"], "result": {{"userAgent": "fake"}}}}
            print(json.dumps(response), flush=True)
        elif request.get("method") == "model/list":
            print(json.dumps({{
                "id": request["id"],
                "result": {{
                    "data": [{{
                        "hidden": False,
                        "id": "gpt-5.6-luna",
                        "model": "gpt-5.6-luna",
                        "supportedReasoningEfforts": [{{"reasoningEffort": "medium"}}],
                    }}],
                    "nextCursor": None,
                }},
            }}), flush=True)
    raise SystemExit(0)
assert "--output-schema" in sys.argv
assert sys.argv[sys.argv.index("--sandbox") + 1] == "read-only"
assert "--ignore-user-config" in sys.argv
assert "--ignore-rules" in sys.argv
assert "--ephemeral" in sys.argv
assert sys.stdin.read()
events = [
    {{"type": "thread.started", "thread_id": "thread-fresh"}},
    {{"type": "turn.started"}},
    {{"type": "item.completed", "item": {{"type": "reasoning", "text": "private"}}}},
    {{"type": "item.completed", "item": {{"type": "agent_message", "text": {response!r}}}}},
    {{
        "type": "turn.completed",
        "usage": {{
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 30,
            "reasoning_output_tokens": 10,
        }},
    }},
]
for event in events:
    print(json.dumps(event, sort_keys=True))
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _fake_bwrap(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/python3
import os
import sys

if sys.argv[-1] == "/bin/true":
    raise SystemExit(0)
separator = sys.argv.index("--")
args = sys.argv[1:separator]
inner = sys.argv[separator + 1:]
outer_codex = "/opt/acl-structured-role/codex"
source = args[args.index(outer_codex) - 1]
if inner[0] == outer_codex:
    inner[0] = source
os.execv(inner[0], inner)
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_structured_role_is_schema_bound_tool_free_and_ephemeral(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = _fake_codex(tmp_path / "codex")
    bwrap = _fake_bwrap(tmp_path / "bwrap")
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    monkeypatch.setattr(
        codex_structured_role,
        "_EXPECTED_CLI_DIGEST",
        _sha(codex.read_bytes()),
    )
    monkeypatch.setattr(
        codex_structured_role,
        "_EXPECTED_BWRAP_DIGEST",
        _sha(bwrap.read_bytes()),
    )
    runner = CodexStructuredRoleRunner(
        executable=codex,
        saved_auth_file=auth,
        bubblewrap=bwrap,
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        max_seconds=10,
    )

    result = runner.run(
        role_id="profile-author-stage-1",
        developer_contract="Use only the supplied evidence. Do not use tools.",
        prompt="Return the registered JSON object.",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    )

    assert result.trace_conformant
    assert json.loads(result.response) == {"answer": "A schema-bound result."}
    assert not result.tool_use_observed
    assert result.config_destroyed
    assert result.workspace_destroyed
    assert not result.session_files_persisted
    assert (result.input_tokens, result.output_tokens) == (100, 30)


def test_structured_role_trace_marks_command_execution_as_tool_use() -> None:
    events: tuple[JsonObject, ...] = (
        {"type": "thread.started"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "command": "pwd"},
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": '{"answer":"done"}'},
        },
        {"type": "turn.completed", "usage": {}},
    )

    _, _, tool_use, _ = _trace_result(events)

    assert tool_use
