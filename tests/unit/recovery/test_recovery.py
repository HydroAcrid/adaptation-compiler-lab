from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.automatic_runtime.credentials import (
    DpapiCredentialStore,
    RuntimeSecrets,
)
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    CodexDogfoodLocalConfig,
    CodexDogfoodProjectConfig,
    _ledger,
)
from adaptation_compiler_lab.automatic_runtime.models import StandingAutomationPolicy
from adaptation_compiler_lab.automatic_runtime.service import initial_runtime_state
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_DOGFOOD_WINDOWS_RUNTIME_LOCK,
    load_dogfood_runtime_pins,
)
from adaptation_compiler_lab.desktop.platform import PlatformPaths
from adaptation_compiler_lab.desktop.preferences import (
    DesktopPreferences,
    LocalDesktopPreferencesStore,
)
from adaptation_compiler_lab.desktop.recovery_service import LocalRecoveryService
from adaptation_compiler_lab.domain import ArtifactRoute, PermittedUse, Scope
from adaptation_compiler_lab.governance import GovernanceEventType, SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    sign_governance_event,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from adaptation_compiler_lab.recovery import (
    TemperRecoveryError,
    decrypt_recovery_bundle,
    read_recovery_envelope,
    rotate_recovery_envelope,
)
from adaptation_compiler_lab.recovery.schema_export import recovery_schema_bundle
from adaptation_compiler_lab.serialization import canonical_json

NOW = datetime(2026, 9, 5, 19, tzinfo=UTC)
PASSPHRASE = "correct horse battery staple"
NEW_PASSPHRASE = "different correct battery staple"


class FakeProtector:
    def protect(self, plaintext: bytes, *, entropy: bytes) -> bytes:
        return bytes(value ^ entropy[index % len(entropy)] for index, value in enumerate(plaintext))

    def unprotect(self, ciphertext: bytes, *, entropy: bytes) -> bytes:
        return self.protect(ciphertext, entropy=entropy)


def _store(root: Path) -> DpapiCredentialStore:
    return DpapiCredentialStore(root, protector=FakeProtector())


def _source_runtime(
    tmp_path: Path,
    *,
    roles: tuple[SignerRole, ...] = (
        SignerRole.ACTIVATION,
        SignerRole.CONSENT,
        SignerRole.CUSTODY,
        SignerRole.RELEASE,
        SignerRole.REVIEW,
    ),
) -> tuple[Path, RuntimeSecrets, RawPayloadRef]:
    project = tmp_path / "source" / "Green Meadow"
    project.mkdir(parents=True)
    state = tmp_path / "source-app" / "runtime"
    state.mkdir(parents=True)
    codex = tmp_path / "source" / "codex.exe"
    codex.write_bytes(b"synthetic-codex")
    codex_home = tmp_path / "source" / "codex-home"
    codex_home.mkdir()
    pin = tmp_path / "source" / "runtime-pin.json"
    pin.write_text("{}", encoding="utf-8")
    secrets_value = RuntimeSecrets.generate_managed()
    signer = GovernanceSigner(
        Ed25519PrivateKey.from_private_bytes(secrets_value.managed_signing_key or b""),
        identity_id="recovery-owner",
        subject_id="kevin",
    )
    identity = create_signer_identity(
        signer,
        roles=roles,
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
    )
    policy = StandingAutomationPolicy(
        policy_id="recovery-policy",
        subject_id="kevin",
        scope=Scope(
            subject_ids=("kevin",),
            project_ids=("green-meadow",),
            target_families=("codex",),
        ),
        permitted_uses=(
            PermittedUse.AUDIT,
            PermittedUse.CONSTRUCTION,
            PermittedUse.PROMOTION,
            PermittedUse.TARGET_DELIVERY,
        ),
        allowed_routes=(
            ArtifactRoute.EXAMPLE,
            ArtifactRoute.MEMORY,
            ArtifactRoute.PREFERENCE,
            ArtifactRoute.PROCEDURE,
            ArtifactRoute.PROMPT_RULE,
        ),
        allowed_target_families=("codex",),
        effective_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=29),
    )
    authorization = sign_governance_event(
        {
            "event_id": "enable-recovery-policy",
            "subject_id": "kevin",
            "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
            "target_ref": policy.authorization_target_ref,
            "target_digest": policy.content_digest,
            "decision": "enabled",
            "reason": "Enable the synthetic recovery fixture.",
            "policy_version": policy.policy_version,
            "occurred_at": NOW.isoformat(),
        },
        signer,
    )
    config = CodexDogfoodLocalConfig(
        subject_id="kevin",
        repository_root=project,
        state_root=state,
        database_path=state / "runtime.sqlite3",
        raw_store_path=state / "raw",
        source_codex_home=codex_home,
        codex_executable=codex,
        windows_interop=True,
        runtime_pin_path=pin,
        capture_after_epoch_seconds=int(NOW.timestamp()),
        policy=policy,
        policy_authorization=authorization,
        signer_identity=identity,
        projects=(
            CodexDogfoodProjectConfig(
                project_id="green-meadow",
                root=project,
                scope=Scope(
                    subject_ids=("kevin",),
                    project_ids=("green-meadow",),
                    target_families=("codex",),
                ),
                source_roots=(project,),
            ),
        ),
    )
    config_path = state / "config.json"
    config_path.write_text(canonical_json(config) + "\n", encoding="utf-8")
    _store(state).enroll(
        secrets_value,
        subject_id=config.subject_id,
        config_digest=config.credential_binding_digest,
        signer_fingerprint=config.signer_identity.key_fingerprint,
        enrolled_at=NOW,
    )
    _ledger(config).initialize(initial_runtime_state(policy))
    assert secrets_value.managed_raw_key is not None
    raw_store = LocalRawPayloadStore(
        config.raw_store_path,
        encryption_key=RawEncryptionKey(secrets_value.managed_raw_key),
    )
    raw_reference = raw_store.put(b"private synthetic feedback", media_type="text/plain")
    return config_path, secrets_value, raw_reference


