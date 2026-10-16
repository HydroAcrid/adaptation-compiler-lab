"""Manual one-turn fictional attribution control, never a learning/source admission command."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from time import monotonic
from typing import Any

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    codex_dogfood_schemas,
    require_chatgpt_account,
)
from adaptation_compiler_lab.autonomy.codex_capacity import CodexAnalysisContract
from adaptation_compiler_lab.autonomy.codex_transport import (
    analysis_profile,
    isolated_environment,
    read_capacity,
    verify_model,
)
from adaptation_compiler_lab.connectors.codex_app_server import CodexAppServerProcess
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import (
    load_dogfood_runtime_pins,
    select_product_codex_runtime_lock,
    verify_codex_runtime,
)


def probe(executable: Path, source_home: Path, *, model: str, effort: str) -> dict[str, Any]:
    pin = load_dogfood_runtime_pins(
        select_product_codex_runtime_lock(executable, sys.platform)
    ).codex
    runtime = verify_codex_runtime(executable, pin)
    schemas = codex_dogfood_schemas(pin)
    contract = CodexAnalysisContract(runtime)
    auth = source_home / "auth.json"
    if not auth.is_file() or auth.is_symlink():
        raise ValueError("saved ChatGPT authentication is unavailable")
    with tempfile.TemporaryDirectory(prefix="temper-fictional-origin-") as name:
        base = Path(name)
        home, workspace = base / "home", base / "workspace"
        home.mkdir(mode=0o700)
        workspace.mkdir(mode=0o700)
        shutil.copyfile(auth, home / "auth.json")
        (home / "auth.json").chmod(0o600)
        (home / "config.toml").write_text(analysis_profile(), encoding="utf-8")
        with CodexAppServerProcess(
            runtime,
            codex_home=home,
            schemas=schemas,
            experimental_api=True,
            isolated_environment=isolated_environment(home),
        ) as rpc:
            require_chatgpt_account(rpc, schemas=schemas)
            capacity = read_capacity(rpc, contract)
            if capacity is None or capacity < 20:
                return {"status": "capacity_deferred", "model_turns_started": 0}
            verify_model(rpc, contract, model=model, effort=effort)
            params: JsonObject = {
                "allowProviderModelFallback": False,
                "approvalPolicy": "never",
                "baseInstructions": "",
                "cwd": str(workspace),
                "developerInstructions": "Fictional origin audit. No tools.",
                "dynamicTools": [],
                "environments": [],
                "ephemeral": False,
                "experimentalRawEvents": False,
                "model": model,
                "personality": "none",
                "runtimeWorkspaceRoots": [str(workspace)],
                "sandbox": "read-only",
                "selectedCapabilityRoots": [],
                "serviceTier": "standard",
                "threadSource": "temperFictionalInputOriginAudit",
            }
            schemas.validate("thread_start_params", params)
            created = rpc.request("thread/start", params)
            schemas.validate("thread_start_response", created)
            sandbox = created.get("sandbox")
            if (
                created.get("instructionSources") != []
                or created.get("model") != model
                or created.get("approvalPolicy") != "never"
                or not isinstance(sandbox, dict)
                or sandbox.get("type") != "readOnly"
                or sandbox.get("networkAccess", False) is not False
            ):
                raise ValueError("fixture context or configured model could not be verified")
            thread = created["thread"]
            assert isinstance(thread, dict)
            thread_id = thread["id"]
            start: JsonObject = {
                "threadId": thread_id,
                "model": model,
                "effort": effort,
                "input": [
                    {
                        "type": "text",
                        "text": "Fictional fixture. Reply only OK.",
                        "text_elements": [],
                    }
                ],
            }
            schemas.validate("turn_start_params", start)
            started = rpc.request("turn/start", start)
            schemas.validate("turn_start_response", started)
            turn = started["turn"]
            assert isinstance(turn, dict)
            turn_id = turn["id"]
            input_seen = False
            ended = False
            deadline = monotonic() + 30
            while monotonic() < deadline:
                notice = rpc.next_notification(timeout_seconds=min(10, deadline - monotonic()))
                values = notice.get("params", {})
                if not isinstance(values, dict):
                    raise ValueError("fixture notification is malformed")
                item = values.get("item", {})
                method = notice.get("method")
                if (
                    "rerout" in str(method).casefold()
                    or "fromModel" in values
                    or "toModel" in values
                ):
                    raise ValueError("fixture model substitution is forbidden")
                if method in {"item/started", "item/completed"} and (
                    values.get("threadId") != thread_id
                    or values.get("turnId") != turn_id
                    or not isinstance(item, dict)
                    or item.get("type") not in {"userMessage", "agentMessage", "reasoning"}
                ):
                    raise ValueError("fixture attempted tools or crossed its context")
                if method == "item/completed" and isinstance(item, dict):
                    schemas.validate("item_completed", values)
                if (
                    method == "item/completed"
                    and isinstance(item, dict)
                    and item.get("type") == "userMessage"
                ):
                    if item.get("content") != start["input"]:
                        raise ValueError("fixture input changed")
                    input_seen = True
                    rpc.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
                if notice.get("method") == "turn/completed":
                    schemas.validate("turn_completed", values)
                    completed = values.get("turn")
                    if (
                        values.get("threadId") != thread_id
                        or not isinstance(completed, dict)
                        or completed.get("id") != turn_id
                        or completed.get("status") not in {"completed", "interrupted"}
                    ):
                        raise ValueError("fixture completion crossed its context or failed")
                    ended = True
                    break
            if not input_seen or not ended:
                raise ValueError("fixture input and termination were not verified")
            read_params: JsonObject = {"threadId": thread_id, "includeTurns": True}
            schemas.validate("thread_read_params", read_params)
            read = rpc.request("thread/read", read_params)
            schemas.validate("thread_read_response", read)
            record = read["thread"]
            assert isinstance(record, dict)
            path = Path(str(record.get("path") or thread.get("path")))
            if not path.resolve().is_relative_to(home.resolve()):
                raise ValueError("fixture transcript escaped disposable state")
            kinds: list[list[str]] = []
            for line in path.open(encoding="utf-8"):
                payload = json.loads(line).get("payload", {})
                if isinstance(payload, dict) and payload.get("role") == "user":
                    meta = payload.get("internal_chat_message_metadata_passthrough")
                    if isinstance(meta, dict) and isinstance(meta.get("content_item_kinds"), list):
                        kinds.append(meta["content_item_kinds"])
            return {
                "status": "observed",
                "client_version": runtime.version,
                "binary_digest": pin.executable.executable_sha256,
                "programmatic_user_message_event": input_seen,
                "programmatic_user_text_marker": ["user.text"] in kinds,
                "model_turns_started": 1,
                "personal_capture": False,
                "production_origin_admitted": False,
            }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--source-home", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    args = parser.parse_args()
    try:
        result = probe(
            args.codex_executable, args.source_home, model=args.model, effort=args.effort
        )
        result["temporary_auth_and_state_removed"] = True
        print(json.dumps(result))
    except Exception as error:
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "personal_capture": False}
            )
        )
        raise SystemExit(1) from None
