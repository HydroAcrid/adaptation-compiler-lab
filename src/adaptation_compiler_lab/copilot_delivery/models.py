"""Versioned, raw-free GitHub Copilot surface capability declarations."""

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

MAX_COPILOT_PROJECTION_UTF8_BYTES = 12_000
MAX_COPILOT_HOOK_INPUT_CHARACTERS = 1_048_576


class CopilotSurface(StrEnum):
    GITHUB_CHAT = "github-chat"
    GITHUB_CLOUD_AGENT = "github-cloud-agent"
    GITHUB_CODE_REVIEW = "github-code-review"
    VSCODE_CHAT = "vscode-chat"
    VISUAL_STUDIO_CHAT = "visual-studio-chat"
    JETBRAINS_CHAT = "jetbrains-chat"
    ECLIPSE_CHAT = "eclipse-chat"
    XCODE_CHAT = "xcode-chat"
    COPILOT_CLI = "copilot-cli"


class CopilotDeliveryMechanism(StrEnum):
    USER_HOOK = "user_hook"
    REPOSITORY_INSTRUCTION_PREVIEW = "repository_instruction_preview"
    OBSERVE_ONLY = "observe_only"


class CopilotSurfaceCapabilityV1(FrozenModel):
    """Current product posture for one documented Copilot surface."""

    capability_version: Literal["1.0.0"] = "1.0.0"
    contract_revision: Literal["github-copilot-docs-2026-09-05"] = "github-copilot-docs-2026-09-05"
    surface: CopilotSurface
    repository_wide_instructions: bool
    path_specific_instructions: bool
    agent_instructions: bool
    personal_instructions: bool
    local_command_hooks: bool
    direct_temper_delivery: bool
    delivery_mechanism: CopilotDeliveryMechanism
    summary: NonEmptyStr
    provider_call_required_for_connection: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False


def default_copilot_capability_matrix() -> tuple[CopilotSurfaceCapabilityV1, ...]:
    """Return the reviewed official support matrix in stable surface order."""

    entries = (
        (CopilotSurface.GITHUB_CHAT, True, False, False, True),
        (CopilotSurface.GITHUB_CLOUD_AGENT, True, True, True, False),
        (CopilotSurface.GITHUB_CODE_REVIEW, True, True, True, False),
        (CopilotSurface.VSCODE_CHAT, True, True, True, False),
        (CopilotSurface.VISUAL_STUDIO_CHAT, True, True, False, False),
        (CopilotSurface.JETBRAINS_CHAT, True, True, False, True),
        (CopilotSurface.ECLIPSE_CHAT, True, False, False, False),
        (CopilotSurface.XCODE_CHAT, True, True, False, False),
        (CopilotSurface.COPILOT_CLI, True, True, True, True),
    )
    return tuple(
        CopilotSurfaceCapabilityV1(
            surface=surface,
            repository_wide_instructions=repository_wide,
            path_specific_instructions=path_specific,
            agent_instructions=agent,
            personal_instructions=personal,
            local_command_hooks=surface is CopilotSurface.COPILOT_CLI,
            direct_temper_delivery=surface is CopilotSurface.COPILOT_CLI,
            delivery_mechanism=(
                CopilotDeliveryMechanism.USER_HOOK
                if surface is CopilotSurface.COPILOT_CLI
                else CopilotDeliveryMechanism.REPOSITORY_INSTRUCTION_PREVIEW
                if repository_wide or path_specific or agent
                else CopilotDeliveryMechanism.OBSERVE_ONLY
            ),
            summary=(
                "Copilot CLI can receive approved, project-scoped Temper context through its "
                "official local prompt-transformation hook."
                if surface is CopilotSurface.COPILOT_CLI
                else "Temper can inspect supported native instructions and offer a confirmed "
                "repository-file preview; it cannot inject directly into this surface."
            ),
        )
        for surface, repository_wide, path_specific, agent, personal in entries
    )


class CopilotHookDisposition(StrEnum):
    """Raw-free result of a Copilot CLI prompt-transformation event."""

    NOOP_UNREGISTERED = "noop_unregistered"
    NOOP_UNAUTHORIZED = "noop_unauthorized"
    NOOP_NO_PROJECTION = "noop_no_projection"
    NOOP_STALE_ENVIRONMENT = "noop_stale_environment"
    DELIVERED = "delivered"