def _paths(root: Path) -> PlatformPaths:
    return PlatformPaths(
        platform="windows",
        state_root=root / "state",
        config_root=root / "preferences",
        historical_state_root=root / "old-state",
        historical_config_root=root / "old-preferences",
    )


def test_encrypted_recovery_round_trip_rotation_and_tamper_detection(tmp_path: Path) -> None:
    config_path, _secrets, _raw_reference = _source_runtime(tmp_path)
    source_paths = _paths(tmp_path / "source-product")
    preferences = LocalDesktopPreferencesStore(source_paths.config_root)
    source_service = LocalRecoveryService(
        paths=source_paths,
        preferences_store=preferences,
        codex_executable=lambda: Path("missing"),
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: NOW,
    )
    output = tmp_path / "owner.temper-recovery"

    preview = source_service.export(
        config_path=config_path,
        passphrase=PASSPHRASE,
        destination=output,
    )
    envelope = read_recovery_envelope(output)
    bundle = decrypt_recovery_bundle(envelope, passphrase=PASSPHRASE)
    rotated = rotate_recovery_envelope(
        envelope,
        current_passphrase=PASSPHRASE,
        new_passphrase=NEW_PASSPHRASE,
    )

    assert len(preview.projects) == 1
    assert config_path.parent.as_posix() not in preview.model_dump_json()
    assert bundle.runtime_secrets_payload not in output.read_bytes()
    assert decrypt_recovery_bundle(rotated, passphrase=NEW_PASSPHRASE) == bundle
    with pytest.raises(TemperRecoveryError, match="decrypted"):
        decrypt_recovery_bundle(rotated, passphrase=PASSPHRASE)

    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["plaintext_digest"] = f"sha256:{'f' * 64}"
    output.write_text(json.dumps(payload), encoding="utf-8")
    tampered = read_recovery_envelope(output)
    with pytest.raises(TemperRecoveryError, match="digest changed"):
        decrypt_recovery_bundle(tampered, passphrase=PASSPHRASE)


