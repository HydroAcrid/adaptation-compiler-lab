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
from adaptation_compiler_lab.governance import ConsentReceipt, SignatureEnvelope
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


class ClaudeCapturedAuthority(StrEnum):
    """Authority retained for captured hook content before any semantic review."""

    USER_AUTHORED_INPUT = "user_authored_input"
    UNTRUSTED_ASSISTANT_CONTEXT = "untrusted_assistant_context"
    UNTRUSTED_FAILURE_CONTEXT = "untrusted_failure_context"


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


class ClaudeHookAuthorizationV1(FrozenModel):
    """Validated local consent and connection posture for one registered project."""

    authorization_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    project_id: Identifier
    consent_digest: Sha256Digest
    project_registration_digest: Sha256Digest
    learning_enabled: bool
    delivery_enabled: bool
    effective_at: UtcDateTime
    expires_at: UtcDateTime
    retention_until: UtcDateTime

    @model_validator(mode="after")
    def time_bounds_are_coherent(self) -> Self:
        if self.expires_at <= self.effective_at:
            raise ValueError("Claude authorization expiry must follow its effective time")
        if self.retention_until < self.expires_at:
            raise ValueError("Claude authorization retention cannot precede consent expiry")
        return self


class ClaudeProjectionManifestV1(FrozenModel):
    """Raw-free binding for the exact native-aware projection cached for Claude."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    project_id: Identifier
    external_release_digest: Sha256Digest
    canonical_projection_digest: Sha256Digest
    delta_projection_digest: Sha256Digest
    instruction_environment_digest: Sha256Digest
    native_source_chain_digest: Sha256Digest
    included_clause_digests: tuple[Sha256Digest, ...]
    omitted_clause_digests: tuple[Sha256Digest, ...]
    blocked_clause_digests: tuple[Sha256Digest, ...]
    relation_digests: tuple[Sha256Digest, ...]
    unresolved_conflict_ids: tuple[Identifier, ...]
    rendered_content_digest: Sha256Digest
    rendered_utf8_bytes: int = Field(gt=0, le=MAX_CLAUDE_PROJECTION_UTF8_BYTES)
    fully_optimized: bool
    created_at: UtcDateTime

    @field_validator(
        "included_clause_digests",
        "omitted_clause_digests",
        "blocked_clause_digests",
        "relation_digests",
        "unresolved_conflict_ids",
    )
    @classmethod
    def digest_sets_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("Claude projection manifest sets must be sorted and unique")
        return value

    @model_validator(mode="after")
    def dispositions_do_not_overlap(self) -> Self:
        dispositions = (
            set(self.included_clause_digests),
            set(self.omitted_clause_digests),
            set(self.blocked_clause_digests),
        )
        if (
            dispositions[0] & dispositions[1]
            or dispositions[0] & dispositions[2]
            or dispositions[1] & dispositions[2]
        ):
            raise ValueError("Claude projection clause dispositions overlap")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


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
    material: str = Field(min_length=1, max_length=MAX_CLAUDE_HOOK_OUTPUT_CHARACTERS)
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


class ClaudeHookCaptureReceiptV1(FrozenModel):
    """Signed raw-free receipt for one encrypted hook payload."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    subject_id: Identifier
    project_id: Identifier
    event: Literal[
        ClaudeHookEvent.USER_PROMPT_SUBMIT,
        ClaudeHookEvent.STOP,
        ClaudeHookEvent.STOP_FAILURE,
    ]
    authority: ClaudeCapturedAuthority
    session_digest: Sha256Digest
    content_digest: Sha256Digest
    raw_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_payload_size_bytes: int = Field(gt=0, le=1_048_576)
    media_type: NonEmptyStr
    consent_digest: Sha256Digest
    project_registration_digest: Sha256Digest
    captured_at: UtcDateTime
    retention_until: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def authority_and_signature_are_exact(self) -> Self:
        expected = {
            ClaudeHookEvent.USER_PROMPT_SUBMIT: ClaudeCapturedAuthority.USER_AUTHORED_INPUT,
            ClaudeHookEvent.STOP: ClaudeCapturedAuthority.UNTRUSTED_ASSISTANT_CONTEXT,
            ClaudeHookEvent.STOP_FAILURE: ClaudeCapturedAuthority.UNTRUSTED_FAILURE_CONTEXT,
        }[self.event]
        if self.authority is not expected:
            raise ValueError("Claude capture authority does not match its source event")
        if self.retention_until <= self.captured_at:
            raise ValueError("Claude capture retention must follow capture")
        if (
            self.signature.purpose != "claude_hook_capture"
            or self.signature.signed_at != self.captured_at
        ):
            raise ValueError("Claude capture signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def receipt_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeHookSpecificOutputV1(FrozenModel):
    """Official structured UserPromptSubmit response shape."""

    hook_event_name: Literal["UserPromptSubmit"] = Field(
        default="UserPromptSubmit",
        serialization_alias="hookEventName",
    )
    additional_context: str = Field(
        min_length=1,
        max_length=MAX_CLAUDE_HOOK_OUTPUT_CHARACTERS,
        serialization_alias="additionalContext",
    )


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


class ClaudeHookLedgerEntryV1(FrozenModel):
    """Signed chained local index entry; it contains no decrypted payload bytes."""

    entry_version: Literal["1.0.0"] = "1.0.0"
    entry_id: Identifier
    subject_id: Identifier
    project_id: Identifier
    sequence: int = Field(ge=1)
    previous_entry_digest: Sha256Digest | None = None
    entry_kind: Literal["capture", "audit"]
    capture_receipt: ClaudeHookCaptureReceiptV1 | None = None
    audit_receipt: ClaudeHookAuditReceiptV1 | None = None
    raw_payload_relative_path: str | None = Field(default=None, max_length=512)
    appended_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def entry_shape_and_signature_are_exact(self) -> Self:
        capture = self.capture_receipt
        audit = self.audit_receipt
        if self.entry_kind == "capture":
            if capture is None or audit is not None or self.raw_payload_relative_path is None:
                raise ValueError("Claude capture ledger entry has the wrong shape")
            record_subject = capture.subject_id
            record_project = capture.project_id
        else:
            if audit is None or capture is not None or self.raw_payload_relative_path is not None:
                raise ValueError("Claude audit ledger entry has the wrong shape")
            record_subject = audit.subject_id
            record_project = audit.project_id
        if record_subject != self.subject_id or record_project != self.project_id:
            raise ValueError("Claude ledger entry crossed its record boundary")
        if self.raw_payload_relative_path is not None:
            parts = self.raw_payload_relative_path.replace("\\", "/").split("/")
            if (
                self.raw_payload_relative_path.startswith(("/", "\\"))
                or ":" in self.raw_payload_relative_path
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise ValueError("Claude ledger raw reference must be a safe relative path")
        if self.sequence == 1 and self.previous_entry_digest is not None:
            raise ValueError("first Claude ledger entry cannot have a predecessor")
        if self.sequence > 1 and self.previous_entry_digest is None:
            raise ValueError("later Claude ledger entries require a predecessor")
        if (
            self.signature.purpose != "claude_hook_ledger_entry"
            or self.signature.signed_at != self.appended_at
        ):
            raise ValueError("Claude ledger entry signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
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


class ClaudeConnectionProjectV1(FrozenModel):
    """One exact registered project authorized for the local Claude hook."""

    project_id: Identifier
    project_registration_digest: Sha256Digest


class ClaudeConnectionPreviewV1(FrozenModel):
    """Raw-free user decision surface for connecting or disconnecting Claude."""

    preview_version: Literal["1.0.0"] = "1.0.0"
    operation: Literal["connect", "disconnect"]
    settings: ClaudeHookSettingsPreviewV1
    project_ids: tuple[Identifier, ...]
    current_connection_digest: Sha256Digest | None = None
    consent_expires_at: UtcDateTime
    retention_until: UtcDateTime
    learning_enabled: bool
    delivery_enabled: bool
    provider_call_required: Literal[False] = False
    provider_authentication_changed: Literal[False] = False
    raw_paths_exposed: Literal[False] = False

    @field_validator("project_ids")
    @classmethod
    def projects_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or value != tuple(sorted(set(value))):
            raise ValueError("Claude connection projects must be sorted and unique")
        return value


class ClaudeConnectionReceiptV1(FrozenModel):
    """Signed active-state transition binding consent to exact hook settings."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    operation: Literal["connect", "disconnect"]
    subject_id: Identifier
    projects: tuple[ClaudeConnectionProjectV1, ...]
    consent: ConsentReceipt
    settings_receipt: ClaudeHookSettingsChangeReceiptV1
    previous_connection_digest: Sha256Digest | None = None
    learning_enabled: bool
    delivery_enabled: bool
    occurred_at: UtcDateTime
    expires_at: UtcDateTime
    retention_until: UtcDateTime
    signature: SignatureEnvelope
    raw_paths_exposed: Literal[False] = False

    @field_validator("projects")
    @classmethod
    def project_bindings_are_sorted_unique(
        cls, value: tuple[ClaudeConnectionProjectV1, ...]
    ) -> tuple[ClaudeConnectionProjectV1, ...]:
        ids = tuple(item.project_id for item in value)
        if not ids or ids != tuple(sorted(set(ids))):
            raise ValueError("Claude connection project bindings must be sorted and unique")
        return value

    @model_validator(mode="after")
    def consent_settings_and_signature_are_exact(self) -> Self:
        project_ids = tuple(item.project_id for item in self.projects)
        if (
            self.consent.subject_id != self.subject_id
            or self.consent.source_selector.source_system != "claude_code_hook"
            or self.consent.source_selector.source_ids != project_ids
            or self.consent.scope.project_ids != project_ids
            or self.consent.scope.target_families != ("claude-code",)
            or self.expires_at != self.consent.expires_at
            or self.retention_until != self.consent.retention_until
        ):
            raise ValueError("Claude connection consent binding changed")
        if self.operation == "connect":
            if (
                self.settings_receipt.operation != "install"
                or not self.learning_enabled
                or not self.delivery_enabled
            ):
                raise ValueError("connected Claude state requires installed learning and delivery")
        elif (
            self.settings_receipt.operation != "uninstall"
            or self.learning_enabled
            or self.delivery_enabled
        ):
            raise ValueError("disconnected Claude state must disable learning and delivery")
        if self.retention_until < self.expires_at or self.expires_at <= self.consent.issued_at:
            raise ValueError("Claude connection time bounds are invalid")
        if (
            self.signature.purpose != "claude_connection_change"
            or self.signature.signed_at != self.occurred_at
        ):
            raise ValueError("Claude connection signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClaudeConnectionStatusV1(FrozenModel):
    """Raw-free verified product status for the Claude connection."""

    status_version: Literal["1.0.0"] = "1.0.0"
    state: Literal["available", "connected", "attention"]
    project_count: int = Field(ge=0)
    learning_enabled: bool
    delivery_enabled: bool
    expires_at: UtcDateTime | None = None
    current_connection_digest: Sha256Digest | None = None
    status_summary: NonEmptyStr
    raw_paths_exposed: Literal[False] = False
