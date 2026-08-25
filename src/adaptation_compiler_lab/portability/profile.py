"""Encrypted offline profiles that preserve provenance without transferring authority."""

from __future__ import annotations

import base64
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    ArtifactKind,
    BehavioralContract,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
)
from adaptation_compiler_lab.domain.values import Scope, strings_are_sorted_unique
from adaptation_compiler_lab.governance import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.runtime import ArtifactGovernanceBinding
from adaptation_compiler_lab.sanitization import ExportSafetyError, assert_export_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection

PROFILE_PURPOSE = "portable_profile_package"
IMPORT_PURPOSE = "portable_profile_import"
MAX_PROFILE_BYTES = 4 * 1024 * 1024
_AAD = b"temper-portable-profile/v1"
_PRIVATE_PATH_PATTERNS = (
    re.compile(r"(?i)(?:[a-z]:[\\/]+users[\\/]+[^\\/\s]+[\\/])"),
    re.compile(r"/(?:home|users)/[^/\s]+/", re.IGNORECASE),
    re.compile(r"file://", re.IGNORECASE),
)


class ProfilePortabilityError(ValueError):
    """Raised when a profile cannot safely cross the offline portability boundary."""


class PortableProfileScope(FrozenModel):
    """Path-free applicability; recipient-local identifiers require explicit mapping."""

    project_ids: tuple[Identifier, ...] = ()
    task_classes: tuple[Identifier, ...] = ()
    target_families: tuple[Identifier, ...] = ()
    environment_ids: tuple[Identifier, ...] = ()
    activation_conditions: tuple[NonEmptyStr, ...] = ()
    exclusions: tuple[NonEmptyStr, ...] = ()
    scope_mapping_required: bool = False

    @field_validator(
        "project_ids",
        "task_classes",
        "target_families",
        "environment_ids",
        "activation_conditions",
        "exclusions",
    )
    @classmethod
    def values_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("portable scope values must be sorted and unique")
        return value

    @classmethod
    def from_governed_scope(cls, scope: Scope) -> Self:
        local_scope = bool(scope.workspace_ids or scope.repository_ids or scope.project_ids)
        return cls(
            project_ids=scope.project_ids,
            task_classes=scope.task_classes,
            target_families=scope.target_families,
            environment_ids=scope.environment_ids,
            activation_conditions=scope.activation_conditions,
            exclusions=scope.exclusions,
            scope_mapping_required=local_scope,
        )


class PortableInstruction(FrozenModel):
    """Raw-free behavioral specification plus digested source lineage."""

    item_id: Identifier
    artifact_kind: ArtifactKind
    behavioral_contract: BehavioralContract
    scope: PortableProfileScope
    source_artifact_digest: Sha256Digest
    source_lineage_digest: Sha256Digest
    supporting_evidence_count: int = Field(ge=1)
    review_required_on_import: Literal[True] = True
    grants_source_authority: Literal[False] = False


