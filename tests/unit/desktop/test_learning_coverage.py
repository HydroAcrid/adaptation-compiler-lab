from types import SimpleNamespace
from unittest.mock import MagicMock

from adaptation_compiler_lab.autonomy.project_registry import (
    LearningProjectRegistry,
    LearningProjectV1,
)
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker
from adaptation_compiler_lab.desktop.engine_protocol import (
    PROTOCOL_VERSION,
    EngineProtocolRouter,
    EngineRequest,
)
from tests.unit.autonomy.test_autonomy import app as app


def test_signed_learning_coverage_is_independent_of_legacy_task_access(app, tmp_path, monkeypatch):
    service, clock = app
    roots = dict(service.projects)
    # Same display names deliberately exercise identity rather than label matching.
    for index in range(56):
        root = tmp_path / str(index) / "project"
        root.mkdir(parents=True)
        roots[f"other-{index}"] = root
    registry = LearningProjectRegistry(
        service.store,
        tuple(
            LearningProjectV1(
                project_id=key,
                root=str(path),
                source_roots=(str(path),),
                capture_after_epoch_seconds=int(clock().timestamp()),
            )
            for key, path in roots.items()
        ),
        clock=clock,
    )
    service.background_worker = BackgroundHabitWorker(service, project_registry=registry)
    monkeypatch.setattr(service, "provenance_ready", lambda: True)
    legacy = MagicMock()
    legacy.load.return_value = SimpleNamespace(projects=["legacy-only"], health="consent_expired")
    router = EngineProtocolRouter(legacy, autonomy_factory=lambda: service)
    before = service.store.events()

    def read():
        response = router.handle(
            EngineRequest(
                protocol_version=PROTOCOL_VERSION, request_id="coverage", method="autonomy.status"
            )
        )
        assert response.ok, response.error
        return response.result

    result = read()
    assert len(result["project_access"]) == 57
    by_id = {p["project_id"]: p for p in result["project_access"]}
    assert by_id["project"]["learning_state"] == "on"
    assert by_id["project"]["learning_authorized"] is True
    assert all(
        not p["learning_authorized"] and p["learning_state"] == "off"
        for key, p in by_id.items()
        if key != "project"
    )
    assert service.store.events() == before
    assert result["capture_summary"]["captured_conversations"] == 0
    assert result["capture_summary"]["eligible_since"] == service.grant().issued_at.isoformat()
    assert all("root" not in p and "task_runner_enabled" not in p for p in by_id.values())
    legacy.load.assert_not_called()
    assert legacy.load.return_value.projects == ["legacy-only"]

    service.set_switch("learning", False, key="pause")
    assert read()["project_access"][-1]["learning_state"] == "paused"
    service.revoke_grant(key="revoke")
    assert all(
        not p["learning_authorized"] and p["learning_state"] == "off"
        for p in read()["project_access"]
    )
