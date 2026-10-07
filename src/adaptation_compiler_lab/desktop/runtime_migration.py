"""Repair installed product endpoints through the existing protected credential rebind."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.credentials import platform_credential_store
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _load_config,
    _registration_signer,
    _replace_config_with_credential_rebind,
)
from adaptation_compiler_lab.connectors.pins import (
    persist_codex_runtime_lock,
    select_product_codex_runtime_lock,
    sha256_file,
)
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.serialization import canonical_digest


@dataclass(frozen=True)
class RuntimeEndpointMigration:
    config_digest: str
    executable: Path
    executable_digest: str
    pin_source: Path
    pin_digest: str
    serialized_legacy_binding: bool


def _admit_legacy_binding(config_path: Path) -> bool:
    config = _load_config(config_path)
    try:
        _registration_signer(config)
        return False
    except ValueError:
        store = platform_credential_store(config.state_root)
        metadata = store.status()
        serialized = canonical_digest(json.loads(config_path.read_text(encoding="utf-8")))
        if metadata is None or serialized != metadata.config_digest:
            raise ValueError(
                "preserved config is not bound to this credential enrollment"
            ) from None
        secrets = store.unlock(
            subject_id=config.subject_id,
            config_digest=serialized,
            signer_fingerprint=config.signer_identity.key_fingerprint,
        )
        signer = GovernanceSigner(
            secrets.private_key(workspace_root=config.repository_root),
            identity_id=config.signer_identity.identity_id,
            subject_id=config.subject_id,
        )
        if signer.fingerprint != config.signer_identity.key_fingerprint:
            raise ValueError("legacy signing identity changed") from None
        return True


def preview_runtime_endpoint_migration(
    config_path: Path, executable: Path
) -> RuntimeEndpointMigration:
    config = _load_config(config_path)
    serialized_legacy = _admit_legacy_binding(config_path)
    candidate = executable.expanduser().resolve(strict=True)
    pin = select_product_codex_runtime_lock(candidate, sys.platform)
    return RuntimeEndpointMigration(
        config_digest=str(canonical_digest(config)),
        executable=candidate,
        executable_digest=sha256_file(candidate),
        pin_source=pin,
        pin_digest=sha256_file(pin),
        serialized_legacy_binding=serialized_legacy,
    )


def apply_runtime_endpoint_migration(config_path: Path, preview: RuntimeEndpointMigration) -> None:
    current = _load_config(config_path)
    if (
        str(canonical_digest(current)) != preview.config_digest
        or sha256_file(preview.executable) != preview.executable_digest
        or sha256_file(preview.pin_source) != preview.pin_digest
        or select_product_codex_runtime_lock(preview.executable, sys.platform) != preview.pin_source
    ):
        raise ValueError("runtime endpoint migration preview changed")
    pin = persist_codex_runtime_lock(preview.pin_source, current.state_root)
    changes: dict[str, object] = {
        "codex_executable": preview.executable,
        "runtime_pin_path": pin,
        "windows_interop": False,
    }
    if current.target_codex_executable == current.codex_executable:
        changes.update(
            target_codex_executable=preview.executable,
            target_runtime_pin_path=pin,
            target_windows_interop=False,
        )
    # Preserve subject, signing identity, policy (including expiry), history, registration cutoffs,
    # and all source/state locations. Persistent learning consent is a separate prospective grant.
    updated = type(current).model_validate(current.model_copy(update=changes).model_dump())
    _replace_config_with_credential_rebind(
        config_path, current, updated, serialized_legacy_binding=preview.serialized_legacy_binding
    )
    _registration_signer(updated)
