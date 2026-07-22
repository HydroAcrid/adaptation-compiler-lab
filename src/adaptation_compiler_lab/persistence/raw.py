"""Separate content-addressed storage for raw evidence payload bytes.

The SQLite ledger stores only a ``RawPayloadRef`` serialized inside evidence metadata.  This
store is intentionally a separate dependency and is not part of target-pack or export repository
ports, preventing those paths from gaining raw-payload access by accident.
"""

from __future__ import annotations

import os
import re
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final

from adaptation_compiler_lab.persistence.errors import IntegrityError, RecordNotFoundError

_DIGEST_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RawPayloadRef:
    """Non-secret metadata safe to place in an Evidence record."""

    sha256: str
    size_bytes: int
    media_type: str
    relative_path: str


class LocalRawPayloadStore:
    """Content-addressed raw bytes rooted in a dedicated evidence directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._set_mode(self._root, 0o700)

    @property
    def root(self) -> Path:
        """Return the dedicated absolute raw-evidence root."""

        return self._root

    def put(self, payload: bytes, *, media_type: str) -> RawPayloadRef:
        """Atomically persist bytes under their digest and return metadata only."""

        if not media_type:
            raise IntegrityError("raw payload media_type must not be empty")
        digest = sha256(payload).hexdigest()
        path = self._path_for_digest(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._set_mode(path.parent, 0o700)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            existing = path.read_bytes()
            if sha256(existing).hexdigest() != digest:
                raise IntegrityError(
                    "existing raw payload does not match its content address"
                ) from error
        else:
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            self._set_mode(path, 0o600)
        return RawPayloadRef(
            sha256=digest,
            size_bytes=len(payload),
            media_type=media_type,
            relative_path=path.relative_to(self._root).as_posix(),
        )

    def read(self, reference: RawPayloadRef) -> bytes:
        """Read and integrity-check bytes for an explicitly supplied Evidence reference."""

        path = self._path_for_digest(reference.sha256)
        expected_relative = path.relative_to(self._root).as_posix()
        if reference.relative_path != expected_relative:
            raise IntegrityError("raw payload reference path does not match its digest")
        try:
            payload = path.read_bytes()
        except FileNotFoundError as error:
            raise RecordNotFoundError(f"raw payload is unavailable: {reference.sha256}") from error
        if len(payload) != reference.size_bytes:
            raise IntegrityError("raw payload size does not match its reference")
        if sha256(payload).hexdigest() != reference.sha256:
            raise IntegrityError("raw payload digest verification failed")
        return payload

    def contains(self, reference: RawPayloadRef) -> bool:
        """Return whether an exact, integrity-valid content address already exists."""

        try:
            self.read(reference)
        except RecordNotFoundError:
            return False
        return True

    def discard(self, reference: RawPayloadRef) -> bool:
        """Remove one exact payload, intended only for failed import rollback."""

        path = self._path_for_digest(reference.sha256)
        if not path.exists():
            return False
        self.read(reference)
        path.unlink()
        with suppress(OSError):
            path.parent.rmdir()
        with suppress(OSError):
            path.parent.parent.rmdir()
        return True

    def _path_for_digest(self, digest: str) -> Path:
        if _DIGEST_PATTERN.fullmatch(digest) is None:
            raise IntegrityError("raw payload digest must be 64 lowercase hexadecimal characters")
        candidate = (self._root / "sha256" / digest[:2] / digest).resolve()
        if not candidate.is_relative_to(self._root):
            raise IntegrityError("raw payload path escaped its configured root")
        return candidate

    @staticmethod
    def _set_mode(path: Path, mode: int) -> None:
        # Windows ACLs do not always implement POSIX modes; the dedicated root still
        # provides path separation and callers must apply platform access controls.
        with suppress(OSError):
            path.chmod(mode)
