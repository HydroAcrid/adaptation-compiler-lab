"""Owner-scoped local checkpoints, separate from learning and temporary skills."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from collections.abc import Callable
from itertools import islice
from pathlib import Path
from typing import Annotated, Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .intake import sha
from .paths import safe
from .sealed import Seals

RETENTION_SECONDS = 30 * 24 * 60 * 60
MAX_CHECKPOINT_BYTES = 12_000
PURPOSE = b"temper/tools-hub/task-continuity/v1"
SECRET_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b"
    r"|\bBearer\s+[A-Za-z0-9._~+/-]{16,}",
    re.IGNORECASE,
)

Entry = Annotated[str, Field(min_length=1, max_length=500)]


class Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    facts: list[Entry] = Field(default_factory=list, max_length=8)
    requirements: list[Entry] = Field(default_factory=list, max_length=8)
    progress: list[Entry] = Field(default_factory=list, max_length=8)
    checks: list[Entry] = Field(default_factory=list, max_length=8)
    next_step: Entry

    @field_validator("facts", "requirements", "progress", "checks")
    @classmethod
    def validate_entries(cls, entries: list[str]) -> list[str]:
        return [cls.validate_text(entry) for entry in entries]

    @field_validator("next_step")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Use concise single-line checkpoint entries")
        reject_credentials(value)
        return value.strip()


def reject_credentials(value: str) -> None:
    if SECRET_PATTERN.search(value):
        raise ValueError("Remove credentials from the checkpoint")


def session_digest(session_id: str) -> str:
    return sha(PURPOSE + b"/native-session/" + session_id.encode())


def goal_key(goal: str) -> str:
    return sha(" ".join(goal.split()).casefold().encode())


class ContinuityStore:
    def __init__(self, home: Path, seals: Seals, key: Callable[[], bytes] | None) -> None:
        self.home, self.seals, self.key = home, seals, key

    def path(self, project_key: str) -> Path:
        return safe(self.home, f"continuity/{project_key}.json")

    def read(
        self, project_key: str, grant: dict[str, Any], project: dict[str, Any]
    ) -> dict[str, Any] | None:
        state = self.read_owned(project_key)
        if state is None or state["grant_id"] != grant["grant_id"] or state["project"] != project:
            return None
        return state

    def read_owned(self, project_key: str) -> dict[str, Any] | None:
        try:
            return self.seals.read(self.path(project_key), "continuity")
        except FileNotFoundError:
            return None

    def keys(self) -> list[str]:
        return [
            path.stem
            for path in islice(safe(self.home, "continuity").glob("p-*.json"), 400)
            if re.fullmatch(r"p-[0-9a-f]{32}", path.stem)
        ]

    def write(self, project_key: str, state: dict[str, Any]) -> None:
        self.seals.write(self.path(project_key), state, "continuity")

    @staticmethod
    def current(state: dict[str, Any] | None) -> dict[str, Any] | None:
        checkpoint = (state or {}).get("checkpoint")
        return checkpoint if checkpoint and checkpoint["expires_at"] > time.time() else None

    @staticmethod
    def summary(checkpoint: dict[str, Any]) -> dict[str, Any]:
        resumed_at = checkpoint["resumed_at"]
        return {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "status": "resumed" if resumed_at is not None else "saved",
            "saved_at": checkpoint["saved_at"],
            "resumed_at": resumed_at,
            "task_class": checkpoint["task_class"],
            "guidance": checkpoint["guidance"],
        }

    def cipher(self) -> AESGCM:
        if self.key is None:
            raise ValueError("The secure checkpoint store is unavailable")
        return AESGCM(
            HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=PURPOSE).derive(self.key())
        )

    @staticmethod
    def aad(state: dict[str, Any], checkpoint: dict[str, Any]) -> bytes:
        return json.dumps(
            [state["grant_id"], state["project"], state["generation"], checkpoint["checkpoint_id"]],
            sort_keys=True,
        ).encode()

    def encrypt(
        self, state: dict[str, Any], checkpoint: dict[str, Any], content: dict[str, Any]
    ) -> str:
        payload = json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()
        if len(payload) > MAX_CHECKPOINT_BYTES:
            raise ValueError("The checkpoint exceeds its supported size")
        nonce = os.urandom(12)
        cipher = self.cipher().encrypt(nonce, payload, self.aad(state, checkpoint))
        return base64.b64encode(nonce + cipher).decode()

    def decrypt(self, state: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = base64.b64decode(checkpoint["encrypted"], validate=True)
            if not 28 <= len(encoded) <= MAX_CHECKPOINT_BYTES + 28:
                raise ValueError("The checkpoint has an invalid size")
            payload = self.cipher().decrypt(encoded[:12], encoded[12:], self.aad(state, checkpoint))
            content = json.loads(payload)
            if not isinstance(content, dict):
                raise ValueError("The checkpoint has an invalid format")
            return content
        except (InvalidTag, ValueError, TypeError, KeyError):
            raise ValueError("The checkpoint could not be verified") from None
