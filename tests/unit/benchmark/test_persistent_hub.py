from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import persistent_hub as hub_module
from scripts.persistent_hub import PROJECT_MARKER, Hub


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail = False

    def __call__(self, argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
        self.calls.append(argv)
        if self.fail:
            return {"returncode": 7, "stdout": "", "stderr": "offline failure", "seconds": 0.1}
        result: Any = {}
        if argv[-1] == "--version":
            return {
                "returncode": 0,
                "stdout": {"skills": "1.7.2", "skillkit": "1.24.0", "node": "v24.18.0"}[argv[0]],
                "stderr": "",
                "seconds": 0.1,
            }
        if argv[:2] == ["skillkit", "recommend"]:
            name = "writing" if "documentation" in argv[3] else "debugging"
            result = [{"skill": {"name": name, "source": "example/source"}, "relevance": 60}]
        elif argv[0] in ("skills", "skillkit"):
            name = argv[argv.index("--skill") + 1]
            directory = ".agents" if argv[0] == "skills" else ".codex"
            shutil.copytree(Path(argv[2]) / "skills" / name, cwd / directory / "skills" / name)
        return {"returncode": 0, "stdout": json.dumps(result), "stderr": "", "seconds": 0.1}


@pytest.fixture
def configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, FakeManager]:
    binary = tmp_path / "manager.js"
    binary.write_text("pinned test executable")
    monkeypatch.setattr("scripts.persistent_hub.shutil.which", lambda _: str(binary))
    source = tmp_path / "source/skills"
    for name, description, body in (
        ("debugging", "Diagnose bugs and regression tests", ""),
        ("writing", "Write developer documentation", "Apply the cleanup skill."),
        ("cleanup", "Clear writing", ""),
    ):
        folder = source / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", encoding="utf-8"
        )
        (folder / "resource.txt").write_text("Original supporting resource.\n")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "source",
                        "path": str(source.parent),
                        "roots": ["skills"],
                        "revision": "v1",
                        "url": "https://github.com/example/source",
                        "node_min": 0,
                    }
                ]
            }
        )
    )
    root = tmp_path / "project"
    root.mkdir()
    (root / PROJECT_MARKER).touch()
    (root / "AGENTS.md").write_text("Owner instructions.\n")
    home = tmp_path / "hub"
    Hub.initialize(home, catalog, "skills")
    manager = FakeManager()
    with Hub(home, manager).transaction() as hub:
        hub.register("project", root)
    return home, root, catalog, manager


def sync(
    home: Path, manager: FakeManager, *, goal: str = "debug test failures", count: int = 2
) -> dict[str, Any]:
    with Hub(home, manager).transaction() as hub:
        result = hub.sync("project", goal, "test", count)
        if result["status"] == "needs_agent_selection":
            choice = "writing" if "documentation" in goal else "debugging"
            result = hub.sync("project", goal, "test", count, choices=["source/skills/" + choice])
        return result


