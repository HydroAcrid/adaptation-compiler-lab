"""Signed, explicitly curated repository setups with closed declarative checks."""

from __future__ import annotations

import base64
import json
import os
import re
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from adaptation_compiler_lab.governance.models import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import GovernanceSigner, verify_detached_envelope
from adaptation_compiler_lab.portability.packages import _assert_shareable_text_safe
from adaptation_compiler_lab.sanitization.scanner import is_sensitive_path
from adaptation_compiler_lab.serialization.canonical import canonical_bytes, canonical_digest

from .continuity import SECRET_PATTERN
from .intake import sha
from .paths import RESERVED, check_root, safe
from .sealed import Seals

EXTENSION = ".temper-setup"
PURPOSE = "portable_repository_setup/v1"
LOCAL_PURPOSE = b"temper/tools-hub/portable-setup/v1"
MAX_PAYLOAD = 48_000
MAX_PACKAGE = 52_000
MAX_LOCAL_RECORD = 170_000
MAX_CHECK_FILE = 1_048_576
PRECEDENCE = "Current requests and manually written native instructions take precedence."
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
ProjectId = Annotated[str, Field(min_length=1, max_length=160)]
ItemId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Title = Annotated[str, Field(min_length=1, max_length=120)]
FileName = Annotated[str, Field(min_length=1, max_length=1024)]

