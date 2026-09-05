"""Build, authenticate, encrypt, and read offline Temper recovery bundles."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from adaptation_compiler_lab.automatic_runtime.credentials import RuntimeSecrets
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import CodexDogfoodLocalConfig
from adaptation_compiler_lab.governance import SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
    verify_signed_governance,
)
from adaptation_compiler_lab.recovery.models import (
    MAX_RECOVERY_PLAINTEXT_BYTES,
    EncryptedTemperRecoveryBundleV1,
    RecoveryFileV1,
    RecoveryPreviewV1,
    RecoveryProjectV1,
    TemperRecoveryBundleV1,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_AAD = b"temper-recovery-bundle/v1"
_MINIMUM_PASSPHRASE_LENGTH = 14


class TemperRecoveryError(ValueError):
    """Recovery material is missing, stale, invalid, or unsafe."""


def build_recovery_bundle(
    config: CodexDogfoodLocalConfig,
    secrets: RuntimeSecrets,
    files: tuple[RecoveryFileV1, ...],
    *,
    signer: GovernanceSigner,
    source_platform: Literal["windows", "macos"],
    bundle_id: str,
    created_at: datetime,
) -> TemperRecoveryBundleV1:
    """Create one signed complete same-owner package before passphrase encryption."""

    if source_platform not in {"windows", "macos"}:
        raise TemperRecoveryError("recovery export requires a supported native platform")
    if not secrets.managed:
        raise TemperRecoveryError("recovery export requires managed local runtime keys")
    if SignerRole.CUSTODY not in config.signer_identity.roles:
        raise TemperRecoveryError("recovery export requires a custody-authorized identity")
    if (
        signer.subject_id != config.subject_id
        or signer.identity_id != config.signer_identity.identity_id
        or signer.fingerprint != config.signer_identity.key_fingerprint
    ):
        raise TemperRecoveryError("recovery signer does not own this runtime")
    private_key = secrets.private_key(workspace_root=config.repository_root)
    if (
        f"sha256:{hashlib.sha256(private_key.public_key().public_bytes_raw()).hexdigest()}"
        != config.signer_identity.key_fingerprint
    ):
        raise TemperRecoveryError("managed recovery key does not match the runtime identity")
    if sum(item.logical_path == "runtime.sqlite3" for item in files) != 1:
        raise TemperRecoveryError("recovery bundle requires the governed SQLite ledger")
    projects = tuple(
        RecoveryProjectV1(
            project_id=project.project_id,
            display_name=project.root.name or project.project_id,
            source_project_digest=canonical_digest(project),
            capture_after_epoch_seconds=project.capture_after_epoch_seconds,
        )
        for project in config.projects
    )
    placeholder = signer.envelope({}, purpose="temper_recovery_bundle", signed_at=created_at)
    draft = TemperRecoveryBundleV1(
        bundle_id=bundle_id,
        subject_id=config.subject_id,
        source_platform=source_platform,
        source_config_digest=config.credential_binding_digest,
        signer_identity=config.signer_identity,
        projects=projects,
        config_payload_base64=base64.b64encode(canonical_json(config).encode("utf-8")).decode(
            "ascii"
        ),
        runtime_secrets_base64=base64.b64encode(secrets.to_bytes()).decode("ascii"),
        files=files,
        created_at=created_at,
        includes_encrypted_raw_payloads=any(item.logical_path.startswith("raw/") for item in files),
        signature=placeholder,
    )
    bundle = draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose="temper_recovery_bundle",
                signed_at=created_at,
            )
        }
    )
    verify_recovery_bundle(bundle)
    return bundle


def verify_recovery_bundle(bundle: TemperRecoveryBundleV1) -> None:
    """Verify identity, owner key, config, project manifest, files, and package signature."""

    try:
        verify_signed_governance(bundle.signer_identity)
        verify_detached_envelope(
            bundle.unsigned_payload,
            bundle.signature,
            public_key_base64=bundle.signer_identity.public_key_base64,
            expected_purpose="temper_recovery_bundle",
        )
        config = CodexDogfoodLocalConfig.model_validate_json(bundle.config_payload, strict=True)
        secrets = RuntimeSecrets.from_bytes(bundle.runtime_secrets_payload)
    except ValueError as error:
        raise TemperRecoveryError("recovery bundle authentication failed") from error
    if not secrets.managed:
        raise TemperRecoveryError("recovery bundle contains non-portable external key references")
    if SignerRole.CUSTODY not in bundle.signer_identity.roles:
        raise TemperRecoveryError("recovery bundle signer lacks custody authority")
    if bundle.created_at < bundle.signer_identity.created_at or (
        bundle.signer_identity.expires_at is not None
        and bundle.created_at > bundle.signer_identity.expires_at
    ):
        raise TemperRecoveryError("recovery bundle was not issued by a valid identity")
    private_key = secrets.private_key(workspace_root=config.repository_root)
    fingerprint = (
        f"sha256:{hashlib.sha256(private_key.public_key().public_bytes_raw()).hexdigest()}"
    )
    expected_projects = tuple(
        RecoveryProjectV1(
            project_id=project.project_id,
            display_name=project.root.name or project.project_id,
            source_project_digest=canonical_digest(project),
            capture_after_epoch_seconds=project.capture_after_epoch_seconds,
        )
        for project in config.projects
    )
    if (
        config.subject_id != bundle.subject_id
        or config.signer_identity != bundle.signer_identity
        or config.credential_binding_digest != bundle.source_config_digest
        or fingerprint != bundle.signer_identity.key_fingerprint
        or expected_projects != bundle.projects
        or bundle.includes_encrypted_raw_payloads
        != any(item.logical_path.startswith("raw/") for item in bundle.files)
    ):
        raise TemperRecoveryError("recovery bundle identity or manifest changed")


def encrypt_recovery_bundle(
    bundle: TemperRecoveryBundleV1,
    *,
    passphrase: str,
    salt: bytes | None = None,
    nonce: bytes | None = None,
) -> EncryptedTemperRecoveryBundleV1:
    verify_recovery_bundle(bundle)
    if len(passphrase) < _MINIMUM_PASSPHRASE_LENGTH:
        raise TemperRecoveryError("recovery passphrase must contain at least 14 characters")
    actual_salt = os.urandom(16) if salt is None else salt
    actual_nonce = os.urandom(12) if nonce is None else nonce
    if len(actual_salt) != 16 or len(actual_nonce) != 12:
        raise TemperRecoveryError("recovery salt or nonce length is invalid")
    plaintext = canonical_json(bundle).encode("utf-8")
    if len(plaintext) > MAX_RECOVERY_PLAINTEXT_BYTES:
        raise TemperRecoveryError("recovery bundle exceeds the offline size limit")
    ciphertext = AESGCM(_derive_key(passphrase, actual_salt)).encrypt(actual_nonce, plaintext, _AAD)
    return EncryptedTemperRecoveryBundleV1(
        salt_base64=base64.b64encode(actual_salt).decode("ascii"),
        nonce_base64=base64.b64encode(actual_nonce).decode("ascii"),
        ciphertext_base64=base64.b64encode(ciphertext).decode("ascii"),
        plaintext_digest=f"sha256:{hashlib.sha256(plaintext).hexdigest()}",
    )


def decrypt_recovery_bundle(
    envelope: EncryptedTemperRecoveryBundleV1, *, passphrase: str
) -> TemperRecoveryBundleV1:
    if len(passphrase) < _MINIMUM_PASSPHRASE_LENGTH:
        raise TemperRecoveryError("recovery passphrase is invalid")
    salt = base64.b64decode(envelope.salt_base64, validate=True)
    nonce = base64.b64decode(envelope.nonce_base64, validate=True)
    ciphertext = base64.b64decode(envelope.ciphertext_base64, validate=True)
    try:
        plaintext = AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, ciphertext, _AAD)
    except (InvalidTag, ValueError) as error:
        raise TemperRecoveryError("recovery bundle could not be decrypted") from error
    if f"sha256:{hashlib.sha256(plaintext).hexdigest()}" != envelope.plaintext_digest:
        raise TemperRecoveryError("recovery plaintext digest changed")
    try:
        bundle = TemperRecoveryBundleV1.model_validate_json(plaintext, strict=True)
    except ValueError as error:
        raise TemperRecoveryError("recovery bundle is invalid") from error
    verify_recovery_bundle(bundle)
    return bundle


def recovery_preview(
    bundle: TemperRecoveryBundleV1,
    *,
    preview_token: str,
    expires_at: datetime,
) -> RecoveryPreviewV1:
    verify_recovery_bundle(bundle)
    return RecoveryPreviewV1(
        preview_token=preview_token,
        bundle_id=bundle.bundle_id,
        bundle_digest=bundle.content_digest,
        signer_fingerprint=bundle.signer_identity.key_fingerprint,
        created_at=bundle.created_at,
        source_platform=bundle.source_platform,
        projects=bundle.projects,
        governed_file_count=len(bundle.files),
        encrypted_raw_file_count=sum(item.logical_path.startswith("raw/") for item in bundle.files),
        total_encrypted_bytes=sum(item.byte_length for item in bundle.files),
        expires_at=expires_at,
    )


def read_recovery_envelope(source: Path) -> EncryptedTemperRecoveryBundleV1:
    resolved = source.expanduser().resolve()
    if resolved.suffix != ".temper-recovery":
        raise TemperRecoveryError("recovery file must use the .temper-recovery extension")
    try:
        if not resolved.is_file() or resolved.stat().st_size > MAX_RECOVERY_PLAINTEXT_BYTES * 3:
            raise TemperRecoveryError("recovery file size is invalid")
        value = json.loads(resolved.read_text(encoding="utf-8"))
        return EncryptedTemperRecoveryBundleV1.model_validate(value, strict=True)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        if isinstance(error, TemperRecoveryError):
            raise
        raise TemperRecoveryError("recovery file is invalid") from error


def write_recovery_envelope(envelope: EncryptedTemperRecoveryBundleV1, destination: Path) -> Path:
    resolved = destination.expanduser().resolve()
    if resolved.suffix != ".temper-recovery":
        raise TemperRecoveryError("recovery file must use the .temper-recovery extension")
    if resolved.exists():
        raise FileExistsError("recovery destination already exists")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical_json(envelope) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        resolved.unlink(missing_ok=True)
        raise
    return resolved


def rotate_recovery_envelope(
    envelope: EncryptedTemperRecoveryBundleV1,
    *,
    current_passphrase: str,
    new_passphrase: str,
) -> EncryptedTemperRecoveryBundleV1:
    """Re-encrypt the exact signed bundle without changing its identity or history."""

    bundle = decrypt_recovery_bundle(envelope, passphrase=current_passphrase)
    return encrypt_recovery_bundle(bundle, passphrase=new_passphrase)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    try:
        return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))
    except (MemoryError, ValueError) as error:
        raise TemperRecoveryError("recovery key derivation failed") from error
