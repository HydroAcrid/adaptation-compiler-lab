from __future__ import annotations

import secrets
import time
from typing import Any

import pytest

from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.service import HubService, project_key

GOAL = "Fix the failing tests"
HANDOFF: dict[str, Any] = {
    "facts": ["The fixture repository has two commands."],
    "requirements": ["Keep the existing command output."],
    "progress": ["The first command was updated."],
    "checks": ["Command A passed. Command B still needs a check."],
    "next_step": "Verify Command B with an empty argument.",
}


def desktop(service: HubService, method: str, **arguments: Any) -> dict[str, Any]:
    return HubProtocol(service).dispatch(
        "tools_hub.continuity." + method,
        arguments,
        expected_digest=service.state()["digest"],
        idempotency_key=secrets.token_hex(16),
    )


def set_continuity(service: HubService, enabled: bool) -> None:
    if enabled:
        grant = service.grant()
        assert grant is not None
        grant["bridge_configured"] = True
        service.seals.write(service.home / "permission.json", grant, "permission")
    preview = desktop(service, "preview", project_id="repo", enabled=enabled)
    result = desktop(service, "apply", preview_id=preview["preview_id"])
    assert result["status"] == ("enabled" if enabled else "disabled")


def prepare(agent: HubProtocol, **extra: Any) -> dict[str, Any]:
    return agent.dispatch(
        "tools_hub.prepare",
        {"project_id": "repo", "goal": GOAL, "task_class": "debugging", **extra},
        agent=True,
    )


def save(
    agent: HubProtocol,
    prepared: dict[str, Any],
    native_session: str = "fixture-origin",
    **extra: Any,
) -> dict[str, Any]:
    return agent.dispatch(
        "tools_hub.checkpoint",
        {
            "task_receipt": prepared["task_receipt"],
            "goal": prepared["effective_task"]["goal"],
            "expected_checkpoint_id": prepared["continuity"]["checkpoint_id"],
            **HANDOFF,
            **extra,
        },
        agent=True,
        native_session=native_session,
    )


def finish(agent: HubProtocol, prepared: dict[str, Any], outcome: str = "completed") -> None:
    result = agent.dispatch(
        "tools_hub.finish",
        {"task_receipt": prepared["task_receipt"], "outcome": outcome},
        agent=True,
    )
    assert result["status"] == "task_finished"


def test_continuity_defaults_off_until_project_opt_in(service: HubService) -> None:
    assert service.state()["projects"][0]["continuity_enabled"] is False
    agent = HubProtocol(service)
    prepared = prepare(agent)
    assert prepared["continuity"]["enabled"] is False
    with pytest.raises(ValueError, match="changed"):
        save(agent, prepared)
    with pytest.raises(ValueError, match="Connect Codex"):
        desktop(service, "preview", project_id="repo", enabled=True)
    assert not (service.home / "continuity").exists()


