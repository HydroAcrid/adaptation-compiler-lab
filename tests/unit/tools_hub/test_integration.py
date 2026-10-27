"""Real file/SQLite/permission mechanics; fake manager is not native SDK evidence."""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.tools_hub import intake
from adaptation_compiler_lab.tools_hub.agent_bridge import serve_hub
from adaptation_compiler_lab.tools_hub.controller import Hub
from adaptation_compiler_lab.tools_hub.manager import (
    SkillKitManager,
    bounded_run,
    clean_environment,
)
from adaptation_compiler_lab.tools_hub.paths import safe, writer_lock
from adaptation_compiler_lab.tools_hub.policy import native_policy_digest
from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.sealed import Seals
from adaptation_compiler_lab.tools_hub.service import HubService, project_key
from adaptation_compiler_lab.tools_hub.sources import (
    SOURCES,
    SourceSnapshots,
    specification,
    tree_digest,
)


class FixtureManager(SkillKitManager):
    def provision(self) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "admission.json").write_text("fixture")
        return self.verify()

    def verify(self) -> str:
        return "fixture-manager-v1"

    def run(self, argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
        if argv[0] == "skillkit" and argv[1] == "install":
            source = (cwd / argv[2]).resolve()
            name = argv[argv.index("--skill") + 1]
            shutil.copytree(source / "skills" / name, cwd / ".codex/skills" / name)
            result: Any = {"installed": name}
        elif argv[0] == "skillkit":
            result = [
                {"skill": {"name": "debugging", "source": "obra/superpowers"}, "relevance": 80}
            ]
        else:
            result = {"indexed": True}
        return {"returncode": 0, "stdout": json.dumps(result), "stderr": "", "seconds": 0.001}


class FixtureSnapshots(SourceSnapshots):
    def acquire(self) -> dict[str, Any]:
        self.cache.mkdir(exist_ok=True)
        revision = (self.home.parent / "revision").read_text()
        approved = next(row for row in SOURCES if row["id"] == "superpowers")
        target = safe(self.cache, "superpowers/obra/superpowers/" + revision)
        if not target.exists():
            shutil.copytree(self.home.parent / "public-fixture", target)
        row = {
            **specification(approved),
            "path": str(target),
            "revision": revision,
            "tree_sha256": tree_digest(target),
            "license_files": {"LICENSE": intake.sha((target / "LICENSE").read_bytes())},
        }
        self.seals.write(
            self.home / "snapshots.json",
            {"grant_id": self.grant["grant_id"], "sources": [row]},
            "snapshots",
        )
        intake.save(self.catalog, {"sources": [row]})
        return {"sources": 1}


def wait_job(service: HubService) -> dict[str, Any]:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        job = service.state()["job"]
        if job and job["state"] != "running":
            return dict(job)
        time.sleep(0.01)
    pytest.fail("fixture job did not finish")


def make_service(tmp_path: Path) -> HubService:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "AGENTS.md").write_text("Preserve manual instructions.\n")
    source = tmp_path / "public-fixture/skills/debugging"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: debugging\ndescription: Diagnose test failures\n---\n"
        "Read the test before changing it. [Details](details.md)\n"
    )
    (source / "details.md").write_text("Public supporting resource.\n")
    (tmp_path / "public-fixture/LICENSE").write_text("Fictional MIT fixture")
    (tmp_path / "revision").write_text("a" * 40)
    codex = tmp_path / "codex"
    codex.mkdir()
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(), identity_id="fixture-hub", subject_id="fixture-owner"
    )
    return HubService(
        tmp_path / "hub",
        seals=Seals(signer),
        projects=lambda: {"repo": repo},
        codex_home=codex,
        manager=FixtureManager(tmp_path / "hub/manager"),
        sources=FixtureSnapshots,
    )


@pytest.fixture
def service(tmp_path: Path) -> HubService:
    result = make_service(tmp_path)
    preview = result.preview(["repo"], ["superpowers"])
    result.enable(preview["preview_id"])
    assert wait_job(result)["state"] == "complete"
    return result


