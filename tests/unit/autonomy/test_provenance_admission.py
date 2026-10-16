"""Native contract audit controls; these fictional inputs do not admit a human producer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT,
    codex_dogfood_schemas,
)
from adaptation_compiler_lab.autonomy.models import InputOrigin
from adaptation_compiler_lab.autonomy.provenance import codex_message_origin
from adaptation_compiler_lab.connectors.pins import (
    load_dogfood_runtime_pins,
    product_codex_runtime_locks,
)


@pytest.mark.parametrize(
    "platform,version",
    [
        ("win32", "0.162.0-alpha.17.2"),
        ("win32", "0.162.0-alpha.2"),
        ("win32", "0.160.1"),
        ("darwin", "0.157.0"),
    ],
)
def test_pinned_message_contract_has_no_positive_human_origin_witness(
    platform: str,
    version: str,
) -> None:
    pin = next(
        value.codex
        for path in product_codex_runtime_locks(platform)
        if (value := load_dogfood_runtime_pins(path)).codex.executable.package_version == version
    )
    codex_dogfood_schemas(pin)  # Verify all recorded native schema hashes first.
    root: Path = DEFAULT_CODEX_DOGFOOD_SCHEMA_ROOT.parent / version
    schema = json.loads((root / "v2/ThreadReadResponse.json").read_text(encoding="utf-8"))
    definitions = schema["definitions"]
    user_item = definitions.get("UserMessageThreadItem") or next(
        item
        for item in definitions["ThreadItem"]["oneOf"]
        if item.get("title") == "UserMessageThreadItem"
    )
    assert set(user_item["properties"]) == {"type", "id", "content", "clientId"}

    # Either producer can emit this same request/response shape. Fictional fixture labels
    # express the control's ground truth, not an origin assertion trusted by Temper.
    wire_item = {
        "type": "userMessage",
        "id": "fictional-message",
        "clientId": "fictional-client",
        "content": [{"type": "text", "text": "Can you make this shorter?", "text_elements": []}],
    }
    assert codex_message_origin(wire_item, client_version=version) is InputOrigin.UNKNOWN


@pytest.mark.parametrize(
    "metadata",
    [
        {"origin": "human"},
        {"actor": {"kind": "user"}},
        {"humanInput": True},
        {"originator": "codex_desktop", "source": "appServer"},
        {"hook_event_name": "UserPromptSubmit", "permission_mode": "default"},
        {"producerSignature": "unverified-self-assertion"},
        {"internal_chat_message_metadata_passthrough": {"content_item_kinds": ["user.text"]}},
    ],
)
def test_unverified_metadata_cannot_upgrade_user_role_to_human(metadata: dict[str, Any]) -> None:
    item = {"type": "userMessage", "clientId": "human-looking", **metadata}
    assert codex_message_origin(item, client_version="0.162.0-alpha.2") is InputOrigin.UNKNOWN
