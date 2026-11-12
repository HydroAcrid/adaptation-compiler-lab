"""Exercise continuity over separate Hub stdio connections and simulated host failures."""

from __future__ import annotations

import io
import json
from unittest.mock import patch
from uuid import uuid4

import pytest

from adaptation_compiler_lab.tools_hub.agent_bridge import serve_hub
from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.service import project_key
from adaptation_compiler_lab.tools_hub.task_lifecycle import TaskOwner

from .test_integration import make_service, wait_job


def tool(name: str, **arguments):
    return {"name": f"temper_hub_{name}", "arguments": arguments}


def call_stream(protocol, producer):
    output = io.StringIO()
    replies = []

    class Requests(io.StringIO):
        def readline(self, size=-1):
            if output.tell():
                output.seek(0)
                replies.extend(json.loads(line) for line in output)
                output.seek(0)
                output.truncate()
            request = next(requests, None)
            if request is None:
                return ""
            return (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": len(replies) + 1,
                        "method": "tools/call",
                        "params": request,
                    }
                )
                + "\n"
            )

    def response():
        return replies[-1]

    requests = iter(producer(response))
    serve_hub(protocol, stdin=Requests(), stdout=output)
    return replies


def packet(response):
    assert "error" not in response, response.get("error")
    return json.loads(response["result"]["content"][0]["text"])


def bind(response, session, turn, nonce=None):
    result = response()["result"]
    return tool(
        "bind_turn",
        session_id=session,
        turn_id=turn,
        lifecycle_nonce=nonce or result["structuredContent"]["lifecycle_nonce"],
    )


def desktop(service, operation, **arguments):
    return HubProtocol(service).dispatch(
        f"tools_hub.continuity.{operation}",
        arguments,
        expected_digest=service.state()["digest"],
        idempotency_key=uuid4().hex,
    )


