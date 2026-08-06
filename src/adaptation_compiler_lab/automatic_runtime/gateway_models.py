"""Raw-free contracts for the writable automatic-adaptation gateway."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import FrozenModel, Identifier, Sha256Digest, UtcDateTime
from adaptation_compiler_lab.serialization import canonical_digest


class GatewaySessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class ChangeApplicationStatus(StrEnum):
    APPLIED = "applied"
    DISCARDED = "discarded"
    REFUSED = "refused"
    ROLLED_BACK = "rolled_back"


class VerificationCommandSpec(FrozenModel):
    """One bounded argv command; shell interpretation is intentionally impossible."""

    command_id: Identifier
    argv: Annotated[tuple[str, ...], Field(min_length=1, max_length=32)]
    timeout_seconds: int = Field(default=600, ge=1, le=1_800)
    maximum_output_bytes: int = Field(default=1_000_000, ge=1_024, le=10_000_000)

    @field_validator("argv")
    @classmethod
    def arguments_are_safe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item or "\x00" in item for item in value):
            raise ValueError("verification argv entries must be non-empty and NUL-free")
        if value[0].lower() in {
            "bash",
            "cmd",
            "cmd.exe",
            "powershell",
            "powershell.exe",
            "sh",
            "zsh",
        }:
            raise ValueError("verification commands must not invoke a general-purpose shell")
        return value


class CredentialEnvelopeMetadata(FrozenModel):
    envelope_id: Identifier
    envelope_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    config_digest: Sha256Digest
    signer_fingerprint: Sha256Digest
    protector: Literal["windows-dpapi-current-user"]
    ciphertext_digest: Sha256Digest
    enrolled_at: UtcDateTime
    revoked_at: UtcDateTime | None = None

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeWatcherLease(FrozenModel):
    lease_id: Identifier
    subject_id: Identifier
    owner_pid: int = Field(ge=1)
    acquired_at: UtcDateTime
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def expiry_follows_acquisition(self) -> Self:
        if self.expires_at <= self.acquired_at:
            raise ValueError("watcher lease expiry must follow acquisition")
        return self


class RuntimeWatcherHeartbeat(FrozenModel):
    heartbeat_id: Identifier
    lease_id: Identifier
    sequence: int = Field(ge=1)
    observed_at: UtcDateTime
    status: Literal["healthy", "backing_off", "stopping"]
    failure_class: str | None = None


class NotificationInboxEntry(FrozenModel):
    entry_id: Identifier
    subject_id: Identifier
    notice_digest: Sha256Digest
    kind: str
    public_summary: str
    created_at: UtcDateTime

    @field_validator("public_summary")
    @classmethod
    def summary_is_generic(cls, value: str) -> str:
        allowed = {
            "Adaptation review available.",
            "Adaptation updated.",
            "Adaptation removed.",
            "Adaptation runtime needs attention.",
        }
        if value not in allowed:
            raise ValueError("notification summary is not on the raw-free allowlist")
        return value


class RuntimeNotificationReceipt(FrozenModel):
    receipt_id: Identifier
    entry_id: Identifier
    channel: Literal["local_inbox", "windows_toast"]
    status: Literal["published", "failed", "acknowledged"]
    recorded_at: UtcDateTime
    failure_class: str | None = None


class WorkspaceBaseline(FrozenModel):
    baseline_id: Identifier
    project_id: Identifier
    canonical_root_digest: Sha256Digest
    commit_sha: str
    tree_sha: str
    workspace_root_digest: Sha256Digest
    created_at: UtcDateTime

    @field_validator("commit_sha", "tree_sha")
    @classmethod
    def git_object_is_hex(cls, value: str) -> str:
        if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("Git object IDs must be lowercase SHA-1 hex")
        return value


class WorkspaceLease(FrozenModel):
    lease_id: Identifier
    session_id: Identifier
    baseline_digest: Sha256Digest
    workspace_root_digest: Sha256Digest
    acquired_at: UtcDateTime
    expires_at: UtcDateTime


class VerificationReceipt(FrozenModel):
    receipt_id: Identifier
    session_id: Identifier
    command_id: Identifier
    argv_digest: Sha256Digest
    exit_code: int
    timed_out: bool
    output_digest: Sha256Digest
    output_bytes: int = Field(ge=0)
    started_at: UtcDateTime
    completed_at: UtcDateTime


class WorkspaceFileChange(FrozenModel):
    path: str
    operation: Literal["add", "modify", "delete"]
    before_digest: Sha256Digest | None = None
    after_digest: Sha256Digest | None = None
    before_mode: int | None = Field(default=None, ge=0, le=0o777)
    after_mode: int | None = Field(default=None, ge=0, le=0o777)
    size_bytes: int = Field(ge=0)
    binary: bool

    @field_validator("path")
    @classmethod
    def path_is_relative(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            not normalized
            or normalized.startswith("/")
            or normalized == ".git"
            or normalized.startswith(".git/")
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
        ):
            raise ValueError("change path must be a safe repository-relative path")
        return normalized


class WorkspaceChangeReceipt(FrozenModel):
    receipt_id: Identifier
    session_id: Identifier
    subject_id: Identifier
    baseline_digest: Sha256Digest
    release_digest: Sha256Digest
    projection_digest: Sha256Digest
    encrypted_bundle_digest: Sha256Digest
    changes: tuple[WorkspaceFileChange, ...]
    total_bytes: int = Field(ge=0, le=25_000_000)
    verification_receipt_digests: tuple[Sha256Digest, ...]
    captured_at: UtcDateTime

    @field_validator("changes")
    @classmethod
    def changes_are_sorted_unique(
        cls, value: tuple[WorkspaceFileChange, ...]
    ) -> tuple[WorkspaceFileChange, ...]:
        paths = tuple(item.path for item in value)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("workspace changes must be path-sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class GatewaySession(FrozenModel):
    session_id: Identifier
    instrument_version: Literal["6A.2D-v1"] = "6A.2D-v1"
    subject_id: Identifier
    project_id: Identifier
    activation_id: Identifier
    release_digest: Sha256Digest
    projection_digest: Sha256Digest
    baseline_digest: Sha256Digest
    model: str
    reasoning_effort: str
    maximum_turns: int = Field(default=15, ge=1, le=15)
    maximum_session_seconds: int = Field(default=3_600, ge=1, le=3_600)
    maximum_turn_seconds: int = Field(default=600, ge=1, le=600)
    projection_utf8_bytes: int = Field(ge=0)
    encrypted_trace_digest: Sha256Digest | None = None
    started_at: UtcDateTime
    completed_at: UtcDateTime | None = None
    status: GatewaySessionStatus = GatewaySessionStatus.ACTIVE
    failure_class: str | None = None

    @model_validator(mode="after")
    def completion_shape_is_coherent(self) -> Self:
        terminal = self.status is not GatewaySessionStatus.ACTIVE
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal gateway sessions require a completion time")
        if (self.status is GatewaySessionStatus.FAILED) != (self.failure_class is not None):
            raise ValueError("failed gateway sessions require exactly one failure class")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class GatewayInstrumentMetrics(FrozenModel):
    instrument_version: Literal["6A.2D-v1"] = "6A.2D-v1"
    subject_id: Identifier
    session_count: int = Field(ge=0)
    turn_count: int = Field(ge=0)
    notification_count: int = Field(ge=0)
    watcher_heartbeat_count: int = Field(ge=0)
    captured_bundle_count: int = Field(ge=0)
    applied_count: int = Field(ge=0)
    rolled_back_count: int = Field(ge=0)
    discarded_count: int = Field(ge=0)
    refused_count: int = Field(ge=0)
    total_projection_utf8_bytes: int = Field(ge=0)
    generated_at: UtcDateTime


class GatewayTurnReceipt(FrozenModel):
    receipt_id: Identifier
    session_id: Identifier
    sequence: int = Field(ge=1, le=15)
    user_message_digest: Sha256Digest
    agent_message_digest: Sha256Digest | None = None
    status: Literal["completed", "failed", "interrupted"]
    started_at: UtcDateTime
    completed_at: UtcDateTime


class ChangeApplicationReceipt(FrozenModel):
    receipt_id: Identifier
    session_id: Identifier
    change_receipt_digest: Sha256Digest
    expected_head: str
    status: ChangeApplicationStatus
    verification_receipt_digests: tuple[Sha256Digest, ...]
    recorded_at: UtcDateTime
    failure_class: str | None = None

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
