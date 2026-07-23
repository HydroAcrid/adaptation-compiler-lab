"""Encrypted external custody store for sealed held-out benchmark bundles.

The store deliberately exposes verification metadata, never plaintext. A later sealed runner may
add an authorized reveal surface after the Milestone 3 gate.
"""

from __future__ import annotations

import base64
import json
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from adaptation_compiler_lab.persistence.errors import IntegrityError, RecordNotFoundError
from adaptation_compiler_lab.serialization import canonical_bytes

CUSTODY_KEY_FILE_ENV: Final = "ACLAB_CUSTODY_KEY_FILE"
_DIGEST_PATTERN: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENVELOPE_MAGIC: Final = b"ACLAB-CUSTODY-1\n"


class CustodyKeyError(ValueError):
    """The separate custody encryption key is absent, invalid, or stored unsafely."""


@dataclass(frozen=True, slots=True)
class CustodyEncryptionKey:
    """In-memory AES-256 key loaded only from outside the compiler workspace."""

    value: bytes

    def __post_init__(self) -> None:
        if len(self.value) != 32:
            raise CustodyKeyError("custody key must contain exactly 32 bytes")

    @property
    def fingerprint(self) -> str:
        return f"sha256:{sha256(self.value).hexdigest()}"

    @classmethod
    def from_file(cls, path: Path, *, workspace_root: Path) -> CustodyEncryptionKey:
        resolved = path.expanduser().resolve()
        workspace = workspace_root.expanduser().resolve()
        if resolved.is_relative_to(workspace):
            raise CustodyKeyError("custody keys must remain outside the compiler workspace")
        if _inside_git_repository(resolved):
            raise CustodyKeyError("custody keys must remain outside every Git repository")
        try:
            encoded = resolved.read_text(encoding="ascii").strip()
        except FileNotFoundError as error:
            raise CustodyKeyError(f"custody key is unavailable: {resolved}") from error
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (UnicodeEncodeError, ValueError) as error:
            raise CustodyKeyError("custody key must be canonical base64") from error
        if base64.b64encode(raw).decode("ascii") != encoded:
            raise CustodyKeyError("custody key must use canonical base64 encoding")
        return cls(raw)

    @classmethod
    def from_environment(
        cls,
        *,
        workspace_root: Path,
        environ: dict[str, str] | None = None,
    ) -> CustodyEncryptionKey:
        environment = os.environ if environ is None else environ
        path = environment.get(CUSTODY_KEY_FILE_ENV)
        if not path:
            raise CustodyKeyError(f"{CUSTODY_KEY_FILE_ENV} is required for custody access")
        return cls.from_file(Path(path), workspace_root=workspace_root)


@dataclass(frozen=True, slots=True)
class SealedBundleRef:
    """Content-addressed metadata safe for a signed CustodyManifest."""

    sealed_bundle_digest: str
    plaintext_digest: str
    plaintext_bytes: int


@dataclass(frozen=True, slots=True)
class SealVerification:
    """Successful integrity result with no plaintext or locator."""

    sealed_bundle_digest: str
    plaintext_digest: str
    plaintext_bytes: int
    split_manifest_digest: str


