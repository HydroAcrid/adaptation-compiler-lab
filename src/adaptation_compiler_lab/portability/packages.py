"""Signed, inactive, raw-free sharing formats for behavior and temporary expertise."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    ArtifactKind,
    BehavioralContract,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    SemVer,
    Sha256Digest,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.governance import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.modes import CapabilityMode, ModeClause
from adaptation_compiler_lab.portability.profile import PortableProfileScope
from adaptation_compiler_lab.sanitization import ExportSafetyError, assert_export_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

BEHAVIOR_PACK_PURPOSE = "shareable_behavior_pack"
MODE_PACKAGE_PURPOSE = "capability_mode_package"
OVERLAY_PURPOSE = "personal_mode_overlay"
PACKAGE_IMPORT_PURPOSE = "shareable_package_import"
MAX_SHAREABLE_PACKAGE_BYTES = 2 * 1024 * 1024

_PRIVATE_PATH = re.compile(
    r"(?i)(?:[a-z]:[\\/]+users[\\/]+[^\\/\s]+[\\/]|/(?:home|users)/[^/\s]+/)"
)
_TRANSCRIPT_ROLE = re.compile(r"(?mi)^(?:user|assistant|system|tool)\s*:\s+")
_EXECUTABLE_CONTENT = re.compile(r"(?im)(?:^#!|```(?:bash|sh|zsh|powershell|python|javascript|js))")
_SOURCE_TASK_ID = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)


class ShareablePackageError(ValueError):
    """Raised when external expertise cannot cross the offline trust boundary."""


class ShareablePackageType(StrEnum):
    BEHAVIOR_PACK = "behavior_pack"
    CAPABILITY_MODE = "capability_mode"
    PERSONAL_MODE_OVERLAY = "personal_mode_overlay"


class ShareableBehaviorClauseV1(FrozenModel):
    clause_id: Identifier
    claim_key: Identifier
    artifact_kind: ArtifactKind
    behavioral_contract: BehavioralContract
    requested_scope: PortableProfileScope
    grants_user_authority: Literal[False] = False
    review_required_on_import: Literal[True] = True

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class _SignedOriginPackage(FrozenModel):
    package_id: Identifier
    release_version: SemVer
    display_name: NonEmptyStr
    publisher_name: NonEmptyStr
    publisher_identity_id: Identifier
    publisher_public_key_base64: NonEmptyStr
    publisher_key_fingerprint: Sha256Digest
    source_license: NonEmptyStr
    created_at: datetime
    contains_raw_conversations: Literal[False] = False
    contains_private_paths: Literal[False] = False
    contains_credentials: Literal[False] = False
    contains_executable_content: Literal[False] = False
    contains_hooks_or_dependencies: Literal[False] = False
    contains_source_task_ids: Literal[False] = False
    auto_activates_on_import: Literal[False] = False
    grants_user_authority: Literal[False] = False
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def origin_metadata_is_canonical(self) -> Self:
        try:
            public_key = base64.b64decode(self.publisher_public_key_base64, validate=True)
        except ValueError as error:
            raise ValueError("package publisher key is not canonical base64") from error
        if len(public_key) != 32:
            raise ValueError("package publisher key must contain exactly 32 bytes")
        fingerprint = f"sha256:{hashlib.sha256(public_key).hexdigest()}"
        if fingerprint != self.publisher_key_fingerprint:
            raise ValueError("package publisher fingerprint changed")
        if (
            self.signature.signer_identity_id != self.publisher_identity_id
            or self.signature.key_fingerprint != self.publisher_key_fingerprint
            or self.signature.signed_at != self.created_at
        ):
            raise ValueError("package signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ShareableBehaviorPackV1(_SignedOriginPackage):
    package_format: Literal["temper-shareable-behavior-pack/v1"] = (
        "temper-shareable-behavior-pack/v1"
    )
    package_type: Literal[ShareablePackageType.BEHAVIOR_PACK] = ShareablePackageType.BEHAVIOR_PACK
    clauses: Annotated[tuple[ShareableBehaviorClauseV1, ...], Field(min_length=1)]

    @field_validator("clauses")
    @classmethod
    def clauses_are_sorted_unique(
        cls, value: tuple[ShareableBehaviorClauseV1, ...]
    ) -> tuple[ShareableBehaviorClauseV1, ...]:
        keys = tuple((item.claim_key, item.clause_id) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("shareable behavior clauses must be sorted and unique")
        if len({item.claim_key for item in value}) != len(value):
            raise ValueError("shareable behavior claim keys must be unique")
        return value

    @model_validator(mode="after")
    def purpose_matches(self) -> Self:
        if self.signature.purpose != BEHAVIOR_PACK_PURPOSE:
            raise ValueError("behavior-pack signature purpose is inconsistent")
        return self


class CapabilityModePackageV1(_SignedOriginPackage):
    package_format: Literal["temper-capability-mode/v1"] = "temper-capability-mode/v1"
    package_type: Literal[ShareablePackageType.CAPABILITY_MODE] = (
        ShareablePackageType.CAPABILITY_MODE
    )
    mode: CapabilityMode

    @model_validator(mode="after")
    def purpose_and_version_match(self) -> Self:
        if self.signature.purpose != MODE_PACKAGE_PURPOSE:
            raise ValueError("Mode-package signature purpose is inconsistent")
        if self.mode.mode_version != self.release_version:
            raise ValueError("Mode package release does not match its embedded Mode")
        return self


class PersonalModeOverlayV1(_SignedOriginPackage):
    package_format: Literal["temper-personal-mode-overlay/v1"] = "temper-personal-mode-overlay/v1"
    package_type: Literal[ShareablePackageType.PERSONAL_MODE_OVERLAY] = (
        ShareablePackageType.PERSONAL_MODE_OVERLAY
    )
    owner_subject_id: Identifier
    base_mode_id: Identifier
    base_mode_version: SemVer
    base_mode_digest: Sha256Digest
    clauses: Annotated[tuple[ModeClause, ...], Field(min_length=1)]

    @field_validator("clauses")
    @classmethod
    def overlay_clauses_are_sorted_unique(
        cls, value: tuple[ModeClause, ...]
    ) -> tuple[ModeClause, ...]:
        keys = tuple((item.claim_key, item.clause_id) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("personal overlay clauses must be sorted and unique")
        return value

    @model_validator(mode="after")
    def purpose_matches(self) -> Self:
        if self.signature.purpose != OVERLAY_PURPOSE:
            raise ValueError("personal-overlay signature purpose is inconsistent")
        return self


ShareablePackage = ShareableBehaviorPackV1 | CapabilityModePackageV1 | PersonalModeOverlayV1


class PackageImportItemPreviewV1(FrozenModel):
    item_id: Identifier
    kind: NonEmptyStr
    summary: NonEmptyStr
    disposition: Literal["new", "exact_duplicate", "conflict", "owner_only"]


class PackageImportPreviewV1(FrozenModel):
    preview_version: Literal["1.0.0"] = "1.0.0"
    package_type: ShareablePackageType
    package_id: Identifier
    release_version: SemVer
    package_digest: Sha256Digest
    display_name: NonEmptyStr
    publisher_name: NonEmptyStr
    publisher_key_fingerprint: Sha256Digest
    source_license: NonEmptyStr
    origin_signature_verified: Literal[True] = True
    item_count: int = Field(ge=1)
    items: Annotated[tuple[PackageImportItemPreviewV1, ...], Field(min_length=1)]
    duplicate_item_ids: tuple[Identifier, ...] = ()
    conflicting_item_ids: tuple[Identifier, ...] = ()
    requested_scope_mapping_count: int = Field(ge=0)
    required_capabilities: tuple[Identifier, ...] = ()
    evaluation_status: NonEmptyStr | None = None
    warnings: tuple[NonEmptyStr, ...]
    starts_inactive: Literal[True] = True
    grants_user_authority: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False

    @field_validator("duplicate_item_ids", "conflicting_item_ids", "required_capabilities")
    @classmethod
    def tuple_values_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("package preview values must be sorted and unique")
        return value


class PackageImportReceiptV1(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    package_type: ShareablePackageType
    package_id: Identifier
    release_version: SemVer
    package_digest: Sha256Digest
    publisher_key_fingerprint: Sha256Digest
    local_subject_id: Identifier
    local_signer_identity_id: Identifier
    local_signer_key_fingerprint: Sha256Digest
    status: Literal["staged_inactive_for_review"] = "staged_inactive_for_review"
    duplicate_item_ids: tuple[Identifier, ...] = ()
    conflicting_item_ids: tuple[Identifier, ...] = ()
    activates_artifacts: Literal[False] = False
    grants_user_authority: Literal[False] = False
    imported_at: datetime
    idempotency_key_digest: Sha256Digest
    signature: SignatureEnvelope

    @model_validator(mode="after")
    def receipt_is_inactive_and_signed(self) -> Self:
        if (
            self.signature.purpose != PACKAGE_IMPORT_PURPOSE
            or self.signature.signed_at != self.imported_at
            or self.signature.signer_identity_id != self.local_signer_identity_id
            or self.signature.key_fingerprint != self.local_signer_key_fingerprint
        ):
            raise ValueError("shareable-package import signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def build_shareable_behavior_pack(
    clauses: tuple[ShareableBehaviorClauseV1, ...],
    *,
    signer: GovernanceSigner,
    package_id: str,
    release_version: str,
    display_name: str,
    publisher_name: str,
    source_license: str,
    created_at: datetime,
) -> ShareableBehaviorPackV1:
    placeholder = signer.envelope({}, purpose=BEHAVIOR_PACK_PURPOSE, signed_at=created_at)
    draft = ShareableBehaviorPackV1(
        package_id=package_id,
        release_version=release_version,
        display_name=display_name,
        publisher_name=publisher_name,
        publisher_identity_id=signer.identity_id,
        publisher_public_key_base64=_public_key_base64(signer),
        publisher_key_fingerprint=signer.fingerprint,
        source_license=source_license,
        created_at=created_at,
        clauses=clauses,
        signature=placeholder,
    )
    package = draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose=BEHAVIOR_PACK_PURPOSE,
                signed_at=created_at,
            )
        }
    )
    verify_shareable_package(package)
    return package


def build_capability_mode_package(
    mode: CapabilityMode,
    *,
    signer: GovernanceSigner,
    package_id: str,
    display_name: str,
    publisher_name: str,
    source_license: str,
    created_at: datetime,
) -> CapabilityModePackageV1:
    placeholder = signer.envelope({}, purpose=MODE_PACKAGE_PURPOSE, signed_at=created_at)
    draft = CapabilityModePackageV1(
        package_id=package_id,
        release_version=mode.mode_version,
        display_name=display_name,
        publisher_name=publisher_name,
        publisher_identity_id=signer.identity_id,
        publisher_public_key_base64=_public_key_base64(signer),
        publisher_key_fingerprint=signer.fingerprint,
        source_license=source_license,
        created_at=created_at,
        mode=mode,
        signature=placeholder,
    )
    package = draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose=MODE_PACKAGE_PURPOSE,
                signed_at=created_at,
            )
        }
    )
    verify_shareable_package(package)
    return package


def build_personal_mode_overlay(
    clauses: tuple[ModeClause, ...],
    *,
    signer: GovernanceSigner,
    package_id: str,
    release_version: str,
    display_name: str,
    publisher_name: str,
    source_license: str,
    base_mode_id: str,
    base_mode_version: str,
    base_mode_digest: str,
    created_at: datetime,
) -> PersonalModeOverlayV1:
    """Sign one owner-bound overlay without granting authority to its recipient."""

    placeholder = signer.envelope({}, purpose=OVERLAY_PURPOSE, signed_at=created_at)
    draft = PersonalModeOverlayV1(
        package_id=package_id,
        release_version=release_version,
        display_name=display_name,
        publisher_name=publisher_name,
        publisher_identity_id=signer.identity_id,
        publisher_public_key_base64=_public_key_base64(signer),
        publisher_key_fingerprint=signer.fingerprint,
        source_license=source_license,
        created_at=created_at,
        owner_subject_id=signer.subject_id,
        base_mode_id=base_mode_id,
        base_mode_version=base_mode_version,
        base_mode_digest=base_mode_digest,
        clauses=clauses,
        signature=placeholder,
    )
    package = draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose=OVERLAY_PURPOSE,
                signed_at=created_at,
            )
        }
    )
    verify_shareable_package(package)
    return package


def verify_shareable_package(package: ShareablePackage) -> None:
    purpose = {
        ShareablePackageType.BEHAVIOR_PACK: BEHAVIOR_PACK_PURPOSE,
        ShareablePackageType.CAPABILITY_MODE: MODE_PACKAGE_PURPOSE,
        ShareablePackageType.PERSONAL_MODE_OVERLAY: OVERLAY_PURPOSE,
    }[package.package_type]
    verify_detached_envelope(
        package.unsigned_payload,
        package.signature,
        public_key_base64=package.publisher_public_key_base64,
        expected_purpose=purpose,
    )
    for text in _package_behavior_text(package):
        _assert_shareable_text_safe(text)
    for identifier in _package_identifiers(package):
        if _SOURCE_TASK_ID.search(identifier):
            raise ShareablePackageError("shareable package contains a source-task-like identifier")
    serialized = canonical_json(package)
    if len(serialized) > MAX_SHAREABLE_PACKAGE_BYTES:
        raise ShareablePackageError("shareable package exceeds its byte ceiling")


def preview_shareable_package(
    package: ShareablePackage,
    *,
    known_claims: Mapping[str, str] | None = None,
    known_mode_digests: Mapping[str, str] | None = None,
    local_subject_id: str | None = None,
) -> PackageImportPreviewV1:
    verify_shareable_package(package)
    claim_map = known_claims or {}
    mode_map = known_mode_digests or {}
    items: list[PackageImportItemPreviewV1] = []
    duplicates: list[str] = []
    conflicts: list[str] = []
    scope_mapping_count = 0
    required_capabilities: tuple[str, ...] = ()
    evaluation_status: str | None = None

    if isinstance(package, ShareableBehaviorPackV1):
        for clause in package.clauses:
            known = claim_map.get(clause.claim_key)
            disposition: Literal["new", "exact_duplicate", "conflict", "owner_only"] = "new"
            if known is not None:
                if any(
                    known.strip() == behavior.strip()
                    for behavior in clause.behavioral_contract.required_behaviors
                ):
                    disposition = "exact_duplicate"
                    duplicates.append(clause.clause_id)
                else:
                    disposition = "conflict"
                    conflicts.append(clause.clause_id)
            scope_mapping_count += int(clause.requested_scope.scope_mapping_required)
            items.append(
                PackageImportItemPreviewV1(
                    item_id=clause.clause_id,
                    kind=clause.artifact_kind.value,
                    summary=clause.behavioral_contract.intent,
                    disposition=disposition,
                )
            )
    elif isinstance(package, CapabilityModePackageV1):
        known = mode_map.get(package.mode.mode_id)
        disposition = "new"
        if known == package.mode.content_digest:
            disposition = "exact_duplicate"
            duplicates.append(package.mode.mode_id)
        elif known is not None:
            disposition = "conflict"
            conflicts.append(package.mode.mode_id)
        items.append(
            PackageImportItemPreviewV1(
                item_id=package.mode.mode_id,
                kind="capability_mode",
                summary=package.mode.summary,
                disposition=disposition,
            )
        )
        required_capabilities = package.mode.required_capabilities
        evaluation_status = package.mode.evaluation_status.value
    else:
        if local_subject_id != package.owner_subject_id:
            disposition = "owner_only"
            conflicts.append(package.base_mode_id)
        else:
            disposition = "new"
        items.append(
            PackageImportItemPreviewV1(
                item_id=package.base_mode_id,
                kind="personal_mode_overlay",
                summary=f"Personal overlay for {package.base_mode_id}",
                disposition=disposition,
            )
        )

    return PackageImportPreviewV1(
        package_type=package.package_type,
        package_id=package.package_id,
        release_version=package.release_version,
        package_digest=package.content_digest,
        display_name=package.display_name,
        publisher_name=package.publisher_name,
        publisher_key_fingerprint=package.publisher_key_fingerprint,
        source_license=package.source_license,
        item_count=len(items),
        items=tuple(items),
        duplicate_item_ids=tuple(sorted(duplicates)),
        conflicting_item_ids=tuple(sorted(conflicts)),
        requested_scope_mapping_count=scope_mapping_count,
        required_capabilities=required_capabilities,
        evaluation_status=evaluation_status,
        warnings=(
            "The signature proves origin and integrity, not truth or user authority.",
            "Every imported item starts inactive and requires local review.",
        ),
    )


def write_shareable_package(package: ShareablePackage, destination: Path) -> Path:
    verify_shareable_package(package)
    resolved = destination.expanduser().resolve()
    if resolved.suffix.casefold() != ".temper-pack":
        raise ShareablePackageError("shareable packages require the .temper-pack extension")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical_json(package) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        resolved.unlink(missing_ok=True)
        raise
    return resolved


def read_shareable_package(source: Path) -> ShareablePackage:
    resolved = source.expanduser().resolve()
    if resolved.suffix.casefold() != ".temper-pack":
        raise ShareablePackageError("shareable packages require the .temper-pack extension")
    try:
        size = resolved.stat().st_size
        raw = resolved.read_bytes()
    except OSError as error:
        raise ShareablePackageError("shareable package could not be read") from error
    if size <= 0 or size > MAX_SHAREABLE_PACKAGE_BYTES:
        raise ShareablePackageError("shareable package size is invalid")
    try:
        payload = json.loads(raw)
        package_type = ShareablePackageType(payload["package_type"])
        if package_type is ShareablePackageType.BEHAVIOR_PACK:
            package: ShareablePackage = ShareableBehaviorPackV1.model_validate_json(
                raw, strict=True
            )
        elif package_type is ShareablePackageType.CAPABILITY_MODE:
            package = CapabilityModePackageV1.model_validate_json(raw, strict=True)
        else:
            package = PersonalModeOverlayV1.model_validate_json(raw, strict=True)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ShareablePackageError("shareable package is invalid") from error
    verify_shareable_package(package)
    return package


class ShareablePackageImportStore:
    """Append-only inactive staging with replay and downgrade protection."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def stage(
        self,
        package: ShareablePackage,
        preview: PackageImportPreviewV1,
        *,
        signer: GovernanceSigner,
        local_subject_id: str,
        imported_at: datetime,
        idempotency_key: str,
    ) -> PackageImportReceiptV1:
        verify_shareable_package(package)
        if preview.package_digest != package.content_digest:
            raise ShareablePackageError("shareable package changed after preview")
        if not idempotency_key.strip():
            raise ShareablePackageError("shareable package import requires an idempotency key")
        if local_subject_id != signer.subject_id:
            raise ShareablePackageError("shareable package crossed the local subject boundary")
        self._root.mkdir(parents=True, exist_ok=True)
        key_digest = canonical_digest({"idempotency_key": idempotency_key})
        receipt_path = self._root / f"{str(key_digest).removeprefix('sha256:')}.json"
        if receipt_path.exists():
            existing = PackageImportReceiptV1.model_validate_json(receipt_path.read_bytes())
            if existing.package_digest != package.content_digest:
                raise ShareablePackageError("idempotency key was reused for another package")
            return existing
        self._reject_downgrade(package)
        self._persist_inactive_package(package)
        placeholder = signer.envelope({}, purpose=PACKAGE_IMPORT_PURPOSE, signed_at=imported_at)
        draft = PackageImportReceiptV1(
            receipt_id=f"package-import-{str(key_digest).removeprefix('sha256:')[:24]}",
            package_type=package.package_type,
            package_id=package.package_id,
            release_version=package.release_version,
            package_digest=package.content_digest,
            publisher_key_fingerprint=package.publisher_key_fingerprint,
            local_subject_id=local_subject_id,
            local_signer_identity_id=signer.identity_id,
            local_signer_key_fingerprint=signer.fingerprint,
            duplicate_item_ids=preview.duplicate_item_ids,
            conflicting_item_ids=preview.conflicting_item_ids,
            imported_at=imported_at,
            idempotency_key_digest=key_digest,
            signature=placeholder,
        )
        receipt = draft.model_copy(
            update={
                "signature": signer.envelope(
                    draft.unsigned_payload,
                    purpose=PACKAGE_IMPORT_PURPOSE,
                    signed_at=imported_at,
                )
            }
        )
        temporary = receipt_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(receipt) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, receipt_path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return receipt

    def _persist_inactive_package(self, package: ShareablePackage) -> None:
        package_root = self._root / "packages"
        package_root.mkdir(parents=True, exist_ok=True)
        digest_name = str(package.content_digest).removeprefix("sha256:")
        destination = package_root / f"{digest_name}.temper-pack"
        if destination.exists():
            if read_shareable_package(destination).content_digest != package.content_digest:
                raise ShareablePackageError("staged shareable package digest changed")
            return
        write_shareable_package(package, destination)

    def _reject_downgrade(self, package: ShareablePackage) -> None:
        incoming = _semver_key(package.release_version)
        for path in self._root.glob("*.json"):
            receipt = PackageImportReceiptV1.model_validate_json(path.read_bytes())
            if (
                receipt.package_type == package.package_type
                and receipt.package_id == package.package_id
                and receipt.publisher_key_fingerprint == package.publisher_key_fingerprint
                and _semver_key(receipt.release_version) > incoming
            ):
                raise ShareablePackageError("shareable package downgrade is not permitted")