class CopilotHookInvocationV1(FrozenModel):
    """Exact transient fields accepted from ``userPromptTransformed``."""

    invocation_version: Literal["1.0.0"] = "1.0.0"
    session_id: str = Field(min_length=1, max_length=512)
    timestamp_epoch_ms: int = Field(ge=0)
    working_directory: str = Field(min_length=1, max_length=4_096)
    prompt: str = Field(min_length=1, max_length=MAX_COPILOT_HOOK_INPUT_CHARACTERS)
    transformed_prompt: str = Field(
        min_length=1,
        max_length=MAX_COPILOT_HOOK_INPUT_CHARACTERS,
    )


class CopilotHookProjectV1(FrozenModel):
    """Registered project resolved locally without exposing its path."""

    subject_id: Identifier
    project_id: Identifier
    instruction_environment_digest: Sha256Digest
    consent_current: bool
    delivery_enabled: bool


class CopilotHookAuthorizationV1(FrozenModel):
    """Current signed connection consent for one registered project."""

    authorization_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    project_id: Identifier
    consent_digest: Sha256Digest
    project_registration_digest: Sha256Digest
    delivery_enabled: bool
    effective_at: UtcDateTime
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def time_bounds_are_coherent(self) -> Self:
        if self.expires_at <= self.effective_at:
            raise ValueError("Copilot authorization expiry must follow issuance")
        return self


