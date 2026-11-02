"""Explicit owner admission of new completed work in existing conversations.

This changes source eligibility, never personal categories, grants or independence.
Native reader admission remains separate from a conversation's creation version.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from adaptation_compiler_lab.autonomy.models import LearningGrantV1
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.domain import FrozenModel, Identifier, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest

if TYPE_CHECKING:
    from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService


class ConversationProjectBinding(FrozenModel):
    task_digest: Sha256Digest
    project_id: Identifier
    expected_cwd: str = Field(min_length=1)


class CompletedWorkAuthorization(FrozenModel):
    policy_version: Literal["completed-work-v1"] = "completed-work-v1"
    grant_digest: Sha256Digest
    capture_after: datetime
    authorized_at: datetime
    owner_confirmed: Literal[True] = True
    bindings: tuple[ConversationProjectBinding, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def bounded(self) -> CompletedWorkAuthorization:
        if any(
            t.tzinfo is None or t.utcoffset() is None
            for t in (self.capture_after, self.authorized_at)
        ):
            raise ValueError("completed-work authorization requires aware dates")
        if self.capture_after > self.authorized_at:
            raise ValueError("completed-work cutoff is in the future")
        keys = [b.task_digest for b in self.bindings]
        if keys != sorted(set(keys)):
            raise ValueError("conversation bindings must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def completed_work_authorization(
    store: AutonomyStore, grant: LearningGrantV1 | None
) -> CompletedWorkAuthorization | None:
    if grant is None:
        return None
    events = store.events()
    confirmed = {
        event["payload"].get("policy_digest")
        for event in events
        if event["type"] == "source_work_confirmation"
    }
    event = None
    for value in reversed(events):
        if value["type"] != "source_work_authorization":
            continue
        body = value["payload"]
        if body.get("disabled") is True:
            return None
        if canonical_digest(body) in confirmed:
            event = body
            break
    if event is None:
        return None
    policy = CompletedWorkAuthorization.model_validate_json(json.dumps(event), strict=True)
    if policy.grant_digest != grant.content_digest:
        return None  # A different/revoked grant never inherits this source permission.
    if (
        grant.input_policy != "owner_authorized_conversations"
        or policy.capture_after != grant.issued_at
        or any(b.project_id not in grant.project_ids for b in policy.bindings)
    ):
        raise AutonomyIntegrityError("completed-work authorization exceeds its grant")
    return policy


class CapturePolicyController:
    """Digest-bound, idempotent owner control; not exposed through the agent bridge."""

    def __init__(self, service: AutonomyApplicationService) -> None:
        self.service = service
        self._previews: dict[str, dict[str, Any]] = {}

    def status(self) -> dict[str, Any]:
        policy = completed_work_authorization(self.service.store, self.service.grant())
        return {
            "capture_window": "completed_work" if policy else "new_conversations",
            "conversation_project_bindings": len(policy.bindings) if policy else 0,
            "conversation_independence": "one_episode_per_conversation",
        }

    def preview(self, bindings: list[dict[str, Any]]) -> dict[str, Any]:
        service = self.service
        grant = service.grant()
        if grant is None or grant.input_policy != "owner_authorized_conversations":
            raise AutonomyIntegrityError("completed work needs an owner-trusted source grant")
        if len(bindings) > 256:
            raise AutonomyIntegrityError("too many conversation project bindings")
        selected = []
        for value in bindings:
            if set(value) != {"thread_id", "project_id", "cwd"} or not all(
                isinstance(v, str) and v for v in value.values()
            ):
                raise AutonomyIntegrityError("invalid conversation project binding")
            project = value["project_id"]
            cwd = Path(value["cwd"]).expanduser()
            if (
                project not in grant.project_ids
                or project not in service.projects
                or not cwd.is_absolute()
                or not cwd.is_dir()
            ):
                raise AutonomyIntegrityError("conversation project is outside the owner grant")
            selected.append(
                ConversationProjectBinding(
                    task_digest=canonical_digest({"task": value["thread_id"]}),
                    project_id=project,
                    expected_cwd=str(cwd.resolve()),
                )
            )
        policy = CompletedWorkAuthorization(
            grant_digest=grant.content_digest,
            capture_after=grant.issued_at,
            authorized_at=service.clock(),
            bindings=tuple(sorted(selected, key=lambda b: b.task_digest)),
        )
        token = "completed-work-preview-" + secrets.token_hex(12)
        self._previews[token] = {
            "policy": policy,
            "head": service.store.head_digest,
            "projects": dict(service.projects),
            "expires": service.clock() + timedelta(minutes=15),
        }
        return {
            "preview_token": token,
            "capture_window": "completed_work",
            "capture_after": policy.capture_after.isoformat(),
            "conversation_project_bindings": len(selected),
            "effect": "Read only completed work after the existing cutoff, including older chats.",
            "historical_messages_before_cutoff": False,
            "conversation_independence": "one_episode_per_conversation",
            "project_ids": sorted(grant.project_ids),
            "categories_changed": False,
            "native_destination_changed": False,
            "raw_payloads_exposed": False,
        }

    def enable(self, token: str, *, confirmed: bool, key: str) -> None:
        service = self.service
        if not key:
            raise AutonomyIntegrityError("completed-work confirmation requires an idempotency key")
        previous = next((e for e in service.store.events() if e["key"] == key), None)
        if previous:
            if (
                previous["type"] != "source_work_confirmation"
                or previous["payload"]["token"] != token
            ):
                raise AutonomyIntegrityError("completed-work idempotency changed")
            return
        preview = self._previews.get(token)
        grant = service.grant()
        if (
            not confirmed
            or preview is None
            or grant is None
            or not service.secure_store_available()
            or preview["expires"] <= service.clock()
            or preview["head"] != service.store.head_digest
            or preview["projects"] != service.projects
            or preview["policy"].grant_digest != grant.content_digest
        ):
            raise AutonomyIntegrityError("completed-work preview changed or lacks confirmation")
        policy = preview["policy"]
        cursor_value = None
        # Validate before writing authority. Confirmation is the final commit marker.
        cursor = service.store.latest("cursor")
        if cursor is not None and cursor["grant_id"] == grant.grant_id:
            from adaptation_compiler_lab.autonomy.codex_source import HabitSourceCursorV1

            before = HabitSourceCursorV1.model_validate_json(str(cursor["cursor"]), strict=True)
            if before.grant_digest != grant.content_digest:
                raise AutonomyIntegrityError("source cursor belongs to another grant")
            cursor_value = before.model_copy(update={"next_page": None}).model_dump_json()
        service.store.append(
            "source-work-" + str(policy.content_digest)[7:],
            "source_work_authorization",
            policy.model_dump(mode="json"),
            at=service.clock(),
        )
        # Resume from the newest page while preserving prior conversation checkpoints.
        if cursor_value is not None:
            service.store.append(
                "source-work-cursor-" + str(policy.content_digest)[7:],
                "cursor",
                {"grant_id": grant.grant_id, "cursor": cursor_value},
                at=service.clock(),
            )
        service.store.append(
            key,
            "source_work_confirmation",
            {"token": token, "policy_digest": policy.content_digest},
            at=service.clock(),
        )

    def disable(self, *, key: str) -> None:
        if not key or not self.service.secure_store_available():
            raise AutonomyIntegrityError("secure store is unavailable")
        self.service.store.append(
            key, "source_work_authorization", {"disabled": True}, at=self.service.clock()
        )