@pytest.fixture
def continuity_service(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    other = tmp_path / "lantern"
    other.mkdir()
    (other / ".git").mkdir()
    (other / "AGENTS.md").write_text("Preserve this fictional repository.\n")
    monkeypatch.setattr(
        service, "project_inventory", lambda: {"repo": tmp_path / "repo", "other": other}
    )
    service.continuity.key = lambda: b"\x15" * 32
    preview = service.preview(["repo", "other"], ["superpowers"])
    service.enable(preview["preview_id"])
    assert wait_job(service)["state"] == "complete"
    grant = service.grant(active=True)
    service.seals.write(
        service.home / "permission.json",
        {**grant, "bridge_configured": True, "native_hooks_configured": True},
        "permission",
    )
    for project in ("repo", "other"):
        preview = desktop(service, "preview", project_id=project, enabled=True)
        assert desktop(service, "apply", preview_id=preview["preview_id"])["status"] == "enabled"
    return service


def prep(goal="Investigate the fictional check.", project="repo", **extra):
    return tool(
        "prepare",
        project_id=project,
        goal=goal,
        task_class="review",
        relative_directory=".",
        **extra,
    )


def checkpoint(prepared, step, expected=None):
    return tool(
        "checkpoint",
        task_receipt=prepared["task_receipt"],
        goal=prepared["effective_task"]["goal"],
        expected_checkpoint_id=expected,
        facts=["Source was checked."],
        requirements=["Keep the owner instructions."],
        progress=["Investigation complete."],
        checks=[],
        next_step=step,
    )


def finish(session, turn, outcome="completed"):
    return tool("end_turn", session_id=session, turn_id=turn, outcome=outcome)


def project(service, project_id="repo"):
    return next(row for row in service.state()["projects"] if row["id"] == project_id)


def test_wire_continuity_recovers_opaque_checkpoint_after_restarting_hub(continuity_service):
    service = continuity_service
    secret = f"fictional decision {uuid4().hex}{uuid4().hex}"
    a, b = HubProtocol(service), HubProtocol(service)
    initial = {}

    def write(response):
        yield prep()
        prepared = packet(response())
        yield bind(response, "actor-a", "first-turn")
        yield checkpoint(prepared, secret)
        initial.update(packet(response()))
        yield finish("actor-a", "first-turn")

    call_stream(a, write)
    assert project(service)["continuity"]["status"] == "saved"
    stored = service.continuity.path(project_key("repo")).read_bytes()
    assert secret.encode() not in stored
    resumed = {}

    def read(response):
        # Neither the continuation goal nor the unrelated repo contains the opaque value.
        yield prep("Continue the prior task.", project="other", continue_previous=True)
        assert "error" in response()
        assert secret not in json.dumps(response())
        yield prep("Continue the prior task.", continue_previous=True)
        context = packet(response())["continuity"]
        assert context["independent_human_evidence"] is False
        assert context["origin"] == "agent_reported_task_context"
        assert context["checks_verified_by_temper"] is False
        resumed.update(context)
        yield bind(response, "actor-b", "second-turn")
        yield finish("actor-b", "second-turn")

    call_stream(b, read)
    assert a.task_owner != b.task_owner
    assert resumed["checkpoint_id"] == initial["checkpoint_id"]
    assert resumed["handoff"]["next_step"] == secret
    assert project(service)["continuity"]["status"] == "resumed"


def test_wire_continuity_rejects_competing_writes_stale_receipts_and_forged_provenance(
    continuity_service,
):
    service = continuity_service
    a, b = HubProtocol(service), HubProtocol(service)
    previous = {}

    def write(response):
        yield prep()
        prepared = packet(response())
        previous.update(prepared)
        yield bind(response, "actor-a", "first-turn")
        yield checkpoint(prepared, "Run the first fictional verification.")
        initial = packet(response())
        yield checkpoint(prepared, "Run the conflicting fictional verification.")
        assert "error" in response()
        yield checkpoint(
            prepared, "Run the current fictional verification.", initial["checkpoint_id"]
        )
        current = packet(response())
        assert current["checkpoint_id"] != initial["checkpoint_id"]
        forged = checkpoint(prepared, "Claim this came from a person.", current["checkpoint_id"])
        forged["arguments"]["independent_human_evidence"] = True
        yield forged
        assert "error" in response()
        yield finish("actor-a", "first-turn")

    call_stream(a, write)

    def stale(response):
        yield checkpoint(previous, "Overwrite from the old connection.")
        assert "error" in response()
        yield tool(
            "continuity_acknowledge",
            task_receipt=previous["task_receipt"],
            checkpoint_id="a" * 32,
            session_id="forged",
        )
        assert "error" in response()
        yield prep("Continue the prior task.", continue_previous=True)
        assert (
            packet(response())["continuity"]["handoff"]["next_step"]
            == "Run the current fictional verification."
        )
        yield bind(response, "actor-b", "second-turn")
        yield finish("actor-b", "second-turn")

    call_stream(b, stale)
    assert project(service)["continuity"]["status"] == "resumed"


def test_wire_continuity_cancellation_preserves_checkpoint_and_revocation_blocks_resume(
    continuity_service,
):
    service = continuity_service
    before = {}

    def cancel(response):
        yield prep()
        prepared = packet(response())
        before.update(prepared)
        yield bind(response, "actor-a", "first-turn")
        yield checkpoint(prepared, "Run the already-saved fictional verification.")
        packet(response())
        yield finish("actor-a", "first-turn", "cancelled")
        yield checkpoint(prepared, "Replace the checkpoint after cancellation.")
        assert "error" in response()

    call_stream(HubProtocol(service), cancel)
    assert project(service)["continuity"]["status"] == "saved"
    preview = desktop(service, "preview", project_id="repo", enabled=False)
    desktop(service, "apply", preview_id=preview["preview_id"])

    def revoked(response):
        yield prep("Continue the prior task.", continue_previous=True)
        assert "error" in response() or packet(response())["continuity"]["handoff"] is None

    call_stream(HubProtocol(service), revoked)
    assert project(service)["continuity"] is None


def test_wire_continuity_ignores_wrong_hook_nonce_and_recovers_dead_task_owner(continuity_service):
    service = continuity_service
    # Simulate process death after a real save by replacing the scoped liveness probe.
    a = HubProtocol(service)
    prepared = {}

    def write(response):
        yield prep()
        prepared.update(packet(response()))
        yield bind(response, "actor-a", "first-turn")
        yield checkpoint(prepared, "Verify saved work after a process restart.")
        packet(response())

    call_stream(a, write)
    with patch.object(TaskOwner, "alive", lambda self: self != a.task_owner):
        service.tick()

    def read(response):
        yield prep("Continue the prior task.", continue_previous=True)
        context = packet(response())["continuity"]
        assert context["handoff"]["next_step"] == "Verify saved work after a process restart."
        yield bind(response, "actor-b", "second-turn", nonce="0" * 32)
        yield finish("actor-b", "second-turn")
        packet(response())

    call_stream(HubProtocol(service), read)
    # Delivery acknowledgement requires the native hook binding as well as a prepare result.
    assert project(service)["continuity"]["status"] == "saved"