class CopilotProjectionManifestV1(FrozenModel):
    """Raw-free lineage for the native-aware Copilot CLI delta."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    subject_id: Identifier
    project_id: Identifier
    external_release_digest: Sha256Digest
    target_authorization_digest: Sha256Digest | None = None
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
    rendered_utf8_bytes: int = Field(gt=0, le=MAX_COPILOT_PROJECTION_UTF8_BYTES)
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
    def sets_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("Copilot projection manifest sets must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CopilotProjectionLeaseV1(FrozenModel):
    """Signed cached projection; hook execution performs no compilation or model call."""

    lease_version: Literal["1.0.0"] = "1.0.0"
    lease_id: Identifier
    subject_id: Identifier
    project_id: Identifier
    target_family: Literal["copilot-cli"] = "copilot-cli"
    instruction_environment_digest: Sha256Digest
    external_release_digest: Sha256Digest
    projection_digest: Sha256Digest
    projection_manifest_digest: Sha256Digest
    material: str = Field(min_length=1, max_length=MAX_COPILOT_PROJECTION_UTF8_BYTES)
    material_digest: Sha256Digest
    material_utf8_bytes: int = Field(gt=0, le=MAX_COPILOT_PROJECTION_UTF8_BYTES)
    issued_at: UtcDateTime
    expires_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def lease_is_exact(self) -> Self:
        if self.material_utf8_bytes != len(self.material.encode("utf-8")):
            raise ValueError("Copilot projection byte count is inconsistent")
        if self.material_digest != sha256_text(self.material):
            raise ValueError("Copilot projection material digest is inconsistent")
        if self.expires_at <= self.issued_at:
            raise ValueError("Copilot projection lease must expire after issuance")
        if (
            self.signature.purpose != "copilot_projection_lease"
            or self.signature.signed_at != self.issued_at
        ):
            raise ValueError("Copilot projection signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CopilotHookOutputV1(FrozenModel):
    """Only official command-hook field returned to Copilot CLI."""

    modified_transformed_prompt: str = Field(
        min_length=1,
        max_length=MAX_COPILOT_HOOK_INPUT_CHARACTERS + MAX_COPILOT_PROJECTION_UTF8_BYTES + 256,
        serialization_alias="modifiedTransformedPrompt",
    )

    def copilot_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)


class CopilotDeliveryReceiptV1(FrozenModel):
    """Signed raw-free record of one exact local projection delivery."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    subject_id: Identifier
    project_id: Identifier
    session_digest: Sha256Digest
    prompt_digest: Sha256Digest
    transformed_prompt_digest: Sha256Digest
    projection_lease_digest: Sha256Digest
    instruction_environment_digest: Sha256Digest
    delivered_at: UtcDateTime
    signature: SignatureEnvelope
    raw_payloads_stored: Literal[False] = False

    @model_validator(mode="after")
    def signature_is_exact(self) -> Self:
        if (
            self.signature.purpose != "copilot_delivery_receipt"
            or self.signature.signed_at != self.delivered_at
        ):
            raise ValueError("Copilot delivery signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CopilotHookResultV1(FrozenModel):
    """Internal broker result; an absent output is an exit-zero no-op."""

    disposition: CopilotHookDisposition
    receipt: CopilotDeliveryReceiptV1 | None = None
    output: CopilotHookOutputV1 | None = None

    @model_validator(mode="after")
    def delivered_shape_is_exact(self) -> Self:
        delivered = self.disposition is CopilotHookDisposition.DELIVERED
        if delivered != (self.receipt is not None and self.output is not None):
            raise ValueError("only a verified Copilot delivery may produce output")
        return self


class CopilotHookFilePreviewV1(FrozenModel):
    """Raw-free exact preview of Temper's dedicated Copilot user hook file."""

    preview_version: Literal["1.0.0"] = "1.0.0"
    preview_token: Identifier
    operation: Literal["install", "uninstall"]
    before_digest: Sha256Digest
    after_digest: Sha256Digest
    before_existed: bool
    after_existed: bool
    helper_digest: Sha256Digest
    events: tuple[Literal["userPromptTransformed"], ...] = ("userPromptTransformed",)
    redacted_diff: NonEmptyStr
    expires_at: UtcDateTime
    dedicated_temper_file: Literal[True] = True
    provider_authentication_changed: Literal[False] = False
    provider_call_required: Literal[False] = False
    raw_paths_exposed: Literal[False] = False


class CopilotHookFileChangeReceiptV1(FrozenModel):
    """Signed receipt for the dedicated Copilot hook-file transition."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    preview_token: Identifier
    operation: Literal["install", "uninstall", "rollback"]
    before_digest: Sha256Digest
    after_digest: Sha256Digest
    before_existed: bool
    after_existed: bool
    helper_digest: Sha256Digest
    hook_file_locator_digest: Sha256Digest
    backup_digest: Sha256Digest
    applied_at: UtcDateTime
    rollback_available_until: UtcDateTime
    rollback_of_receipt_id: Identifier | None = None
    signature: SignatureEnvelope
    raw_paths_exposed: Literal[False] = False

    @model_validator(mode="after")
    def rollback_and_signature_are_exact(self) -> Self:
        if (self.operation == "rollback") != (self.rollback_of_receipt_id is not None):
            raise ValueError("Copilot hook rollback lineage is inconsistent")
        if self.rollback_available_until <= self.applied_at:
            raise ValueError("Copilot hook rollback window is invalid")
        if (
            self.signature.purpose != "copilot_hook_file_change"
            or self.signature.signed_at != self.applied_at
        ):
            raise ValueError("Copilot hook-file signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})


class CopilotConnectionProjectV1(FrozenModel):
    project_id: Identifier
    project_registration_digest: Sha256Digest


class CopilotConnectionPreviewV1(FrozenModel):
    """Explicit local delivery-only connection decision."""

    preview_version: Literal["1.0.0"] = "1.0.0"
    operation: Literal["connect", "disconnect"]
    hook_file: CopilotHookFilePreviewV1
    project_ids: tuple[Identifier, ...]
    current_connection_digest: Sha256Digest | None = None
    consent_expires_at: UtcDateTime
    learning_enabled: Literal[False] = False
    delivery_enabled: bool
    provider_call_required: Literal[False] = False
    provider_authentication_changed: Literal[False] = False
    raw_paths_exposed: Literal[False] = False


class CopilotConnectionReceiptV1(FrozenModel):
    """Signed connection state binding projects, consent, helper, and hook file."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    operation: Literal["connect", "disconnect"]
    subject_id: Identifier
    projects: tuple[CopilotConnectionProjectV1, ...]
    consent: ConsentReceipt
    hook_file_receipt: CopilotHookFileChangeReceiptV1
    previous_connection_digest: Sha256Digest | None = None
    learning_enabled: Literal[False] = False
    delivery_enabled: bool
    occurred_at: UtcDateTime
    expires_at: UtcDateTime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def state_and_signature_are_exact(self) -> Self:
        if self.delivery_enabled != (self.operation == "connect"):
            raise ValueError("Copilot delivery state does not match operation")
        if self.expires_at != self.consent.expires_at:
            raise ValueError("Copilot connection expiry changed from consent")
        if (
            self.signature.purpose != "copilot_connection_change"
            or self.signature.signed_at != self.occurred_at
        ):
            raise ValueError("Copilot connection signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CopilotConnectionStatusV1(FrozenModel):
    status_version: Literal["1.0.0"] = "1.0.0"
    state: Literal["available", "connected", "attention"]
    project_count: int = Field(ge=0)
    learning_enabled: Literal[False] = False
    delivery_enabled: bool
    expires_at: UtcDateTime | None = None
    current_connection_digest: Sha256Digest | None = None
    status_summary: NonEmptyStr
