"""Offline actor journeys through the Hub boundary with fictional repositories."""

from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TextIO, cast
from uuid import uuid4

import pytest

from adaptation_compiler_lab.tools_hub.lifetime import process_identity
from adaptation_compiler_lab.tools_hub.manager import bounded_run, clean_environment
from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.service import HubService
from adaptation_compiler_lab.tools_hub.workflow_runtime import runtime_directory

from .test_integration import make_service, wait_job

DEBUG = "superpowers/skills/debugging"
POPULAR = "superpowers/skills/presentation"
SKILL_FILE = ".agents/skills/debugging/SKILL.md"
DETAIL_FILE = ".agents/skills/debugging/details.md"


@dataclass(frozen=True)
class Simulation:
    service: HubService
    protocol: HubProtocol
    first: Path
    second: Path

    def agent(self, method: str, **arguments: Any) -> dict[str, Any]:
        return self.protocol.dispatch("tools_hub." + method, arguments, agent=True)

    def desktop(self, method: str, **arguments: Any) -> dict[str, Any]:
        return self.protocol.dispatch(
            "tools_hub." + method,
            arguments,
            expected_digest=self.service.state()["digest"],
            idempotency_key=uuid4().hex,
        )

    def choose(
        self,
        task: dict[str, Any],
        prepared: dict[str, Any],
        choices: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        ticket = prepared["selection_ticket"]
        receipts = [
            self.agent("inspect", selection_ticket=ticket, skill_id=skill_id)["inspection_receipt"]
            for skill_id in choices
        ]
        return self.agent(
            "select",
            **task,
            selection_ticket=ticket,
            choices=list(choices),
            inspections=receipts,
        )


@pytest.fixture
def simulation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Simulation:
    service = make_service(tmp_path)
    first, second = tmp_path / "repo", tmp_path / "lantern-catalog"
    second.mkdir()
    (second / ".git").mkdir()
    (second / "AGENTS.md").write_bytes(b"Preserve Lantern's manual instructions.\n")
    monkeypatch.setattr(service, "project_inventory", lambda: {"repo": first, "lantern": second})

    popular = tmp_path / "public-fixture/skills/presentation"
    popular.mkdir()
    (popular / "SKILL.md").write_bytes(
        b"---\nname: presentation\ndescription: Make presentation slides\n---\n"
        b"Create a slide for each agenda item.\n"
    )
    manager_run = service.manager.run

    def rank_irrelevant_first(argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
        result = manager_run(argv, cwd, home)
        if argv[:2] == ["skillkit", "recommend"]:
            recommendations = json.loads(result["stdout"])
            recommendations.insert(
                0,
                {
                    "skill": {"name": "presentation", "source": "obra/superpowers"},
                    "relevance": 100,
                },
            )
            return {**result, "stdout": json.dumps(recommendations)}
        return result

    monkeypatch.setattr(service.manager, "run", rank_irrelevant_first)
    state = Simulation(service, HubProtocol(service), first, second)
    preview = state.desktop(
        "permission.preview", project_ids=["repo", "lantern"], source_ids=["superpowers"]
    )
    state.desktop("permission.enable", preview_id=preview["preview_id"])
    assert wait_job(service)["state"] == "complete"
    return state


def task(goal: str, *, project_id: str = "repo", relative_directory: str = ".") -> dict[str, Any]:
    return {
        "project_id": project_id,
        "goal": goal,
        "task_class": "debugging",
        "relative_directory": relative_directory,
    }


def test_no_workflow_for_simple_request_despite_ranked_skill(simulation: Simulation) -> None:
    request = task("Read whether the fictional fixture contains a license.")
    request["task_class"] = "review"
    prepared = simulation.agent("prepare", **request)
    assert prepared["native_recommendations"][0]["name"] == "presentation"
    assert any(row["id"] == POPULAR for row in prepared["authorized_catalog"])

    simulation.choose(request, prepared)

    assert not (simulation.first / ".agents/skills/presentation/SKILL.md").exists(), (
        "empty selection published the top-ranked irrelevant skill"
    )
    assert not (simulation.first / SKILL_FILE).exists()
    assert not (simulation.second / ".agents").exists()


def test_switches_and_stale_tasks_cannot_cross_project_scopes(simulation: Simulation) -> None:
    first = task("Reproduce the failure in fictional Harbor's parser tests.")
    first_plan = simulation.agent("prepare", **first)
    competing = task("Inspect a different fictional test failure.")
    with pytest.raises(ValueError, match=r"(?i)task|lease|switch|busy"):
        HubProtocol(simulation.service).dispatch("tools_hub.prepare", competing, agent=True)
    overlapping = replace(simulation, protocol=HubProtocol(simulation.service))
    with pytest.raises(ValueError, match=r"(?i)stale|task"):
        overlapping.choose(first, first_plan, (DEBUG,))
    first_receipt = first_plan["task_receipt"]
    simulation.choose(first, first_plan, (DEBUG,))
    assert (simulation.first / DETAIL_FILE).read_text() == "Public supporting resource.\n"

    parallel = task("Trace a fictional Lantern Catalog test failure.", project_id="lantern")
    parallel_plan = overlapping.agent("prepare", **parallel)
    overlapping.choose(parallel, parallel_plan, (DEBUG,))
    assert (simulation.second / DETAIL_FILE).is_file()

    second = task("Explain the purpose of the fictional parser fixture.")
    second_plan = simulation.agent("prepare", **second, prior_task_receipt=first_receipt)
    assert not (simulation.first / SKILL_FILE).exists()
    simulation.choose(second, second_plan)
    assert (simulation.second / SKILL_FILE).is_file(), "switch cleared another project's profile"

    third = task("Diagnose a fictional empty-input parser regression.")
    third_plan = simulation.agent(
        "prepare", **third, prior_task_receipt=second_plan["task_receipt"]
    )
    simulation.choose(third, third_plan, (DEBUG,))
    for prior in (first_receipt, second_plan["task_receipt"]):
        try:
            simulation.agent("finish", task_receipt=prior, outcome="cancelled")
        except ValueError as error:
            assert any(word in str(error).lower() for word in ("stale", "lease", "task"))
    assert (simulation.first / SKILL_FILE).is_file(), "stale task finish removed the current skill"
    assert (simulation.second / SKILL_FILE).is_file()
    with pytest.raises(ValueError, match=r"(?i)changed|stale|task"):
        simulation.choose(first, first_plan, (DEBUG,))

    simulation.agent("finish", task_receipt=third_plan["task_receipt"], outcome="completed")
    assert not (simulation.first / SKILL_FILE).exists()
    assert (simulation.second / SKILL_FILE).is_file()
    overlapping.agent("finish", task_receipt=parallel_plan["task_receipt"], outcome="completed")
    assert not (simulation.second / SKILL_FILE).exists()


def test_native_policy_conflict_and_owner_edit_survive_finish(simulation: Simulation) -> None:
    scoped = simulation.first / "restricted"
    scoped.mkdir()
    request = task("Diagnose a fictional queue failure.", relative_directory="restricted")
    prepared = simulation.agent("prepare", **request)
    policy = scoped / "AGENTS.md"
    manual_policy = b"Do not load external workflow guidance in this directory.\n"
    policy.write_bytes(manual_policy)
    with pytest.raises(ValueError, match=r"(?i)changed|policy|task"):
        simulation.choose(request, prepared, (DEBUG,))
    assert not (simulation.first / SKILL_FILE).exists()

    follow_up = task("Diagnose a fictional top-level worker timeout.")
    plan = simulation.agent("prepare", **follow_up, prior_task_receipt=prepared["task_receipt"])
    simulation.choose(follow_up, plan, (DEBUG,))
    edited = simulation.first / SKILL_FILE
    manual_skill = b"Owner-authored fixture guidance.\n"
    edited.write_bytes(manual_skill)
    owner_note = simulation.first / "work-notes.md"
    owner_note.write_bytes(b"Unrelated fictional work note.\n")

    result = simulation.agent("finish", task_receipt=plan["task_receipt"], outcome="failed")
    assert SKILL_FILE in result["retained_owner_files"], "cleanup omitted the edited file"
    assert edited.read_bytes() == manual_skill
    assert not (simulation.first / DETAIL_FILE).exists()
    assert policy.read_bytes() == manual_policy
    assert owner_note.read_bytes() == b"Unrelated fictional work note.\n"

    next_task = task("Make slides for a fictional review.")
    next_task["task_class"] = "documentation"
    successor = simulation.agent("prepare", **next_task)
    simulation.choose(next_task, successor, (POPULAR,))
    with pytest.raises(ValueError, match=r"(?i)stale|task"):
        simulation.agent("finish", task_receipt=plan["task_receipt"], outcome="failed")
    assert (simulation.first / ".agents/skills/presentation/SKILL.md").is_file()
    assert edited.read_bytes() == manual_skill


def abandon_scratch(simulation: Simulation, prepared: dict[str, Any]) -> Path:
    service = simulation.service
    token = service.seals.open(prepared["task_receipt"], "task")["task_token"]
    path = runtime_directory(service.home / "remotion", token)
    path.mkdir(parents=True)
    (path / "abandoned.bundle").write_bytes(b"Fictional renderer scratch.")
    return path


def test_paused_and_revoked_permission_cannot_resume_prior_task(simulation: Simulation) -> None:
    request = task("Reproduce a fictional checksum failure.")
    prepared = simulation.agent("prepare", **request)
    simulation.choose(request, prepared, (DEBUG,))
    assert (simulation.first / DETAIL_FILE).is_file()

    paused_scratch = abandon_scratch(simulation, prepared)
    simulation.desktop("control", operation="pause")
    with pytest.raises(ValueError, match=r"(?i)paused|enabled"):
        simulation.agent("prepare", **request)
    with pytest.raises(ValueError, match=r"(?i)paused|enabled"):
        simulation.choose(request, prepared, (DEBUG,))
    simulation.desktop("maintenance")
    assert not (simulation.first / DETAIL_FILE).exists(), "pause left active task resources"
    assert not paused_scratch.exists(), "pause left active task scratch"

    simulation.desktop("control", operation="resume")
    resumed = simulation.agent("prepare", **request)
    with pytest.raises(ValueError, match=r"(?i)stale|expired|task"):
        simulation.choose(request, prepared, (DEBUG,))
    if "selection_ticket" in resumed:
        simulation.choose(request, resumed, (DEBUG,))
    else:
        assert resumed["status"] == "ready" and resumed["cache_hit"]
    assert (simulation.first / DETAIL_FILE).is_file()

    revoked_scratch = abandon_scratch(simulation, resumed)
    simulation.desktop("control", operation="stop")
    assert wait_job(simulation.service)["state"] == "complete"
    with pytest.raises(ValueError, match=r"(?i)paused|enabled"):
        simulation.agent("prepare", **request)
    assert not (simulation.first / DETAIL_FILE).exists(), "revocation left active task resources"
    assert not revoked_scratch.exists(), "revocation left active task scratch"
    assert not simulation.service.state()["cleanup_pending"]


def test_broken_approved_update_keeps_only_same_tasks_known_good_profile(
    simulation: Simulation,
) -> None:
    request = task("Diagnose the fictional queue's duplicate dequeue.")
    prepared = simulation.agent("prepare", **request)
    simulation.choose(request, prepared, (DEBUG,))
    published = simulation.first / SKILL_FILE
    original = published.read_bytes()

    source = simulation.first.parent / "public-fixture/skills/debugging/SKILL.md"
    source.write_bytes(original + b"\n[Missing runtime](missing.js)\n")
    (simulation.first.parent / "revision").write_text("b" * 40)
    simulation.desktop("refresh")
    assert wait_job(simulation.service)["state"] == "complete"

    ready = simulation.agent("prepare", **request, prior_task_receipt=prepared["task_receipt"])
    assert ready["status"] == "deferred_incompatible_update"
    assert published.read_bytes() == original, "broken update replaced known-good task guidance"
    assert not (published.parent / "missing.js").exists()

    different = task("Summarize the fixture's license.")
    next_plan = simulation.agent("prepare", **different, prior_task_receipt=ready["task_receipt"])
    assert not published.exists(), "known-good profile leaked into an unrelated task"
    simulation.choose(different, next_plan)


@pytest.mark.skipif(os.name != "nt", reason="asserts Windows Job Object process ownership")
def test_native_adapter_process_tree_is_gone_after_success(tmp_path: Path) -> None:
    # A successful renderer can exit before its browser. The shared native launcher owns both.
    fixture_program = (
        "import subprocess, sys; "
        "from adaptation_compiler_lab.tools_hub.lifetime import process_identity; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, "
        "creationflags=subprocess.CREATE_NO_WINDOW); "
        "print(child.pid, process_identity(child.pid))"
    )
    result = bounded_run(
        [sys.executable, "-c", fixture_program], tmp_path, tmp_path / "native-home", timeout=10
    )
    assert result["returncode"] == 0, result["stderr"]
    raw_pid, identity = result["stdout"].split()
    pid = int(raw_pid)
    assert identity != "None", "the fixture child did not start"
    try:
        assert process_identity(pid) != identity, "native adapter descendant survived success"
    finally:
        if process_identity(pid) == identity:
            os.kill(pid, signal.SIGTERM)


def test_admitted_remotion_renders_small_real_mp4_and_removes_scratch(
    simulation: Simulation,
) -> None:
    paths = {
        key: os.environ.get("TEMPER_TEST_REMOTION_" + key) for key in ("NODE", "MODULES", "BROWSER")
    }
    if not all(paths.values()):
        pytest.skip("set the three TEMPER_TEST_REMOTION toolchain paths for native rendering")
    preview = simulation.desktop(
        "runtime.preview",
        node=paths["NODE"],
        node_modules=paths["MODULES"],
        browser=paths["BROWSER"],
    )
    assert (
        simulation.desktop("runtime.enable", preview_id=preview["preview_id"])["status"]
        == "enabled"
    )

    request = task("Render a one-second fictional Lantern Catalog title card.")
    request["task_class"] = "implementation"
    prepared = simulation.agent("prepare", **request)
    simulation.choose(request, prepared)
    receipt = prepared["task_receipt"]
    spec = {
        "title": "Lantern Catalog",
        "subtitle": "Fictional launch notes",
        "background": "#111827",
        "foreground": "#ffffff",
        "accent": "#7dd3fc",
        "seconds": 1,
    }
    artifact = simulation.agent("render", task_receipt=receipt, spec=spec)
    root = simulation.service.home / "remotion"
    output = Path(artifact["artifact_path"])
    assert output.is_relative_to(root / "artifacts")
    video = output.read_bytes()
    assert video[4:8] == b"ftyp" and all(box in video for box in (b"moov", b"mdat", b"avc1"))
    assert len(video) == artifact["bytes"]
    assert hashlib.sha256(video).hexdigest() == artifact["sha256"]
    assert (artifact["width"], artifact["height"], artifact["fps"], artifact["frames"]) == (
        320,
        400,
        15,
        15,
    )
    runs = root / "runs"
    assert not runs.exists() or not list(runs.iterdir()), "render left task-owned runtime scratch"

    simulation.desktop("runtime.revoke")
    with pytest.raises(ValueError, match=r"(?i)Remotion.*not approved"):
        simulation.agent("render", task_receipt=receipt, spec=spec)
    simulation.agent("finish", task_receipt=receipt, outcome="completed")
    assert output.read_bytes() == video, "finish removed the completed video artifact"


def test_native_hooks_release_only_the_matching_turn_generation(
    simulation: Simulation, monkeypatch: pytest.MonkeyPatch
) -> None:
    from adaptation_compiler_lab.tools_hub import native
    from adaptation_compiler_lab.tools_hub.agent_bridge import serve_hub
    from adaptation_compiler_lab.tools_hub.connection import HOOKS

    monkeypatch.setattr(native, "native_hub_service", lambda _path: simulation.service)
    native_protocol = native.NativeHubAgentProtocol(simulation.first.parent / "fixture-config.json")
    hooks = tomllib.loads(HOOKS)["hooks"]
    output = io.StringIO()

    def reply() -> dict[str, Any]:
        response = json.loads(output.getvalue().splitlines()[-1])
        assert "error" not in response, response.get("error")
        return dict(response["result"])

    def packet() -> dict[str, Any]:
        return dict(json.loads(reply()["content"][0]["text"]))

    def call(name: str, **arguments: Any) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }

    def hook(event: str, turn: str, *, nonce: str = "") -> dict[str, Any]:
        row = hooks[event][0]["hooks"][0]
        assert row["type"] == "mcp_tool" and row["server"] == "temper_hub"
        native_inputs = {
            "${session_id}": "fictional-native-session",
            "${turn_id}": turn,
            "${tool_response.structuredContent.lifecycle_nonce}": nonce,
        }
        arguments = {name: native_inputs.get(value, value) for name, value in row["input"].items()}
        return call(row["tool"], **arguments)

    def frames() -> Iterator[dict[str, Any]]:
        prior = None
        old_nonce = ""
        for turn, goal in (
            ("fictional-turn-1", "Diagnose a fictional split-path failure."),
            ("fictional-turn-2", "Diagnose a fictional normalization failure."),
            ("fictional-turn-3", "Diagnose a fictional fixture timeout."),
        ):
            request = task(goal)
            yield call(
                "temper_hub_prepare",
                **request,
                **({"prior_task_receipt": prior} if prior else {}),
            )
            prepared = packet()
            nonce = reply()["structuredContent"]["lifecycle_nonce"]
            yield hook("PostToolUse", turn, nonce=nonce)
            packet()
            yield call(
                "temper_hub_inspect", selection_ticket=prepared["selection_ticket"], skill_id=DEBUG
            )
            inspected = packet()
            yield call(
                "temper_hub_select",
                **request,
                selection_ticket=prepared["selection_ticket"],
                choices=[DEBUG],
                inspections=[inspected["inspection_receipt"]],
            )
            packet()
            assert (simulation.first / DETAIL_FILE).is_file()

            if turn == "fictional-turn-1":
                prior, old_nonce = prepared["task_receipt"], nonce
            elif turn == "fictional-turn-2":
                yield hook("PostToolUse", "fictional-turn-1", nonce=old_nonce)
                packet()
                yield hook("Stop", "fictional-turn-1")
                packet()
                assert (simulation.first / DETAIL_FILE).is_file(), (
                    "delayed Stop removed the successor turn's profile"
                )
                yield hook("Interrupt", turn)
                packet()
                assert not (simulation.first / DETAIL_FILE).exists(), "Interrupt leaked skill"
                prior = None
            else:
                yield hook("Stop", turn)
                packet()
                assert not (simulation.first / DETAIL_FILE).exists(), "Stop leaked skill"

    class Frames:
        def __init__(self, requests: Iterator[dict[str, Any]]) -> None:
            super().__init__()
            self.requests = requests

        def readline(self, size: int | None = -1) -> str:
            request = next(self.requests, None)
            return "" if request is None else json.dumps(request) + "\n"

    serve_hub(native_protocol, stdin=cast(TextIO, Frames(frames())), stdout=output)


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled", "expired", "crashed"])
def test_terminal_paths_reap_only_the_tasks_abandoned_runtime_scratch(
    simulation: Simulation, monkeypatch: pytest.MonkeyPatch, terminal: str
) -> None:
    from adaptation_compiler_lab.tools_hub.task_lifecycle import MAX_LEASE_SECONDS, TaskOwner

    service = simulation.service
    native_owner = None
    if terminal == "crashed":
        native_owner = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=simulation.first,
            env=clean_environment(simulation.first.parent / "fictional-native-home"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    try:
        if native_owner is not None:
            identity = process_identity(native_owner.pid)
            assert identity is not None
            owner = TaskOwner("fictional-native-connection", native_owner.pid, identity)
            simulation = replace(simulation, protocol=HubProtocol(service, task_owner=owner))
        request = task("Reproduce a fictional background worker failure.")
        prepared = simulation.agent("prepare", **request)
        simulation.choose(request, prepared, (DEBUG,))
        receipt = prepared["task_receipt"]
        runtime = service.home / "remotion"
        scratch = abandon_scratch(simulation, prepared)
        unrelated = runtime_directory(runtime, "f" * 64)
        unrelated.mkdir(parents=True)
        (unrelated / "other.bundle").write_bytes(b"Independent fixture data.")
        artifact = runtime / "artifacts" / "fictional.mp4"
        artifact.parent.mkdir()
        artifact.write_bytes(b"Already completed artifact.")
        assert (simulation.first / DETAIL_FILE).is_file()

        if terminal == "expired":
            now = time.time()
            with monkeypatch.context() as clock:
                clock.setattr(time, "time", lambda: now + MAX_LEASE_SECONDS + 1)
                simulation.desktop("maintenance")
        elif terminal == "crashed":
            assert native_owner is not None
            native_owner.kill()
            native_owner.wait(timeout=5)
            restarted = HubService(
                service.home,
                seals=service.seals,
                projects=service.project_inventory,
                codex_home=service.codex_home,
                manager=service.manager,
                sources=service.source_factory,
            )
            HubProtocol(restarted).dispatch("tools_hub.maintenance", {})
        else:
            result = simulation.agent("finish", task_receipt=receipt, outcome=terminal)
            assert result["outcome"] == terminal

        assert not scratch.exists(), f"{terminal} left task-owned runtime scratch"
        assert not (simulation.first / DETAIL_FILE).exists(), f"{terminal} left task-owned skill"
        assert artifact.read_bytes() == b"Already completed artifact."
        assert (unrelated / "other.bundle").read_bytes() == b"Independent fixture data."
    finally:
        if native_owner is not None and native_owner.poll() is None:
            native_owner.kill()
            native_owner.wait(timeout=5)