def test_two_connections_preserve_checkpoint_and_clean_approved_skill(service: HubService) -> None:
    set_continuity(service, True)
    first = HubProtocol(service)
    task = prepare(first)
    selected_id = "superpowers/skills/debugging"
    ticket = task["selection_ticket"]
    inspect = first.dispatch(
        "tools_hub.inspect", {"selection_ticket": ticket, "skill_id": selected_id}, agent=True
    )
    first.dispatch(
        "tools_hub.select",
        {
            **task["effective_task"],
            "selection_ticket": ticket,
            "choices": [selected_id],
            "inspections": [inspect["inspection_receipt"]],
        },
        agent=True,
    )
    checkpoint = save(first, task)
    checkpoint_id = checkpoint["checkpoint_id"]
    assert checkpoint["guidance"] == ["debugging"]
    assert save(first, task) == checkpoint  # Same in-flight request can safely be retried.
    repo = service.project_inventory()["repo"]
    installed = repo / ".agents/skills/debugging/SKILL.md"
    assert installed.is_file()
    finish(first, task, "cancelled")
    assert not installed.exists()
    state_file = service.continuity.path(project_key("repo"))
    stored = state_file.read_text()
    assert GOAL not in stored and HANDOFF["next_step"] not in stored
    assert "fixture-origin" not in stored
    assert HANDOFF["next_step"] not in str(service.state())

    other = HubProtocol(service)
    new_task = prepare(
        other, goal="Continue saved work", task_class="planning", continue_previous=True
    )
    assert new_task["task_receipt"] != task["task_receipt"]
    assert new_task["effective_task"]["goal"] == GOAL
    assert new_task["effective_task"]["task_class"] == "debugging"
    assert new_task["status"] == "ready"
    assert new_task["selected"] == ["debugging"]
    assert installed.is_file()
    assert new_task["continuity"]["handoff"] == HANDOFF
    assert new_task["continuity"]["independent_human_evidence"] is False
    assert new_task["continuity"]["checks_verified_by_temper"] is False
    acknowledge = {
        "task_receipt": new_task["task_receipt"],
        "checkpoint_id": checkpoint_id,
        "session_id": "fixture-origin",
    }
    other.dispatch("tools_hub.continuity.acknowledge", acknowledge, agent=True)
    assert service.state()["projects"][0]["continuity"]["status"] == "saved"
    other.dispatch(
        "tools_hub.continuity.acknowledge",
        {**acknowledge, "session_id": "fixture-fresh-session"},
        agent=True,
    )
    assert service.state()["projects"][0]["continuity"]["status"] == "resumed"
    assert desktop(service, "read", project_id="repo", checkpoint_id=checkpoint_id) == {
        "checkpoint_id": checkpoint_id,
        **HANDOFF,
    }
    finish(other, new_task)
    assert not installed.exists()


