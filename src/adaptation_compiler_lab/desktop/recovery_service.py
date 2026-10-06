"""Presentation-neutral offline recovery export, preview, path rebind, and restore."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.automatic_runtime.credentials import (
    PlatformCredentialStore,
    RuntimeSecrets,
    platform_credential_store,
)
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    CodexDogfoodLocalConfig,
    CodexDogfoodProjectConfig,
    _enrollment_binding_digest,
    _ledger,
    _load_config,
)
from adaptation_compiler_lab.automatic_runtime.models import CodexProjectRecoveryBindingV1
from adaptation_compiler_lab.connectors.pins import (
    persist_codex_runtime_lock,
    persistent_codex_runtime_lock_path,
)
from adaptation_compiler_lab.desktop.platform import PlatformPaths
from adaptation_compiler_lab.desktop.preferences import LocalDesktopPreferencesStore
from adaptation_compiler_lab.domain import Sha256Digest
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.recovery.bundle import (
    TemperRecoveryError,
    build_recovery_bundle,
    decrypt_recovery_bundle,
    encrypt_recovery_bundle,
    read_recovery_envelope,
    recovery_preview,
    write_recovery_envelope,
)
from adaptation_compiler_lab.recovery.models import (
    RecoveryFileV1,
    RecoveryPreviewV1,
    RecoveryProjectSelectionV1,
    RecoveryRestoreReceiptV1,
    RecoveryRestoreResultV1,
    TemperRecoveryBundleV1,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_PREVIEW_TTL = timedelta(minutes=10)
_MAX_METADATA_FILES = 10_000
_EXACT_METADATA_FILES = frozenset(
    {
        "successor-receipt.json",
        "runtime/target-authorizations.json",
        "claude-delivery/connection-receipts.json",
        "claude-delivery/hook-ledger.jsonl",
        "claude-delivery/settings-change-receipts.json",
    }
)
_METADATA_PREFIXES = (
    "modes/receipts/",
    "portable-imports/",
    "recovery/",
    "shareable-imports/",
)


@dataclass(frozen=True, slots=True)
class _HeldRecovery:
    bundle: TemperRecoveryBundleV1
    expires_at: datetime
    operation: Literal["export", "restore"]


@dataclass(frozen=True, slots=True)
class _HeldSelection:
    preview_token: str
    project_id: str
    root: Path
    expires_at: datetime


class LocalRecoveryService:
    """Own decrypted recovery state in memory only for one bounded native interaction."""

    def __init__(
        self,
        *,
        paths: PlatformPaths,
        preferences_store: LocalDesktopPreferencesStore,
        codex_executable: Callable[[], Path | None],
        source_codex_home: Callable[[], Path],
        runtime_pin_path: Callable[[], Path],
        credential_store: Callable[[Path], PlatformCredentialStore] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if paths.platform not in {"windows", "macos"}:
            raise TemperRecoveryError("offline recovery requires Windows or macOS")
        self._paths = paths
        self._preferences = preferences_store
        self._codex_executable = codex_executable
        self._source_codex_home = source_codex_home
        self._runtime_pin_path = runtime_pin_path
        self._credential_store_factory = credential_store or (
            lambda root: platform_credential_store(
                root,
                platform_name="win32" if paths.platform == "windows" else "darwin",
            )
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._previews: dict[str, _HeldRecovery] = {}
        self._selections: dict[str, _HeldSelection] = {}

    def export(
        self,
        *,
        config_path: Path,
        passphrase: str,
        destination: Path,
    ) -> RecoveryPreviewV1:
        preview = self.preview_export(config_path=config_path)
        self.write_export(
            preview_token=preview.preview_token,
            expected_bundle_digest=str(preview.bundle_digest),
            passphrase=passphrase,
            destination=destination,
        )
        return preview

    def preview_export(self, *, config_path: Path) -> RecoveryPreviewV1:
        """Prepare and hold one exact owner backup for a raw-free confirmation."""

        self._purge_expired()
        config = _load_config(config_path)
        metadata = self._credential_store_factory(config.state_root).status()
        if metadata is None:
            raise TemperRecoveryError("the native secure store is unavailable")
        secrets_value = self._credential_store_factory(config.state_root).unlock(
            subject_id=config.subject_id,
            config_digest=_enrollment_binding_digest(config, metadata),
            signer_fingerprint=config.signer_identity.key_fingerprint,
        )
        signer = GovernanceSigner(
            secrets_value.private_key(workspace_root=config.repository_root),
            identity_id=config.signer_identity.identity_id,
            subject_id=config.subject_id,
        )
        now = self._clock()
        bundle = build_recovery_bundle(
            config,
            secrets_value,
            _collect_recovery_files(config),
            signer=signer,
            source_platform=cast(Literal["windows", "macos"], self._paths.platform),
            bundle_id=f"temper-recovery-{now.strftime('%Y%m%dT%H%M%SZ')}",
            created_at=now,
        )
        token = f"recovery-export-{secrets.token_hex(12)}"
        preview = recovery_preview(
            bundle,
            preview_token=token,
            expires_at=now + _PREVIEW_TTL,
        )
        self._previews[token] = _HeldRecovery(
            bundle=bundle,
            expires_at=preview.expires_at,
            operation="export",
        )
        return preview

    def write_export(
        self,
        *,
        preview_token: str,
        expected_bundle_digest: str,
        passphrase: str,
        destination: Path,
    ) -> RecoveryPreviewV1:
        """Encrypt and write exactly the recovery material the owner previewed."""

        held = self._require_preview(preview_token, operation="export")
        if str(held.bundle.content_digest) != expected_bundle_digest:
            raise TemperRecoveryError("recovery bundle changed after preview")
        envelope = encrypt_recovery_bundle(held.bundle, passphrase=passphrase)
        write_recovery_envelope(envelope, destination)
        preview = recovery_preview(
            held.bundle,
            preview_token=preview_token,
            expires_at=held.expires_at,
        )
        del self._previews[preview_token]
        return preview

    def preview_import(self, *, source: Path, passphrase: str) -> RecoveryPreviewV1:
        self._purge_expired()
        envelope = read_recovery_envelope(source)
        bundle = decrypt_recovery_bundle(envelope, passphrase=passphrase)
        now = self._clock()
        token = f"recovery-preview-{secrets.token_hex(12)}"
        preview = recovery_preview(bundle, preview_token=token, expires_at=now + _PREVIEW_TTL)
        self._previews[token] = _HeldRecovery(
            bundle=bundle,
            expires_at=preview.expires_at,
            operation="restore",
        )
        return preview

    def select_project_root(
        self, *, preview_token: str, project_id: str, root: Path
    ) -> RecoveryProjectSelectionV1:
        held = self._require_preview(preview_token, operation="restore")
        project = next(
            (item for item in held.bundle.projects if item.project_id == project_id), None
        )
        if project is None:
            raise TemperRecoveryError("recovery project is unavailable")
        resolved = root.expanduser().resolve()
        if not resolved.is_dir() or resolved.is_symlink():
            raise TemperRecoveryError("recovery project root must be an existing local directory")
        destination = (self._paths.state_root / "runtime").resolve()
        if (
            resolved == destination
            or resolved.is_relative_to(destination)
            or destination.is_relative_to(resolved)
        ):
            raise TemperRecoveryError("recovery project root overlaps Temper storage")
        token = f"recovery-project-{secrets.token_hex(12)}"
        self._selections[token] = _HeldSelection(
            preview_token=preview_token,
            project_id=project_id,
            root=resolved,
            expires_at=held.expires_at,
        )
        return RecoveryProjectSelectionV1(
            selection_token=token,
            preview_token=preview_token,
            project_id=project_id,
            display_name=resolved.name or project.display_name,
            expires_at=held.expires_at,
        )

    def restore(
        self,
        *,
        preview_token: str,
        project_selection_tokens: Mapping[str, str],
        expected_bundle_digest: str,
        confirmed: bool,
    ) -> RecoveryRestoreResultV1:
        if not confirmed:
            raise TemperRecoveryError("explicit recovery confirmation is required")
        held = self._require_preview(preview_token, operation="restore")
        bundle = held.bundle
        if str(bundle.content_digest) != expected_bundle_digest:
            raise TemperRecoveryError("recovery bundle changed after preview")
        expected_projects = {item.project_id for item in bundle.projects}
        if set(project_selection_tokens) != expected_projects:
            raise TemperRecoveryError("every recovered project requires one new local root")
        selected: dict[str, Path] = {}
        for project_id, token in project_selection_tokens.items():
            selection = self._selections.get(token)
            if (
                selection is None
                or selection.preview_token != preview_token
                or selection.project_id != project_id
                or selection.expires_at <= self._clock()
            ):
                raise TemperRecoveryError("recovery project selection expired or changed")
            selected[project_id] = selection.root
        _require_non_overlapping_projects(selected)
        executable = self._codex_executable()
        if executable is None or not executable.is_file():
            raise TemperRecoveryError("compatible Codex must be installed before recovery")
        destination = (self._paths.state_root / "runtime").resolve()
        if destination.exists() and any(destination.iterdir()):
            raise TemperRecoveryError(
                "Temper is already configured; recovery will not overwrite it"
            )
        if destination.exists() and destination.is_symlink():
            raise TemperRecoveryError("Temper recovery destination is unsafe")
        source_config = CodexDogfoodLocalConfig.model_validate_json(
            bundle.config_payload, strict=True
        )
        runtime_secrets = RuntimeSecrets.from_bytes(bundle.runtime_secrets_payload)
        signer = GovernanceSigner(
            runtime_secrets.private_key(workspace_root=source_config.repository_root),
            identity_id=source_config.signer_identity.identity_id,
            subject_id=source_config.subject_id,
        )
        restored_at = self._clock()
        projects = tuple(
            _rebind_project(
                project,
                root=selected[project.project_id],
                bundle_digest=bundle.content_digest,
                source_project_digest=next(
                    item.source_project_digest
                    for item in bundle.projects
                    if item.project_id == project.project_id
                ),
                signer=signer,
                rebound_at=restored_at,
            )
            for project in source_config.projects
        )
        runtime_pin_source = self._runtime_pin_path().expanduser().resolve()
        runtime_pin_path = persistent_codex_runtime_lock_path(runtime_pin_source, destination)
        restored = CodexDogfoodLocalConfig.model_validate(
            source_config.model_copy(
                update={
                    "config_version": "1.5.0",
                    "repository_root": projects[0].root,
                    "state_root": destination,
                    "database_path": destination / "runtime.sqlite3",
                    "raw_store_path": destination / "raw",
                    "source_codex_home": self._source_codex_home().expanduser().resolve(),
                    "codex_executable": executable.resolve(),
                    "windows_interop": False,
                    "runtime_pin_path": runtime_pin_path,
                    "projects": projects,
                    "target_codex_home": None,
                    "target_codex_executable": None,
                    "target_windows_interop": None,
                    "target_runtime_pin_path": None,
                    "gateway_workspace_root": (
                        None
                        if source_config.gateway_workspace_root is None
                        else destination / "workspaces"
                    ),
                }
            ).model_dump(mode="python"),
            strict=True,
        )
        receipt = self._restore_atomically(
            bundle=bundle,
            restored=restored,
            runtime_secrets=runtime_secrets,
            signer=signer,
            restored_at=restored_at,
            runtime_pin_source=runtime_pin_source,
        )
        try:
            preferences = self._preferences.load().model_copy(
                update={
                    "background_enabled": False,
                    "decision_notifications_enabled": False,
                    "launch_at_login_enabled": False,
                    "runtime_config_path": destination / "config.json",
                }
            )
            self._preferences.save(preferences)
        except BaseException:
            self._rollback_restore(destination)
            raise
        del self._previews[preview_token]
        self._selections = {
            key: value
            for key, value in self._selections.items()
            if value.preview_token != preview_token
        }
        return RecoveryRestoreResultV1(
            receipt_id=receipt.receipt_id,
            restoration_digest=receipt.content_digest,
            project_count=len(projects),
        )

    def _restore_atomically(
        self,
        *,
        bundle: TemperRecoveryBundleV1,
        restored: CodexDogfoodLocalConfig,
        runtime_secrets: RuntimeSecrets,
        signer: GovernanceSigner,
        restored_at: datetime,
        runtime_pin_source: Path,
    ) -> RecoveryRestoreReceiptV1:
        destination = restored.state_root
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".temper-recovery-", dir=destination.parent))
        enrolled = False
        try:
            for item in bundle.files:
                target = (stage / item.logical_path).resolve()
                if not target.is_relative_to(stage):
                    raise TemperRecoveryError("recovery file escaped its staging directory")
                target.parent.mkdir(parents=True, exist_ok=True)
                _write_new_file(target, item.payload)
            persist_codex_runtime_lock(runtime_pin_source, destination, staging_root=stage)
            staged_config = restored.model_copy(
                update={
                    "state_root": destination,
                    "database_path": destination / "runtime.sqlite3",
                    "raw_store_path": destination / "raw",
                }
            )
            _write_new_file(
                stage / "config.json",
                (canonical_json(staged_config) + "\n").encode("utf-8"),
            )
            if destination.exists():
                destination.rmdir()
            os.replace(stage, destination)
            store = self._credential_store_factory(destination)
            store.enroll(
                runtime_secrets,
                subject_id=restored.subject_id,
                config_digest=restored.credential_binding_digest,
                signer_fingerprint=restored.signer_identity.key_fingerprint,
                enrolled_at=restored_at,
            )
            enrolled = True
            receipt = _build_restore_receipt(
                bundle,
                restored,
                signer=signer,
                target_platform=self._paths.platform,
                restored_at=restored_at,
            )
            verify_detached_envelope(
                receipt.unsigned_payload,
                receipt.signature,
                public_key_base64=restored.signer_identity.public_key_base64,
                expected_purpose="temper_recovery_restore",
            )
            receipt_path = destination / "recovery" / "restore-receipt.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            _write_new_file(
                receipt_path,
                (canonical_json(receipt) + "\n").encode("utf-8"),
            )
            _load_config(destination / "config.json")
            if _ledger(restored).current() is None:
                raise TemperRecoveryError("recovered governed ledger has no current state")
            return receipt
        except BaseException:
            if enrolled:
                with suppress(ValueError):
                    self._credential_store_factory(destination).revoke()
            if stage.exists() and stage.parent == destination.parent:
                shutil.rmtree(stage, ignore_errors=True)
            if destination.exists() and destination.parent == self._paths.state_root.resolve():
                shutil.rmtree(destination, ignore_errors=True)
            raise

    def _rollback_restore(self, destination: Path) -> None:
        """Remove only this incomplete fresh restore if final preference binding fails."""

        with suppress(ValueError):
            self._credential_store_factory(destination).revoke()
        expected = (self._paths.state_root / "runtime").resolve()
        if destination.resolve() == expected and destination.exists():
            shutil.rmtree(destination, ignore_errors=True)

    def _require_preview(
        self,
        preview_token: str,
        *,
        operation: Literal["export", "restore"],
    ) -> _HeldRecovery:
        self._purge_expired()
        held = self._previews.get(preview_token)
        if held is None or held.operation != operation:
            raise TemperRecoveryError("recovery preview expired")
        return held

    def _purge_expired(self) -> None:
        """Release decrypted previews and their opaque path selections after the TTL."""

        now = self._clock()
        expired = {token for token, held in self._previews.items() if held.expires_at <= now}
        if not expired:
            return
        self._previews = {
            token: held for token, held in self._previews.items() if token not in expired
        }
        self._selections = {
            token: selection
            for token, selection in self._selections.items()
            if selection.preview_token not in expired and selection.expires_at > now
        }


def _collect_recovery_files(config: CodexDogfoodLocalConfig) -> tuple[RecoveryFileV1, ...]:
    root = config.state_root.expanduser().resolve()
    if config.database_path.resolve().parent != root or not config.database_path.is_file():
        raise TemperRecoveryError("governed recovery ledger is unavailable")
    entries = [_sqlite_backup_entry(config.database_path)]
    candidates: list[Path] = []
    raw_root = config.raw_store_path.resolve()
    if raw_root.is_dir() and raw_root.parent == root and not raw_root.is_symlink():
        candidates.extend(path for path in raw_root.rglob("*") if path.is_file())
    for exact in _EXACT_METADATA_FILES:
        candidate = root / exact
        if candidate.is_file():
            candidates.append(candidate)
    for prefix in _METADATA_PREFIXES:
        candidate_root = root / prefix
        if candidate_root.is_dir() and not candidate_root.is_symlink():
            candidates.extend(path for path in candidate_root.rglob("*") if path.is_file())
    unique = sorted({path.resolve() for path in candidates})
    if len(unique) > _MAX_METADATA_FILES:
        raise TemperRecoveryError("recovery state contains too many files")
    for path in unique:
        if path.is_symlink() or not path.is_relative_to(root):
            raise TemperRecoveryError("recovery state contains an unsafe file")
        logical = path.relative_to(root).as_posix()
        if logical in {"config.json", "credential-envelope.json"}:
            continue
        entries.append(_file_entry(path, logical_path=logical))
    return tuple(sorted(entries, key=lambda item: item.logical_path))


def _sqlite_backup_entry(source: Path) -> RecoveryFileV1:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".temper-ledger-", suffix=".sqlite3")
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        target_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()
        return _file_entry(temporary, logical_path="runtime.sqlite3")
    except sqlite3.Error as error:
        raise TemperRecoveryError("governed ledger could not be snapshotted") from error
    finally:
        temporary.unlink(missing_ok=True)


def _file_entry(path: Path, *, logical_path: str) -> RecoveryFileV1:
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise TemperRecoveryError("recovery source changed while it was being read")
    if logical_path.startswith("raw/") and not payload.startswith(b"ACLAB-RAW-1\n"):
        raise TemperRecoveryError("recovery raw payload is not an encrypted Temper envelope")
    return RecoveryFileV1(
        logical_path=logical_path,
        content_digest=Sha256Digest(f"sha256:{hashlib.sha256(payload).hexdigest()}"),
        byte_length=len(payload),
        payload_base64=base64.b64encode(payload).decode("ascii"),
    )


def _rebind_project(
    source: CodexDogfoodProjectConfig,
    *,
    root: Path,
    bundle_digest: str,
    source_project_digest: str,
    signer: GovernanceSigner,
    rebound_at: datetime,
) -> CodexDogfoodProjectConfig:
    placeholder = signer.envelope(
        {}, purpose="codex_project_recovery_binding", signed_at=rebound_at
    )
    draft = CodexProjectRecoveryBindingV1(
        binding_id=f"recover-{source.project_id}-{secrets.token_hex(8)}",
        subject_id=signer.subject_id,
        project_id=source.project_id,
        source_project_digest=source_project_digest,
        recovery_bundle_digest=bundle_digest,
        restored_project_root_digest=canonical_digest({"project_root": str(root)}),
        restored_source_roots_digest=canonical_digest({"source_roots": [str(root)]}),
        rebound_at=rebound_at,
        signature=placeholder,
    )
    binding = draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose="codex_project_recovery_binding",
                signed_at=rebound_at,
            )
        }
    )
    return CodexDogfoodProjectConfig.model_validate(
        source.model_copy(
            update={"root": root, "source_roots": (root,), "recovery_binding": binding}
        ).model_dump(mode="python"),
        strict=True,
    )


def _build_restore_receipt(
    bundle: TemperRecoveryBundleV1,
    restored: CodexDogfoodLocalConfig,
    *,
    signer: GovernanceSigner,
    target_platform: str,
    restored_at: datetime,
) -> RecoveryRestoreReceiptV1:
    if target_platform not in {"windows", "macos"}:
        raise TemperRecoveryError("recovery target platform is unsupported")
    bindings = tuple(
        sorted(
            project.recovery_binding.content_digest
            for project in restored.projects
            if project.recovery_binding is not None
        )
    )
    placeholder = signer.envelope({}, purpose="temper_recovery_restore", signed_at=restored_at)
    draft = RecoveryRestoreReceiptV1(
        receipt_id=f"restore-{secrets.token_hex(12)}",
        subject_id=restored.subject_id,
        bundle_id=bundle.bundle_id,
        bundle_digest=bundle.content_digest,
        source_config_digest=bundle.source_config_digest,
        restored_config_digest=restored.credential_binding_digest,
        restored_file_manifest_digest=canonical_digest(
            {
                "files": [
                    {
                        "byte_length": item.byte_length,
                        "content_digest": item.content_digest,
                        "logical_path": item.logical_path,
                    }
                    for item in bundle.files
                ]
            }
        ),
        project_binding_digests=bindings,
        target_platform=cast(Literal["windows", "macos"], target_platform),
        restored_at=restored_at,
        signer_identity_id=restored.signer_identity.identity_id,
        signer_fingerprint=restored.signer_identity.key_fingerprint,
        signature=placeholder,
    )
    return draft.model_copy(
        update={
            "signature": signer.envelope(
                draft.unsigned_payload,
                purpose="temper_recovery_restore",
                signed_at=restored_at,
            )
        }
    )


def _require_non_overlapping_projects(projects: Mapping[str, Path]) -> None:
    values = tuple(projects.items())
    for index, (project_id, root) in enumerate(values):
        for other_id, other in values[index + 1 :]:
            if root == other or root.is_relative_to(other) or other.is_relative_to(root):
                raise TemperRecoveryError(
                    f"recovered project selections overlap: {project_id} and {other_id}"
                )


def _write_new_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