def test_restart_reuses_profile_without_discovery_or_install(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    first = sync(home, manager)
    manager.calls.clear()
    second = sync(home, manager)
    assert first["status"] == second["status"] == "ready"
    assert second["cache_hit"] and not second["changed"]
    assert manager.calls == []
    assert (
        root / ".agents/skills/debugging/resource.txt"
    ).read_text() == "Original supporting resource.\n"


def test_skillkit_is_the_default_and_does_not_require_the_other_installer(
    configured: tuple[Path, Path, Path, FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, root, catalog, manager = configured
    single_home = home.parent / "skillkit-only"
    assert Hub.initialize(single_home, catalog)["manager"] == "skillkit"
    binary = home.parent / "skillkit-only.js"
    binary.write_text("pinned skillkit runtime")
    looked_up: list[str] = []

    def which(command: str) -> str | None:
        looked_up.append(command)
        return None if command == "skills" else str(binary)

    monkeypatch.setattr("scripts.persistent_hub.shutil.which", which)
    with Hub(single_home, manager).transaction() as hub:
        hub.register("project", root)
    result = sync(single_home, manager)
    assert result["status"] == "ready"
    assert "skills" not in looked_up
    assert all(call[0] != "skills" for call in manager.calls)
    assert (root / ".agents/skills/debugging/resource.txt").is_file()
    manager.calls.clear()
    assert sync(single_home, manager)["cache_hit"]
    assert not manager.calls


def test_explicit_legacy_installer_still_requires_its_own_binary(
    configured: tuple[Path, Path, Path, FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _, _, manager = configured
    monkeypatch.setattr(
        "scripts.persistent_hub.shutil.which",
        lambda command: None if command == "skills" else sys.executable,
    )
    with (
        Hub(home, manager).transaction() as hub,
        pytest.raises(ValueError, match="unavailable: skills"),
    ):
        hub.manager_identity()
    assert not manager.calls


def test_project_and_goal_scopes_do_not_share_profiles(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    sync(home, manager)
    result = sync(home, manager, goal="write developer documentation")
    assert set(result["selected"]) == {"writing", "cleanup"}
    assert not (root / ".agents/skills/debugging/SKILL.md").exists()
    assert (root / "AGENTS.md").read_text() == "Owner instructions.\n"


def test_new_goal_rechecks_selection_but_reuses_exact_native_bundle(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, _, _, manager = configured
    sync(home, manager)
    manager.calls.clear()
    result = sync(home, manager, goal="debug another test failure")
    assert result["status"] == "ready" and not result["cache_hit"]
    assert len(manager.calls) == 1 and manager.calls[0][:2] == ["skillkit", "recommend"]


def test_policy_change_invalidates_selection_cache(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    sync(home, manager)
    (root / "AGENTS.md").write_text("Changed owner policy.\n")
    result = sync(home, manager)
    assert not result["cache_hit"]
    assert (root / "AGENTS.md").read_text() == "Changed owner policy.\n"


def test_owner_edit_pauses_and_unowned_note_survives_removal(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    sync(home, manager)
    skill = root / ".agents/skills/debugging/SKILL.md"
    skill.write_text("Owner replaced this instruction.")
    assert sync(home, manager)["status"] == "paused_owner_edit"
    assert skill.read_text() == "Owner replaced this instruction."
    with Hub(home, manager).transaction() as hub:
        skill.write_bytes(
            hub_module.raw(hub.get("active:project")["files"][".agents/skills/debugging/SKILL.md"])
            or b""
        )
    note = skill.parent / "owner-note.md"
    note.write_text("Keep my note.")
    assert sync(home, manager, count=0)["status"] == "ready"
    assert note.read_text() == "Keep my note."
    assert not skill.exists()


def test_missing_resource_restores_without_manager_or_source_access(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    sync(home, manager)
    resource = root / ".agents/skills/debugging/resource.txt"
    resource.unlink()
    manager.fail = True
    result = sync(home, manager)
    assert result["cache_hit"] and result["changed"]
    assert resource.read_text() == "Original supporting resource.\n"


def test_incompatible_update_recovers_exact_previous_bundle(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, catalog, manager = configured
    sync(home, manager)
    data = json.loads(catalog.read_text())
    data["sources"][0].update(revision="v2", node_min=99)
    catalog.write_text(json.dumps(data))
    resource = root / ".agents/skills/debugging/resource.txt"
    resource.unlink()
    result = sync(home, manager)
    assert result["status"] == "deferred_incompatible_update"
    assert result["restored_from_known_good_bundle"]
    assert resource.read_text() == "Original supporting resource.\n"


def test_failed_native_install_preserves_previous_profile(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    sync(home, manager)
    manager.fail = True
    with pytest.raises(ValueError, match="Native manager failed"):
        sync(home, manager, goal="write developer documentation")
    assert (root / ".agents/skills/debugging/SKILL.md").exists()
    assert not (root / ".agents/skills/writing/SKILL.md").exists()


def test_actual_process_exit_is_recoverable(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    sync(home, manager)
    code = (
        "from pathlib import Path; from scripts.persistent_hub import Hub; import sys\n"
        "with Hub(Path(sys.argv[1])).transaction() as hub:\n"
        " hub.publish('project', {'files':{},'selected':[]}, fault_after=1)"
    )
    result = subprocess.run([sys.executable, "-c", code, str(home)], capture_output=True)
    assert result.returncode == 86
    assert (home / "project.pending.json").is_file()
    assert sync(home, manager)["status"] == "ready"
    assert not (home / "project.pending.json").exists()
    assert (root / ".agents/skills/debugging/resource.txt").exists()


def test_rollback_blocks_regeneration_and_disable_still_works(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, catalog, manager = configured
    sync(home, manager)
    data = json.loads(catalog.read_text())
    data["sources"][0]["revision"] = "v2"
    (Path(data["sources"][0]["path"]) / "skills/debugging/resource.txt").write_text("Version two.")
    catalog.write_text(json.dumps(data))
    sync(home, manager)
    with Hub(home, manager).transaction() as hub:
        assert hub.rollback("project")["status"] == "ready"
    assert (
        root / ".agents/skills/debugging/resource.txt"
    ).read_text() == "Original supporting resource.\n"
    assert sync(home, manager)["status"] == "rejected_update"
    assert sync(home, manager, count=0)["status"] == "ready"
    assert not (root / ".agents/skills/debugging/SKILL.md").exists()


def test_unmarked_project_and_alias_rebinding_are_refused(
    configured: tuple[Path, Path, Path, FakeManager], tmp_path: Path
) -> None:
    home, root, _, manager = configured
    with Hub(home, manager).transaction() as hub:
        with pytest.raises(ValueError, match="separately marked"):
            hub.register("other", tmp_path)
        with pytest.raises(ValueError, match="already registered"):
            hub.register("alias", root)


def test_source_tamper_after_index_is_not_published(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, catalog, manager = configured
    with Hub(home, manager).transaction() as hub:
        hub.refresh()
    data = json.loads(catalog.read_text())
    (Path(data["sources"][0]["path"]) / "skills/debugging/resource.txt").write_text("Tampered.")
    with pytest.raises(ValueError, match="Source changed after indexing"):
        sync(home, manager)
    assert not (root / ".agents/skills/debugging/SKILL.md").exists()


def test_native_version_drift_rejected(
    configured: tuple[Path, Path, Path, FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, root, _, manager = configured
    original = manager.__call__

    def changed(argv: list[str], cwd: Path, home: Path) -> dict[str, Any]:
        result = original(argv, cwd, home)
        if argv == ["skills", "--version"]:
            result["stdout"] = "2.0.0"
        return result

    with (
        Hub(home, changed).transaction() as hub,
        pytest.raises(ValueError, match="version changed"),
    ):
        hub.sync("project", "debug failures", "test")
    assert not (root / ".agents/skills/debugging/SKILL.md").exists()


def test_ranking_alone_cannot_publish_a_profile(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    with Hub(home, manager).transaction() as hub:
        assert hub.sync("project", "debug tests", "test")["status"] == "needs_agent_selection"
    assert not (root / ".agents/skills").exists()


def test_current_explicit_selection_overrides_a_cached_profile(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, _, manager = configured
    sync(home, manager)
    with Hub(home, manager).transaction() as hub:
        result = hub.sync(
            "project", "debug test failures", "test", choices=["source/skills/writing"]
        )
    assert set(result["selected"]) == {"writing", "cleanup"}
    assert not (root / ".agents/skills/debugging/SKILL.md").exists()


def test_explicit_only_source_is_excluded_from_autonomous_selection(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, root, catalog, manager = configured
    source = (
        Path(json.loads(catalog.read_text())["sources"][0]["path"]) / "skills/debugging/SKILL.md"
    )
    source.write_text(
        source.read_text().replace(
            "name: debugging", "disable-model-invocation: true\nname: debugging"
        )
    )
    with (
        Hub(home, manager).transaction() as hub,
        pytest.raises(ValueError, match="explicit owner invocation"),
    ):
        hub.sync("project", "debug tests", "test", choices=["source/skills/debugging"])
    assert not (root / ".agents/skills").exists()


def test_catalog_edit_cannot_silently_authorize_another_publisher(
    configured: tuple[Path, Path, Path, FakeManager],
) -> None:
    home, _, catalog, manager = configured
    data = json.loads(catalog.read_text())
    data["sources"][0]["url"] = "https://github.com/other/publisher"
    catalog.write_text(json.dumps(data))
    with (
        Hub(home, manager).transaction() as hub,
        pytest.raises(ValueError, match="Source scope changed"),
    ):
        hub.refresh()


def test_partial_source_batch_survives_restart_without_losing_receipts(
    configured: tuple[Path, Path, Path, FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, root, catalog, manager = configured
    data = json.loads(catalog.read_text())
    data["sources"].append({**data["sources"][0], "id": "second"})
    catalog.write_text(json.dumps(data))
    home = tmp_path / "poll-hub"
    Hub.initialize(home, catalog, "skills")
    seen = []
    fail_second = True

    def fetch(path: Path, cache: Path) -> dict[str, Any]:
        nonlocal fail_second
        document = json.loads(path.read_text())
        source = document["sources"][0]
        seen.append({"id": source["id"], "bound": source.get("tree_sha256"), "cache": str(cache)})
        (cache / "partial-source.bin").write_text("Preserve failed acquisition evidence")
        if source["id"] == "second" and fail_second:
            fail_second = False
            raise OSError("Controlled second-source failure")
        source.update(revision="new-version", tree_sha256="bound-tree")
        path.write_text(json.dumps(document))
        return {"sources": [{"id": source["id"], "reused": seen[-1]["bound"] is not None}]}

    monkeypatch.setattr("scripts.persistent_hub.core.refresh", fetch)
    with Hub(home, manager).transaction() as hub, pytest.raises(OSError, match="second-source"):
        hub.poll()
    first = json.loads((home / "source-receipts/source.json").read_text())
    assert first["sources"][0]["tree_sha256"] == "bound-tree"
    with Hub(home, manager).transaction() as hub:
        assert hub.get("index") is None
        assert hub.poll()["project_files_changed"] is False
    assert seen[2]["id"] == "source" and seen[2]["bound"] == "bound-tree"
    assert seen[1]["cache"] != seen[3]["cache"]
    assert Path(seen[1]["cache"], "partial-source.bin").is_file()
    assert (root / "AGENTS.md").read_text() == "Owner instructions.\n"


def test_source_intake_reserves_space_before_acquisition(
    configured: tuple[Path, Path, Path, FakeManager], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, root, _, manager = configured
    cache = home / "source-cache"
    cache.mkdir()
    (cache / "retained.bin").write_bytes(b"x" * 801)
    monkeypatch.setattr(hub_module, "SOURCE_CACHE_BUDGET", 1000)
    monkeypatch.setattr(hub_module, "SOURCE_EXPANSION_BUDGET", 200)

    def unexpected_fetch(*args: Any) -> Any:
        pytest.fail("Acquisition started without its full expansion reservation")

    monkeypatch.setattr("scripts.persistent_hub.core.refresh", unexpected_fetch)
    with Hub(home, manager).transaction() as hub, pytest.raises(ValueError, match="intake space"):
        hub.poll()
    assert sum(p.stat().st_size for p in cache.rglob("*") if p.is_file()) == 801
    assert (root / "AGENTS.md").read_text() == "Owner instructions.\n"


def test_source_batch_rechecks_space_and_keeps_completed_receipt(
    configured: tuple[Path, Path, Path, FakeManager],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, _, catalog, manager = configured
    data = json.loads(catalog.read_text())
    data["sources"].append({**data["sources"][0], "id": "second"})
    catalog.write_text(json.dumps(data))
    home = tmp_path / "bounded-poll-hub"
    Hub.initialize(home, catalog, "skills")
    cache = home / "source-cache"
    cache.mkdir()
    retained = cache / "retained.bin"
    retained.write_bytes(b"x" * 700)
    monkeypatch.setattr(hub_module, "SOURCE_CACHE_BUDGET", 1000)
    monkeypatch.setattr(hub_module, "SOURCE_EXPANSION_BUDGET", 200)
    fetched = []

    def fetch(path: Path, source_cache: Path) -> dict[str, Any]:
        document = json.loads(path.read_text())
        source = document["sources"][0]
        fetched.append(source["id"])
        (source_cache / "snapshot.bin").write_bytes(b"y" * 150)
        source.update(revision="new-version", tree_sha256="bound-tree")
        path.write_text(json.dumps(document))
        return {"sources": [{"id": source["id"]}]}

    monkeypatch.setattr("scripts.persistent_hub.core.refresh", fetch)
    with Hub(home, manager).transaction() as hub, pytest.raises(ValueError, match="intake space"):
        hub.poll()
    assert fetched == ["source"]
    assert sum(p.stat().st_size for p in cache.rglob("*") if p.is_file()) == 850
    receipt = json.loads((home / "source-receipts/source.json").read_text())
    assert receipt["sources"][0]["tree_sha256"] == "bound-tree"
    retained.unlink()  # Owner-approved cleanup in this synthetic fixture only.
    with Hub(home, manager).transaction() as hub:
        assert hub.poll()["project_files_changed"] is False
    assert fetched == ["source", "source", "second"]
