"""Current Codex schemas do not attest per-message human input origin."""

from collections.abc import Mapping
from typing import Any

from adaptation_compiler_lab.autonomy.models import InputOrigin


def codex_message_origin(item: Mapping[str, Any], *, client_version: str) -> InputOrigin:
    # clientId is an opaque caller-supplied identifier. Thread source and a user-message role
    # cannot distinguish a typed message from send_message_to_thread or a delegated prompt.
    # A new client must pass human/automated fixtures with a verifiable origin proof before
    # this boundary can admit HUMAN. Unknown versions remain excluded as well.
    # Native 0.162.0-alpha.2 also emits content_item_kinds=["user.text"] for a plain
    # programmatic turn/start. Hidden transcript markers are not human-origin witnesses.
    if item.get("type") == "functionCallOutput" and item.get("name") in {
        "send_message_to_thread",
        "followup_task",
        "send_message",
    }:
        return InputOrigin.DELEGATED
    if item.get("type") != "userMessage":
        return InputOrigin.AGENT
    return InputOrigin.UNKNOWN