def prepare(service: HubService, goal: str = "Fix the failing tests") -> dict[str, Any]:
    with writer_lock(service.home):
        return service.prepare("repo", goal, "debugging")


def select(
    service: HubService, proposal: dict[str, Any], goal: str = "Fix the failing tests"
) -> dict[str, Any]:
    ticket = proposal["selection_ticket"]
    with writer_lock(service.home):
        inspected = service.inspect(ticket, "superpowers/skills/debugging")
        return service.select(
            ticket,
            "repo",
            goal,
            "debugging",
            ["superpowers/skills/debugging"],
            [inspected["inspection_receipt"]],
        )


def test_learning_inventory_does_not_authorize_installation(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    assert not service.state()["enabled"]
    assert service.inventory()[0]["id"] == "repo"
    with pytest.raises(ValueError, match="not enabled"):
        service.prepare("repo", "Fix the tests", "debugging")
    assert not (tmp_path / "repo/.agents").exists()
    assert not service.home.exists()


def test_native_manager_staging_complete_resources_cache_and_task_switch(
    service: HubService,
) -> None:
    first = prepare(service)
    assert first["status"] == "needs_agent_selection"
    assert first["native_recommendations"][0]["name"] == "debugging"
    assert select(service, first)["status"] == "ready"
    root = service.home.parent / "repo"
    assert (
        root / ".agents/skills/debugging/details.md"
    ).read_text() == "Public supporting resource.\n"
    assert prepare(service)["cache_hit"] is True
    switched = prepare(service, "Write the README")
    assert switched["status"] == "needs_agent_selection"
    assert switched["changed"]
    assert not (root / ".agents/skills/debugging/SKILL.md").exists()
    assert (root / "AGENTS.md").read_text() == "Preserve manual instructions.\n"


def test_agent_cannot_enable_or_expand_permission(service: HubService) -> None:
    protocol = HubProtocol(service)
    for method in (
        "permission.enable",
        "permission.preview",
        "control",
        "connection.apply",
        "maintenance",
        "repair",
    ):
        with pytest.raises(ValueError, match="Unsupported"):
            protocol.dispatch("tools_hub." + method, {}, agent=True)
    with pytest.raises(ValueError, match="not authorized"):
        protocol.dispatch(
            "tools_hub.prepare",
            {"project_id": "other", "goal": "work", "task_class": "review"},
            agent=True,
        )


def test_catalog_path_rebind_cannot_admit_unsigned_bytes(
    service: HubService, tmp_path: Path
) -> None:
    catalog = json.loads((service.home / "catalog.json").read_text())
    replacement = tmp_path / "replacement"
    shutil.copytree(tmp_path / "public-fixture", replacement)
    (replacement / "skills/debugging/SKILL.md").write_text(
        "---\nname: debugging\ndescription: unauthorized\n---\nNew unapproved guidance"
    )
    catalog["sources"][0]["path"] = str(replacement)
    intake.save(service.home / "catalog.json", catalog)
    with pytest.raises(ValueError, match="matching acquisition"):
        prepare(service)
    assert not (tmp_path / "repo/.agents/skills/debugging/SKILL.md").exists()


def test_cached_state_tampering_is_rejected(service: HubService) -> None:
    select(service, prepare(service))
    with sqlite3.connect(service.home / "hub.sqlite3") as connection:
        connection.execute("UPDATE state SET value='{}' WHERE key LIKE 'profile:%'")
    with pytest.raises(ValueError, match="changed outside Temper"):
        prepare(service)


@pytest.mark.parametrize("change", ["ancestor", "personal_skill", "fallback", "global_config"])
def test_native_policy_changes_require_agent_reselection(service: HubService, change: str) -> None:
    if change == "personal_skill":
        skill = service.codex_home / "skills/my-policy/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("Use debugging guidance")
    if change == "fallback":
        (service.codex_home / "config.toml").write_text(
            'project_doc_fallback_filenames = ["POLICY.md"]\n'
        )
    select(service, prepare(service))
    assert prepare(service)["cache_hit"]
    if change == "ancestor":
        (service.home.parent / "AGENTS.md").write_text("Do not use debugging guidance")
    elif change == "personal_skill":
        skill.write_text("Do not use debugging guidance")
    elif change == "fallback":
        (service.home.parent / "POLICY.md").write_text("Do not use debugging guidance")
    else:
        (service.codex_home / "config.toml").write_text('model = "owner-choice"\n')
    result = prepare(service)
    assert result["status"] == "needs_agent_selection"
    assert not (service.home.parent / "repo/.agents/skills/debugging/SKILL.md").exists()


def test_policy_change_with_incompatible_update_cannot_restore_old_guidance(
    service: HubService,
) -> None:
    select(service, prepare(service))
    public = service.home.parent / "public-fixture/skills/debugging/SKILL.md"
    public.write_text(public.read_text() + "\n[Missing runtime](missing.js)\n")
    (service.home.parent / "revision").write_text("b" * 40)
    with writer_lock(service.home):
        service.maintain(force=True)
    (service.home.parent / "AGENTS.md").write_text("Do not use debugging guidance")
    assert prepare(service)["status"] == "needs_agent_selection"
    assert not (service.home.parent / "repo/.agents/skills/debugging/SKILL.md").exists()


def test_stale_selection_ticket_cannot_override_current_policy(service: HubService) -> None:
    proposal = prepare(service)
    (service.home.parent / "repo/AGENTS.md").write_text("Use no extra tools")
    with pytest.raises(ValueError, match="changed"):
        select(service, proposal)


def test_all_selected_resources_need_inspection(service: HubService) -> None:
    proposal = prepare(service)
    with writer_lock(service.home), pytest.raises(ValueError, match="Inspect every"):
        service.select(
            proposal["selection_ticket"],
            "repo",
            "Fix the failing tests",
            "debugging",
            ["superpowers/skills/debugging"],
            [],
        )


@pytest.mark.parametrize("edit", ["change", "delete"])
def test_manual_profile_edits_are_preserved(service: HubService, edit: str) -> None:
    select(service, prepare(service))
    path = service.home.parent / "repo/.agents/skills/debugging/SKILL.md"
    if edit == "change":
        path.write_text("Manual owner guidance")
    else:
        path.unlink()
    result = prepare(service)
    assert result["status"] == "paused_owner_edit"
    assert path.read_text() == "Manual owner guidance" if path.exists() else edit == "delete"


def test_stop_reports_incomplete_cleanup_and_blocks_reenable(service: HubService) -> None:
    select(service, prepare(service))
    path = service.home.parent / "repo/.agents/skills/debugging/SKILL.md"
    path.write_text("Manual owner guidance")
    service.control("stop")
    job = wait_job(service)
    state = service.state()
    assert not state["enabled"] and state["cleanup_pending"]
    assert state["projects"][0]["active"] == ["debugging"]
    assert job["result"]["projects"][0]["conflicts"] == [".agents/skills/debugging/SKILL.md"]
    with pytest.raises(ValueError, match="cleanup"):
        service.preview(["repo"], ["superpowers"])
    # Removing the owner-edited files is an explicit owner resolution. The remaining
    # unchanged resource can then be safely removed without restoring the deleted file.
    path.unlink()
    service.control("stop")
    assert wait_job(service)["state"] == "complete"
    assert not service.state()["cleanup_pending"]
    assert not (path.parent / "details.md").exists()


def test_pause_takes_effect_during_long_job(service: HubService) -> None:
    entered, finish = threading.Event(), threading.Event()

    def work() -> dict[str, Any]:
        entered.set()
        finish.wait(3)
        service.grant(active=True)
        return {"status": "should_not_publish"}

    service.start("fixture", work)
    assert entered.wait(2)
    assert service.control("pause")["status"] == "paused"
    assert service.state()["paused"]
    finish.set()
    assert wait_job(service)["state"] == "failed"


def test_signed_journal_cannot_move_between_projects(service: HubService) -> None:
    grant = service.grant(active=True)
    assert grant is not None
    with writer_lock(service.home), service.controller(grant) as hub:
        key = project_key("repo")
        journal = service.seals.seal(
            {"project": "other", "root": "other", "previous": {}, "changes": []}, "journal"
        )
        intake.save(service.home / (key + ".pending.json"), journal)
        with pytest.raises(ValueError, match="different project"):
            hub.recover(key)


def test_mcp_exposes_only_task_tools_and_never_grants(service: HubService) -> None:
    source = io.StringIO(
        "\n".join(
            json.dumps(request)
            for request in [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "temper_hub_permission_enable", "arguments": {}},
                },
            ]
        )
        + "\n"
    )
    output = io.StringIO()
    serve_hub(HubProtocol(service), stdin=source, stdout=output)
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert {row["name"] for row in rows[0]["result"]["tools"]} == {
        "temper_hub_status",
        "temper_hub_prepare",
        "temper_hub_inspect",
        "temper_hub_select",
    }
    assert "error" in rows[1]


