from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.credentials import (
    CredentialStoreError,
    DpapiCredentialStore,
    RuntimeSecrets,
    WindowsDpapiProtector,
)

DIGEST = f"sha256:{'a' * 64}"
OTHER_DIGEST = f"sha256:{'b' * 64}"


class FakeProtector:
    def protect(self, plaintext: bytes, *, entropy: bytes) -> bytes:
        return bytes(value ^ entropy[index % len(entropy)] for index, value in enumerate(plaintext))

    def unprotect(self, ciphertext: bytes, *, entropy: bytes) -> bytes:
        return self.protect(ciphertext, entropy=entropy)


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
    assert secrets.signing_key_passphrase not in stored
    assert metadata.protector == "windows-dpapi-current-user"


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
