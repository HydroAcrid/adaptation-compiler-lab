"""Fail-closed platform credential enrollment for unattended local operation."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Final, Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    CredentialEnvelopeMetadata,
    CredentialEnvelopeMetadataRecord,
    CredentialEnvelopeMetadataV1_1,
)
from adaptation_compiler_lab.automatic_runtime.macos_keychain import (
    KeychainBackend,
    KeychainBackendError,
    SecurityFrameworkKeychainBackend,
)
from adaptation_compiler_lab.domain import Sha256Digest
from adaptation_compiler_lab.governance.signing import (
    SIGNING_KEY_FILE_ENV,
    SIGNING_KEY_PASSPHRASE_ENV,
    load_private_key,
)
from adaptation_compiler_lab.persistence.raw import RAW_KEY_FILE_ENV, RawEncryptionKey
from adaptation_compiler_lab.serialization import canonical_json

_ENVELOPE_FILE: Final = "credential-envelope.json"


class CredentialStoreError(ValueError):
    """Raised when credentials cannot be enrolled or unlocked without widening authority."""


class ByteProtector(Protocol):
    def protect(self, plaintext: bytes, *, entropy: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes, *, entropy: bytes) -> bytes: ...


class PlatformCredentialStore(Protocol):
    """Common same-user store contract used by setup, desktop, and recovery CLI surfaces."""

    def enroll(
        self,
        secrets: RuntimeSecrets,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
        enrolled_at: datetime | None = None,
    ) -> CredentialEnvelopeMetadataRecord: ...

    def status(self) -> CredentialEnvelopeMetadataRecord | None: ...

    def unlock(
        self,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
    ) -> RuntimeSecrets: ...

    def revoke(self) -> bool: ...

    def rebind(
        self,
        *,
        subject_id: str,
        current_config_digest: Sha256Digest,
        new_config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
        enrolled_at: datetime | None = None,
    ) -> CredentialEnvelopeMetadataRecord: ...


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
    """Either legacy external locators or key bytes sealed inside the DPAPI envelope."""

    signing_key_file: Path | None = None
    signing_key_passphrase: str | None = None
    raw_key_file: Path | None = None
    managed_signing_key: bytes | None = None
    managed_raw_key: bytes | None = None

    def __post_init__(self) -> None:
        external = (
            self.signing_key_file is not None,
            bool(self.signing_key_passphrase),
            self.raw_key_file is not None,
        )
        managed = (
            self.managed_signing_key is not None,
            self.managed_raw_key is not None,
        )
        if all(external) and not any(managed):
            return
        if all(managed) and not any(external):
            if len(self.managed_signing_key or b"") != 32:
                raise CredentialStoreError("managed Ed25519 key must contain exactly 32 bytes")
            if len(self.managed_raw_key or b"") != 32:
                raise CredentialStoreError("managed raw key must contain exactly 32 bytes")
            return
        raise CredentialStoreError(
            "runtime secrets must be either complete external references or complete managed keys"
        )

    @property
    def managed(self) -> bool:
        return self.managed_signing_key is not None

    @classmethod
    def generate_managed(cls) -> RuntimeSecrets:
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return cls(
            managed_signing_key=private_bytes,
            managed_raw_key=os.urandom(32),
        )

    def private_key(self, *, workspace_root: Path) -> Ed25519PrivateKey:
        if self.managed:
            assert self.managed_signing_key is not None
            return Ed25519PrivateKey.from_private_bytes(self.managed_signing_key)
        assert self.signing_key_file is not None
        assert self.signing_key_passphrase is not None
        return load_private_key(
            self.signing_key_file,
            passphrase=self.signing_key_passphrase,
            workspace_root=workspace_root,
        )

    def raw_encryption_key(self, *, workspace_root: Path) -> RawEncryptionKey:
        if self.managed:
            assert self.managed_raw_key is not None
            return RawEncryptionKey(self.managed_raw_key)
        assert self.raw_key_file is not None
        return RawEncryptionKey.from_file(self.raw_key_file, workspace_root=workspace_root)

    def to_bytes(self) -> bytes:
        if self.managed:
            assert self.managed_signing_key is not None
            assert self.managed_raw_key is not None
            return canonical_json(
                {
                    "managed_raw_key_base64": base64.b64encode(self.managed_raw_key).decode(
                        "ascii"
                    ),
                    "managed_signing_key_base64": base64.b64encode(self.managed_signing_key).decode(
                        "ascii"
                    ),
                    "version": 2,
                }
            ).encode("utf-8")
        assert self.raw_key_file is not None
        assert self.signing_key_file is not None
        assert self.signing_key_passphrase is not None
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
        if not isinstance(value, dict) or value.get("version") not in {1, 2}:
            raise CredentialStoreError("decrypted credential payload version is unsupported")
        try:
            if value["version"] == 2:
                return cls(
                    managed_signing_key=base64.b64decode(
                        value["managed_signing_key_base64"], validate=True
                    ),
                    managed_raw_key=base64.b64decode(
                        value["managed_raw_key_base64"], validate=True
                    ),
                )
            return cls(
                signing_key_file=Path(str(value["signing_key_file"])),
                signing_key_passphrase=str(value["signing_key_passphrase"]),
                raw_key_file=Path(str(value["raw_key_file"])),
            )
        except (KeyError, ValueError) as error:
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
    ) -> CredentialEnvelopeMetadataV1_1:
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
        metadata = CredentialEnvelopeMetadataV1_1(
            envelope_id=f"credentials-{subject_id}",
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
            protector="windows-dpapi-current-user",
            protected_payload_digest=digest,
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

    def status(self) -> CredentialEnvelopeMetadataRecord | None:
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

    def rebind(
        self,
        *,
        subject_id: str,
        current_config_digest: Sha256Digest,
        new_config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
        enrolled_at: datetime | None = None,
    ) -> CredentialEnvelopeMetadataV1_1:
        """Atomically bind an existing same-user enrollment to an explicit config update."""

        secrets = self.unlock(
            subject_id=subject_id,
            config_digest=current_config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        entropy = self._entropy(
            subject_id=subject_id,
            config_digest=new_config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        ciphertext = self._protector.protect(secrets.to_bytes(), entropy=entropy)
        metadata = CredentialEnvelopeMetadataV1_1(
            envelope_id=f"credentials-{subject_id}",
            subject_id=subject_id,
            config_digest=new_config_digest,
            signer_fingerprint=signer_fingerprint,
            protector="windows-dpapi-current-user",
            protected_payload_digest=Sha256Digest(f"sha256:{sha256(ciphertext).hexdigest()}"),
            enrolled_at=enrolled_at or datetime.now(UTC),
        )
        payload = {
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "metadata": metadata.model_dump(mode="json"),
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{_ENVELOPE_FILE}.",
            suffix=".tmp",
            dir=self._root,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(canonical_json(payload) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)
        return metadata

    def _read(self) -> tuple[CredentialEnvelopeMetadataRecord, bytes]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            metadata_payload = value["metadata"]
            version = metadata_payload.get("envelope_version", "1.0.0")
            if version == "1.0.0":
                metadata: CredentialEnvelopeMetadataRecord = (
                    CredentialEnvelopeMetadata.model_validate_json(
                        canonical_json(metadata_payload), strict=True
                    )
                )
            elif version == "1.1.0":
                metadata = CredentialEnvelopeMetadataV1_1.model_validate_json(
                    canonical_json(metadata_payload), strict=True
                )
            else:
                raise ValueError("unsupported credential metadata version")
            ciphertext = base64.b64decode(value["ciphertext"], validate=True)
        except (AttributeError, OSError, KeyError, ValueError, json.JSONDecodeError) as error:
            raise CredentialStoreError("credential envelope is invalid") from error
        actual = Sha256Digest(f"sha256:{sha256(ciphertext).hexdigest()}")
        expected = (
            metadata.ciphertext_digest
            if isinstance(metadata, CredentialEnvelopeMetadata)
            else metadata.protected_payload_digest
        )
        if actual != expected:
            raise CredentialStoreError("credential envelope ciphertext was tampered with")
        return metadata, ciphertext


class MacOSKeychainCredentialStore:
    """Keep one identity-bound secret payload in the same-user macOS Keychain."""

    _SERVICE: Final = "com.hydroacrid.temper.runtime-secrets"

    def __init__(self, state_root: Path, *, backend: KeychainBackend | None = None) -> None:
        self._root = state_root.expanduser().resolve()
        self._path = self._root / _ENVELOPE_FILE
        try:
            self._backend = backend or SecurityFrameworkKeychainBackend()
        except KeychainBackendError as error:
            raise CredentialStoreError(str(error)) from error

    def enroll(
        self,
        secrets: RuntimeSecrets,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
        enrolled_at: datetime | None = None,
    ) -> CredentialEnvelopeMetadataV1_1:
        if self._path.exists():
            raise CredentialStoreError("credential enrollment already exists; revoke it first")
        payload = self._bound_payload(
            secrets,
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        metadata = self._metadata(
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
            payload=payload,
            enrolled_at=enrolled_at,
        )
        self._root.mkdir(parents=True, exist_ok=True)
        self._root.chmod(0o700)
        try:
            self._backend.add(service=self._SERVICE, account=subject_id, payload=payload)
            self._write_metadata(metadata)
        except (KeychainBackendError, OSError) as error:
            with suppress(KeychainBackendError):
                self._backend.delete(service=self._SERVICE, account=subject_id)
            self._path.unlink(missing_ok=True)
            raise CredentialStoreError("macOS Keychain enrollment failed closed") from error
        return metadata

    def status(self) -> CredentialEnvelopeMetadataV1_1 | None:
        if not self._path.is_file():
            return None
        metadata = self._read_metadata()
        payload = self._get_payload(metadata.subject_id)
        self._verify_payload_digest(metadata, payload)
        return metadata

    def unlock(
        self,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
    ) -> RuntimeSecrets:
        metadata = self._read_metadata()
        self._require_binding(
            metadata,
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        payload = self._get_payload(subject_id)
        self._verify_payload_digest(metadata, payload)
        return self._secrets_from_bound_payload(
            payload,
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
        )

    def revoke(self) -> bool:
        if not self._path.exists():
            return False
        metadata = self._read_metadata()
        try:
            self._backend.delete(service=self._SERVICE, account=metadata.subject_id)
        except KeychainBackendError as error:
            raise CredentialStoreError("macOS Keychain revocation failed closed") from error
        self._path.unlink()
        return True

    def rebind(
        self,
        *,
        subject_id: str,
        current_config_digest: Sha256Digest,
        new_config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
        enrolled_at: datetime | None = None,
    ) -> CredentialEnvelopeMetadataV1_1:
        secrets = self.unlock(
            subject_id=subject_id,
            config_digest=current_config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        old_payload = self._get_payload(subject_id)
        new_payload = self._bound_payload(
            secrets,
            subject_id=subject_id,
            config_digest=new_config_digest,
            signer_fingerprint=signer_fingerprint,
        )
        metadata = self._metadata(
            subject_id=subject_id,
            config_digest=new_config_digest,
            signer_fingerprint=signer_fingerprint,
            payload=new_payload,
            enrolled_at=enrolled_at,
        )
        try:
            self._backend.update(
                service=self._SERVICE,
                account=subject_id,
                payload=new_payload,
            )
            self._replace_metadata(metadata)
        except (KeychainBackendError, OSError) as error:
            try:
                self._backend.update(
                    service=self._SERVICE,
                    account=subject_id,
                    payload=old_payload,
                )
            except KeychainBackendError as rollback_error:
                raise CredentialStoreError(
                    "macOS Keychain rebind and rollback both failed closed"
                ) from rollback_error
            raise CredentialStoreError("macOS Keychain rebind failed closed") from error
        return metadata

    def _read_metadata(self) -> CredentialEnvelopeMetadataV1_1:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            metadata = CredentialEnvelopeMetadataV1_1.model_validate_json(
                canonical_json(value["metadata"]), strict=True
            )
            keychain = value["keychain"]
            if metadata.protector != "macos-keychain-security-framework" or keychain != {
                "account": metadata.subject_id,
                "service": self._SERVICE,
            }:
                raise ValueError("credential metadata names another protector")
            return metadata
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
            raise CredentialStoreError("macOS Keychain metadata is invalid") from error

    def _write_metadata(self, metadata: CredentialEnvelopeMetadataV1_1) -> None:
        descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(self._serialized_metadata(metadata))
            stream.flush()
            os.fsync(stream.fileno())

    def _replace_metadata(self, metadata: CredentialEnvelopeMetadataV1_1) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{_ENVELOPE_FILE}.", suffix=".tmp", dir=self._root
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(self._serialized_metadata(metadata))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)

    def _serialized_metadata(self, metadata: CredentialEnvelopeMetadataV1_1) -> str:
        return (
            canonical_json(
                {
                    "keychain": {"account": metadata.subject_id, "service": self._SERVICE},
                    "metadata": metadata.model_dump(mode="json"),
                }
            )
            + "\n"
        )

    def _get_payload(self, subject_id: str) -> bytes:
        try:
            payload = self._backend.get(service=self._SERVICE, account=subject_id)
        except KeychainBackendError as error:
            raise CredentialStoreError(str(error)) from error
        if payload is None:
            raise CredentialStoreError("macOS Keychain enrollment is unavailable")
        return payload

    @staticmethod
    def _metadata(
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
        payload: bytes,
        enrolled_at: datetime | None,
    ) -> CredentialEnvelopeMetadataV1_1:
        return CredentialEnvelopeMetadataV1_1(
            envelope_id=f"credentials-{subject_id}",
            subject_id=subject_id,
            config_digest=config_digest,
            signer_fingerprint=signer_fingerprint,
            protector="macos-keychain-security-framework",
            protected_payload_digest=Sha256Digest(f"sha256:{sha256(payload).hexdigest()}"),
            enrolled_at=enrolled_at or datetime.now(UTC),
        )

    @staticmethod
    def _require_binding(
        metadata: CredentialEnvelopeMetadataV1_1,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
    ) -> None:
        if metadata.revoked_at is not None:
            raise CredentialStoreError("credential enrollment is revoked")
        if (
            metadata.subject_id != subject_id
            or metadata.config_digest != config_digest
            or metadata.signer_fingerprint != signer_fingerprint
        ):
            raise CredentialStoreError("credential envelope is bound to another runtime identity")

    @staticmethod
    def _verify_payload_digest(metadata: CredentialEnvelopeMetadataV1_1, payload: bytes) -> None:
        actual = Sha256Digest(f"sha256:{sha256(payload).hexdigest()}")
        if actual != metadata.protected_payload_digest:
            raise CredentialStoreError("macOS Keychain payload was changed outside Temper")

    @staticmethod
    def _bound_payload(
        secrets: RuntimeSecrets,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
    ) -> bytes:
        return canonical_json(
            {
                "binding": {
                    "config_digest": str(config_digest),
                    "signer_fingerprint": str(signer_fingerprint),
                    "subject_id": subject_id,
                },
                "secrets_base64": base64.b64encode(secrets.to_bytes()).decode("ascii"),
                "version": 1,
            }
        ).encode("utf-8")

    @staticmethod
    def _secrets_from_bound_payload(
        payload: bytes,
        *,
        subject_id: str,
        config_digest: Sha256Digest,
        signer_fingerprint: Sha256Digest,
    ) -> RuntimeSecrets:
        try:
            value = json.loads(payload)
            expected = {
                "config_digest": str(config_digest),
                "signer_fingerprint": str(signer_fingerprint),
                "subject_id": subject_id,
            }
            if value.get("version") != 1 or value.get("binding") != expected:
                raise ValueError("binding mismatch")
            secrets = base64.b64decode(value["secrets_base64"], validate=True)
        except (AttributeError, KeyError, ValueError, json.JSONDecodeError) as error:
            raise CredentialStoreError(
                "macOS Keychain payload is bound to another runtime identity"
            ) from error
        return RuntimeSecrets.from_bytes(secrets)


def platform_credential_store(
    state_root: Path,
    *,
    platform_name: str | None = None,
    keychain_backend: KeychainBackend | None = None,
    dpapi_protector: ByteProtector | None = None,
) -> PlatformCredentialStore:
    """Select exactly one native protector; no plaintext fallback exists."""

    selected = sys.platform if platform_name is None else platform_name
    if selected == "darwin":
        return MacOSKeychainCredentialStore(state_root, backend=keychain_backend)
    return DpapiCredentialStore(state_root, protector=dpapi_protector)
