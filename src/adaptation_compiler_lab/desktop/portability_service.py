"""Presentation-neutral desktop bridge for offline profile portability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _ledger,
    _load_config,
    _registration_signer,
)
from adaptation_compiler_lab.modes import MODE_CATALOG, mode_by_id
from adaptation_compiler_lab.portability import (
    CapabilityModePackageV1,
    EncryptedProfileEnvelope,
    PackageImportPreviewV1,
    PackageImportReceiptV1,
    PortableProfilePackage,
    PortableProfilePreview,
    ProfileImportReceipt,
    ProfileImportStore,
    ShareableBehaviorClauseV1,
    ShareableBehaviorPackV1,
    ShareablePackage,
    ShareablePackageImportStore,
    build_capability_mode_package,
    build_portable_profile,
    build_shareable_behavior_pack,
    encrypt_portable_profile,
    preview_portable_profile,
    preview_profile_export,
    preview_shareable_package,
    read_portable_profile,
    read_shareable_package,
    write_portable_profile,
    write_shareable_package,
)
from adaptation_compiler_lab.portability.profile import PortableProfileScope


@dataclass(frozen=True, slots=True)
class LocalProfilePortabilityService:
    """Use the current governed release and local signing identity without exposing either."""

    config_path: Path

    def build_export(self, *, created_at: datetime | None = None) -> PortableProfilePackage:
        config = _load_config(self.config_path)
        state = _ledger(config).current()
        if state is None or state.release is None:
            raise ValueError("Temper has no active Core to export")
        release = state.release.governed_release
        now = created_at or datetime.now(UTC)
        package_id = f"temper-core-{now.strftime('%Y%m%dT%H%M%SZ')}"
        return build_portable_profile(
            release.active_artifacts,
            release.active_bindings,
            signer=_registration_signer(config),
            source_release_digest=release.content_digest,
            package_id=package_id,
            display_name="Temper Core",
            created_at=now,
        )

    @staticmethod
    def preview_export(package: PortableProfilePackage) -> PortableProfilePreview:
        return preview_profile_export(package)

    @staticmethod
    def write_export(
        package: PortableProfilePackage, *, passphrase: str, destination: Path
    ) -> PortableProfilePreview:
        envelope = encrypt_portable_profile(package, passphrase=passphrase)
        write_portable_profile(envelope, destination)
        return preview_profile_export(package)

    @staticmethod
    def read_import(source: Path) -> EncryptedProfileEnvelope:
        return read_portable_profile(source)

    @staticmethod
    def preview_import(
        envelope: EncryptedProfileEnvelope, *, passphrase: str
    ) -> PortableProfilePreview:
        return preview_portable_profile(envelope, passphrase=passphrase)

    def stage_import(
        self,
        envelope: EncryptedProfileEnvelope,
        *,
        passphrase: str,
        expected_package_digest: str,
        idempotency_key: str,
        imported_at: datetime | None = None,
    ) -> ProfileImportReceipt:
        config = _load_config(self.config_path)
        return ProfileImportStore(config.state_root / "portable-imports").stage(
            envelope,
            passphrase=passphrase,
            expected_package_digest=expected_package_digest,
            signer=_registration_signer(config),
            imported_at=imported_at or datetime.now(UTC),
            idempotency_key=idempotency_key,
        )

    def build_shareable_behavior_export(
        self, *, created_at: datetime | None = None
    ) -> ShareableBehaviorPackV1:
        """Build a raw-free behavior pack without source evidence or local scope IDs."""

        config = _load_config(self.config_path)
        state = _ledger(config).current()
        if state is None or state.release is None:
            raise ValueError("Temper has no active Core to share")
        release = state.release.governed_release
        clauses = tuple(
            ShareableBehaviorClauseV1(
                clause_id=f"shared-clause-{index:04d}",
                claim_key=f"shared.behavior.{index:04d}",
                artifact_kind=artifact.artifact_type,
                behavioral_contract=artifact.behavioral_contract,
                requested_scope=PortableProfileScope.from_governed_scope(artifact.scope),
            )
            for index, artifact in enumerate(release.active_artifacts, start=1)
        )
        now = created_at or datetime.now(UTC)
        return build_shareable_behavior_pack(
            clauses,
            signer=_registration_signer(config),
            package_id=f"temper-behaviors-{now.strftime('%Y%m%dT%H%M%SZ')}",
            release_version=release.release_ref.record_version,
            display_name="Temper behavior pack",
            publisher_name="Local Temper owner",
            source_license="Private sharing; recipient review required",
            created_at=now,
        )

    def build_shareable_mode_export(
        self, mode_id: str, *, created_at: datetime | None = None
    ) -> CapabilityModePackageV1:
        config = _load_config(self.config_path)
        mode = mode_by_id(mode_id)
        if mode is None:
            raise ValueError("unknown capability Mode")
        now = created_at or datetime.now(UTC)
        return build_capability_mode_package(
            mode,
            signer=_registration_signer(config),
            package_id=f"{mode.mode_id}-package",
            display_name=mode.name,
            publisher_name=mode.publisher,
            source_license=mode.source_license,
            created_at=now,
        )

    @staticmethod
    def preview_shareable_export(package: ShareablePackage) -> PackageImportPreviewV1:
        return preview_shareable_package(package)

    @staticmethod
    def write_shareable_export(package: ShareablePackage, destination: Path) -> Path:
        return write_shareable_package(package, destination)

    @staticmethod
    def read_shareable_import(source: Path) -> ShareablePackage:
        return read_shareable_package(source)

    def preview_shareable_import(self, package: ShareablePackage) -> PackageImportPreviewV1:
        config = _load_config(self.config_path)
        state = _ledger(config).current()
        known_behaviors: set[str] = set()
        if state is not None and state.release is not None:
            known_behaviors = {
                behavior.strip()
                for artifact in state.release.governed_release.active_artifacts
                for behavior in artifact.behavioral_contract.required_behaviors
            }
        known_claims = {
            clause.claim_key: next(
                (
                    behavior
                    for behavior in clause.behavioral_contract.required_behaviors
                    if behavior.strip() in known_behaviors
                ),
                "",
            )
            for clause in (package.clauses if isinstance(package, ShareableBehaviorPackV1) else ())
            if any(
                behavior.strip() in known_behaviors
                for behavior in clause.behavioral_contract.required_behaviors
            )
        }
        return preview_shareable_package(
            package,
            known_claims=known_claims,
            known_mode_digests={mode.mode_id: mode.content_digest for mode in MODE_CATALOG},
            local_subject_id=config.subject_id,
        )

    def stage_shareable_import(
        self,
        package: ShareablePackage,
        preview: PackageImportPreviewV1,
        *,
        idempotency_key: str,
        imported_at: datetime | None = None,
    ) -> PackageImportReceiptV1:
        config = _load_config(self.config_path)
        return ShareablePackageImportStore(config.state_root / "shareable-imports").stage(
            package,
            preview,
            signer=_registration_signer(config),
            local_subject_id=config.subject_id,
            imported_at=imported_at or datetime.now(UTC),
            idempotency_key=idempotency_key,
        )
