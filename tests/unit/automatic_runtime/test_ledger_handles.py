"""Ledger reads and writes must release SQLite handles before temporary cleanup."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.automatic_runtime import AutomaticRuntimeLedger, initial_runtime_state
from adaptation_compiler_lab.automatic_runtime.gateway_ledger import GatewayLedger
from adaptation_compiler_lab.automatic_runtime.gateway_models import NotificationInboxEntry
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from tests.unit.automatic_runtime.test_runtime import NOW, _runtime


def test_ledger_connections_close_without_waiting_for_garbage_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(path).initialize()
    connect = sqlite3.connect
    connections: list[sqlite3.Connection] = []

    def retained_connection(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", retained_connection)
    _service, policy = _runtime(tmp_path)
    state = initial_runtime_state(policy)
    runtime = AutomaticRuntimeLedger(path, subject_id=state.subject_id)
    runtime.initialize(state)
    assert runtime.current() == state
    gateway = GatewayLedger(path, subject_id=state.subject_id)
    gateway.append_inbox(
        NotificationInboxEntry(
            entry_id="fictional-notice",
            subject_id=state.subject_id,
            notice_digest="sha256:" + "a" * 64,
            kind="needs_review",
            public_summary="Adaptation review available.",
            created_at=NOW,
        )
    )
    assert len(gateway.inbox()) == 1
    assert len(connections) >= 4
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
