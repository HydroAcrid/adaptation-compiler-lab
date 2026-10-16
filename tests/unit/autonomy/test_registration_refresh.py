from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.desktop.engine_protocol import (
    PROTOCOL_VERSION,
    EngineProtocolRouter,
    EngineRequest,
)
from tests.unit.autonomy.test_codex_source import fixture as fixture


def test_registration_refreshes_existing_learning_service_without_restart(
    fixture: dict[str, Any],
) -> None:
    projects = dict(fixture["service"].projects)
    added = fixture["home"].parent / "added"
    added.mkdir()
    digest = "sha256:" + "d" * 64
    desktop = MagicMock()
    desktop.load.return_value.content_digest = digest
    setup = MagicMock()
    setup.register_project.side_effect = lambda **kwargs: (
        projects.update({"added": added})
        or MagicMock(project_id="added", display_name="Added", capture_after_epoch_seconds=0)
    )

    def factory() -> AutonomyApplicationService:
        return AutonomyApplicationService(
            store=fixture["store"], projects=projects, codex_home=fixture["home"]
        )

    router = EngineProtocolRouter(
        cast(Any, desktop), setup_factory=lambda: cast(Any, setup), autonomy_factory=factory
    )

    def request(method: str, **kwargs: Any) -> Any:
        return router.handle(
            EngineRequest(
                protocol_version=PROTOCOL_VERSION, request_id=method, method=method, **kwargs
            )
        )

    assert request("autonomy.status").ok  # The desktop's initial status read caches the service.
    registration = request(
        "project.register",
        params={"preview_token": "registration"},
        expected_snapshot_digest=digest,
        idempotency_key="register",
    )
    assert registration.ok
    preview = request(
        "autonomy.grant.preview",
        params={
            "project_ids": ["added"],
            "categories": ["communication_detail"],
            "trust_authorized_chats": True,
        },
    )
    assert preview.ok, "Registered project must be available to learning without restart"
    assert preview.result["project_ids"] == ["added"]
    # Registration/preview alone cannot widen the existing signed learning grant.
    assert fixture["service"].grant().project_ids == ("project",)
