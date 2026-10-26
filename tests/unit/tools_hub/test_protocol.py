from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.desktop.engine_protocol import EngineProtocolRouter, EngineRequest
from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.service import HubService

from .test_integration import make_service, prepare, select


def test_desktop_permission_roundtrip_uses_the_real_typed_digest_contract(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    router = EngineProtocolRouter(None, tools_hub_factory=lambda: service)

    def call(method: str, params: dict[str, Any], digest: str | None = None) -> dict[str, Any]:
        request = EngineRequest.model_validate(
            {
                "protocol_version": "temper-engine-protocol/v1",
                "request_id": method,
                "method": method,
                "params": params,
                "expected_snapshot_digest": digest,
                "idempotency_key": method if digest else None,
            },
            strict=True,
        )
        result = router.handle(request)
        assert result.ok, result.error
        return dict(result.result or {})

    current = call("tools_hub.status", {})
    assert current["digest"].startswith("sha256:")
    preview = call(
        "tools_hub.permission.preview",
        {"project_ids": ["repo"], "source_ids": ["superpowers"]},
        current["digest"],
    )
    assert preview["source_specs"][0]["url"] == "https://github.com/obra/superpowers"


def test_unknown_methods_and_untyped_params_cannot_reach_the_manager(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    protocol = HubProtocol(service)
    with pytest.raises(ValueError, match="Unsupported"):
        protocol.dispatch("tools_hub.execute", {"argv": ["arbitrary"]}, agent=True)
    with pytest.raises(ValueError):
        protocol.dispatch(
            "tools_hub.prepare",
            {"project_id": "repo", "goal": "work", "task_class": "review", "path": "C:/"},
            agent=True,
        )
    assert not service.home.exists()


def test_current_subdirectory_instructions_invalidate_a_selection(service: HubService) -> None:
    root = service.home.parent / "repo/src"
    root.mkdir()
    result = service.prepare("repo", "Fix the tests", "debugging", "src")
    ticket = result["selection_ticket"]
    inspected = service.inspect(ticket, "superpowers/skills/debugging")
    (root / "AGENTS.md").write_text("Do not load extra skills here")
    with pytest.raises(ValueError, match="changed"):
        service.select(
            ticket,
            "repo",
            "Fix the tests",
            "debugging",
            ["superpowers/skills/debugging"],
            [inspected["inspection_receipt"]],
            "src",
        )


def test_prepared_selection_cannot_overwrite_another_tasks_new_profile(service: HubService) -> None:
    pending = prepare(service)
    other = prepare(service, "Investigate another failure")
    select(service, other, "Investigate another failure")
    with pytest.raises(ValueError, match="changed"):
        select(service, pending)
