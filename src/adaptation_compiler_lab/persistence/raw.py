"""Separate AES-256-GCM content-addressed storage for raw payload bytes.

The ledger stores only ``RawPayloadRef`` metadata. Encryption keys are explicit dependencies,
must live outside the workspace, and are never serialized with ciphertext. Immutable legacy v1.0
synthetic blobs remain readable only when the caller opts into the compatibility path.
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
from adaptation_compiler_lab.serialization.canonical import canonical_bytes

RAW_KEY_FILE_ENV: Final = "ACLAB_RAW_KEY_FILE"
_DIGEST_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
_ENVELOPE_MAGIC: Final = b"ACLAB-RAW-1\n"


class RawPayloadKeyError(ValueError):
    """Raised when the separate AES-256 key is absent, unsafe, or invalid."""


class RawPayloadLocationError(ValueError):
    """Raised when raw research bytes would be stored in a Git-controlled location."""


def require_external_raw_root(path: Path, *, workspace_root: Path) -> Path:
    """Resolve a raw store root and reject every workspace or Git-repository location."""

    resolved = path.expanduser().resolve()
    root = workspace_root.expanduser().resolve()
    if resolved.is_relative_to(root) or any(
        (parent / ".git").exists() for parent in (resolved, *resolved.parents)
    ):
        raise RawPayloadLocationError("raw payloads must remain outside every Git repository")
    return resolved


@dataclass(frozen=True, slots=True)
class RawEncryptionKey:
    """In-memory AES-256 key loaded from an external file."""

    value: bytes

    def __post_init__(self) -> None:
        if len(self.value) != 32:
            raise RawPayloadKeyError("raw-payload key must contain exactly 32 bytes")

    @property
    def fingerprint(self) -> str:
        return f"sha256:{sha256(self.value).hexdigest()}"

    @classmethod
    def from_file(cls, path: Path, *, workspace_root: Path) -> RawEncryptionKey:
        resolved = path.expanduser().resolve()
        root = workspace_root.expanduser().resolve()
        if resolved.is_relative_to(root):
            raise RawPayloadKeyError("raw-payload keys must remain outside the workspace")
        for parent in (resolved.parent, *resolved.parents):
            if (parent / ".git").exists():
                raise RawPayloadKeyError(
                    "raw-payload keys must remain outside every Git repository"
                )
        try:
            encoded = resolved.read_text(encoding="ascii").strip()
        except FileNotFoundError as error:
            raise RawPayloadKeyError(f"raw-payload key is unavailable: {resolved}") from error
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (UnicodeEncodeError, ValueError) as error:
            raise RawPayloadKeyError("raw-payload key must be canonical base64") from error
        if base64.b64encode(raw).decode("ascii") != encoded:
            raise RawPayloadKeyError("raw-payload key must use canonical base64 encoding")
        return cls(raw)

    @classmethod
    def from_environment(
        cls, *, workspace_root: Path, environ: dict[str, str] | None = None
    ) -> RawEncryptionKey:
        environment = os.environ if environ is None else environ
        path = environment.get(RAW_KEY_FILE_ENV)
        if not path:
            raise RawPayloadKeyError(f"{RAW_KEY_FILE_ENV} is required for raw-payload access")
        return cls.from_file(Path(path), workspace_root=workspace_root)


@dataclass(frozen=True, slots=True)
class RawPayloadRef:
    """Non-secret metadata safe to place in an Evidence record."""

    sha256: str
    size_bytes: int
    media_type: str
    relative_path: str


class LocalRawPayloadStore:
    """Encrypted content-addressed bytes rooted in a dedicated evidence directory."""

    def __init__(
        self,
        root: Path,
        *,
        encryption_key: RawEncryptionKey | None = None,
        allow_legacy_plaintext: bool = False,
    ) -> None:
        self._root = root.expanduser().resolve()
        self._key = encryption_key
        self._allow_legacy_plaintext = allow_legacy_plaintext
        self._root.mkdir(parents=True, exist_ok=True)
        self._set_mode(self._root, 0o700)

    @classmethod
    def from_environment(
        cls,
        root: Path,
        *,
        workspace_root: Path,
        allow_legacy_plaintext: bool = True,
    ) -> LocalRawPayloadStore:
        key = RawEncryptionKey.from_environment(workspace_root=workspace_root)
        return cls(
            root,
            encryption_key=key,
            allow_legacy_plaintext=allow_legacy_plaintext,
        )

    @classmethod
    def legacy_v1_synthetic(cls, root: Path) -> LocalRawPayloadStore:
        """Explicit compatibility adapter for immutable pre-encryption synthetic fixtures."""

        return cls(root, allow_legacy_plaintext=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def encrypted(self) -> bool:
        return self._key is not None

    def reference_for(self, payload: bytes, *, media_type: str) -> RawPayloadRef:
        if not media_type:
            raise IntegrityError("raw payload media_type must not be empty")
        digest = sha256(payload).hexdigest()
        path = self._path_for_digest(digest)
        return RawPayloadRef(
            sha256=digest,
            size_bytes=len(payload),
            media_type=media_type,
            relative_path=path.relative_to(self._root).as_posix(),
        )

    def put(self, payload: bytes, *, media_type: str) -> RawPayloadRef:
        """Encrypt and atomically persist bytes under their plaintext digest."""

        key = self._require_key()
        reference = self.reference_for(payload, media_type=media_type)
        path = self._path_for_digest(reference.sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._set_mode(path.parent, 0o700)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            try:
                existing = self.read(reference)
            except (IntegrityError, RawPayloadKeyError) as read_error:
                raise IntegrityError(
                    "existing raw payload does not match its content address"
                ) from read_error
            if existing != payload:
                raise IntegrityError(
                    "existing raw payload does not match its content address"
                ) from error
        else:
            nonce = os.urandom(12)
            ciphertext = AESGCM(key.value).encrypt(nonce, payload, self._aad(reference))
            envelope = {
                "algorithm": "AES-256-GCM",
                "ciphertext_base64": base64.b64encode(ciphertext).decode("ascii"),
                "key_fingerprint": key.fingerprint,
                "nonce_base64": base64.b64encode(nonce).decode("ascii"),
                "plaintext_sha256": reference.sha256,
                "plaintext_size": reference.size_bytes,
                "version": 1,
            }
            encoded = _ENVELOPE_MAGIC + canonical_bytes(envelope)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            self._set_mode(path, 0o600)
        return reference

    def read(self, reference: RawPayloadRef) -> bytes:
        """Decrypt and integrity-check bytes for an exact Evidence reference."""

        path = self._validated_path(reference)
        try:
            stored = path.read_bytes()
        except FileNotFoundError as error:
            raise RecordNotFoundError(f"raw payload is unavailable: {reference.sha256}") from error
        if stored.startswith(_ENVELOPE_MAGIC):
            payload = self._decrypt(stored.removeprefix(_ENVELOPE_MAGIC), reference)
        else:
            if not self._allow_legacy_plaintext:
                raise IntegrityError("unencrypted legacy raw payload is not permitted")
            payload = stored
        if len(payload) != reference.size_bytes:
            raise IntegrityError("raw payload size does not match its reference")
        if sha256(payload).hexdigest() != reference.sha256:
            raise IntegrityError("raw payload digest verification failed")
        return payload

    def contains(self, reference: RawPayloadRef) -> bool:
        try:
            self.read(reference)
        except RecordNotFoundError:
            return False
        return True

    def discard(self, reference: RawPayloadRef) -> bool:
        """Remove one exact payload, intended only for failed import rollback."""

        path = self._validated_path(reference)
        if not path.exists():
            return False
        self.read(reference)
        path.unlink()
        with suppress(OSError):
            path.parent.rmdir()
        with suppress(OSError):
            path.parent.parent.rmdir()
        return True

    def _decrypt(self, encoded: bytes, reference: RawPayloadRef) -> bytes:
        key = self._require_key()
        try:
            value = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IntegrityError("encrypted raw-payload envelope is invalid") from error
        if not isinstance(value, dict):
            raise IntegrityError("encrypted raw-payload envelope must be an object")
        required_fields = {
            "algorithm",
            "ciphertext_base64",
            "key_fingerprint",
            "nonce_base64",
            "plaintext_sha256",
            "plaintext_size",
            "version",
        }
        if set(value) != required_fields:
            raise IntegrityError("encrypted raw-payload envelope fields are invalid")
        expected = {
            "algorithm": "AES-256-GCM",
            "key_fingerprint": key.fingerprint,
            "plaintext_sha256": reference.sha256,
            "plaintext_size": reference.size_bytes,
            "version": 1,
        }
        if any(value.get(name) != item for name, item in expected.items()):
            raise IntegrityError("encrypted raw-payload envelope metadata mismatch")
        try:
            nonce = base64.b64decode(str(value["nonce_base64"]), validate=True)
            ciphertext = base64.b64decode(str(value["ciphertext_base64"]), validate=True)
        except (KeyError, ValueError) as error:
            raise IntegrityError("encrypted raw-payload envelope encoding is invalid") from error
        if len(nonce) != 12:
            raise IntegrityError("AES-GCM nonce must contain exactly 12 bytes")
        try:
            return AESGCM(key.value).decrypt(nonce, ciphertext, self._aad(reference))
        except InvalidTag as error:
            raise IntegrityError("AES-GCM authentication failed") from error

    def _require_key(self) -> RawEncryptionKey:
        if self._key is None:
            raise RawPayloadKeyError("AES-256-GCM raw-payload key is unavailable")
        return self._key

    def _validated_path(self, reference: RawPayloadRef) -> Path:
        path = self._path_for_digest(reference.sha256)
        expected_relative = path.relative_to(self._root).as_posix()
        if reference.relative_path != expected_relative:
            raise IntegrityError("raw payload reference path does not match its digest")
        return path

    def _path_for_digest(self, digest: str) -> Path:
        if _DIGEST_PATTERN.fullmatch(digest) is None:
            raise IntegrityError("raw payload digest must be 64 lowercase hexadecimal characters")
        candidate = (self._root / "sha256" / digest[:2] / digest).resolve()
        if not candidate.is_relative_to(self._root):
            raise IntegrityError("raw payload path escaped its configured root")
        return candidate

    @staticmethod
    def _aad(reference: RawPayloadRef) -> bytes:
        return canonical_bytes(
            {
                "media_type": reference.media_type,
                "plaintext_sha256": reference.sha256,
                "plaintext_size": reference.size_bytes,
                "version": 1,
            }
        )

    @staticmethod
    def _set_mode(path: Path, mode: int) -> None:
        with suppress(OSError):
            path.chmod(mode)
