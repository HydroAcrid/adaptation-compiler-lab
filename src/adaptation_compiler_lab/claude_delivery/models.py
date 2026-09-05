"""Strict transient inputs and signed raw-free receipts for Claude Code hooks."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.governance import SignatureEnvelope
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.base import sha256_text

MAX_CLAUDE_HOOK_OUTPUT_CHARACTERS = 10_000
MAX_CLAUDE_PROJECTION_UTF8_BYTES = 12_000


class ClaudeHookEvent(StrEnum):
    """Lifecycle events used by Temper's official Claude Code hook integration."""

    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"
    STOP_FAILURE = "StopFailure"
    SESSION_END = "SessionEnd"


class ClaudeHookDisposition(StrEnum):
    """Raw-free outcome of one hook invocation."""

    NOOP_UNREGISTERED = "noop_unregistered"
    NOOP_UNAUTHORIZED = "noop_unauthorized"
    NOOP_NO_PROJECTION = "noop_no_projection"
    NOOP_INVALID_PROJECTION = "noop_invalid_projection"
    DELIVERED = "delivered"
    OUTCOME_CAPTURED = "outcome_captured"
    FAILURE_CAPTURED = "failure_captured"
    SESSION_CLOSED = "session_closed"


class ClaudeHookInvocationV1(FrozenModel):
    """Transient allowlisted event data; transcript paths are deliberately absent."""

    invocation_version: Literal["1.0.0"] = "1.0.0"
    event: ClaudeHookEvent
    session_id: str = Field(min_length=1, max_length=512)
    working_directory: str = Field(min_length=1, max_length=4_096)
    permission_mode: str | None = Field(default=None, min_length=1, max_length=100)
    prompt: str | None = Field(default=None, min_length=1, max_length=1_048_576)
    last_assistant_message: str | None = Field(
        default=None,
        min_length=1,
        max_length=1_048_576,
    )
    failure_class: str | None = Field(default=None, min_length=1, max_length=100)
    failure_details: str | None = Field(default=None, min_length=1, max_length=16_384)
    session_end_reason: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def event_shape_is_exact(self) -> Self:
        if self.event is ClaudeHookEvent.USER_PROMPT_SUBMIT:
            if self.prompt is None or any(
                value is not None
                for value in (
                    self.last_assistant_message,
                    self.failure_class,
                    self.failure_details,
                    self.session_end_reason,
                )
            ):
                raise ValueError("UserPromptSubmit requires only one exact prompt")
        elif self.event is ClaudeHookEvent.STOP:
            if self.last_assistant_message is None or any(
                value is not None
                for value in (
                    self.prompt,
                    self.failure_class,
                    self.failure_details,
                    self.session_end_reason,
                )
            ):
                raise ValueError("Stop requires only the final assistant message")
        elif self.event is ClaudeHookEvent.STOP_FAILURE:
            if self.failure_class is None or any(
                value is not None for value in (self.prompt, self.session_end_reason)
            ):
                raise ValueError("StopFailure requires one bounded failure class")
        elif self.session_end_reason is None or any(
            value is not None
            for value in (
                self.prompt,
                self.last_assistant_message,
                self.failure_class,
                self.failure_details,
            )
        ):
            raise ValueError("SessionEnd requires only one end reason")
        return self


class ClaudeHookProjectV1(FrozenModel):
    """Exact registered project selected locally from an invocation working directory."""

    subject_id: Identifier
    project_id: Identifier
    instruction_environment_digest: Sha256Digest
    consent_current: bool
    learning_enabled: bool
    delivery_enabled: bool


class ClaudeProjectionLeaseV1(FrozenModel):
    """Signed, cached, task-independent Claude projection available to the hook path."""

    lease_version: Literal["1.0.0"] = "1.0.0"
    lease_id: Identifier
    subject_id: Identifier
    project_id: Identifier
    target_family: Literal["claude-code"] = "claude-code"
    instruction_environment_digest: Sha256Digest
    external_release_digest: Sha256Digest
    projection_digest: Sha256Digest
    projection_manifest_digest: Sha256Digest
    material: NonEmptyStr
    material_digest: Sha256Digest
    material_utf8_bytes: int = Field(gt=0, le=MAX_CLAUDE_PROJECTION_UTF8_BYTES)
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def material_and_signature_are_exact(self) -> Self:
        if len(self.material) > MAX_CLAUDE_HOOK_OUTPUT_CHARACTERS:
            raise ValueError("Claude projection exceeds the official hook output limit")
        if self.material_utf8_bytes != len(self.material.encode("utf-8")):
            raise ValueError("Claude projection byte count is inconsistent")
        if self.material_digest != sha256_text(self.material):
            raise ValueError("Claude projection material digest is inconsistent")
        if self.expires_at <= self.issued_at:
            raise ValueError("Claude projection lease must expire after issuance")
        if (
            self.signature.purpose != "claude_projection_lease"
            or self.signature.signed_at != self.issued_at
        ):
            raise ValueError("Claude projection signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeHookSpecificOutputV1(FrozenModel):
    """Official structured UserPromptSubmit response shape."""

    hook_event_name: Literal["UserPromptSubmit"] = Field(
        default="UserPromptSubmit",
        serialization_alias="hookEventName",
    )
    additional_context: NonEmptyStr = Field(serialization_alias="additionalContext")


class ClaudeUserPromptHookOutputV1(FrozenModel):
    """Only output Temper ever returns to Claude Code."""

    hook_specific_output: ClaudeHookSpecificOutputV1 = Field(
        serialization_alias="hookSpecificOutput"
    )

    @field_validator("hook_specific_output")
    @classmethod
    def output_is_below_claude_limit(
        cls, value: ClaudeHookSpecificOutputV1
    ) -> ClaudeHookSpecificOutputV1:
        if len(value.additional_context) > MAX_CLAUDE_HOOK_OUTPUT_CHARACTERS:
            raise ValueError("Claude hook output exceeds its official character limit")
        return value

    def claude_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)