# Closed path grammar. Hidden control directories and common local secret paths
# are outside the scope of repository checks even when physically in the repo.
CHECK_PATH = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_. -]*(?:/[A-Za-z0-9_-][A-Za-z0-9_. -]*)*$")
LOCAL_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|(?:^|[\s(`'\"\[])(?:~[\\/]|/(?!/)|\\\\))")
TRANSCRIPT_ID = re.compile(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b")
EXECUTABLE_BLOCK = re.compile(
    r"(?im)^\s*(?:#!|(?:`{3,}|~{3,})\s*"
    r"(?:bash|sh|zsh|cmd|bat|powershell|pwsh|python|py|javascript|js|ruby|perl|php)\b)"
)
SECRET_NAMES = re.compile(
    r"(?i)(?:^|[._ -])(?:credentials?|secrets?|tokens?|private[._ -]?key)(?:[._ -]|$)"
    r"|[.](?:pem|key|p12|pfx|kdbx|sqlite3?|db|jsonl)$"
)


class SetupError(ValueError):
    """A portable-setup error with a message safe to display in desktop and MCP."""


class UnreadableSetup(SetupError):
    """An available record failed local authentication or decoding."""


def shareable_text(value: str) -> str:
    if not value.strip() or any(ord(char) < 32 and char not in "\r\n\t" for char in value):
        raise ValueError("Enter shareable text")
    if SECRET_PATTERN.search(value) or LOCAL_PATH.search(value):
        raise ValueError("Remove credentials and local paths from the setup")
    if TRANSCRIPT_ID.search(value) or EXECUTABLE_BLOCK.search(value):
        raise ValueError("Remove session identifiers and executable blocks from the setup")
    _assert_shareable_text_safe(value)
    return value


class SetupModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Item(SetupModel):
    id: ItemId
    title: Title

    _safe_id = field_validator("id")(shareable_text)
    _safe_title = field_validator("title")(shareable_text)


class Guidance(Item):
    kind: Literal["skill", "knowledge", "preference"]
    text: str = Field(min_length=1, max_length=4000)

    _safe_text = field_validator("text")(shareable_text)


class RepositoryCheck(Item):
    kind: Literal["check"]
    path: str = Field(min_length=1, max_length=240)
    operation: Literal["file_exists", "file_contains"]
    text: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("path")
    @classmethod
    def approved_relative_path(cls, value: str) -> str:
        shareable_text(value)
        if (
            is_sensitive_path(value)
            or not CHECK_PATH.fullmatch(value)
            or any(
                part.endswith((".", " "))
                or part.casefold().split(".")[0] in RESERVED
                or SECRET_NAMES.search(part)
                for part in value.split("/")
            )
        ):
            raise ValueError(
                "Use a regular repository-relative path outside hidden or secret locations"
            )
        return value

    @model_validator(mode="after")
    def operation_matches(self) -> Self:
        if (self.operation == "file_contains") != (self.text is not None):
            raise ValueError("Supply literal text only for a file-contains check")
        if self.text is not None:
            shareable_text(self.text)
        return self

    def run(self, root: Path) -> bool:
        try:
            data = read_regular(safe(root, self.path), MAX_CHECK_FILE, read=self.text is not None)
        except FileNotFoundError:
            return False
        except (OSError, ValueError) as error:
            raise SetupError("The check cannot read a bounded regular repository file") from error
        if self.text is None:
            return True
        return self.text.encode("utf-8") in data


SetupItem = Annotated[Guidance | RepositoryCheck, Field(discriminator="kind")]


class SetupDraft(SetupModel):
    title: Title
    items: list[SetupItem] = Field(min_length=1, max_length=20)

    _safe_title = field_validator("title")(shareable_text)

    @model_validator(mode="after")
    def valid_content(self) -> Self:
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Give each setup item a different ID")
        if len(canonical_bytes(self.model_dump(include={"title", "items"}))) > MAX_PAYLOAD:
            raise ValueError("The setup exceeds its supported size")
        return self


class SetupPackage(SetupDraft):
    format: Literal["temper-setup/v1"]
    publisher_public_key_base64: str = Field(min_length=44, max_length=44)
    signature: SignatureEnvelope

    @property
    def digest(self) -> str:
        return canonical_digest(self)

    def verify(self) -> None:
        if self.signature.signer_identity_id != "setup-publisher":
            raise SetupError("The setup has an unsupported publisher identity")
        verify_detached_envelope(
            self.model_dump(mode="json", exclude={"signature"}),
            self.signature,
            public_key_base64=self.publisher_public_key_base64,
            expected_purpose=PURPOSE,
        )

    def preview(self) -> dict[str, Any]:
        return {
            **self.model_dump(mode="json", include={"title", "items"}, exclude_none=True),
            "digest": self.digest,
            "signer_fingerprint": self.signature.key_fingerprint,
        }

    def context(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "digest": self.digest,
            "skills": [{"id": i.id, "title": i.title} for i in self.items if i.kind == "skill"],
            "knowledge": [i.model_dump() for i in self.items if i.kind == "knowledge"],
            "preferences": [i.model_dump() for i in self.items if i.kind == "preference"],
            "checks": [{"id": i.id, "title": i.title} for i in self.items if i.kind == "check"],
        }


def build_package(draft: SetupDraft, seals: Seals) -> SetupPackage:
    publisher = GovernanceSigner(seals.signer.private_key, "setup-publisher", "setup-publisher")
    payload = {
        **draft.model_dump(mode="json"),
        "format": "temper-setup/v1",
        "publisher_public_key_base64": seals.public_key,
    }
    return SetupPackage.model_validate(
        {
            **payload,
            "signature": publisher.envelope(payload, purpose=PURPOSE, signed_at=datetime.now(UTC)),
        }
    )


def parse_package(data: bytes) -> SetupPackage:
    if not data or len(data) > MAX_PACKAGE:
        raise SetupError("The setup file exceeds its supported size")
    try:
        package = SetupPackage.model_validate_json(data)
        package.verify()
    except (TypeError, ValueError) as error:
        raise SetupError("The setup file has an invalid format, content, or signature") from error
    return package


def read_regular(path: Path, limit: int, *, read: bool = True) -> bytes:
    path = check_root(path)
    before = path.lstat()
    if not regular(before, limit):
        raise ValueError("Expected a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not regular(opened, limit) or not os.path.samestat(before, opened):
            raise ValueError("The file changed while opening")
        if not os.path.samestat(check_root(path).lstat(), opened):
            raise ValueError("The file changed while opening")
        data = stream.read(limit + 1) if read else b""
        if len(data) > limit:
            raise ValueError("The file exceeds the read limit")
        after = check_root(path).lstat()
        if (
            not os.path.samestat(after, opened)
            or not regular(after, limit)
            or (after.st_mtime_ns, after.st_size) != (opened.st_mtime_ns, opened.st_size)
        ):
            raise ValueError("The file changed while reading")
        return data


def regular(info: os.stat_result, limit: int) -> bool:
    return bool(
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        and info.st_size <= limit
    )


def package_path(path: Path) -> Path:
    path = check_root(path)
    if path.suffix.casefold() != EXTENSION:
        raise SetupError("Choose a .temper-setup file")
    return path


def write_package(path: Path, package: SetupPackage) -> None:
    path = package_path(path)
    data = canonical_bytes(package) + b"\n"
    if len(data) > MAX_PACKAGE:
        raise SetupError("The setup file exceeds its supported size")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise SetupError("A file already exists at that destination") from error
    created = None
    try:
        with os.fdopen(descriptor, "wb") as stream:
            created = os.fstat(stream.fileno())
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        with suppress(OSError, ValueError):
            if created is not None and os.path.samestat(check_root(path).lstat(), created):
                path.unlink()
        raise


class UpdateSource(SetupModel):
    directory: FileName
    directory_device: int
    directory_inode: int
    replay: FileName
    replay_digest: Digest
    revision: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]


@dataclass(frozen=True)
class StoredSetup:
    revision: str | None = None
    active: SetupPackage | None = None
    previous: SetupPackage | None = None
    source: UpdateSource | None = None


class SetupStore:
    def __init__(self, home: Path, seals: Seals, key: Callable[[], bytes] | None) -> None:
        self.home, self.seals, self.key = home, seals, key

    def path(self, key: str) -> Path:
        return safe(self.home, f"portable-setups/{key}.json")

    def cipher(self) -> AESGCM:
        if self.key is None:
            raise SetupError("The secure setup store is unavailable")
        return AESGCM(
            HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=LOCAL_PURPOSE).derive(
                self.key()
            )
        )

    def read(
        self, key: str, grant_id: str, project: dict[str, Any]
    ) -> tuple[str | None, SetupPackage | None]:
        record = self.read_record(key, grant_id, project)
        return record.revision, record.active

    def read_record(self, key: str, grant_id: str, project: dict[str, Any]) -> StoredSetup:
        try:
            raw = read_regular(self.path(key), MAX_LOCAL_RECORD)
        except FileNotFoundError:
            return StoredSetup()
        return self.decode(raw, grant_id, project)

    def decode(self, raw: bytes, grant_id: str, project: dict[str, Any]) -> StoredSetup:
        try:
            state = self.seals.open(json.loads(raw), "portable_setup")
            if state["grant_id"] != grant_id or state["project"] != project:
                return StoredSetup()
            revision = state["revision"]
            if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{32}", revision):
                raise ValueError("Invalid setup revision")
            version = state.get("version", 1)
            if type(version) is not int or version not in (1, 2):
                raise ValueError("Invalid setup record version")
            if state["encrypted"] is None:
                return StoredSetup(revision)
            encoded = base64.b64decode(state["encrypted"], validate=True)
            if len(encoded) < 28:
                raise ValueError("Invalid encrypted setup")
            aad = canonical_bytes({k: v for k, v in state.items() if k != "encrypted"})
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            raise UnreadableSetup("The saved setup could not be verified") from error
        # Unlock errors must not be interpreted as a corrupt package.
        cipher = self.cipher()
        try:
            payload = cipher.decrypt(encoded[:12], encoded[12:], aad)
            if version == 1:
                return StoredSetup(revision, parse_package(payload))
            raw_record = json.loads(payload)
            return StoredSetup(
                revision,
                parse_package(canonical_bytes(raw_record["active"])),
                parse_package(canonical_bytes(raw_record["previous"]))
                if raw_record["previous"] is not None
                else None,
                UpdateSource.model_validate(raw_record["source"])
                if raw_record["source"] is not None
                else None,
            )
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError) as error:
            raise UnreadableSetup("The saved setup could not be verified") from error

    def recovery_digest(self, key: str, grant_id: str, project: dict[str, Any]) -> str:
        raw = read_regular(self.path(key), MAX_LOCAL_RECORD)
        self.cipher()
        try:
            self.decode(raw, grant_id, project)
        except UnreadableSetup:
            return "sha256:" + sha(raw)
        raise SetupError("The setup is readable. Use the normal setup controls.")

    def write(
        self,
        key: str,
        grant_id: str,
        project: dict[str, Any],
        package: SetupPackage | None,
    ) -> None:
        self.write_record(key, grant_id, project, StoredSetup(os.urandom(16).hex(), package))

    def write_record(
        self, key: str, grant_id: str, project: dict[str, Any], record: StoredSetup
    ) -> None:
        state: dict[str, Any] = {
            "grant_id": grant_id,
            "project": project,
            "revision": record.revision,
        }
        encoded = None
        if record.active is not None:
            nonce = os.urandom(12)
            if record.source is None and record.previous is None:
                payload = canonical_bytes(record.active)
            else:
                state["version"] = 2
                payload = canonical_bytes(
                    {
                        "active": record.active.model_dump(mode="json"),
                        "previous": record.previous.model_dump(mode="json")
                        if record.previous
                        else None,
                        "source": record.source.model_dump(mode="json") if record.source else None,
                    }
                )
            ciphertext = self.cipher().encrypt(nonce, payload, canonical_bytes(state))
            encoded = base64.b64encode(nonce + ciphertext).decode("ascii")
        self.seals.write(self.path(key), {**state, "encrypted": encoded}, "portable_setup")
