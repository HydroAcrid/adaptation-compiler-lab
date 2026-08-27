from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.credentials import (
    CredentialStoreError,
    DpapiCredentialStore,
    MacOSKeychainCredentialStore,
    RuntimeSecrets,
    WindowsDpapiProtector,
    platform_credential_store,
)
from adaptation_compiler_lab.automatic_runtime.macos_keychain import (
    KeychainBackendError,
    SecurityFrameworkKeychainBackend,
)

DIGEST = f"sha256:{'a' * 64}"
OTHER_DIGEST = f"sha256:{'b' * 64}"


class FakeProtector:
    def protect(self, plaintext: bytes, *, entropy: bytes) -> bytes:
        return bytes(value ^ entropy[index % len(entropy)] for index, value in enumerate(plaintext))

    def unprotect(self, ciphertext: bytes, *, entropy: bytes) -> bytes:
        return self.protect(ciphertext, entropy=entropy)


class FakeKeychain:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], bytes] = {}

    def add(self, *, service: str, account: str, payload: bytes) -> None:
        key = (service, account)
        if key in self.items:
            raise KeychainBackendError("duplicate")
        self.items[key] = payload

    def get(self, *, service: str, account: str) -> bytes | None:
        return self.items.get((service, account))

    def update(self, *, service: str, account: str, payload: bytes) -> None:
        key = (service, account)
        if key not in self.items:
            raise KeychainBackendError("missing")
        self.items[key] = payload

    def delete(self, *, service: str, account: str) -> bool:
        return self.items.pop((service, account), None) is not None


def _secrets(tmp_path: Path) -> RuntimeSecrets:
    return RuntimeSecrets(
        signing_key_file=tmp_path / "signing.pem",
        signing_key_passphrase="correct horse battery staple",
        raw_key_file=tmp_path / "raw.key",
    )


def test_same_binding_unlocks_without_serializing_plaintext(tmp_path: Path) -> None:
    store = DpapiCredentialStore(tmp_path / "state", protector=FakeProtector())
    secrets = _secrets(tmp_path)

    metadata = store.enroll(
        secrets,
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )

    assert (
        store.unlock(
            subject_id="kevin",
            config_digest=DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )
        == secrets
    )
    stored = (tmp_path / "state" / "credential-envelope.json").read_text()
    assert secrets.signing_key_passphrase is not None
    assert secrets.signing_key_passphrase not in stored
    assert metadata.protector == "windows-dpapi-current-user"
    assert metadata.envelope_version == "1.1.0"


def test_legacy_v1_windows_metadata_remains_readable(tmp_path: Path) -> None:
    store = DpapiCredentialStore(tmp_path / "state", protector=FakeProtector())
    secrets = _secrets(tmp_path)
    store.enroll(
        secrets,
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )
    envelope = tmp_path / "state" / "credential-envelope.json"
    payload = json.loads(envelope.read_text(encoding="utf-8"))
    metadata = payload["metadata"]
    metadata["envelope_version"] = "1.0.0"
    metadata["ciphertext_digest"] = metadata.pop("protected_payload_digest")
    envelope.write_text(json.dumps(payload), encoding="utf-8")

    assert store.status() is not None
    assert store.status().envelope_version == "1.0.0"  # type: ignore[union-attr]
    assert (
        store.unlock(
            subject_id="kevin",
            config_digest=DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )
        == secrets
    )


