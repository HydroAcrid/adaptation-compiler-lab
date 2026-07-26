from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.isolated_rating import isolated_rating_output_schema
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.runners import codex_blind_rating
from adaptation_compiler_lab.runners.codex_blind_rating import (
    IsolatedCodexBlindRatingRunner,
    _trace_result,
)


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _decision() -> dict[str, object]:
    return {
        "decision_version": "1.0.0",
        "pair_ratings": [
            {
                "task_id": "task-a",
                "ordered_output_ids": ["output-a1", "output-a2"],
                "preference": "first_better",
                "preferred_output_id": "output-a1",
                "rationale": "The first patch handles the required edge case more safely.",
            },
            {
                "task_id": "task-b",
                "ordered_output_ids": ["output-b1", "output-b2"],
                "preference": "tie",
                "preferred_output_id": None,
                "rationale": "The patches are functionally equivalent with no material advantage.",
            },
        ],
        "overall_assessment": "The first task separates the candidates; the second does not.",
        "evaluator_limitations": ["Only anonymous packet content was available."],
    }


def _fake_codex(path: Path) -> Path:
    decision = json.dumps(_decision(), sort_keys=True)
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
                        "id": "gpt-5.6-sol",
                        "model": "gpt-5.6-sol",
                        "supportedReasoningEfforts": [{{"reasoningEffort": "xhigh"}}],
                    }}],
                    "nextCursor": None,
                }},
            }}), flush=True)
    raise SystemExit(0)
prompt = sys.stdin.read()
assert "BEGIN ANONYMOUS PACKET" in prompt
assert "--ignore-user-config" in sys.argv
assert "--ignore-rules" in sys.argv
assert "--ephemeral" in sys.argv
assert "--skip-git-repo-check" in sys.argv
assert sys.argv[sys.argv.index("--sandbox") + 1] == "read-only"
events = [
    {{"type": "thread.started", "thread_id": "thread-fresh"}},
    {{"type": "turn.started"}},
    {{"type": "item.completed", "item": {{"type": "reasoning", "text": "private"}}}},
    {{"type": "item.completed", "item": {{"type": "agent_message", "text": {decision!r}}}}},
    {{
        "type": "turn.completed",
        "usage": {{
            "input_tokens": 120,
            "cached_input_tokens": 0,
            "output_tokens": 80,
            "reasoning_output_tokens": 40,
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
outer_codex = "/opt/acl-blind-rating/codex"
source = args[args.index(outer_codex) - 1]
if inner[0] == outer_codex:
    inner[0] = source
os.execv(inner[0], inner)
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_blank_rating_runner_uses_schema_bound_tool_free_ephemeral_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex = _fake_codex(tmp_path / "codex")
    bwrap = _fake_bwrap(tmp_path / "bwrap")
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    monkeypatch.setattr(codex_blind_rating, "_EXPECTED_CLI_DIGEST", _sha(codex.read_bytes()))
    monkeypatch.setattr(codex_blind_rating, "_EXPECTED_BWRAP_DIGEST", _sha(bwrap.read_bytes()))
    runner = IsolatedCodexBlindRatingRunner(
        executable=codex,
        saved_auth_file=auth,
        bubblewrap=bwrap,
        max_seconds=10,
    )

    result = runner.run(
        packet="# Anonymous\n\n## task-a\n\n## task-b\n",
        output_schema=isolated_rating_output_schema(),
    )

    assert result.trace_conformant
    assert result.decision is not None
    assert result.decision.pair_ratings[0].preference == "first_better"
    assert not result.tool_use_observed
    assert result.config_destroyed
    assert result.workspace_destroyed
    assert not result.session_files_persisted
    assert result.model == "gpt-5.6-sol"
    assert result.reasoning_effort == "xhigh"
    assert (result.input_tokens, result.output_tokens) == (120, 80)


def test_rating_trace_marks_any_non_reasoning_item_as_tool_use() -> None:
    response = json.dumps(_decision())
    events: tuple[JsonObject, ...] = (
        {"type": "thread.started"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "command": "pwd"},
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": response},
        },
        {"type": "turn.completed", "usage": {}},
    )

    _, _, tool_use, _ = _trace_result(events)

    assert tool_use
