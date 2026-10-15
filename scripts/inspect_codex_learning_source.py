"""Read native source metadata and readiness, without turns, model calls or state changes."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexProjectScope,
    codex_dogfood_schemas,
    require_chatgpt_account,
)
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config
from adaptation_compiler_lab.autonomy.native import native_autonomy_service
from adaptation_compiler_lab.connectors.codex_app_server import CodexAppServerProcess
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import load_dogfood_runtime_pins, verify_codex_runtime


def inspect(config_path: Path) -> dict[str, object]:
    config = _load_config(config_path)
    pin = load_dogfood_runtime_pins(config.runtime_pin_path).codex
    runtime = verify_codex_runtime(config.codex_executable, pin)
    schemas = codex_dogfood_schemas(pin)
    service = native_autonomy_service(config_path)
    state = service.status()
    grant = service.grant()
    scopes = tuple(
        CodexProjectScope(root=root, scope=project.scope)
        for project in config.projects
        for root in project.effective_source_roots
    )
    with CodexAppServerProcess(
        runtime, codex_home=config.source_codex_home, schemas=schemas, experimental_api=True
    ) as rpc:
        require_chatgpt_account(rpc, schemas=schemas)
        params: JsonObject = {
            "archived": False,
            "cursor": None,
            "limit": 20,
            "sortDirection": "desc",
            "sortKey": "updated_at",
            "sourceKinds": ["cli", "vscode", "appServer"],
            "useStateDbOnly": True,
        }
        schemas.validate("thread_list_params", params)
        page = rpc.request("thread/list", params)
        schemas.validate("thread_list_response", page)
    data = page["data"]
    assert isinstance(data, list)
    matched = 0
    prospective = 0
    for thread in data:
        assert isinstance(thread, dict) and isinstance(thread["cwd"], str)
        if any(scope.contains(thread["cwd"]) for scope in scopes):
            matched += 1
            created = thread["createdAt"]
            assert isinstance(created, int)
            if grant and datetime.fromtimestamp(created, UTC) >= grant.issued_at:
                prospective += 1
    worker = service.background_worker
    return {
        "source_connected": True,
        "client_version": runtime.version,
        "client_binary_digest": pin.executable.executable_sha256,
        "metadata_sample_size": len(data),
        "additional_pages": page["nextCursor"] is not None,
        "registered_project_count": len(config.projects),
        "matched_registered_project_chats_in_sample": matched,
        "prospective_chats_in_sample": prospective,
        "completed_chat_reader_connected": bool(worker and worker.read_completed),
        "grant_enabled": state["grant_enabled"],
        "learning_enabled": state["learning_enabled"],
        "human_input_producer_admitted": state["provenance_state"] == "verified",
        "automatic_serving_ready": state["automatic_serving_ready"],
        "thread_read_calls": 0,
        "model_turns": 0,
        "raw_payloads_exposed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.config), sort_keys=True))