def test_managed_keys_round_trip_without_files_or_environment(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    store = DpapiCredentialStore(tmp_path / "state", protector=FakeProtector())
    secrets = RuntimeSecrets.generate_managed()

    store.enroll(
        secrets,
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )
    unlocked = store.unlock(
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )

    assert unlocked == secrets
    assert unlocked.managed is True
    assert unlocked.private_key(workspace_root=repository) is not None
    assert len(unlocked.raw_encryption_key(workspace_root=repository).value) == 32
    envelope = (tmp_path / "state" / "credential-envelope.json").read_text()
    assert "managed_signing_key_base64" not in envelope
    assert "managed_raw_key_base64" not in envelope


@pytest.mark.parametrize(
    "payload",
    [
        b'{"version":2}',
        b'{"managed_raw_key_base64":"eA==","managed_signing_key_base64":"eA==","version":2}',
        b'{"version":3}',
    ],
)
def test_managed_payload_validation_fails_closed(payload: bytes) -> None:
    with pytest.raises(CredentialStoreError):
        RuntimeSecrets.from_bytes(payload)


@pytest.mark.parametrize(
    ("subject", "config", "fingerprint"),
    [
        ("other", DIGEST, OTHER_DIGEST),
        ("kevin", OTHER_DIGEST, OTHER_DIGEST),
        ("kevin", DIGEST, DIGEST),
    ],
)
def test_binding_changes_fail_closed(
    tmp_path: Path, subject: str, config: str, fingerprint: str
) -> None:
    store = DpapiCredentialStore(tmp_path / "state", protector=FakeProtector())
    store.enroll(
        _secrets(tmp_path),
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )

    with pytest.raises(CredentialStoreError, match="another runtime identity"):
        store.unlock(
            subject_id=subject,
            config_digest=config,
            signer_fingerprint=fingerprint,
        )


def test_tamper_and_revocation_fail_closed(tmp_path: Path) -> None:
    store = DpapiCredentialStore(tmp_path / "state", protector=FakeProtector())
    store.enroll(
        _secrets(tmp_path),
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )
    envelope = tmp_path / "state" / "credential-envelope.json"
    envelope.write_text(envelope.read_text().replace('ciphertext":"', 'ciphertext":"AA'))

    with pytest.raises(CredentialStoreError):
        store.unlock(
            subject_id="kevin",
            config_digest=DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )

    envelope.unlink()
    store.enroll(
        _secrets(tmp_path),
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )
    assert store.revoke() is True
    assert store.status() is None


def test_rebind_atomically_moves_enrollment_to_new_configuration(tmp_path: Path) -> None:
    store = DpapiCredentialStore(tmp_path / "state", protector=FakeProtector())
    secrets = _secrets(tmp_path)
    store.enroll(
        secrets,
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )

    metadata = store.rebind(
        subject_id="kevin",
        current_config_digest=DIGEST,
        new_config_digest=OTHER_DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )

    assert metadata.config_digest == OTHER_DIGEST
    assert (
        store.unlock(
            subject_id="kevin",
            config_digest=OTHER_DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )
        == secrets
    )
    with pytest.raises(CredentialStoreError):
        store.unlock(
            subject_id="kevin",
            config_digest=DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )


def test_macos_keychain_round_trip_binding_rebind_and_revoke(tmp_path: Path) -> None:
    backend = FakeKeychain()
    store = MacOSKeychainCredentialStore(tmp_path / "state", backend=backend)
    secrets = RuntimeSecrets.generate_managed()

    metadata = store.enroll(
        secrets,
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )

    assert metadata.protector == "macos-keychain-security-framework"
    assert store.status() == metadata
    assert (
        store.unlock(
            subject_id="kevin",
            config_digest=DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )
        == secrets
    )
    raw_free_metadata = (tmp_path / "state" / "credential-envelope.json").read_text()
    assert "managed_raw_key" not in raw_free_metadata
    assert "managed_signing_key" not in raw_free_metadata

    rebound = store.rebind(
        subject_id="kevin",
        current_config_digest=DIGEST,
        new_config_digest=OTHER_DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )
    assert rebound.config_digest == OTHER_DIGEST
    with pytest.raises(CredentialStoreError, match="another runtime identity"):
        store.unlock(
            subject_id="kevin",
            config_digest=DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )
    assert store.revoke() is True
    assert store.status() is None
    assert backend.items == {}


def test_macos_keychain_tampering_and_cross_subject_access_fail_closed(tmp_path: Path) -> None:
    backend = FakeKeychain()
    store = MacOSKeychainCredentialStore(tmp_path / "state", backend=backend)
    store.enroll(
        RuntimeSecrets.generate_managed(),
        subject_id="kevin",
        config_digest=DIGEST,
        signer_fingerprint=OTHER_DIGEST,
    )
    with pytest.raises(CredentialStoreError, match="another runtime identity"):
        store.unlock(
            subject_id="other",
            config_digest=DIGEST,
            signer_fingerprint=OTHER_DIGEST,
        )

    key = next(iter(backend.items))
    backend.items[key] += b"tampered"
    with pytest.raises(CredentialStoreError, match="changed outside Temper"):
        store.status()


def test_platform_store_selects_keychain_only_for_macos(tmp_path: Path) -> None:
    backend = FakeKeychain()

    macos = platform_credential_store(
        tmp_path / "mac", platform_name="darwin", keychain_backend=backend
    )
    windows = platform_credential_store(
        tmp_path / "win", platform_name="win32", dpapi_protector=FakeProtector()
    )

    assert isinstance(macos, MacOSKeychainCredentialStore)
    assert isinstance(windows, DpapiCredentialStore)


def _windows_interop_available() -> bool:
    executable = shutil.which("powershell.exe")
    if executable is None:
        return False
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", "exit 0"],
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.mark.skipif(not _windows_interop_available(), reason="Windows DPAPI unavailable")
def test_real_current_user_dpapi_synthetic_round_trip() -> None:
    protector = WindowsDpapiProtector()
    payload = b"synthetic-runtime-secret"
    entropy = b"synthetic-runtime-binding"

    ciphertext = protector.protect(payload, entropy=entropy)

    assert ciphertext != payload
    assert protector.unprotect(ciphertext, entropy=entropy) == payload
    with pytest.raises(CredentialStoreError):
        protector.unprotect(ciphertext, entropy=b"different-binding")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain unavailable")
def test_real_security_framework_keychain_synthetic_round_trip() -> None:
    backend = SecurityFrameworkKeychainBackend()
    service = f"com.hydroacrid.temper.tests.{uuid.uuid4()}"
    account = f"synthetic-{uuid.uuid4()}"
    original = b"synthetic-temper-keychain-secret"
    updated = b"updated-synthetic-temper-keychain-secret"
    try:
        backend.add(service=service, account=account, payload=original)
        assert backend.get(service=service, account=account) == original
        backend.update(service=service, account=account, payload=updated)
        assert backend.get(service=service, account=account) == updated
    finally:
        backend.delete(service=service, account=account)
    assert backend.get(service=service, account=account) is None
