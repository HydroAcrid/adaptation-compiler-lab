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
PACKAGE_REVIEW_PURPOSE = "shareable_package_review"
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


PackageReviewDisposition = Literal["new", "exact_duplicate", "conflict", "owner_only"]


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
    disposition: PackageReviewDisposition


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
    local_public_key_base64: NonEmptyStr
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
        try:
            public_key = base64.b64decode(self.local_public_key_base64, validate=True)
        except ValueError as error:
            raise ValueError("package import public key is not canonical base64") from error
        if len(public_key) != 32:
            raise ValueError("package import public key must contain exactly 32 bytes")
        fingerprint = f"sha256:{hashlib.sha256(public_key).hexdigest()}"
        if fingerprint != self.local_signer_key_fingerprint:
            raise ValueError("package import signer fingerprint changed")
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


class PackageReviewItemV1(FrozenModel):
    """One externally-authored item waiting for an explicit local decision."""

    review_version: Literal["1.0.0"] = "1.0.0"
    review_id: Identifier
    local_subject_id: Identifier
    import_receipt_id: Identifier
    import_receipt_digest: Sha256Digest
    package_type: ShareablePackageType
    package_id: Identifier
    package_digest: Sha256Digest
    item_id: Identifier
    item_digest: Sha256Digest
    claim_key: Identifier | None = None
    publisher_name: NonEmptyStr
    publisher_key_fingerprint: Sha256Digest
    kind: NonEmptyStr
    summary: NonEmptyStr
    disposition: PackageReviewDisposition
    requested_scope: PortableProfileScope | None = None
    behavioral_contract: BehavioralContract | None = None
    required_capabilities: tuple[Identifier, ...] = ()
    evaluation_status: NonEmptyStr | None = None
    available_actions: tuple[Literal["approve", "reject"], ...]
    created_at: datetime
    starts_inactive: Literal[True] = True
    origin_grants_authority: Literal[False] = False
    raw_payloads_exposed: Literal[False] = False

    @model_validator(mode="after")
    def review_shape_matches_item(self) -> Self:
        behavior = self.package_type is ShareablePackageType.BEHAVIOR_PACK
        if behavior != (self.behavioral_contract is not None):
            raise ValueError("only behavior-pack reviews may carry a behavioral contract")
        if behavior != (self.requested_scope is not None):
            raise ValueError("only behavior-pack reviews may carry a requested scope")
        if behavior != (self.claim_key is not None):
            raise ValueError("only behavior-pack reviews may carry a claim key")
        expected_actions: tuple[Literal["approve", "reject"], ...] = (
            ("approve", "reject") if self.disposition == "new" else ("reject",)
        )
        if self.available_actions != expected_actions:
            raise ValueError("package review actions do not match its safe disposition")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PackageReviewDecisionReceiptV1(FrozenModel):
    """Signed local adoption decision; the publisher signature grants no authority."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    review_id: Identifier
    review_digest: Sha256Digest
    package_type: ShareablePackageType
    package_id: Identifier
    package_digest: Sha256Digest
    item_id: Identifier
    item_digest: Sha256Digest
    local_subject_id: Identifier
    local_signer_identity_id: Identifier
    local_public_key_base64: NonEmptyStr
    local_signer_key_fingerprint: Sha256Digest
    decision: Literal["approved", "rejected"]
    resulting_status: Literal[
        "approved_for_core",
        "approved_inactive_mode",
        "approved_inactive_overlay",
        "rejected",
    ]
    mapped_project_ids: tuple[Identifier, ...] = ()
    runtime_adoption_digest: Sha256Digest | None = None
    decided_at: datetime
    idempotency_key_digest: Sha256Digest
    signature: SignatureEnvelope
    origin_granted_authority: Literal[False] = False
    local_user_decision_required: Literal[True] = True

    @field_validator("mapped_project_ids")
    @classmethod
    def mapped_projects_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("mapped package projects must be sorted and unique")
        return value

    @model_validator(mode="after")
    def decision_is_local_and_exact(self) -> Self:
        try:
            public_key = base64.b64decode(self.local_public_key_base64, validate=True)
        except ValueError as error:
            raise ValueError("package review public key is not canonical base64") from error
        if len(public_key) != 32:
            raise ValueError("package review public key must contain exactly 32 bytes")
        fingerprint = f"sha256:{hashlib.sha256(public_key).hexdigest()}"
        if fingerprint != self.local_signer_key_fingerprint:
            raise ValueError("package review signer fingerprint changed")
        expected_status = {
            ShareablePackageType.BEHAVIOR_PACK: "approved_for_core",
            ShareablePackageType.CAPABILITY_MODE: "approved_inactive_mode",
            ShareablePackageType.PERSONAL_MODE_OVERLAY: "approved_inactive_overlay",
        }[self.package_type]
        if self.decision == "rejected":
            if self.resulting_status != "rejected" or self.runtime_adoption_digest is not None:
                raise ValueError("rejected package review cannot claim adopted output")
        elif self.resulting_status != expected_status:
            raise ValueError("approved package review has an inconsistent status")
        elif (self.package_type is ShareablePackageType.BEHAVIOR_PACK) != (
            self.runtime_adoption_digest is not None
        ):
            raise ValueError("approved behavior review must bind one runtime adoption")
        if self.package_type is not ShareablePackageType.BEHAVIOR_PACK and self.mapped_project_ids:
            raise ValueError("Mode and overlay decisions cannot claim project scope mappings")
        if (
            self.signature.purpose != PACKAGE_REVIEW_PURPOSE
            or self.signature.signed_at != self.decided_at
            or self.signature.signer_identity_id != self.local_signer_identity_id
            or self.signature.key_fingerprint != self.local_signer_key_fingerprint
        ):
            raise ValueError("package review signature metadata is inconsistent")
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
        elif mode_map.get(package.base_mode_id) != package.base_mode_digest:
            disposition = "conflict"
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
            _verify_package_import_receipt(existing)
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
            local_public_key_base64=_public_key_base64(signer),
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
            _verify_package_import_receipt(receipt)
            if (
                receipt.package_type == package.package_type
                and receipt.package_id == package.package_id
                and receipt.publisher_key_fingerprint == package.publisher_key_fingerprint
                and _semver_key(receipt.release_version) > incoming
            ):
                raise ShareablePackageError("shareable package downgrade is not permitted")

    def review_items(self, *, include_resolved: bool = False) -> tuple[PackageReviewItemV1, ...]:
        """Return every staged item without treating package origin as local authority."""

        decisions = {item.review_id for item in self.decisions()}
        reviews: list[PackageReviewItemV1] = []
        if not self._root.exists():
            return ()
        for path in sorted(self._root.glob("*.json")):
            receipt = PackageImportReceiptV1.model_validate_json(path.read_bytes(), strict=True)
            _verify_package_import_receipt(receipt)
            package_path = (
                self._root
                / "packages"
                / f"{str(receipt.package_digest).removeprefix('sha256:')}.temper-pack"
            )
            package = read_shareable_package(package_path)
            if (
                package.content_digest != receipt.package_digest
                or package.package_id != receipt.package_id
                or package.package_type is not receipt.package_type
            ):
                raise ShareablePackageError("staged package no longer matches its import receipt")
            preview_dispositions: dict[str, PackageReviewDisposition] = {
                item_id: "exact_duplicate" for item_id in receipt.duplicate_item_ids
            }
            preview_dispositions.update(
                {item_id: "conflict" for item_id in receipt.conflicting_item_ids}
            )
            for item in _review_items_for_package(package, receipt, preview_dispositions):
                if include_resolved or item.review_id not in decisions:
                    reviews.append(item)
        return tuple(sorted(reviews, key=lambda item: (item.created_at, item.review_id)))

    def review_item(self, review_id: str) -> PackageReviewItemV1 | None:
        return next(
            (
                item
                for item in self.review_items(include_resolved=True)
                if item.review_id == review_id
            ),
            None,
        )

    def decisions(self) -> tuple[PackageReviewDecisionReceiptV1, ...]:
        decision_root = self._root / "decisions"
        if not decision_root.exists():
            return ()
        decisions_list: list[PackageReviewDecisionReceiptV1] = []
        for path in sorted(decision_root.glob("*.json")):
            receipt = PackageReviewDecisionReceiptV1.model_validate_json(
                path.read_bytes(), strict=True
            )
            _verify_package_review_decision(receipt)
            decisions_list.append(receipt)
        decisions = tuple(decisions_list)
        if len({item.review_id for item in decisions}) != len(decisions):
            raise ShareablePackageError("package review has conflicting local decisions")
        return decisions

    def decide(
        self,
        item: PackageReviewItemV1,
        *,
        signer: GovernanceSigner,
        decision: Literal["approved", "rejected"],
        mapped_project_ids: tuple[str, ...],
        runtime_adoption_digest: Sha256Digest | None,
        decided_at: datetime,
        idempotency_key: str,
    ) -> PackageReviewDecisionReceiptV1:
        """Persist one exact signed recipient decision after any governed Core transition."""

        current_item = self.review_item(item.review_id)
        if current_item is None or current_item.content_digest != item.content_digest:
            raise ShareablePackageError("package review item changed after it was presented")
        item = current_item
        if item.local_subject_id != signer.subject_id:
            raise ShareablePackageError("package review crossed the local subject boundary")
        if not idempotency_key.strip():
            raise ShareablePackageError("package review requires an idempotency key")
        if decision == "approved" and "approve" not in item.available_actions:
            raise ShareablePackageError("this package item cannot be approved safely")
        if decision == "approved" and item.package_type is ShareablePackageType.BEHAVIOR_PACK:
            scope = item.requested_scope
            if scope is None:
                raise ShareablePackageError("behavior review lost its requested scope")
            if scope.scope_mapping_required and not mapped_project_ids:
                raise ShareablePackageError("behavior review requires an explicit project mapping")
        key_digest = canonical_digest({"idempotency_key": idempotency_key})
        decision_root = self._root / "decisions"
        decision_root.mkdir(parents=True, exist_ok=True)
        existing_for_review = next(
            (value for value in self.decisions() if value.review_id == item.review_id),
            None,
        )
        if existing_for_review is not None:
            if (
                existing_for_review.decision != decision
                or existing_for_review.review_digest != item.content_digest
                or existing_for_review.mapped_project_ids != mapped_project_ids
                or existing_for_review.runtime_adoption_digest != runtime_adoption_digest
            ):
                raise ShareablePackageError("package item already has another local decision")
            return existing_for_review
        receipt_path = decision_root / f"{str(key_digest).removeprefix('sha256:')}.json"
        if receipt_path.exists():
            existing = PackageReviewDecisionReceiptV1.model_validate_json(
                receipt_path.read_bytes(), strict=True
            )
            _verify_package_review_decision(existing)
            if existing.review_id != item.review_id:
                raise ShareablePackageError("idempotency key was reused for another package item")
            return existing
        status: Literal[
            "approved_for_core",
            "approved_inactive_mode",
            "approved_inactive_overlay",
            "rejected",
        ]
        if decision == "rejected":
            status = "rejected"
        elif item.package_type is ShareablePackageType.BEHAVIOR_PACK:
            status = "approved_for_core"
        elif item.package_type is ShareablePackageType.CAPABILITY_MODE:
            status = "approved_inactive_mode"
        else:
            status = "approved_inactive_overlay"
        placeholder = signer.envelope({}, purpose=PACKAGE_REVIEW_PURPOSE, signed_at=decided_at)
        draft = PackageReviewDecisionReceiptV1(
            receipt_id=f"package-review-{str(key_digest).removeprefix('sha256:')[:24]}",
            review_id=item.review_id,
            review_digest=item.content_digest,
            package_type=item.package_type,
            package_id=item.package_id,
            package_digest=item.package_digest,
            item_id=item.item_id,
            item_digest=item.item_digest,
            local_subject_id=item.local_subject_id,
            local_signer_identity_id=signer.identity_id,
            local_public_key_base64=_public_key_base64(signer),
            local_signer_key_fingerprint=signer.fingerprint,
            decision=decision,
            resulting_status=status,
            mapped_project_ids=mapped_project_ids,
            runtime_adoption_digest=runtime_adoption_digest,
            decided_at=decided_at,
            idempotency_key_digest=key_digest,
            signature=placeholder,
        )
        receipt = draft.model_copy(
            update={
                "signature": signer.envelope(
                    draft.unsigned_payload,
                    purpose=PACKAGE_REVIEW_PURPOSE,
                    signed_at=decided_at,
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

    def accepted_modes(self) -> tuple[CapabilityMode, ...]:
        """Load imported Modes only after an explicit local approval receipt."""

        modes: list[CapabilityMode] = []
        for decision in self.decisions():
            if decision.resulting_status != "approved_inactive_mode":
                continue
            package_path = (
                self._root
                / "packages"
                / f"{str(decision.package_digest).removeprefix('sha256:')}.temper-pack"
            )
            package = read_shareable_package(package_path)
            if not isinstance(package, CapabilityModePackageV1):
                raise ShareablePackageError("approved Mode decision points to another package type")
            if package.mode.content_digest != decision.item_digest:
                raise ShareablePackageError("approved imported Mode digest changed")
            modes.append(package.mode.model_copy(update={"source_kind": "imported"}))
        keys = tuple((mode.mode_id, mode.mode_version) for mode in modes)
        if len(keys) != len(set(keys)):
            raise ShareablePackageError("approved imported Mode catalog contains duplicates")
        return tuple(sorted(modes, key=lambda mode: (mode.name.casefold(), mode.mode_id)))

    def accepted_overlays(self) -> tuple[PersonalModeOverlayV1, ...]:
        """Load owner-bound personal overlays only after explicit local approval."""

        overlays: list[PersonalModeOverlayV1] = []
        for decision in self.decisions():
            if decision.resulting_status != "approved_inactive_overlay":
                continue
            package_path = (
                self._root
                / "packages"
                / f"{str(decision.package_digest).removeprefix('sha256:')}.temper-pack"
            )
            package = read_shareable_package(package_path)
            if not isinstance(package, PersonalModeOverlayV1):
                raise ShareablePackageError("approved overlay points to another package type")
            if package.owner_subject_id != decision.local_subject_id:
                raise ShareablePackageError("approved overlay crossed its owner boundary")
            if _personal_overlay_item_digest(package) != decision.item_digest:
                raise ShareablePackageError("approved personal overlay digest changed")
            overlays.append(package)
        keys = tuple((item.base_mode_id, item.base_mode_digest) for item in overlays)
        if len(keys) != len(set(keys)):
            raise ShareablePackageError("more than one personal overlay targets the same Mode")
        return tuple(sorted(overlays, key=lambda item: (item.base_mode_id, item.package_id)))


def _review_items_for_package(
    package: ShareablePackage,
    receipt: PackageImportReceiptV1,
    dispositions: Mapping[str, PackageReviewDisposition],
) -> tuple[PackageReviewItemV1, ...]:
    """Project a verified staged package into raw-free, locally reviewable items."""

    rows: list[PackageReviewItemV1] = []
    if isinstance(package, ShareableBehaviorPackV1):
        for clause in package.clauses:
            disposition = dispositions.get(clause.clause_id, "new")
            rows.append(
                PackageReviewItemV1(
                    review_id=_package_review_id(package.content_digest, clause.clause_id),
                    local_subject_id=receipt.local_subject_id,
                    import_receipt_id=receipt.receipt_id,
                    import_receipt_digest=receipt.content_digest,
                    package_type=package.package_type,
                    package_id=package.package_id,
                    package_digest=package.content_digest,
                    item_id=clause.clause_id,
                    item_digest=clause.content_digest,
                    claim_key=clause.claim_key,
                    publisher_name=package.publisher_name,
                    publisher_key_fingerprint=package.publisher_key_fingerprint,
                    kind=clause.artifact_kind.value,
                    summary=clause.behavioral_contract.intent,
                    disposition=disposition,
                    requested_scope=clause.requested_scope,
                    behavioral_contract=clause.behavioral_contract,
                    available_actions=(
                        ("approve", "reject") if disposition == "new" else ("reject",)
                    ),
                    created_at=receipt.imported_at,
                )
            )
    elif isinstance(package, CapabilityModePackageV1):
        disposition = dispositions.get(package.mode.mode_id, "new")
        rows.append(
            PackageReviewItemV1(
                review_id=_package_review_id(package.content_digest, package.mode.mode_id),
                local_subject_id=receipt.local_subject_id,
                import_receipt_id=receipt.receipt_id,
                import_receipt_digest=receipt.content_digest,
                package_type=package.package_type,
                package_id=package.package_id,
                package_digest=package.content_digest,
                item_id=package.mode.mode_id,
                item_digest=package.mode.content_digest,
                publisher_name=package.publisher_name,
                publisher_key_fingerprint=package.publisher_key_fingerprint,
                kind="capability_mode",
                summary=package.mode.summary,
                disposition=disposition,
                required_capabilities=package.mode.required_capabilities,
                evaluation_status=package.mode.evaluation_status.value,
                available_actions=(("approve", "reject") if disposition == "new" else ("reject",)),
                created_at=receipt.imported_at,
            )
        )
    else:
        disposition = dispositions.get(package.base_mode_id, "new")
        if package.owner_subject_id != receipt.local_subject_id:
            disposition = "owner_only"
        overlay_digest = _personal_overlay_item_digest(package)
        rows.append(
            PackageReviewItemV1(
                review_id=_package_review_id(package.content_digest, package.base_mode_id),
                local_subject_id=receipt.local_subject_id,
                import_receipt_id=receipt.receipt_id,
                import_receipt_digest=receipt.content_digest,
                package_type=package.package_type,
                package_id=package.package_id,
                package_digest=package.content_digest,
                item_id=package.base_mode_id,
                item_digest=overlay_digest,
                publisher_name=package.publisher_name,
                publisher_key_fingerprint=package.publisher_key_fingerprint,
                kind="personal_mode_overlay",
                summary=f"Personal overlay for {package.base_mode_id}",
                disposition=disposition,
                available_actions=(("approve", "reject") if disposition == "new" else ("reject",)),
                created_at=receipt.imported_at,
            )
        )
    return tuple(rows)


def _package_review_id(package_digest: Sha256Digest, item_id: str) -> str:
    digest = canonical_digest({"package_digest": package_digest, "item_id": item_id})
    return f"package-review-{str(digest).removeprefix('sha256:')[:24]}"


def _personal_overlay_item_digest(package: PersonalModeOverlayV1) -> Sha256Digest:
    return canonical_digest(
        {
            "base_mode_id": package.base_mode_id,
            "base_mode_digest": package.base_mode_digest,
            "clauses": tuple(clause.model_dump(mode="json") for clause in package.clauses),
        }
    )


def _verify_package_review_decision(receipt: PackageReviewDecisionReceiptV1) -> None:
    try:
        verify_detached_envelope(
            receipt.unsigned_payload,
            receipt.signature,
            public_key_base64=receipt.local_public_key_base64,
            expected_purpose=PACKAGE_REVIEW_PURPOSE,
        )
    except ValueError as error:
        raise ShareablePackageError("local package-review signature is invalid") from error


def _verify_package_import_receipt(receipt: PackageImportReceiptV1) -> None:
    try:
        verify_detached_envelope(
            receipt.unsigned_payload,
            receipt.signature,
            public_key_base64=receipt.local_public_key_base64,
            expected_purpose=PACKAGE_IMPORT_PURPOSE,
        )
    except ValueError as error:
        raise ShareablePackageError("local package-import signature is invalid") from error


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