class ClaudeHookAuditReceiptV1(FrozenModel):
    """Signed raw-free audit entry; session and content are represented only by digests."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    subject_id: Identifier
    project_id: Identifier
    event: ClaudeHookEvent
    disposition: ClaudeHookDisposition
    session_digest: Sha256Digest
    invocation_digest: Sha256Digest
    content_digest: Sha256Digest | None = None
    projection_lease_digest: Sha256Digest | None = None
    occurred_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def signed_shape_is_consistent(self) -> Self:
        delivered = self.disposition is ClaudeHookDisposition.DELIVERED
        if delivered != (self.projection_lease_digest is not None):
            raise ValueError("Claude delivery audit binding is inconsistent")
        if (
            self.signature.purpose != "claude_hook_audit"
            or self.signature.signed_at != self.occurred_at
        ):
            raise ValueError("Claude hook audit signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def receipt_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeHookResultV1(FrozenModel):
    """Broker result; an absent output means Claude Code receives a silent exit-0 no-op."""

    event: ClaudeHookEvent
    disposition: ClaudeHookDisposition
    audit_receipt: ClaudeHookAuditReceiptV1 | None = None
    output: ClaudeUserPromptHookOutputV1 | None = None

    @model_validator(mode="after")
    def output_only_accompanies_delivery(self) -> Self:
        delivered = self.disposition is ClaudeHookDisposition.DELIVERED
        if delivered != (self.output is not None):
            raise ValueError("only a verified Claude projection may produce hook output")
        return self


class ClaudeHookSettingsPreviewV1(FrozenModel):
    """Raw-free, expiring preview of one exact user-settings mutation."""

    preview_version: Literal["1.0.0"] = "1.0.0"
    preview_token: Identifier
    operation: Literal["install", "uninstall"]
    before_digest: Sha256Digest
    after_digest: Sha256Digest
    before_existed: bool
    after_existed: bool
    helper_digest: Sha256Digest
    events: tuple[ClaudeHookEvent, ...]
    redacted_diff: NonEmptyStr
    expires_at: UtcDateTime
    modifies_only_user_settings: Literal[True] = True
    provider_authentication_changed: Literal[False] = False
    provider_call_required: Literal[False] = False
    raw_paths_exposed: Literal[False] = False

    @field_validator("events")
    @classmethod
    def event_set_is_complete_and_ordered(
        cls, value: tuple[ClaudeHookEvent, ...]
    ) -> tuple[ClaudeHookEvent, ...]:
        expected = tuple(sorted(ClaudeHookEvent, key=lambda item: item.value))
        if value != expected:
            raise ValueError("Claude settings preview requires the complete hook event set")
        return value


class ClaudeHookSettingsChangeReceiptV1(FrozenModel):
    """Signed receipt for install, uninstall, or exact encrypted rollback."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    preview_token: Identifier
    operation: Literal["install", "uninstall", "rollback"]
    before_digest: Sha256Digest
    after_digest: Sha256Digest
    before_existed: bool
    after_existed: bool
    helper_digest: Sha256Digest
    settings_locator_digest: Sha256Digest
    backup_digest: Sha256Digest
    applied_at: UtcDateTime
    rollback_available_until: UtcDateTime
    rollback_of_receipt_id: Identifier | None = None
    signature: SignatureEnvelope
    raw_paths_exposed: Literal[False] = False

    @model_validator(mode="after")
    def rollback_and_signature_are_consistent(self) -> Self:
        if (self.operation == "rollback") != (self.rollback_of_receipt_id is not None):
            raise ValueError("Claude settings rollback lineage is inconsistent")
        if self.rollback_available_until <= self.applied_at:
            raise ValueError("Claude settings rollback window is invalid")
        if (
            self.signature.purpose != "claude_hook_settings_change"
            or self.signature.signed_at != self.applied_at
        ):
            raise ValueError("Claude settings change signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