def test_environment_never_inherits_authentication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fictional-do-not-inherit")
    monkeypatch.setenv("GITHUB_TOKEN", "fictional-do-not-inherit")
    environment = clean_environment(tmp_path)
    assert "OPENAI_API_KEY" not in environment and "GITHUB_TOKEN" not in environment
    assert environment["npm_config_ignore_scripts"] == "true"


def test_manager_timeout_terminates_worker(tmp_path: Path) -> None:
    import sys

    with pytest.raises(ValueError, match="time or output"):
        bounded_run(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            tmp_path,
            tmp_path / "home",
            timeout=0.1,
        )


def test_policy_digest_is_stable_without_changes(service: HubService) -> None:
    root = service.home.parent / "repo"
    assert native_policy_digest(root, service.codex_home) == native_policy_digest(
        root, service.codex_home
    )


def test_undo_rejects_the_exact_update_without_blocking_other_profiles(service: HubService) -> None:
    select(service, prepare(service))
    public = service.home.parent / "public-fixture/skills/debugging/SKILL.md"
    original = public.read_bytes()
    public.write_bytes(original + b"\nUpdated public guidance.\n")
    other = public.parent.parent / "reviewing"
    other.mkdir()
    (other / "SKILL.md").write_text(
        "---\nname: reviewing\ndescription: Review a change\n---\nFictional review guidance.\n"
    )
    (service.home.parent / "revision").write_text("b" * 40)
    with writer_lock(service.home):
        service.maintain(force=True)
    select(service, prepare(service))
    assert service.state()["projects"][0]["can_rollback"]
    assert service.control("rollback", "repo")["projects"][0]["status"] == "ready"
    assert not service.state()["projects"][0]["can_rollback"]
    assert (service.home.parent / "repo/.agents/skills/debugging/SKILL.md").read_bytes() == original
    rejected = select(service, prepare(service))
    assert rejected["status"] == "rejected_update"
    fresh = prepare(service, "Review this change")
    assert fresh["status"] == "needs_agent_selection"
    with writer_lock(service.home):
        receipt = service.inspect(fresh["selection_ticket"], "superpowers/skills/reviewing")[
            "inspection_receipt"
        ]
        result = service.select(
            fresh["selection_ticket"],
            "repo",
            "Review this change",
            "debugging",
            ["superpowers/skills/reviewing"],
            [receipt],
        )
    assert result["status"] == "ready"