class ExternalCustodyStore:
    """AES-GCM store that must live outside the compiler workspace and every Git repository."""

    def __init__(
        self,
        root: Path,
        *,
        workspace_root: Path,
        encryption_key: CustodyEncryptionKey,
    ) -> None:
        self._root = root.expanduser().resolve()
        self._workspace_root = workspace_root.expanduser().resolve()
        self._require_external_boundary()
        self._key = encryption_key
        self._root.mkdir(parents=True, exist_ok=True)
        _set_mode(self._root, 0o700)

    def _require_external_boundary(self) -> None:
        if self._root.is_relative_to(self._workspace_root):
            raise CustodyKeyError("held-out bundles must remain outside the compiler workspace")
        if _inside_git_repository(self._root):
            raise CustodyKeyError("held-out bundles must remain outside every Git repository")

    @property
    def root(self) -> Path:
        return self._root

    def seal(
        self,
        payload: bytes,
        *,
        benchmark_id: str,
        split_manifest_digest: str,
    ) -> SealedBundleRef:
        """Encrypt and atomically persist an opaque held-out bundle."""

        self._require_external_boundary()
        _require_digest(split_manifest_digest, label="split-manifest")
        plaintext_digest = f"sha256:{sha256(payload).hexdigest()}"
        reference_without_seal = {
            "benchmark_id": benchmark_id,
            "plaintext_bytes": len(payload),
            "plaintext_digest": plaintext_digest,
            "split_manifest_digest": split_manifest_digest,
            "version": 1,
        }
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key.value).encrypt(
            nonce,
            payload,
            canonical_bytes(reference_without_seal),
        )
        envelope = {
            "algorithm": "AES-256-GCM",
            "benchmark_id": benchmark_id,
            "ciphertext_base64": base64.b64encode(ciphertext).decode("ascii"),
            "key_fingerprint": self._key.fingerprint,
            "nonce_base64": base64.b64encode(nonce).decode("ascii"),
            "plaintext_bytes": len(payload),
            "plaintext_digest": plaintext_digest,
            "split_manifest_digest": split_manifest_digest,
            "version": 1,
        }
        encoded = _ENVELOPE_MAGIC + canonical_bytes(envelope)
        sealed_digest = f"sha256:{sha256(encoded).hexdigest()}"
        reference = SealedBundleRef(
            sealed_bundle_digest=sealed_digest,
            plaintext_digest=plaintext_digest,
            plaintext_bytes=len(payload),
        )
        path = self.location(reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        _set_mode(path.parent, 0o700)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            try:
                self.verify(
                    reference,
                    benchmark_id=benchmark_id,
                    split_manifest_digest=split_manifest_digest,
                )
            except (IntegrityError, RecordNotFoundError) as verify_error:
                raise IntegrityError("existing sealed bundle failed content verification") from (
                    verify_error
                )
            raise IntegrityError(
                "randomized custody seal unexpectedly reused an envelope"
            ) from error
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        _set_mode(path, 0o600)
        return reference

    def verify(
        self,
        reference: SealedBundleRef,
        *,
        benchmark_id: str,
        split_manifest_digest: str,
    ) -> SealVerification:
        """Authenticate the full seal and discard decrypted bytes before returning."""

        self._require_external_boundary()
        path = self.location(reference)
        try:
            stored = path.read_bytes()
        except FileNotFoundError as error:
            raise RecordNotFoundError("sealed benchmark bundle is unavailable") from error
        if f"sha256:{sha256(stored).hexdigest()}" != reference.sealed_bundle_digest:
            raise IntegrityError("sealed benchmark bundle digest mismatch")
        if not stored.startswith(_ENVELOPE_MAGIC):
            raise IntegrityError("sealed benchmark bundle envelope is invalid")
        try:
            value = json.loads(stored.removeprefix(_ENVELOPE_MAGIC))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IntegrityError("sealed benchmark bundle envelope is invalid") from error
        if not isinstance(value, dict):
            raise IntegrityError("sealed benchmark bundle envelope must be an object")
        required_fields = {
            "algorithm",
            "benchmark_id",
            "ciphertext_base64",
            "key_fingerprint",
            "nonce_base64",
            "plaintext_bytes",
            "plaintext_digest",
            "split_manifest_digest",
            "version",
        }
        if set(value) != required_fields:
            raise IntegrityError("sealed benchmark bundle fields are invalid")
        expected = {
            "algorithm": "AES-256-GCM",
            "benchmark_id": benchmark_id,
            "key_fingerprint": self._key.fingerprint,
            "plaintext_bytes": reference.plaintext_bytes,
            "plaintext_digest": reference.plaintext_digest,
            "split_manifest_digest": split_manifest_digest,
            "version": 1,
        }
        if any(value.get(name) != item for name, item in expected.items()):
            raise IntegrityError("sealed benchmark bundle metadata mismatch")
        try:
            nonce = base64.b64decode(str(value["nonce_base64"]), validate=True)
            ciphertext = base64.b64decode(str(value["ciphertext_base64"]), validate=True)
        except ValueError as error:
            raise IntegrityError("sealed benchmark bundle encoding is invalid") from error
        if len(nonce) != 12:
            raise IntegrityError("custody AES-GCM nonce must contain exactly 12 bytes")
        aad = canonical_bytes(
            {
                "benchmark_id": benchmark_id,
                "plaintext_bytes": reference.plaintext_bytes,
                "plaintext_digest": reference.plaintext_digest,
                "split_manifest_digest": split_manifest_digest,
                "version": 1,
            }
        )
        try:
            plaintext = AESGCM(self._key.value).decrypt(nonce, ciphertext, aad)
        except InvalidTag as error:
            raise IntegrityError("sealed benchmark bundle authentication failed") from error
        if len(plaintext) != reference.plaintext_bytes:
            raise IntegrityError("sealed benchmark plaintext length mismatch")
        if f"sha256:{sha256(plaintext).hexdigest()}" != reference.plaintext_digest:
            raise IntegrityError("sealed benchmark plaintext digest mismatch")
        return SealVerification(
            sealed_bundle_digest=reference.sealed_bundle_digest,
            plaintext_digest=reference.plaintext_digest,
            plaintext_bytes=reference.plaintext_bytes,
            split_manifest_digest=split_manifest_digest,
        )

    def location(self, reference: SealedBundleRef) -> Path:
        """Resolve the external content address without storing it in signed metadata."""

        _require_digest(reference.sealed_bundle_digest, label="sealed-bundle")
        digest = reference.sealed_bundle_digest.removeprefix("sha256:")
        candidate = (self._root / "sha256" / digest[:2] / digest).resolve()
        if not candidate.is_relative_to(self._root):
            raise IntegrityError("sealed bundle path escaped its custody root")
        return candidate


def _require_digest(value: str, *, label: str) -> None:
    if _DIGEST_PATTERN.fullmatch(value) is None:
        raise IntegrityError(f"{label} digest must be canonical SHA-256")


def _inside_git_repository(path: Path) -> bool:
    candidate = path if path.is_dir() else path.parent
    return any((parent / ".git").exists() for parent in (candidate, *candidate.parents))


def _set_mode(path: Path, mode: int) -> None:
    with suppress(OSError):
        path.chmod(mode)
