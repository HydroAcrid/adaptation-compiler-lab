"""Separate append-only signed habit events; raw episodes remain encrypted."""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from adaptation_compiler_lab.governance.models import SignatureEnvelope
from adaptation_compiler_lab.governance.signing import GovernanceSigner, verify_detached_envelope
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class AutonomyIntegrityError(ValueError):
    """A habit event or its owner binding cannot be verified."""


class AutonomyStore:
    def __init__(
        self, path: Path, *, signer: GovernanceSigner, raw_store: LocalRawPayloadStore
    ) -> None:
        if not raw_store.encrypted:
            raise AutonomyIntegrityError("autonomy requires an encrypted raw store")
        root = path.expanduser().resolve()
        if any((parent / ".git").exists() for parent in (root.parent, *root.parents)):
            raise AutonomyIntegrityError("autonomy state must remain outside Git")
        root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root
        self.signer = signer
        self.raw_store = raw_store
        self._public = base64.b64encode(
            signer.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode("ascii")
        with closing(sqlite3.connect(root)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS autonomy_events (
                    sequence INTEGER PRIMARY KEY,
                    event_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    envelope TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    content_digest TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS autonomy_no_update
                BEFORE UPDATE ON autonomy_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
                CREATE TRIGGER IF NOT EXISTS autonomy_no_delete
                BEFORE DELETE ON autonomy_events BEGIN SELECT RAISE(ABORT, 'append-only'); END;
                """
            )

    def events(self) -> tuple[dict[str, Any], ...]:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            rows = connection.execute(
                "SELECT sequence,event_key,event_type,payload,envelope,"
                "previous_digest,content_digest "
                "FROM autonomy_events ORDER BY sequence"
            ).fetchall()
        previous = "sha256:" + "0" * 64
        result: list[dict[str, Any]] = []
        for index, row in enumerate(rows, 1):
            sequence, key, kind, payload, envelope, parent, digest = row
            if sequence != index or parent != previous:
                raise AutonomyIntegrityError("autonomy event chain changed")
            try:
                body = json.loads(payload)
                signed = {
                    "sequence": sequence,
                    "event_key": key,
                    "event_type": kind,
                    "payload": body,
                    "previous_digest": parent,
                    "subject_id": self.signer.subject_id,
                }
                signature = SignatureEnvelope.model_validate_json(envelope, strict=True)
                verify_detached_envelope(
                    signed,
                    signature,
                    public_key_base64=self._public,
                    expected_purpose="temper_autonomy_event",
                )
                observed = canonical_digest(
                    {**signed, "signature": signature.model_dump(mode="json")}
                )
            except (ValueError, TypeError) as error:
                raise AutonomyIntegrityError("autonomy event signature changed") from error
            if observed != digest:
                raise AutonomyIntegrityError("autonomy event digest changed")
            previous = digest
            result.append({"key": key, "type": kind, "payload": body, "digest": digest})
        return tuple(result)

    @property
    def head_digest(self) -> str:
        events = self.events()
        return events[-1]["digest"] if events else "sha256:" + "0" * 64

    def append(self, key: str, kind: str, payload: Mapping[str, Any], *, at: datetime) -> bool:
        verified = self.events()
        before = verified[-1]["digest"] if verified else "sha256:" + "0" * 64
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT event_type,payload FROM autonomy_events WHERE event_key=?", (key,)
            ).fetchone()
            rendered = canonical_json(dict(payload))
            if existing is not None:
                if existing != (kind, rendered):
                    raise AutonomyIntegrityError("autonomy idempotency key changed")
                return False
            latest = connection.execute(
                "SELECT sequence,content_digest FROM autonomy_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if latest is not None and latest[1] != before:
                raise AutonomyIntegrityError("autonomy state changed concurrently")
            sequence = 1 if latest is None else latest[0] + 1
            signed = {
                "sequence": sequence,
                "event_key": key,
                "event_type": kind,
                "payload": dict(payload),
                "previous_digest": before,
                "subject_id": self.signer.subject_id,
            }
            envelope = self.signer.envelope(signed, purpose="temper_autonomy_event", signed_at=at)
            digest = canonical_digest({**signed, "signature": envelope.model_dump(mode="json")})
            connection.execute(
                "INSERT INTO autonomy_events VALUES (?,?,?,?,?,?,?)",
                (sequence, key, kind, rendered, canonical_json(envelope), before, digest),
            )
        return True

    def save_raw(self, payload: bytes, *, media_type: str = "application/json") -> RawPayloadRef:
        return self.raw_store.put(payload, media_type=media_type)

    def raw(self, ref: Mapping[str, Any]) -> bytes:
        return self.raw_store.read(RawPayloadRef(**ref))

    def latest(self, kind: str) -> Mapping[str, Any] | None:
        return next(
            (event["payload"] for event in reversed(self.events()) if event["type"] == kind), None
        )

    def verify(self, payload: Mapping[str, Any], envelope: SignatureEnvelope, purpose: str) -> None:
        verify_detached_envelope(
            payload, envelope, public_key_base64=self._public, expected_purpose=purpose
        )