def _public_key_base64(signer: GovernanceSigner) -> str:
    return base64.b64encode(signer.private_key.public_key().public_bytes_raw()).decode("ascii")


def _package_behavior_text(package: ShareablePackage) -> tuple[str, ...]:
    common = (package.display_name, package.publisher_name, package.source_license)
    if isinstance(package, ShareableBehaviorPackV1):
        return common + tuple(
            text
            for clause in package.clauses
            for text in (
                clause.behavioral_contract.intent,
                *clause.behavioral_contract.required_behaviors,
                *clause.behavioral_contract.non_goals,
                *clause.behavioral_contract.verification_requirements,
                *clause.requested_scope.activation_conditions,
                *clause.requested_scope.exclusions,
            )
        )
    if isinstance(package, CapabilityModePackageV1):
        return (
            *common,
            package.mode.name,
            package.mode.summary,
            package.mode.source_revision,
            *package.mode.requested_tools,
            *package.mode.required_capabilities,
            *(
                value
                for target in package.mode.target_compatibility
                for value in (target.version_constraint, target.delivery_surface)
            ),
            *(clause.text for clause in package.mode.clauses),
        )
    return common + tuple(clause.text for clause in package.clauses)


def _package_identifiers(package: ShareablePackage) -> tuple[str, ...]:
    common = (package.package_id, package.publisher_identity_id)
    if isinstance(package, ShareableBehaviorPackV1):
        return common + tuple(
            value
            for clause in package.clauses
            for value in (
                clause.clause_id,
                clause.claim_key,
                *clause.requested_scope.project_ids,
                *clause.requested_scope.task_classes,
                *clause.requested_scope.environment_ids,
            )
        )
    if isinstance(package, CapabilityModePackageV1):
        return (
            *common,
            package.mode.mode_id,
            *(
                value
                for clause in package.mode.clauses
                for value in (clause.clause_id, clause.claim_key)
            ),
        )
    return (
        *common,
        package.owner_subject_id,
        package.base_mode_id,
        *(value for clause in package.clauses for value in (clause.clause_id, clause.claim_key)),
    )


def _assert_shareable_text_safe(text: str) -> None:
    try:
        assert_export_safe(text, label="shareable package")
    except ExportSafetyError as error:
        raise ShareablePackageError(str(error)) from error
    if _PRIVATE_PATH.search(text):
        raise ShareablePackageError("shareable package contains a private path")
    if _TRANSCRIPT_ROLE.search(text):
        raise ShareablePackageError("shareable package contains transcript-like content")
    if _EXECUTABLE_CONTENT.search(text):
        raise ShareablePackageError("shareable package contains executable content")


def _semver_key(value: str) -> tuple[int, int, int, int, str]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", value)
    if match is None:
        raise ShareablePackageError("shareable package version is invalid")
    prerelease = match.group(4)
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        1 if prerelease is None else 0,
        prerelease or "",
    )
