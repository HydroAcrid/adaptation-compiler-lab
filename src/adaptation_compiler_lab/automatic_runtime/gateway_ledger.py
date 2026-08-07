"""Append-only raw-free persistence for the writable gateway."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    ChangeApplicationReceipt,
    GatewayInstrumentMetrics,
    GatewaySession,
    GatewayTurnReceipt,
    NotificationInboxEntry,
    RuntimeNotificationReceipt,
    RuntimeWatcherHeartbeat,
    VerificationReceipt,
    WorkspaceChangeReceipt,
)
from adaptation_compiler_lab.automatic_runtime.workspace_gateway import CapturedChangeBundle
from adaptation_compiler_lab.persistence.errors import RecordConflictError
from adaptation_compiler_lab.persistence.raw import RawPayloadRef
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

ModelT = TypeVar("ModelT", bound=BaseModel)


class GatewayLedger:
    """Small typed adapter over migration 0011 tables."""

    def __init__(self, path: Path, *, subject_id: str) -> None:
        self._path = path
        self._subject_id = subject_id

    def _append(
        self,
        *,
        table: str,
        key_column: str,
        key: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        model: BaseModel,
    ) -> bool:
        with sqlite3.connect(self._path) as connection:
            inserted = self._insert(
                connection,
                table=table,
                key_column=key_column,
                key=key,
                columns=columns,
                values=values,
                model=model,
            )
            connection.commit()
        return inserted

    @staticmethod
    def _insert(
        connection: sqlite3.Connection,
        *,
        table: str,
        key_column: str,
        key: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        model: BaseModel,
    ) -> bool:
        payload = canonical_json(model)
        digest = str(canonical_digest(model)).removeprefix("sha256:")
        existing = connection.execute(
            f"SELECT canonical_json, content_sha256 FROM {table} WHERE {key_column} = ?",
            (key,),
        ).fetchone()
        if existing is not None:
            if tuple(existing) == (payload, digest):
                return False
            raise RecordConflictError(f"{table} identifier names different immutable content")
        names = (*columns, "canonical_json", "content_sha256")
        placeholders = ", ".join("?" for _ in names)
        connection.execute(
            f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders})",
            (*values, payload, digest),
        )
        return True

    def append_inbox(self, entry: NotificationInboxEntry) -> bool:
        if entry.subject_id != self._subject_id:
            raise ValueError("notification crossed the ledger subject")
        return self._append(
            table="runtime_notification_inbox",
            key_column="entry_id",
            key=entry.entry_id,
            columns=("entry_id", "subject_id", "kind", "created_at"),
            values=(entry.entry_id, entry.subject_id, entry.kind, entry.created_at.isoformat()),
            model=entry,
        )

    def append_notification_receipt(self, receipt: RuntimeNotificationReceipt) -> bool:
        return self._append(
            table="runtime_notification_receipts",
            key_column="receipt_id",
            key=receipt.receipt_id,
            columns=("receipt_id", "entry_id", "channel", "status", "recorded_at"),
            values=(
                receipt.receipt_id,
                receipt.entry_id,
                receipt.channel,
                receipt.status,
                receipt.recorded_at.isoformat(),
            ),
            model=receipt,
        )

    def append_heartbeat(self, heartbeat: RuntimeWatcherHeartbeat) -> bool:
        return self._append(
            table="runtime_watcher_heartbeats",
            key_column="heartbeat_id",
            key=heartbeat.heartbeat_id,
            columns=("heartbeat_id", "lease_id", "sequence", "observed_at"),
            values=(
                heartbeat.heartbeat_id,
                heartbeat.lease_id,
                heartbeat.sequence,
                heartbeat.observed_at.isoformat(),
            ),
            model=heartbeat,
        )

    def append_session(self, session: GatewaySession) -> bool:
        if session.subject_id != self._subject_id:
            raise ValueError("gateway session crossed the ledger subject")
        return self._append(
            table="runtime_gateway_sessions",
            key_column="session_id",
            key=session.session_id,
            columns=("session_id", "subject_id", "project_id", "status", "started_at"),
            values=(
                session.session_id,
                session.subject_id,
                session.project_id,
                session.status.value,
                session.started_at.isoformat(),
            ),
            model=session,
        )

    def append_turn(self, turn: GatewayTurnReceipt) -> bool:
        return self._append(
            table="runtime_gateway_turns",
            key_column="receipt_id",
            key=turn.receipt_id,
            columns=("receipt_id", "session_id", "sequence", "status", "completed_at"),
            values=(
                turn.receipt_id,
                turn.session_id,
                turn.sequence,
                turn.status,
                turn.completed_at.isoformat(),
            ),
            model=turn,
        )

    def append_verification(self, receipt: VerificationReceipt) -> bool:
        return self._append(
            table="runtime_verification_receipts",
            key_column="receipt_id",
            key=receipt.receipt_id,
            columns=("receipt_id", "session_id", "command_id", "completed_at"),
            values=(
                receipt.receipt_id,
                receipt.session_id,
                receipt.command_id,
                receipt.completed_at.isoformat(),
            ),
            model=receipt,
        )

    def append_change_bundle(self, bundle: CapturedChangeBundle) -> bool:
        receipt = bundle.receipt
        if receipt.subject_id != self._subject_id:
            raise ValueError("change bundle crossed the ledger subject")
        reference = bundle.raw_reference
        return self._append(
            table="runtime_workspace_change_receipts",
            key_column="receipt_id",
            key=receipt.receipt_id,
            columns=(
                "receipt_id",
                "session_id",
                "subject_id",
                "captured_at",
                "raw_sha256",
                "raw_size_bytes",
                "raw_media_type",
                "raw_relative_path",
            ),
            values=(
                receipt.receipt_id,
                receipt.session_id,
                receipt.subject_id,
                receipt.captured_at.isoformat(),
                reference.sha256,
                reference.size_bytes,
                reference.media_type,
                reference.relative_path,
            ),
            model=receipt,
        )

    def append_application_outcome(
        self,
        receipt: ChangeApplicationReceipt,
        verifications: tuple[VerificationReceipt, ...],
    ) -> None:
        """Atomically persist one application decision and all supporting checks."""

        if self.session(receipt.session_id) is None:
            raise ValueError("change application crossed the ledger subject")
        with sqlite3.connect(self._path) as connection:
            for verification in verifications:
                self._insert(
                    connection,
                    table="runtime_verification_receipts",
                    key_column="receipt_id",
                    key=verification.receipt_id,
                    columns=("receipt_id", "session_id", "command_id", "completed_at"),
                    values=(
                        verification.receipt_id,
                        verification.session_id,
                        verification.command_id,
                        verification.completed_at.isoformat(),
                    ),
                    model=verification,
                )
            self._insert(
                connection,
                table="runtime_change_application_receipts",
                key_column="receipt_id",
                key=receipt.receipt_id,
                columns=("receipt_id", "session_id", "status", "recorded_at"),
                values=(
                    receipt.receipt_id,
                    receipt.session_id,
                    receipt.status.value,
                    receipt.recorded_at.isoformat(),
                ),
                model=receipt,
            )
            connection.commit()

    def inbox(self) -> tuple[NotificationInboxEntry, ...]:
        return self._read_many(
            "SELECT canonical_json, content_sha256 FROM runtime_notification_inbox "
            "WHERE subject_id = ? ORDER BY created_at, entry_id",
            (self._subject_id,),
            NotificationInboxEntry,
        )

    def sessions(self) -> tuple[GatewaySession, ...]:
        return self._read_many(
            "SELECT canonical_json, content_sha256 FROM runtime_gateway_sessions "
            "WHERE subject_id = ? ORDER BY started_at, session_id",
            (self._subject_id,),
            GatewaySession,
        )

    def session(self, session_id: str) -> GatewaySession | None:
        sessions = tuple(item for item in self.sessions() if item.session_id == session_id)
        if len(sessions) > 1:
            raise ValueError("gateway session identity is ambiguous")
        return None if not sessions else sessions[0]

    def application(self, session_id: str) -> ChangeApplicationReceipt | None:
        applications = self._read_many(
            "SELECT application.canonical_json, application.content_sha256 "
            "FROM runtime_change_application_receipts AS application "
            "JOIN runtime_gateway_sessions AS session "
            "ON session.session_id = application.session_id "
            "WHERE session.subject_id = ? AND application.session_id = ?",
            (self._subject_id, session_id),
            ChangeApplicationReceipt,
        )
        if len(applications) > 1:
            raise ValueError("gateway application identity is ambiguous")
        return None if not applications else applications[0]

    def change_bundle(self, session_id: str) -> CapturedChangeBundle | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                """
                SELECT canonical_json, content_sha256, raw_sha256, raw_size_bytes,
                       raw_media_type, raw_relative_path
                FROM runtime_workspace_change_receipts
                WHERE subject_id = ? AND session_id = ?
                """,
                (self._subject_id, session_id),
            ).fetchone()
        if row is None:
            return None
        receipt = WorkspaceChangeReceipt.model_validate_json(row[0])
        if canonical_json(receipt) != row[0] or (
            str(canonical_digest(receipt)).removeprefix("sha256:") != row[1]
        ):
            raise ValueError("stored change receipt failed integrity verification")
        return CapturedChangeBundle(
            receipt=receipt,
            raw_reference=RawPayloadRef(
                sha256=str(row[2]),
                size_bytes=int(row[3]),
                media_type=str(row[4]),
                relative_path=str(row[5]),
            ),
        )

    def metrics(self, *, generated_at: datetime) -> GatewayInstrumentMetrics:
        with sqlite3.connect(self._path) as connection:

            def scalar(query: str, values: tuple[object, ...] = ()) -> int:
                row = connection.execute(query, values).fetchone()
                if row is None:
                    raise ValueError("gateway metric query returned no row")
                return int(row[0])

            sessions = self.sessions()
            return GatewayInstrumentMetrics(
                subject_id=self._subject_id,
                session_count=len(sessions),
                turn_count=scalar(
                    "SELECT COUNT(*) FROM runtime_gateway_turns WHERE session_id IN "
                    "(SELECT session_id FROM runtime_gateway_sessions WHERE subject_id = ?)",
                    (self._subject_id,),
                ),
                notification_count=scalar(
                    "SELECT COUNT(*) FROM runtime_notification_inbox WHERE subject_id = ?",
                    (self._subject_id,),
                ),
                watcher_heartbeat_count=scalar("SELECT COUNT(*) FROM runtime_watcher_heartbeats"),
                captured_bundle_count=scalar(
                    "SELECT COUNT(*) FROM runtime_workspace_change_receipts WHERE subject_id = ?",
                    (self._subject_id,),
                ),
                applied_count=scalar(
                    "SELECT COUNT(*) FROM runtime_change_application_receipts "
                    "WHERE status = 'applied'"
                ),
                rolled_back_count=scalar(
                    "SELECT COUNT(*) FROM runtime_change_application_receipts "
                    "WHERE status = 'rolled_back'"
                ),
                discarded_count=scalar(
                    "SELECT COUNT(*) FROM runtime_change_application_receipts "
                    "WHERE status = 'discarded'"
                ),
                refused_count=scalar(
                    "SELECT COUNT(*) FROM runtime_change_application_receipts "
                    "WHERE status = 'refused'"
                ),
                total_projection_utf8_bytes=sum(item.projection_utf8_bytes for item in sessions),
                generated_at=generated_at,
            )

    def _read_many(
        self,
        query: str,
        values: tuple[object, ...],
        model_type: type[ModelT],
    ) -> tuple[ModelT, ...]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(query, values).fetchall()
        result: list[ModelT] = []
        for payload, digest in rows:
            model = model_type.model_validate_json(payload)
            if canonical_json(model) != payload or (
                str(canonical_digest(model)).removeprefix("sha256:") != digest
            ):
                raise ValueError("stored gateway record failed integrity verification")
            result.append(model)
        return tuple(result)