def test_unrelated_work_does_not_read_previous_task(service: HubService) -> None:
    set_continuity(service, True)
    first = HubProtocol(service)
    task = prepare(first)
    checkpoint = save(first, task)
    finish(first, task)
    other = HubProtocol(service)
    unrelated = prepare(other, goal="Explain the example", task_class="documentation")
    assert unrelated["continuity"]["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert unrelated["continuity"]["handoff"] is None
    finish(other, unrelated)
    matching = prepare(other, goal="fix  the failing tests")
    assert matching["continuity"]["handoff"] == HANDOFF
    with pytest.raises(ValueError, match="authorized"):
        prepare(other, project_id="unrelated", continue_previous=True)


def test_stale_writes_clear_and_reenable(service: HubService) -> None:
    set_continuity(service, True)
    agent = HubProtocol(service)
    prepared = prepare(agent)
    saved = save(agent, prepared)
    saved_id = saved["checkpoint_id"]
    with pytest.raises(ValueError, match="changed"):
        save(agent, prepared, next_step="Do not overwrite the current checkpoint.")
    with pytest.raises(ValueError, match="changed"):
        desktop(service, "clear", project_id="repo", checkpoint_id="b" * 32)
    desktop(service, "clear", project_id="repo", checkpoint_id=saved_id)
    with pytest.raises(ValueError, match="changed"):
        save(agent, prepared, expected_checkpoint_id=None)
    with pytest.raises(ValueError, match="changed"):
        desktop(service, "read", project_id="repo", checkpoint_id=saved_id)
    refreshed = prepare(agent, prior_task_receipt=prepared["task_receipt"])
    save(agent, refreshed)
    set_continuity(service, False)
    set_continuity(service, True)
    assert service.state()["projects"][0]["continuity"] is None
    with pytest.raises(ValueError, match="changed"):
        save(agent, refreshed)


def test_clear_between_decrypt_and_desktop_read_rejects_stale_content(
    service: HubService, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_continuity(service, True)
    agent = HubProtocol(service)
    prepared = prepare(agent)
    saved = save(agent, prepared)
    checkpoint_id = saved["checkpoint_id"]
    decrypt = service.continuity.decrypt

    def decrypt_then_clear(state: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
        content = decrypt(state, checkpoint)
        service.clear_continuity("repo", checkpoint_id)
        return content

    monkeypatch.setattr(service.continuity, "decrypt", decrypt_then_clear)
    with pytest.raises(ValueError, match="changed"):
        desktop(service, "read", project_id="repo", checkpoint_id=checkpoint_id)


def test_checkpoint_rejects_credential_patterns_without_echoing_them(service: HubService) -> None:
    set_continuity(service, True)
    agent = HubProtocol(service)
    prepared = prepare(agent)
    fake_secret = "ghp_" + "fictional" * 4
    with pytest.raises(ValueError, match="Remove credentials") as rejected:
        save(agent, prepared, next_step="Do not store " + fake_secret)
    assert fake_secret not in str(rejected.value)
    assert service.state()["projects"][0]["continuity"] is None


def test_expired_and_corrupted_store_cannot_deliver(service: HubService) -> None:
    set_continuity(service, True)
    agent = HubProtocol(service)
    prepared = prepare(agent)
    saved = save(agent, prepared)
    finish(agent, prepared)
    key = project_key("repo")
    state = service.continuity.read_owned(key)
    assert state is not None
    state["checkpoint"]["expires_at"] = time.time() - 1
    service.continuity.write(key, state)
    assert service.state()["projects"][0]["continuity_issue"] == "expired"
    with pytest.raises(ValueError, match="no current checkpoint"):
        prepare(agent, continue_previous=True)
    with pytest.raises(ValueError, match="expired"):
        desktop(service, "read", project_id="repo", checkpoint_id=saved["checkpoint_id"])
    service.tick()
    pruned = service.continuity.read_owned(key)
    assert pruned is not None and pruned["checkpoint"] is None

    prepared = prepare(agent)
    save(agent, prepared)
    finish(agent, prepared)
    service.continuity.path(key).write_text("invalid unsigned fixture")
    assert service.state()["projects"][0]["continuity_issue"] == "unavailable"
    with pytest.raises(ValueError, match="could not be verified"):
        prepare(agent, continue_previous=True)
    ordinary = prepare(agent)
    assert ordinary["continuity"]["handoff"] is None
    assert ordinary["continuity"]["issue"] == "unavailable"


def test_new_native_instructions_require_fresh_selection(service: HubService) -> None:
    set_continuity(service, True)
    agent = HubProtocol(service)
    prepared = prepare(agent)
    ticket = prepared["selection_ticket"]
    agent.dispatch(
        "tools_hub.select",
        {
            **prepared["effective_task"],
            "selection_ticket": ticket,
            "choices": [],
            "inspections": [],
        },
        agent=True,
    )
    save(agent, prepared)
    finish(agent, prepared)
    repo = service.project_inventory()["repo"]
    (repo / "AGENTS.md").write_text("Change both command outputs in this fixture.\n")
    resumed = prepare(HubProtocol(service), continue_previous=True)
    assert resumed["status"] == "needs_agent_selection"
    assert resumed["continuity"]["handoff"]["requirements"] == HANDOFF["requirements"]
    assert "native instructions take precedence" in resumed["continuity"]["precedence"]


def test_checkpoint_is_bound_to_repository_and_permission(service: HubService) -> None:
    set_continuity(service, True)
    agent = HubProtocol(service)
    task = prepare(agent)
    checkpoint = save(agent, task)
    finish(agent, task)
    with pytest.raises(ValueError, match="authorized"):
        desktop(service, "read", project_id="other", checkpoint_id=checkpoint["checkpoint_id"])
    repo = service.project_inventory()["repo"]
    (repo / ".git").rename(repo / ".git-old")
    (repo / ".git").mkdir()
    with pytest.raises(ValueError, match="authorized"):
        prepare(agent, continue_previous=True)
    with pytest.raises(ValueError, match="authorized"):
        desktop(service, "read", project_id="repo", checkpoint_id=checkpoint["checkpoint_id"])
    (repo / ".git").rmdir()
    (repo / ".git-old").rename(repo / ".git")
    grant = service.grant()
    assert grant is not None
    grant.update(enabled=False, paused=True)
    service.seals.write(service.home / "permission.json", grant, "permission")
    with pytest.raises(ValueError, match="not enabled"):
        prepare(agent, continue_previous=True)
    with pytest.raises(ValueError, match="stopped"):
        desktop(service, "read", project_id="repo", checkpoint_id=checkpoint["checkpoint_id"])
    service.tick()
    assert not service.continuity.path(project_key("repo")).exists()
