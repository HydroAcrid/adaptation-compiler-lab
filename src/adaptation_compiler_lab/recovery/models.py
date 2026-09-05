"""Versioned encrypted same-owner recovery contracts."""

from __future__ import annotations

import base64
import hashlib
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.governance import SignatureEnvelope, SignerIdentity
from adaptation_compiler_lab.serialization import canonical_digest

MAX_RECOVERY_PLAINTEXT_BYTES = 128 * 1024 * 1024
MAX_RECOVERY_FILE_BYTES = 64 * 1024 * 1024


def _decode(value: str, label: str) -> bytes:
    try:
        payload = base64.b64decode(value, validate=True)
    except ValueError as error:
        raise ValueError(f"recovery {label} is not canonical base64") from error
    if base64.b64encode(payload).decode("ascii") != value:
        raise ValueError(f"recovery {label} is not canonical base64")
    return payload


class RecoveryProjectV1(FrozenModel):
    """Path-free identity for one project contained in the encrypted bundle."""

    project_id: Identifier
    display_name: NonEmptyStr
    source_project_digest: Sha256Digest
    capture_after_epoch_seconds: int | None = Field(default=None, ge=0)


class RecoveryFileV1(FrozenModel):
    """One bounded product-owned state file embedded inside the encrypted bundle."""

    logical_path: NonEmptyStr
    content_digest: Sha256Digest
    byte_length: int = Field(ge=0, le=MAX_RECOVERY_FILE_BYTES)
    payload_base64: str

    @field_validator("logical_path")
    @classmethod
    def path_is_safe_and_relative(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if (
            value != normalized
            or value.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("recovery file path is unsafe")
        return value

    @model_validator(mode="after")
    def payload_matches_manifest(self) -> Self:
        payload = _decode(self.payload_base64, "file payload")
        if len(payload) != self.byte_length:
            raise ValueError("recovery file length changed")
        digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        if digest != self.content_digest:
            raise ValueError("recovery file digest changed")
        return self

    @property
    def payload(self) -> bytes:
        return _decode(self.payload_base64, "file payload")


class TemperRecoveryBundleV1(FrozenModel):
    """Signed plaintext package encrypted as one offline same-owner backup."""

    recovery_version: Literal["1.0.0"] = "1.0.0"
    bundle_id: Identifier
    subject_id: Identifier
    source_platform: Literal["windows", "macos"]
    source_config_digest: Sha256Digest
    signer_identity: SignerIdentity
    projects: Annotated[tuple[RecoveryProjectV1, ...], Field(min_length=1)]
    config_payload_base64: str
    runtime_secrets_base64: str
    files: Annotated[tuple[RecoveryFileV1, ...], Field(min_length=1)]
    created_at: UtcDateTime
    includes_encrypted_raw_payloads: bool
    includes_native_agent_credentials: Literal[False] = False
    includes_provider_api_keys: Literal[False] = False
    signature: SignatureEnvelope

    @field_validator("projects")
    @classmethod
    def projects_are_sorted_unique(
        cls, value: tuple[RecoveryProjectV1, ...]
    ) -> tuple[RecoveryProjectV1, ...]:
        ids = tuple(item.project_id for item in value)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("recovery projects must be sorted and unique")
        return value

    @field_validator("files")
    @classmethod
    def files_are_sorted_unique(
        cls, value: tuple[RecoveryFileV1, ...]
    ) -> tuple[RecoveryFileV1, ...]:
        paths = tuple(item.logical_path for item in value)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("recovery files must be sorted and unique")
        if sum(item.byte_length for item in value) > MAX_RECOVERY_PLAINTEXT_BYTES:
            raise ValueError("recovery files exceed the bundle limit")
        return value

    @field_validator("config_payload_base64", "runtime_secrets_base64")
    @classmethod
    def embedded_values_are_canonical_base64(cls, value: str) -> str:
        _decode(value, "embedded value")
        return value

    @model_validator(mode="after")
    def identity_and_signature_are_exact(self) -> Self:
        if self.signer_identity.subject_id != self.subject_id:
            raise ValueError("recovery bundle crossed its signer subject")
        if (
            self.signature.purpose != "temper_recovery_bundle"
            or self.signature.signer_identity_id != self.signer_identity.identity_id
            or self.signature.key_fingerprint != self.signer_identity.key_fingerprint
            or self.signature.signed_at != self.created_at
        ):
            raise ValueError("recovery bundle signature metadata changed")
        return self

    @property
    def config_payload(self) -> bytes:
        return _decode(self.config_payload_base64, "configuration")

    @property
    def runtime_secrets_payload(self) -> bytes:
        return _decode(self.runtime_secrets_base64, "runtime secrets")

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class EncryptedTemperRecoveryBundleV1(FrozenModel):
    """Memory-hard passphrase envelope with no plaintext owner or project metadata."""

    envelope_version: Literal["1.0.0"] = "1.0.0"
    cipher: Literal["AES-256-GCM"] = "AES-256-GCM"
    kdf: Literal["scrypt-n32768-r8-p1"] = "scrypt-n32768-r8-p1"
    salt_base64: NonEmptyStr
    nonce_base64: NonEmptyStr
    ciphertext_base64: NonEmptyStr
    plaintext_digest: Sha256Digest

    @field_validator("salt_base64")
    @classmethod
    def salt_is_exact(cls, value: str) -> str:
        if len(_decode(value, "salt")) != 16:
            raise ValueError("recovery salt length changed")
        return value

    @field_validator("nonce_base64")
    @classmethod
    def nonce_is_exact(cls, value: str) -> str:
        if len(_decode(value, "nonce")) != 12:
            raise ValueError("recovery nonce length changed")
        return value

    @field_validator("ciphertext_base64")
    @classmethod
    def ciphertext_is_bounded(cls, value: str) -> str:
        size = len(_decode(value, "ciphertext"))
        if size < 17 or size > MAX_RECOVERY_PLAINTEXT_BYTES * 2:
            raise ValueError("recovery ciphertext size is invalid")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RecoveryPreviewV1(FrozenModel):
    """Raw-free owner review after local passphrase decryption."""

    preview_version: Literal["1.0.0"] = "1.0.0"
    preview_token: Identifier
    bundle_id: Identifier
    bundle_digest: Sha256Digest
    signer_fingerprint: Sha256Digest
    created_at: UtcDateTime
    source_platform: Literal["windows", "macos"]
    projects: tuple[RecoveryProjectV1, ...]
    governed_file_count: int = Field(ge=1)
    encrypted_raw_file_count: int = Field(ge=0)
    total_encrypted_bytes: int = Field(ge=0)
    expires_at: UtcDateTime
    requires_project_rebinding: Literal[True] = True
    overwrites_existing_installation: Literal[False] = False
    raw_paths_exposed: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False


class RecoveryProjectSelectionV1(FrozenModel):
    """Opaque renderer-safe validation of one new local project root."""

    selection_token: Identifier
    preview_token: Identifier
    project_id: Identifier
    display_name: NonEmptyStr
    expires_at: UtcDateTime
    path_exposed: Literal[False] = False


class RecoveryRestoreReceiptV1(FrozenModel):
    """Signed proof that one encrypted bundle became one new local installation."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    subject_id: Identifier
    bundle_id: Identifier
    bundle_digest: Sha256Digest
    source_config_digest: Sha256Digest
    restored_config_digest: Sha256Digest
    restored_file_manifest_digest: Sha256Digest
    project_binding_digests: tuple[Sha256Digest, ...]
    target_platform: Literal["windows", "macos"]
    restored_at: UtcDateTime
    signer_identity_id: Identifier
    signer_fingerprint: Sha256Digest
    signature: SignatureEnvelope

    @field_validator("project_binding_digests")
    @classmethod
    def bindings_are_sorted_unique(
        cls, value: tuple[Sha256Digest, ...]
    ) -> tuple[Sha256Digest, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("recovery project bindings must be sorted and unique")
        return value

    @model_validator(mode="after")
    def signature_metadata_is_exact(self) -> Self:
        if (
            self.signature.purpose != "temper_recovery_restore"
            or self.signature.signed_at != self.restored_at
            or self.signature.signer_identity_id != self.signer_identity_id
            or self.signature.key_fingerprint != self.signer_fingerprint
        ):
            raise ValueError("recovery restore signature metadata changed")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RecoveryRestoreResultV1(FrozenModel):
    """Renderer-safe result of an exact restore mutation."""

    result_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    restoration_digest: Sha256Digest
    project_count: int = Field(ge=1)
    configured: Literal[True] = True
    restart_required: Literal[True] = True
    raw_paths_exposed: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False
