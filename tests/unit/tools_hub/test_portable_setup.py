"""Exercise explicit portable setup approval and connected task use."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from adaptation_compiler_lab.desktop.engine_protocol import EngineProtocolRouter, EngineRequest
from adaptation_compiler_lab.tools_hub.portable_setup import RepositoryCheck
from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.service import HubService, project_key
from adaptation_compiler_lab.tools_hub.task_lifecycle import TaskOwner

from .test_continuity_protocol import ReadResponse, call_stream, packet, prep, tool
from .test_integration import make_service

DRAFT: dict[str, Any] = {
    "title": "Harbor maintenance",
    "items": [
        {"id": "skill", "kind": "skill", "title": "Procedure", "text": "## Exact guidance"},
        {"id": "fact", "kind": "knowledge", "title": "Known fact", "text": "The harbor is amber."},
        {"id": "style", "kind": "preference", "title": "Style", "text": "Lead with the result."},
        {
            "id": "check",
            "kind": "check",
            "title": "Harbor marker",
            "path": "marker.txt",
            "operation": "file_contains",
            "text": "Amber harbor",
        },
    ],
}


def desktop(protocol: HubProtocol, operation: str, **params: Any) -> dict[str, Any]:
    return protocol.dispatch(f"portable_setup.{operation}", params, idempotency_key=uuid4().hex)


@pytest.fixture
def package(service: HubService, tmp_path: Path) -> tuple[HubProtocol, Path, dict[str, Any]]:
    sender = tmp_path / "sender"
    sender.mkdir()
    publisher = HubProtocol(make_service(sender))
    preview = desktop(publisher, "export.preview", **DRAFT)
    destination = tmp_path / "harbor.temper-setup"
    with pytest.raises(ValueError, match="Preview this exact"):
        desktop(
            publisher, "export.create", destination=str(destination), digest="sha256:" + "0" * 64
        )
    assert (
        desktop(publisher, "export.create", destination=str(destination), digest=preview["digest"])
        == preview
    )
    assert service.seals.signer.fingerprint != preview["signer_fingerprint"]
    return HubProtocol(service), destination, preview


def connect(service: HubService) -> None:
    grant = service.grant(active=True)
    assert grant is not None
    service.seals.write(
        service.home / "permission.json", {**grant, "bridge_configured": True}, "permission"
    )


def review(protocol: HubProtocol, path: Path) -> dict[str, Any]:
    return desktop(protocol, "import.preview", source=str(path), project_id="repo")


def approve(protocol: HubProtocol, preview: dict[str, Any]) -> dict[str, Any]:
    return desktop(
        protocol,
        "import.approve",
        project_id=preview["project_id"],
        digest=preview["digest"],
        active_digest=preview["active_digest"],
    )


def test_cross_owner_roundtrip_with_fresh_agent_and_live_check(
    service: HubService, package: tuple[HubProtocol, Path, dict[str, Any]]
) -> None:
    recipient, path, exported = package
    assert desktop(recipient, "status", project_id="repo") == {"active": None}
    preview = review(recipient, path)
    assert preview["digest"] == exported["digest"]
    assert preview["source_name"] == path.name
    with pytest.raises(ValueError, match="Connect Codex"):
        approve(recipient, preview)
    connect(service)
    path.unlink()
    assert approve(recipient, preview) == exported
    assert desktop(HubProtocol(service), "status", project_id="repo") == {"active": exported}
    storage = service.portable_setups.path(project_key("repo")).read_text()
    assert "Exact guidance" not in storage and "amber" not in storage

    root = service.project_inventory()["repo"]
    client = HubProtocol(service, task_owner=TaskOwner.current())

    def conversation(read: ReadResponse) -> Any:
        yield prep()
        prepared = packet(read())
        assert prepared["portable_setup"]["digest"] == exported["digest"]
        assert "Exact guidance" not in json.dumps(prepared["portable_setup"])
        task = {"project_id": "repo", "task_receipt": prepared["task_receipt"]}
        yield tool("setup_context", **task)
        context = packet(read())["setup"]
        assert context["skills"] == [{"id": "skill", "title": "Procedure"}]
        assert context["knowledge"][0]["text"] == "The harbor is amber."
        assert context["preferences"][0]["text"] == "Lead with the result."
        assert context["checks"] == [{"id": "check", "title": "Harbor marker"}]
        yield tool("setup_skill", **task, digest=context["digest"], item_id="skill")
        assert packet(read())["item"]["text"] == "## Exact guidance"
        yield tool("setup_check", **task, digest=context["digest"], item_id="check")
        assert packet(read())["passed"] is False
        (root / "marker.txt").write_text("Amber harbor", encoding="utf-8")
        yield tool("setup_check", **task, digest=context["digest"], item_id="check")
        assert packet(read())["passed"] is True
        yield tool("setup_context", **{**task, "project_id": "different"})
        assert "error" in read()
        desktop(recipient, "remove", project_id="repo", digest=exported["digest"])
        yield tool("setup_context", **task)
        assert "approved setup changed" in read()["error"]["message"]
        yield tool("finish", task_receipt=task["task_receipt"], outcome="completed")
        assert packet(read())["outcome"] == "completed"

    call_stream(client, conversation)
    assert desktop(recipient, "status", project_id="repo") == {"active": None}


def test_tamper_invalidates_previous_preview_and_stale_revision_fails(
    service: HubService, package: tuple[HubProtocol, Path, dict[str, Any]]
) -> None:
    recipient, path, exported = package
    connect(service)
    preview = review(recipient, path)
    changed = json.loads(path.read_bytes())
    changed["items"][0]["text"] = "Tampered guidance"
    raw = path.read_bytes()
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid format, content, or signature"):
        review(recipient, path)
    with pytest.raises(ValueError, match="Preview this exact"):
        approve(recipient, preview)
    path.write_bytes(raw)
    preview = review(recipient, path)
    concurrent = HubProtocol(service)
    approve(concurrent, review(concurrent, path))
    with pytest.raises(ValueError, match="active setup changed"):
        approve(recipient, preview)
    desktop(concurrent, "remove", project_id="repo", digest=exported["digest"])
    with pytest.raises(ValueError, match="repository setup changed"):
        approve(recipient, preview)


def test_setup_router_preserves_existing_onboarding_and_excludes_agent_import(
    service: HubService, package: tuple[HubProtocol, Path, dict[str, Any]]
) -> None:
    _, path, exported = package
    connect(service)
    router = EngineProtocolRouter(None, tools_hub_factory=lambda: service)

    def request(method: str, params: dict[str, Any]) -> EngineRequest:
        return EngineRequest(
            protocol_version="temper-engine-protocol/v1",
            request_id=uuid4().hex,
            method=method,
            params=params,
            idempotency_key=uuid4().hex,
        )

    assert router.handle(request("setup.status", {})).ok
    args = {"source": str(path), "project_id": "repo"}
    preview = router.handle(request("portable_setup.import.preview", args))
    assert preview.ok and preview.result is not None
    assert preview.snapshot_digest == exported["digest"]
    approval = router.handle(
        request(
            "portable_setup.import.approve",
            {"project_id": "repo", "digest": preview.result["digest"], "active_digest": None},
        )
    )
    assert approval.ok and approval.result == exported
    denied = router.handle(request("portable_setup.status", {"project_id": "unauthorized"}))
    assert not denied.ok and denied.error is not None
    assert denied.error.code == "portable_setup_unavailable"
    assert str(path) not in denied.error.message
    with pytest.raises(ValueError, match="Unsupported"):
        HubProtocol(service).dispatch("portable_setup.import.preview", args, agent=True)


def test_unreadable_setup_reset_requires_exact_revision_and_preserves_permission(
    service: HubService,
    package: tuple[HubProtocol, Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipient, path, exported = package
    connect(service)
    approve(recipient, review(recipient, path))
    record = service.portable_setups.path(project_key("repo"))
    permission = (service.home / "permission.json").read_bytes()
    with pytest.raises(ValueError, match="readable"):
        desktop(recipient, "reset", project_id="repo", digest=exported["digest"])
    record.write_text("First broken record")
    first = desktop(recipient, "status", project_id="repo")
    assert first["active"] is None and first["issue"] == "unavailable"
    assert first["recovery_digest"].startswith("sha256:")
    record.write_text("Changed broken record")
    with pytest.raises(ValueError, match="changed"):
        desktop(recipient, "reset", project_id="repo", digest=first["recovery_digest"])
    current = desktop(recipient, "status", project_id="repo")
    assert current["recovery_digest"] != first["recovery_digest"]
    with monkeypatch.context() as patch:
        patch.setattr(service.portable_setups, "key", None)
        assert desktop(recipient, "status", project_id="repo")["recovery_digest"] is None
        with pytest.raises(ValueError, match="secure setup store"):
            desktop(recipient, "reset", project_id="repo", digest=current["recovery_digest"])
    assert desktop(recipient, "reset", project_id="repo", digest=current["recovery_digest"]) == {
        "active": None
    }
    assert desktop(recipient, "status", project_id="repo") == {"active": None}
    assert (service.home / "permission.json").read_bytes() == permission
    assert approve(recipient, review(recipient, path)) == exported


@pytest.mark.parametrize(
    "path", ["../marker", ".git/config", "C:/temp/file", "data/.env", "secrets.txt", "config.jsonl"]
)
def test_check_rejects_out_of_scope_paths(path: str) -> None:
    with pytest.raises(ValueError):
        RepositoryCheck(id="safe", kind="check", title="Check", operation="file_exists", path=path)


def test_check_cannot_open_linked_or_over_limit_files(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    marker.write_bytes(b"x")
    target = tmp_path / "target"
    os.link(marker, target)
    check = RepositoryCheck(
        id="safe", kind="check", title="Check", operation="file_exists", path="target"
    )
    with pytest.raises(ValueError, match="bounded regular"):
        check.run(tmp_path)
    target.unlink()
    target.write_bytes(b"x" * 1_048_577)
    with pytest.raises(ValueError, match="bounded regular"):
        check.run(tmp_path)


@pytest.mark.parametrize(
    "text", ["user: pasted chat", "C:/tmp/local", "sk-proj-123456789abcdefghijklm", "~~~"]
)
def test_curated_text_admission(text: str, service: HubService) -> None:
    protocol = HubProtocol(service)
    draft = {"title": "Setup", "items": [{**DRAFT["items"][0], "text": text}]}
    if text == "~~~":
        assert desktop(protocol, "export.preview", **draft)["items"][0]["text"] == text
    else:
        with pytest.raises(ValueError, match="unsafe, invalid"):
            desktop(protocol, "export.preview", **draft)


@pytest.mark.parametrize(
    "token",
    ["ghp_123456789abcdefghijklm", "a1234567-1234-1234-1234-123456789abc"],
)
def test_setup_rejects_sensitive_ids_and_path_components(token: str) -> None:
    check = {
        "id": "check",
        "kind": "check",
        "title": "Marker",
        "path": "fixtures/marker.txt",
        "operation": "file_exists",
    }
    assert RepositoryCheck.model_validate(check).path == "fixtures/marker.txt"
    with pytest.raises(ValueError):
        RepositoryCheck.model_validate({**check, "id": token})
    with pytest.raises(ValueError):
        RepositoryCheck.model_validate({**check, "path": f"fixtures/{token}/marker.txt"})