class PortableProfilePackage(FrozenModel):
    """Signed plaintext held only inside the encrypted offline envelope."""

    package_version: Literal["1.0.0"] = "1.0.0"
    package_id: Identifier
    display_name: NonEmptyStr
    source_release_digest: Sha256Digest
    source_identity_id: Identifier
    source_public_key_base64: NonEmptyStr
    source_key_fingerprint: Sha256Digest
    items: Annotated[tuple[PortableInstruction, ...], Field(min_length=1)]
    created_at: datetime
    contains_raw_evidence: Literal[False] = False
    contains_private_paths: Literal[False] = False
    auto_activates_on_import: Literal[False] = False
    signature: SignatureEnvelope

    @field_validator("items")
    @classmethod
    def items_are_sorted_unique(
        cls, value: tuple[PortableInstruction, ...]
    ) -> tuple[PortableInstruction, ...]:
        ids = tuple(item.item_id for item in value)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("portable profile items must be sorted and unique")
        return value

    @model_validator(mode="after")
    def signature_metadata_matches_source(self) -> Self:
        if (
            self.signature.purpose != PROFILE_PURPOSE
            or self.signature.signer_identity_id != self.source_identity_id
            or self.signature.key_fingerprint != self.source_key_fingerprint
            or self.signature.signed_at != self.created_at
        ):
            raise ValueError("portable profile signature metadata is inconsistent")
        try:
            public_key = base64.b64decode(self.source_public_key_base64, validate=True)
        except ValueError as error:
            raise ValueError("portable profile public key is not canonical base64") from error
        if len(public_key) != 32:
            raise ValueError("portable profile public key must contain exactly 32 bytes")
        fingerprint = f"sha256:{hashlib.sha256(public_key).hexdigest()}"
        if fingerprint != self.source_key_fingerprint:
            raise ValueError("portable profile public key fingerprint changed")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class EncryptedProfileEnvelope(FrozenModel):
    """Passphrase-encrypted file format; no behavior text appears outside ciphertext."""

    envelope_version: Literal["1.0.0"] = "1.0.0"
    cipher: Literal["AES-256-GCM"] = "AES-256-GCM"
    kdf: Literal["scrypt-n32768-r8-p1"] = "scrypt-n32768-r8-p1"
    salt_base64: NonEmptyStr
    nonce_base64: NonEmptyStr
    ciphertext_base64: NonEmptyStr
    plaintext_digest: Sha256Digest
    contains_raw_evidence: Literal[False] = False

    @field_validator("salt_base64")
    @classmethod
    def salt_is_valid(cls, value: str) -> str:
        _decode_exact(value, 16, "salt")
        return value

    @field_validator("nonce_base64")
    @classmethod
    def nonce_is_valid(cls, value: str) -> str:
        _decode_exact(value, 12, "nonce")
        return value

    @field_validator("ciphertext_base64")
    @classmethod
    def ciphertext_is_bounded(cls, value: str) -> str:
        payload = _decode(value, "ciphertext")
        if len(payload) < 17 or len(payload) > MAX_PROFILE_BYTES:
            raise ValueError("portable profile ciphertext size is invalid")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PortableProfileItemPreview(FrozenModel):
    item_id: Identifier
    kind: ArtifactKind
    summary: NonEmptyStr
    required_behavior_count: int = Field(ge=1)
    scope_mapping_required: bool


class PortableProfilePreview(FrozenModel):
    """Exact owner-facing review shown before any import is persisted."""

    package_id: Identifier
    display_name: NonEmptyStr
    package_digest: Sha256Digest
    source_key_fingerprint: Sha256Digest
    source_signature_verified: Literal[True] = True
    item_count: int = Field(ge=1)
    items: tuple[PortableProfileItemPreview, ...]
    scope_mapping_count: int = Field(ge=0)
    warnings: tuple[NonEmptyStr, ...]
    activates_nothing: Literal[True] = True
    raw_payloads_exposed: Literal[False] = False


