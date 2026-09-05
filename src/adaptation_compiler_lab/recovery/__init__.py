"""Offline same-owner identity and governed-state recovery.

Bundle operations are loaded lazily so the unconfigured desktop handshake does not
import the managed runtime merely to expose raw-free recovery presentation models.
"""

from typing import Any

from adaptation_compiler_lab.recovery.models import (
    EncryptedTemperRecoveryBundleV1,
    RecoveryFileV1,
    RecoveryPreviewV1,
    RecoveryProjectSelectionV1,
    RecoveryProjectV1,
    RecoveryRestoreReceiptV1,
    RecoveryRestoreResultV1,
    TemperRecoveryBundleV1,
)

_BUNDLE_EXPORTS = frozenset(
    {
        "TemperRecoveryError",
        "build_recovery_bundle",
        "decrypt_recovery_bundle",
        "encrypt_recovery_bundle",
        "read_recovery_envelope",
        "recovery_preview",
        "rotate_recovery_envelope",
        "verify_recovery_bundle",
        "write_recovery_envelope",
    }
)


def __getattr__(name: str) -> Any:
    if name in _BUNDLE_EXPORTS:
        from adaptation_compiler_lab.recovery import bundle

        return getattr(bundle, name)
    if name == "export_recovery_schemas":
        from adaptation_compiler_lab.recovery.schema_export import export_recovery_schemas

        return export_recovery_schemas
    raise AttributeError(name)


__all__ = [
    "EncryptedTemperRecoveryBundleV1",
    "RecoveryFileV1",
    "RecoveryPreviewV1",
    "RecoveryProjectSelectionV1",
    "RecoveryProjectV1",
    "RecoveryRestoreReceiptV1",
    "RecoveryRestoreResultV1",
    "TemperRecoveryBundleV1",
    "TemperRecoveryError",
    "build_recovery_bundle",
    "decrypt_recovery_bundle",
    "encrypt_recovery_bundle",
    "export_recovery_schemas",
    "read_recovery_envelope",
    "recovery_preview",
    "rotate_recovery_envelope",
    "verify_recovery_bundle",
    "write_recovery_envelope",
]