def test_recovery_restores_identity_ledger_raw_payload_and_rebinds_project(
    tmp_path: Path,
) -> None:
    config_path, secrets_value, raw_reference = _source_runtime(tmp_path)
    source_paths = _paths(tmp_path / "source-product")
    source_service = LocalRecoveryService(
        paths=source_paths,
        preferences_store=LocalDesktopPreferencesStore(source_paths.config_root),
        codex_executable=lambda: Path("missing"),
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: NOW,
    )
    output = tmp_path / "owner.temper-recovery"
    source_service.export(
        config_path=config_path,
        passphrase=PASSPHRASE,
        destination=output,
    )

    target_root = tmp_path / "target-product"
    target_paths = _paths(target_root)
    target_project = tmp_path / "restored" / "Green Meadow"
    target_project.mkdir(parents=True)
    target_codex = tmp_path / "restored" / "codex.exe"
    target_codex.write_bytes(b"synthetic-codex")
    target_codex_home = tmp_path / "restored" / "codex-home"
    target_codex_home.mkdir()
    target_pin = tmp_path / "restored" / "runtime-pin.json"
    target_pin.write_bytes(DEFAULT_DOGFOOD_WINDOWS_RUNTIME_LOCK.read_bytes())
    target_preferences = LocalDesktopPreferencesStore(target_paths.config_root)
    target_preferences.save(DesktopPreferences())
    target_service = LocalRecoveryService(
        paths=target_paths,
        preferences_store=target_preferences,
        codex_executable=lambda: target_codex,
        source_codex_home=lambda: target_codex_home,
        runtime_pin_path=lambda: target_pin,
        credential_store=_store,
        clock=lambda: NOW + timedelta(hours=1),
    )
    preview = target_service.preview_import(source=output, passphrase=PASSPHRASE)
    selection = target_service.select_project_root(
        preview_token=preview.preview_token,
        project_id="green-meadow",
        root=target_project,
    )
    with pytest.raises(TemperRecoveryError, match="explicit recovery confirmation"):
        target_service.restore(
            preview_token=preview.preview_token,
            project_selection_tokens={"green-meadow": selection.selection_token},
            expected_bundle_digest=str(preview.bundle_digest),
            confirmed=False,
        )
    result = target_service.restore(
        preview_token=preview.preview_token,
        project_selection_tokens={"green-meadow": selection.selection_token},
        expected_bundle_digest=str(preview.bundle_digest),
        confirmed=True,
    )

    restored_path = target_paths.state_root / "runtime" / "config.json"
    restored = CodexDogfoodLocalConfig.model_validate_json(restored_path.read_text(), strict=True)
    assert restored.runtime_pin_path.is_relative_to(restored.state_root)
    target_pin.unlink()
    assert load_dogfood_runtime_pins(restored.runtime_pin_path).codex.executable.package_version
    restored_secrets = _store(restored.state_root).unlock(
        subject_id=restored.subject_id,
        config_digest=restored.credential_binding_digest,
        signer_fingerprint=restored.signer_identity.key_fingerprint,
    )
    assert result.configured is True
    assert restored.config_version == "1.5.0"
    assert restored.windows_interop is False
    assert restored.subject_id == "kevin"
    assert restored.projects[0].root == target_project
    assert restored.projects[0].recovery_binding is not None
    assert restored_secrets == secrets_value
    assert _ledger(restored).current() == initial_runtime_state(restored.policy)
    assert restored_secrets.managed_raw_key is not None
    raw_store = LocalRawPayloadStore(
        restored.raw_store_path,
        encryption_key=RawEncryptionKey(restored_secrets.managed_raw_key),
    )
    assert raw_store.read(raw_reference) == b"private synthetic feedback"
    assert (restored.state_root / "recovery" / "restore-receipt.json").is_file()
    assert target_preferences.load().runtime_config_path == restored_path
    assert target_preferences.load().background_enabled is False

    tampered_payload = json.loads(restored_path.read_text(encoding="utf-8"))
    tampered_payload["projects"][0]["root"] = str(tmp_path / "different-project")
    with pytest.raises(ValueError, match="binding does not match"):
        CodexDogfoodLocalConfig.model_validate_json(json.dumps(tampered_payload), strict=True)


