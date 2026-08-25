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
from adaptation_compiler_lab.portability import (
    EncryptedProfileEnvelope,
    PortableProfilePackage,
    PortableProfilePreview,
    ProfileImportReceipt,
    ProfileImportStore,
    build_portable_profile,
    encrypt_portable_profile,
    preview_portable_profile,
    preview_profile_export,
    read_portable_profile,
    write_portable_profile,
)


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
