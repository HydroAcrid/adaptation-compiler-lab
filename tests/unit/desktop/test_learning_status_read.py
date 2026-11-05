from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import MagicMock

import pytest

from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.desktop.engine_protocol import (
    PROTOCOL_VERSION,
    EngineProtocolRouter,
    EngineRequest,
    EngineResponse,
)
from tests.unit.autonomy.test_autonomy import Clock, calibrated
from tests.unit.autonomy.test_autonomy import app as app


def read(router: EngineProtocolRouter, **params: Any) -> EngineResponse:
    return router.handle(
        EngineRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id="learning-status",
            method="autonomy.status",
            params=params,
        )
    )


def ready(app: tuple[AutonomyApplicationService, Clock]) -> AutonomyApplicationService:
    service, clock = app
    calibrated(service, clock)
    service.set_switch("personalization", True, key="owner-enabled")
    return service


def test_learning_status_is_calculated_once_with_the_existing_mutation_binding(
    app: tuple[AutonomyApplicationService, Clock], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ready(app)
    router = EngineProtocolRouter(MagicMock(), autonomy_factory=lambda: service)
    original = service.status
    calls = 0

    def counted() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(service, "status", counted)
    response = read(router)
    assert response.ok, response.error
    assert response.result is not None
    assert response.result["personalization_enabled"] is True
    assert response.result["automatic_serving_ready"] is True
    assert calls == 1, "one desktop read must calculate status only once"
    monkeypatch.setattr(service, "status", original)
    assert response.snapshot_digest == service.snapshot_digest

    changed = router.handle(
        EngineRequest(
            protocol_version=PROTOCOL_VERSION,
            request_id="owner-disable",
            method="autonomy.personalization.disable",
            expected_snapshot_digest=response.snapshot_digest,
            idempotency_key="disable-with-displayed-state",
        )
    )
    assert changed.ok, changed.error
    assert changed.result is not None
    assert changed.result["personalization_enabled"] is False


def test_external_switch_change_is_reflected_in_status_and_digest(
    app: tuple[AutonomyApplicationService, Clock], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ready(app)
    router = EngineProtocolRouter(MagicMock(), autonomy_factory=lambda: service)
    original = service.status
    calls = 0

    def change_after_read() -> dict[str, Any]:
        nonlocal calls
        value = original()
        calls += 1
        if calls == 1:
            service.set_switch("personalization", False, key="external-owner-disable")
        return value

    monkeypatch.setattr(service, "status", change_after_read)
    response = read(router)
    assert response.ok, response.error
    assert response.result is not None
    assert response.result["personalization_enabled"] is False, (
        "do not display a stale enabled state with a newer disabled-state digest"
    )
    assert calls == 2
    monkeypatch.setattr(service, "status", original)
    assert response.snapshot_digest == service.snapshot_digest


def test_continuously_changing_status_returns_retryable_error_and_worker_recovers(
    app: tuple[AutonomyApplicationService, Clock], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ready(app)
    router = EngineProtocolRouter(MagicMock(), autonomy_factory=lambda: service)
    original = service.status
    calls = 0

    def always_changed() -> dict[str, Any]:
        nonlocal calls
        value = original()
        calls += 1
        service.store.append(
            f"other-process-{calls}", "protocol_receipt", {"result": {}}, at=service.clock()
        )
        return value

    monkeypatch.setattr(service, "status", always_changed)
    response = read(router)
    assert not response.ok
    assert response.error is not None
    assert response.error.code == "autonomy_state_changed"
    assert response.error.retryable is True
    assert response.snapshot_digest is None
    assert calls == 2, "a changing store must not cause an unbounded status retry"
    monkeypatch.setattr(service, "status", original)
    assert read(router).ok


def test_fresh_status_still_rejects_tampered_signed_history(
    app: tuple[AutonomyApplicationService, Clock],
) -> None:
    service = ready(app)
    router = EngineProtocolRouter(MagicMock(), autonomy_factory=lambda: service)
    assert read(router).ok
    with sqlite3.connect(service.store.path) as connection, connection:
        connection.execute("DROP TRIGGER autonomy_no_update")
        connection.execute("UPDATE autonomy_events SET payload='{}' WHERE sequence=1")
    response = read(router)
    assert not response.ok
    assert response.result is None
    assert response.error is not None
    assert response.error.code == "autonomy_unavailable"


def test_status_reader_still_rejects_parameters(
    app: tuple[AutonomyApplicationService, Clock],
) -> None:
    service = ready(app)
    router = EngineProtocolRouter(MagicMock(), autonomy_factory=lambda: service)
    assert not read(router, project_id="another-project").ok