def test_recovery_never_overwrites_an_existing_installation(tmp_path: Path) -> None:
    config_path, _secrets, _raw_reference = _source_runtime(tmp_path)
    source_paths = _paths(tmp_path / "source-product")
    source = LocalRecoveryService(
        paths=source_paths,
        preferences_store=LocalDesktopPreferencesStore(source_paths.config_root),
        codex_executable=lambda: Path("missing"),
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: NOW,
    )
    output = tmp_path / "owner.temper-recovery"
    source.export(config_path=config_path, passphrase=PASSPHRASE, destination=output)
    target_paths = _paths(tmp_path / "target-product")
    destination = target_paths.state_root / "runtime"
    destination.mkdir(parents=True)
    (destination / "keep.txt").write_text("owner data", encoding="utf-8")
    target_codex = tmp_path / "target-codex.exe"
    target_codex.write_bytes(b"synthetic-codex")
    target = LocalRecoveryService(
        paths=target_paths,
        preferences_store=LocalDesktopPreferencesStore(target_paths.config_root),
        codex_executable=lambda: target_codex,
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: NOW,
    )
    preview = target.preview_import(source=output, passphrase=PASSPHRASE)
    restored_project = tmp_path / "new-project"
    restored_project.mkdir()
    selection = target.select_project_root(
        preview_token=preview.preview_token,
        project_id="green-meadow",
        root=restored_project,
    )

    with pytest.raises(TemperRecoveryError):
        target.restore(
            preview_token=preview.preview_token,
            project_selection_tokens={"green-meadow": selection.selection_token},
            expected_bundle_digest=str(preview.bundle_digest),
            confirmed=True,
        )
    assert (destination / "keep.txt").read_text() == "owner data"


def test_recovery_schema_snapshots_are_current() -> None:
    root = Path(__file__).resolve().parents[3] / "schemas" / "recovery" / "v1"
    expected = recovery_schema_bundle()

    assert {path.name for path in root.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in expected
    }
    for name, schema in expected.items():
        assert json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8")) == schema


def test_recovery_export_requires_custody_authority(tmp_path: Path) -> None:
    config_path, _secrets, _raw_reference = _source_runtime(
        tmp_path,
        roles=(
            SignerRole.ACTIVATION,
            SignerRole.CONSENT,
            SignerRole.RELEASE,
            SignerRole.REVIEW,
        ),
    )
    paths = _paths(tmp_path / "product")
    service = LocalRecoveryService(
        paths=paths,
        preferences_store=LocalDesktopPreferencesStore(paths.config_root),
        codex_executable=lambda: None,
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: NOW,
    )

    with pytest.raises(TemperRecoveryError, match="custody-authorized"):
        service.preview_export(config_path=config_path)


def test_recovery_rejects_plaintext_in_the_raw_store(tmp_path: Path) -> None:
    config_path, _secrets, _raw_reference = _source_runtime(tmp_path)
    config = CodexDogfoodLocalConfig.model_validate_json(
        config_path.read_text(encoding="utf-8"), strict=True
    )
    raw_file = next(path for path in config.raw_store_path.rglob("*") if path.is_file())
    raw_file.write_text("plaintext must never enter recovery", encoding="utf-8")
    paths = _paths(tmp_path / "product")
    service = LocalRecoveryService(
        paths=paths,
        preferences_store=LocalDesktopPreferencesStore(paths.config_root),
        codex_executable=lambda: None,
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: NOW,
    )

    with pytest.raises(TemperRecoveryError, match="not an encrypted Temper envelope"):
        service.preview_export(config_path=config_path)


def test_recovery_releases_expired_decrypted_preview_and_path_selections(
    tmp_path: Path,
) -> None:
    config_path, _secrets, _raw_reference = _source_runtime(tmp_path)
    source_paths = _paths(tmp_path / "source-product")
    source = LocalRecoveryService(
        paths=source_paths,
        preferences_store=LocalDesktopPreferencesStore(source_paths.config_root),
        codex_executable=lambda: None,
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: NOW,
    )
    output = tmp_path / "owner.temper-recovery"
    source.export(config_path=config_path, passphrase=PASSPHRASE, destination=output)

    current_time = [NOW]
    target_paths = _paths(tmp_path / "target-product")
    target = LocalRecoveryService(
        paths=target_paths,
        preferences_store=LocalDesktopPreferencesStore(target_paths.config_root),
        codex_executable=lambda: None,
        source_codex_home=lambda: tmp_path / "unused",
        runtime_pin_path=lambda: tmp_path / "unused-pin",
        credential_store=_store,
        clock=lambda: current_time[0],
    )
    preview = target.preview_import(source=output, passphrase=PASSPHRASE)
    project_root = tmp_path / "rebound-project"
    project_root.mkdir()
    target.select_project_root(
        preview_token=preview.preview_token,
        project_id="green-meadow",
        root=project_root,
    )

    current_time[0] = NOW + timedelta(minutes=11)
    with pytest.raises(TemperRecoveryError, match="preview expired"):
        target.select_project_root(
            preview_token=preview.preview_token,
            project_id="green-meadow",
            root=project_root,
        )

    assert target._previews == {}
    assert target._selections == {}