class ProfileImportReceipt(FrozenModel):
    """Locally signed staging receipt; import never means approval or activation."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    package_id: Identifier
    package_digest: Sha256Digest
    local_subject_id: Identifier
    imported_item_ids: tuple[Identifier, ...]
    status: Literal["staged_for_review"] = "staged_for_review"
    activates_artifacts: Literal[False] = False
    imported_at: datetime
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def receipt_is_review_only(self) -> Self:
        if self.signature.purpose != IMPORT_PURPOSE or self.signature.signed_at != self.imported_at:
            raise ValueError("portable import receipt signature metadata is inconsistent")
        if self.imported_item_ids != tuple(sorted(set(self.imported_item_ids))):
            raise ValueError("portable import item IDs must be sorted and unique")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})


def build_portable_profile(
    artifacts: tuple[ArtifactRenderProjection, ...],
    bindings: tuple[ArtifactGovernanceBinding, ...],
    *,
    signer: GovernanceSigner,
    source_release_digest: Sha256Digest,
    package_id: str,
    display_name: str,
    created_at: datetime,
) -> PortableProfilePackage:
    """Build and sign an exact raw-free profile from one governed active release."""

    if len(artifacts) != len(bindings) or not artifacts:
        raise ProfilePortabilityError("portable profile requires exact active artifact bindings")
    items: list[PortableInstruction] = []
    for index, (artifact, binding) in enumerate(zip(artifacts, bindings, strict=True), start=1):
        if artifact.artifact_ref != binding.artifact_ref or artifact.scope != binding.scope:
            raise ProfilePortabilityError("portable profile artifact lineage changed")
        item = PortableInstruction(
            item_id=f"profile-item-{index:04d}",
            artifact_kind=artifact.artifact_type,
            behavioral_contract=artifact.behavioral_contract,
            scope=PortableProfileScope.from_governed_scope(artifact.scope),
            source_artifact_digest=canonical_digest(artifact),
            source_lineage_digest=binding.content_digest,
            supporting_evidence_count=len(binding.evidence_links.supporting),
        )
        _assert_instruction_safe(item)
        items.append(item)
    public_key_base64 = base64.b64encode(signer.private_key.public_key().public_bytes_raw()).decode(
        "ascii"
    )
    placeholder = signer.envelope({}, purpose=PROFILE_PURPOSE, signed_at=created_at)
    draft = PortableProfilePackage(
        package_id=package_id,
        display_name=display_name,
        source_release_digest=source_release_digest,
        source_identity_id=signer.identity_id,
        source_public_key_base64=public_key_base64,
        source_key_fingerprint=signer.fingerprint,
        items=tuple(items),
        created_at=created_at,
        signature=placeholder,
    )
    signature = signer.envelope(
        draft.unsigned_payload, purpose=PROFILE_PURPOSE, signed_at=created_at
    )
    package = draft.model_copy(update={"signature": signature})
    verify_portable_profile(package)
    return package


def verify_portable_profile(package: PortableProfilePackage) -> None:
    """Authenticate package bytes while explicitly granting no behavioral authority."""

    verify_detached_envelope(
        package.unsigned_payload,
        package.signature,
        public_key_base64=package.source_public_key_base64,
        expected_purpose=PROFILE_PURPOSE,
    )
    for item in package.items:
        _assert_instruction_safe(item)


def encrypt_portable_profile(
    package: PortableProfilePackage,
    *,
    passphrase: str,
    salt: bytes | None = None,
    nonce: bytes | None = None,
) -> EncryptedProfileEnvelope:
    """Encrypt a verified package; a passphrase is never retained in the envelope."""

    verify_portable_profile(package)
    if len(passphrase) < 12:
        raise ProfilePortabilityError(
            "portable profile passphrase must contain at least 12 characters"
        )
    actual_salt = os.urandom(16) if salt is None else salt
    actual_nonce = os.urandom(12) if nonce is None else nonce
    if len(actual_salt) != 16 or len(actual_nonce) != 12:
        raise ProfilePortabilityError("portable profile salt or nonce length is invalid")
    plaintext = canonical_json(package).encode("utf-8")
    if len(plaintext) > MAX_PROFILE_BYTES - 16:
        raise ProfilePortabilityError("portable profile exceeds the offline file limit")
    ciphertext = AESGCM(_derive_key(passphrase, actual_salt)).encrypt(actual_nonce, plaintext, _AAD)
    return EncryptedProfileEnvelope(
        salt_base64=base64.b64encode(actual_salt).decode("ascii"),
        nonce_base64=base64.b64encode(actual_nonce).decode("ascii"),
        ciphertext_base64=base64.b64encode(ciphertext).decode("ascii"),
        plaintext_digest=f"sha256:{hashlib.sha256(plaintext).hexdigest()}",
    )


def decrypt_portable_profile(
    envelope: EncryptedProfileEnvelope, *, passphrase: str
) -> PortableProfilePackage:
    """Decrypt, parse, digest-check, and authenticate a portable profile."""

    if len(passphrase) < 12:
        raise ProfilePortabilityError("portable profile passphrase is invalid")
    salt = _decode_exact(envelope.salt_base64, 16, "salt")
    nonce = _decode_exact(envelope.nonce_base64, 12, "nonce")
    ciphertext = _decode(envelope.ciphertext_base64, "ciphertext")
    try:
        plaintext = AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, ciphertext, _AAD)
    except (InvalidTag, ValueError) as error:
        raise ProfilePortabilityError("portable profile could not be decrypted") from error
    digest = f"sha256:{hashlib.sha256(plaintext).hexdigest()}"
    if digest != envelope.plaintext_digest:
        raise ProfilePortabilityError("portable profile plaintext digest changed")
    try:
        package = PortableProfilePackage.model_validate_json(plaintext, strict=True)
    except ValueError as error:
        raise ProfilePortabilityError("portable profile package is invalid") from error
    verify_portable_profile(package)
    return package


def preview_portable_profile(
    envelope: EncryptedProfileEnvelope, *, passphrase: str
) -> PortableProfilePreview:
    package = decrypt_portable_profile(envelope, passphrase=passphrase)
    mapping_count = sum(item.scope.scope_mapping_required for item in package.items)
    warnings = [
        "Imported guidance remains inactive until you review and approve it.",
        "The source signature proves origin; it does not become your instruction authority.",
    ]
    if mapping_count:
        warnings.append("Project-specific guidance needs a local scope before approval.")
    return PortableProfilePreview(
        package_id=package.package_id,
        display_name=package.display_name,
        package_digest=package.content_digest,
        source_key_fingerprint=package.source_key_fingerprint,
        item_count=len(package.items),
        items=tuple(
            PortableProfileItemPreview(
                item_id=item.item_id,
                kind=item.artifact_kind,
                summary=item.behavioral_contract.intent,
                required_behavior_count=len(item.behavioral_contract.required_behaviors),
                scope_mapping_required=item.scope.scope_mapping_required,
            )
            for item in package.items
        ),
        scope_mapping_count=mapping_count,
        warnings=tuple(warnings),
    )


def write_portable_profile(envelope: EncryptedProfileEnvelope, destination: Path) -> Path:
    """Write one new offline profile without overwriting an existing file."""

    resolved = destination.expanduser().resolve()
    if resolved.suffix != ".temper-profile":
        raise ProfilePortabilityError("portable profile must use the .temper-profile extension")
    if resolved.exists():
        raise FileExistsError("portable profile destination already exists")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical_json(envelope) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        resolved.unlink(missing_ok=True)
        raise
    return resolved


class ProfileImportStore:
    """Append-only local staging area; accepted packages remain non-active candidates."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def stage(
        self,
        envelope: EncryptedProfileEnvelope,
        *,
        passphrase: str,
        expected_package_digest: Sha256Digest,
        signer: GovernanceSigner,
        imported_at: datetime,
        idempotency_key: str,
    ) -> ProfileImportReceipt:
        package = decrypt_portable_profile(envelope, passphrase=passphrase)
        if package.content_digest != expected_package_digest:
            raise ProfilePortabilityError("portable profile changed after preview")
        receipt_id = f"profile-import-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]}"
        placeholder = signer.envelope({}, purpose=IMPORT_PURPOSE, signed_at=imported_at)
        draft = ProfileImportReceipt(
            receipt_id=receipt_id,
            package_id=package.package_id,
            package_digest=package.content_digest,
            local_subject_id=signer.subject_id,
            imported_item_ids=tuple(sorted(item.item_id for item in package.items)),
            imported_at=imported_at,
            signature=placeholder,
        )
        signature = signer.envelope(
            draft.unsigned_payload, purpose=IMPORT_PURPOSE, signed_at=imported_at
        )
        receipt = draft.model_copy(update={"signature": signature})
        self._write_once(receipt_id, envelope, receipt)
        return receipt

    def _write_once(
        self,
        receipt_id: str,
        envelope: EncryptedProfileEnvelope,
        receipt: ProfileImportReceipt,
    ) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._root.chmod(0o700)
        path = self._root / f"{receipt_id}.json"
        content = (
            canonical_json(
                {
                    "envelope": envelope.model_dump(mode="json"),
                    "receipt": receipt.model_dump(mode="json"),
                }
            )
            + "\n"
        )
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise ProfilePortabilityError("portable profile idempotency key was reused")
            return
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _decode(value: str, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except ValueError as error:
        raise ValueError(f"portable profile {label} is not canonical base64") from error
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"portable profile {label} is not canonical base64")
    return decoded


def _decode_exact(value: str, length: int, label: str) -> bytes:
    decoded = _decode(value, label)
    if len(decoded) != length:
        raise ValueError(f"portable profile {label} length is invalid")
    return decoded


def _assert_instruction_safe(item: PortableInstruction) -> None:
    contract = item.behavioral_contract
    visible_text = "\n".join(
        (
            contract.intent,
            *contract.required_behaviors,
            *contract.non_goals,
            *contract.verification_requirements,
            *item.scope.project_ids,
            *item.scope.task_classes,
            *item.scope.environment_ids,
            *item.scope.activation_conditions,
            *item.scope.exclusions,
        )
    )
    if any(pattern.search(visible_text) for pattern in _PRIVATE_PATH_PATTERNS):
        raise ProfilePortabilityError(
            f"{item.item_id} contains a private path that cannot be exported"
        )
    try:
        assert_export_safe(visible_text, label=item.item_id)
    except ExportSafetyError as error:
        raise ProfilePortabilityError(str(error)) from error