def test_interrupted_publication_rolls_back_from_signed_journal(
    service: HubService, monkeypatch: pytest.MonkeyPatch
) -> None:
    import adaptation_compiler_lab.tools_hub.controller as controller

    original = controller.Hub.sync

    def interrupt(self: Hub, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return original(self, *args, **{**kwargs, "fault_after": 1})

    def exit_for_fixture(_code: int) -> None:
        raise SystemExit(86)

    with monkeypatch.context() as patch:
        patch.setattr(os, "_exit", exit_for_fixture)
        patch.setattr(controller.Hub, "sync", interrupt)
        with pytest.raises(SystemExit, match="86"):
            select(service, prepare(service))
    assert service.state()["projects"][0]["pending_recovery"]
    assert prepare(service)["status"] == "needs_agent_selection"
    assert not service.state()["projects"][0]["pending_recovery"]
    assert not (service.home.parent / "repo/.agents/skills/debugging/SKILL.md").exists()


def test_agent_failure_is_visible_without_storing_the_goal(
    service: HubService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ValueError("Private manager needs repair")

    monkeypatch.setattr(service.manager, "run", fail)
    goal = "fictional-private-goal-do-not-retain-plaintext"
    with pytest.raises(ValueError, match="needs repair"):
        HubProtocol(service).dispatch(
            "tools_hub.prepare",
            {"project_id": "repo", "goal": goal, "task_class": "review"},
            agent=True,
        )
    state = service.state()
    assert state["last_task"]["state"] == "failed"
    assert state["last_task"]["message"] == "Private manager needs repair"
    assert goal not in (service.home / "agent-state.json").read_text()


def test_policy_change_during_native_staging_prevents_publication(
    service: HubService, monkeypatch: pytest.MonkeyPatch
) -> None:
    select(service, prepare(service))
    target = service.home.parent / "repo/.agents/skills/debugging/SKILL.md"
    previous = target.read_bytes()
    public = service.home.parent / "public-fixture/skills/debugging/SKILL.md"
    public.write_bytes(public.read_bytes() + b"\nNew public revision.\n")
    (service.home.parent / "revision").write_text("b" * 40)
    with writer_lock(service.home):
        service.maintain(force=True)
    proposal = prepare(service)
    original = service.manager.run

    def change_policy(argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
        result = original(argv, cwd, home)
        if argv[:2] == ["skillkit", "install"]:
            (service.home.parent / "repo/AGENTS.md").write_text("Do not use debugging guidance")
        return result

    monkeypatch.setattr(service.manager, "run", change_policy)
    with pytest.raises(ValueError, match="context changed during"):
        select(service, proposal)
    assert target.read_bytes() == previous


@pytest.mark.parametrize("initial", [False, True])
def test_interrupted_index_construction_recovers_on_next_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, initial: bool
) -> None:
    service = make_service(tmp_path)
    original = service.manager.run

    def fail_index(argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
        if argv[0] == "node":
            raise ValueError("Fictional interrupted index construction")
        return original(argv, cwd, home)

    preview = service.preview(["repo"], ["superpowers"])
    if initial:
        monkeypatch.setattr(service.manager, "run", fail_index)
        service.enable(preview["preview_id"])
        assert wait_job(service)["state"] == "failed"
    else:
        service.enable(preview["preview_id"])
        assert wait_job(service)["state"] == "complete"
        select(service, prepare(service))
        public = tmp_path / "public-fixture/skills/debugging/SKILL.md"
        public.write_bytes(public.read_bytes() + b"\nNew public revision.\n")
        (tmp_path / "revision").write_text("b" * 40)
        monkeypatch.setattr(service.manager, "run", fail_index)
        with writer_lock(service.home), pytest.raises(ValueError, match="interrupted index"):
            service.maintain(force=True)
    monkeypatch.setattr(service.manager, "run", original)
    assert select(service, prepare(service))["status"] == "ready"


def test_failed_first_setup_does_not_retry_sources_every_scheduler_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = make_service(tmp_path)

    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ValueError("Fictional offline source")

    monkeypatch.setattr(service.manager, "run", fail)
    preview = service.preview(["repo"], ["superpowers"])
    service.enable(preview["preview_id"])
    assert wait_job(service)["state"] == "failed"
    grant = service.grant()
    assert grant is not None and grant["last_attempt"] > 0
    assert service.tick()["status"] == "idle"
