"""Same-user Windows credential enrollment for unattended local dogfood operation."""

from __future__ import annotations

import base64
import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Final, Protocol

from adaptation_compiler_lab.automatic_runtime.gateway_models import CredentialEnvelopeMetadata
from adaptation_compiler_lab.domain import Sha256Digest
from adaptation_compiler_lab.governance.signing import (
    SIGNING_KEY_FILE_ENV,
    SIGNING_KEY_PASSPHRASE_ENV,
)
from adaptation_compiler_lab.persistence.raw import RAW_KEY_FILE_ENV
from adaptation_compiler_lab.serialization import canonical_json

_ENVELOPE_FILE: Final = "credential-envelope.json"


class CredentialStoreError(ValueError):
    """Raised when credentials cannot be enrolled or unlocked without widening authority."""


class ByteProtector(Protocol):
    def protect(self, plaintext: bytes, *, entropy: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes, *, entropy: bytes) -> bytes: ...


class WindowsDpapiProtector:
    """Call CurrentUser DPAPI without placing plaintext in arguments or environment variables."""

    _SCRIPT: Final = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$inputJson = [Console]::In.ReadToEnd() | ConvertFrom-Json
$payload = [Convert]::FromBase64String($inputJson.payload)
$entropy = [Convert]::FromBase64String($inputJson.entropy)
if ($inputJson.operation -eq 'protect') {
  $result = [Security.Cryptography.ProtectedData]::Protect(
    $payload, $entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
} elseif ($inputJson.operation -eq 'unprotect') {
  $result = [Security.Cryptography.ProtectedData]::Unprotect(
    $payload, $entropy, [Security.Cryptography.DataProtectionScope]::CurrentUser)
} else { throw 'unsupported DPAPI operation' }
[Console]::Out.Write([Convert]::ToBase64String($result))
"""

    def __init__(self, executable: str = "powershell.exe") -> None:
        self._executable = executable

    def protect(self, plaintext: bytes, *, entropy: bytes) -> bytes:
        return self._invoke("protect", plaintext, entropy)

    def unprotect(self, ciphertext: bytes, *, entropy: bytes) -> bytes:
        return self._invoke("unprotect", ciphertext, entropy)

    def _invoke(self, operation: str, payload: bytes, entropy: bytes) -> bytes:
        encoded_script = base64.b64encode(self._SCRIPT.encode("utf-16-le")).decode("ascii")
        request = json.dumps(
            {
                "entropy": base64.b64encode(entropy).decode("ascii"),
                "operation": operation,
                "payload": base64.b64encode(payload).decode("ascii"),
            },
            separators=(",", ":"),
        )
        try:
            completed = subprocess.run(
                [
                    self._executable,
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    encoded_script,
                ],
                input=request,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CredentialStoreError("Windows DPAPI is unavailable") from error
        if completed.returncode != 0:
            raise CredentialStoreError("Windows DPAPI refused the credential operation")
        try:
            return base64.b64decode(completed.stdout.strip(), validate=True)
        except ValueError as error:
            raise CredentialStoreError("Windows DPAPI returned an invalid envelope") from error


@dataclass(frozen=True, slots=True)
class RuntimeSecrets:
    signing_key_file: Path
    signing_key_passphrase: str
    raw_key_file: Path

    def __post_init__(self) -> None:
        if not self.signing_key_passphrase:
            raise CredentialStoreError("signing-key passphrase is unavailable")

    def to_bytes(self) -> bytes:
        return canonical_json(
            {
                "raw_key_file": str(self.raw_key_file),
                "signing_key_file": str(self.signing_key_file),
                "signing_key_passphrase": self.signing_key_passphrase,
                "version": 1,
            }
        ).encode("utf-8")

    @classmethod
    def from_bytes(cls, payload: bytes) -> RuntimeSecrets:
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CredentialStoreError("decrypted credential payload is invalid") from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise CredentialStoreError("decrypted credential payload version is unsupported")
        try:
            return cls(
                signing_key_file=Path(str(value["signing_key_file"])),
                signing_key_passphrase=str(value["signing_key_passphrase"]),
                raw_key_file=Path(str(value["raw_key_file"])),
            )
        except KeyError as error:
            raise CredentialStoreError("decrypted credential payload is incomplete") from error

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> RuntimeSecrets:
        source = os.environ if environ is None else environ
        signing_file = source.get(SIGNING_KEY_FILE_ENV)
        passphrase = source.get(SIGNING_KEY_PASSPHRASE_ENV)
        raw_file = source.get(RAW_KEY_FILE_ENV)
        if not signing_file or not passphrase or not raw_file:
            raise CredentialStoreError(
                f"{SIGNING_KEY_FILE_ENV}, {SIGNING_KEY_PASSPHRASE_ENV}, and "
                f"{RAW_KEY_FILE_ENV} are required for enrollment"
            )
        return cls(Path(signing_file), passphrase, Path(raw_file))


class DpapiCredentialStore:
    """Persist a revocable DPAPI envelope and expose secrets only as an in-memory value."""

    def __init__(self, state_root: Path, *, protector: ByteProtector | None = None) -> None:
        self._root = state_root.expanduser().resolve()
        self._path = self._root / _ENVELOPE_FILE
        self._protector = protector or WindowsDpapiProtector()

    @staticmethod
    def _entropy(
        *, subject_id: str, config_digest: Sha256Digest, signer_fingerprint: Sha256Digest
    ) -> bytes:
        return canonical_json(
            {
                "config_digest": str(config_digest),
                "purpose": "adaptation-compiler-lab-runtime-unlock",
                "signer_fingerprint": str(signer_fingerprint),
                "subject_id": subject_id,
            }
        ).encode("utf-8")

    def enroll(
        self,
        secrets: RuntimeSecrets,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
        enrolled_at: datetime | None = None,
    ) -> CredentialEnvelopeMetadata:
        if self._path.exists():
            raise CredentialStoreError("credential enrollment already exists; revoke it first")
        self._root.mkdir(parents=True, exist_ok=True)
        self._root.chmod(0o700)
        entropy = self._entropy(
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        ciphertext = self._protector.protect(secrets.to_bytes(), entropy=entropy)
        digest = Sha256Digest(f"sha256:{sha256(ciphertext).hexdigest()}")
        metadata = CredentialEnvelopeMetadata(
            envelope_id=f"credentials-{subject_id}",
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
            protector="windows-dpapi-current-user",
            ciphertext_digest=digest,
            enrolled_at=enrolled_at or datetime.now(UTC),
        )
        payload = {
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "metadata": metadata.model_dump(mode="json"),
        }
        descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(canonical_json(payload) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            self._path.unlink(missing_ok=True)
            raise
        return metadata

    def status(self) -> CredentialEnvelopeMetadata | None:
        if not self._path.is_file():
            return None
        return self._read()[0]

    def unlock(
        self,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
    ) -> RuntimeSecrets:
        metadata, ciphertext = self._read()
        if metadata.revoked_at is not None:
            raise CredentialStoreError("credential enrollment is revoked")
        if (
            metadata.subject_id != subject_id
            or metadata.config_digest != config_digest
            or metadata.signer_fingerprint != signer_fingerprint
        ):
            raise CredentialStoreError("credential envelope is bound to another runtime identity")
        entropy = self._entropy(
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        return RuntimeSecrets.from_bytes(self._protector.unprotect(ciphertext, entropy=entropy))

    def revoke(self) -> bool:
        if not self._path.exists():
            return False
        self._path.unlink()
        return True

    def _read(self) -> tuple[CredentialEnvelopeMetadata, bytes]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            metadata = CredentialEnvelopeMetadata.model_validate_json(
                canonical_json(value["metadata"]), strict=True
            )
            ciphertext = base64.b64decode(value["ciphertext"], validate=True)
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
            raise CredentialStoreError("credential envelope is invalid") from error
        actual = Sha256Digest(f"sha256:{sha256(ciphertext).hexdigest()}")
        if actual != metadata.ciphertext_digest:
            raise CredentialStoreError("credential envelope ciphertext was tampered with")
        return metadata, ciphertext
