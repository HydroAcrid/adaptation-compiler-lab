"""Schema-shaped source transcript projection for an attributable human review.

This module classifies message channels, not semantic claims. It never decides that a user message
is a correction, success, preference, or durable lesson.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from adaptation_compiler_lab.connectors.models import JsonObject, JsonValue
from adaptation_compiler_lab.domain.base import FrozenModel, Identifier, NonEmptyStr
from adaptation_compiler_lab.domain.enums import AuthorityClass, SourceClass
from adaptation_compiler_lab.serialization import canonical_json


class ReviewChannel(StrEnum):
    """Channel-level origin shown to a human reviewer."""

    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"


class ReviewSegment(FrozenModel):
    """Exact review text plus a non-escalating trust classification."""

    task_id: Identifier
    turn_id: Identifier
    item_id: Identifier
    item_type: Identifier
    channel: ReviewChannel
    source_class: SourceClass
    authority_class: AuthorityClass
    eligible_user_authority: bool
    text: NonEmptyStr


class SourceReviewPacket(FrozenModel):
    """Local-only transcript projection; still sensitive and never a target artifact."""

    packet_version: Literal["1.0.0"] = "1.0.0"
    task_id: Identifier
    segments: tuple[ReviewSegment, ...] = Field(min_length=1)

    @field_validator("segments")
    @classmethod
    def segment_ids_are_unique(
        cls,
        value: tuple[ReviewSegment, ...],
    ) -> tuple[ReviewSegment, ...]:
        identities = tuple((item.turn_id, item.item_id) for item in value)
        if len(identities) != len(set(identities)):
            raise ValueError("review packet contains duplicate source items")
        return value


_AGENT_TYPES = frozenset({"agentMessage", "plan", "reasoning"})
_TOOL_TYPES = frozenset(
    {
        "collabAgentToolCall",
        "commandExecution",
        "dynamicToolCall",
        "fileChange",
        "imageGeneration",
        "imageView",
        "mcpToolCall",
        "subAgentActivity",
        "webSearch",
    }
)


def _object(value: JsonValue | None, *, field: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return value


def _string(value: JsonValue | None, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _user_text(item: JsonObject) -> str:
    content = item.get("content")
    if not isinstance(content, list):
        raise ValueError("userMessage content must be an array")
    text_parts: list[str] = []
    for entry_value in content:
        entry = _object(entry_value, field="userMessage content")
        if entry.get("type") != "text":
            continue
        text_parts.append(_string(entry.get("text"), field="userMessage text"))
    if not text_parts:
        raise ValueError("userMessage has no reviewable text")
    return "\n\n".join(text_parts)


def _agent_text(item: JsonObject) -> str:
    item_type = item.get("type")
    if item_type in {"agentMessage", "plan"}:
        return _string(item.get("text"), field=f"{item_type} text")
    values: list[str] = []
    for field in ("summary", "content"):
        value = item.get(field)
        if isinstance(value, list):
            values.extend(entry for entry in value if isinstance(entry, str) and entry.strip())
    if values:
        return "\n\n".join(values)
    return canonical_json(item)


def _tool_text(item: JsonObject) -> str:
    """Preserve tool context canonically without interpreting it as instruction."""

    return canonical_json(item)


def build_source_review_packet(raw_payload: bytes) -> SourceReviewPacket:
    """Project a validated Codex thread payload into explicitly labeled review segments."""

    try:
        payload_value = json.loads(raw_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("source review payload is not valid UTF-8 JSON") from error
    thread = _object(payload_value, field="thread")
    task_id = _string(thread.get("id"), field="thread id")
    turns = thread.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("source review requires persisted turns")
    segments: list[ReviewSegment] = []
    for turn_value in turns:
        turn = _object(turn_value, field="turn")
        turn_id = _string(turn.get("id"), field="turn id")
        items = turn.get("items")
        if not isinstance(items, list):
            raise ValueError("turn items must be an array")
        for item_value in items:
            item = _object(item_value, field="thread item")
            item_id = _string(item.get("id"), field="thread item id")
            item_type = _string(item.get("type"), field="thread item type")
            if item_type == "userMessage":
                channel = ReviewChannel.USER
                source_class = SourceClass.EXPLICIT_USER_FEEDBACK
                authority_class = AuthorityClass.USER_NORMATIVE
                eligible = True
                text = _user_text(item)
            elif item_type in _AGENT_TYPES:
                channel = ReviewChannel.AGENT
                source_class = SourceClass.AGENT_GENERATED
                authority_class = AuthorityClass.UNTRUSTED_CONTEXT
                eligible = False
                text = _agent_text(item)
            elif item_type in _TOOL_TYPES:
                channel = ReviewChannel.TOOL
                source_class = SourceClass.TOOL_OUTPUT
                authority_class = AuthorityClass.UNTRUSTED_CONTEXT
                eligible = False
                text = _tool_text(item)
            else:
                channel = ReviewChannel.SYSTEM
                source_class = SourceClass.SYSTEM_POLICY
                authority_class = AuthorityClass.UNTRUSTED_CONTEXT
                eligible = False
                text = canonical_json(item)
            segments.append(
                ReviewSegment(
                    task_id=task_id,
                    turn_id=turn_id,
                    item_id=item_id,
                    item_type=item_type,
                    channel=channel,
                    source_class=source_class,
                    authority_class=authority_class,
                    eligible_user_authority=eligible,
                    text=text,
                )
            )
    if not segments:
        raise ValueError("source review payload contains no reviewable items")
    return SourceReviewPacket(task_id=task_id, segments=tuple(segments))
