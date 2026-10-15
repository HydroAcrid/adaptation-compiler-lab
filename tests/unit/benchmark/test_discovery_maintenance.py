from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from scripts.discovery_maintenance import (
    MARKER,
    STATE,
    discover,
    recommend,
    reconcile,
    refresh,
    sha,
)


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / MARKER).touch()
    (root / "pyproject.toml").write_text('[project]\nname = "example"\n')
    sources = tmp_path / "source"
    for name, description in (
        ("debug", "Isolate test failures and trace root causes"),
        ("writing", "Write clear documentation and prose"),
    ):
        skill = sources / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\nSee [guide](guide.md).\n"
        )
        (skill / "guide.md").write_bytes(b"Public supporting resource\n")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "source",
                        "revision": "first",
                        "path": str(sources),
                        "url": "https://example.invalid/source",
                    }
                ]
            }
        )
    )
    return root, catalog


def test_goal_routing_and_project_switch_preserve_manual_files(tmp_path: Path) -> None:
    root, catalog = fixture(tmp_path)
    first = recommend(root, catalog, "Isolate test failures", count=1)
    assert first["selected"][0]["name"] == "debug"
    assert reconcile(root, first)["status"] == "ready"
    note = root / ".agents/skills/debug/owner.md"
    note.write_text("Owner material")
    other = recommend(root, catalog, "Write clear prose documentation", count=1)
    assert other["selected"][0]["name"] == "writing"
    result = reconcile(root, other)
    assert result["removed"] == 2
    assert note.read_text() == "Owner material"
    assert not (root / ".agents/skills/debug/SKILL.md").exists()
    assert reconcile(root, other)["changed"] is False
    negative = recommend(
        root, catalog, "Write clear documentation; not isolate test failures", count=1
    )
    assert negative["selected"][0]["name"] == "writing"


def test_updates_defer_incompatible_release_and_accept_fixed_one(tmp_path: Path) -> None:
    root, catalog = fixture(tmp_path)
    first = recommend(root, catalog, "Isolate test failures", count=1)
    reconcile(root, first)
    config = json.loads(catalog.read_text())
    config["sources"][0].update(node_min=99, revision="incompatible")
    catalog.write_text(json.dumps(config))
    blocked = reconcile(root, recommend(root, catalog, "Isolate test failures", count=1))
    assert blocked["status"] == "deferred_update"
    assert json.loads((root / STATE).read_text())["sources"]["debug"]["revision"] == "first"
    config["sources"][0].update(node_min=18, revision="compatible")
    catalog.write_text(json.dumps(config))
    reconcile(root, recommend(root, catalog, "Isolate test failures", count=1))
    assert json.loads((root / STATE).read_text())["sources"]["debug"]["revision"] == "compatible"


def test_stack_mentions_do_not_activate_irrelevant_coding_guidance(tmp_path: Path) -> None:
    root, catalog = fixture(tmp_path)
    (root / "package.json").write_text(json.dumps({"devDependencies": {"typescript": "5.0"}}))
    code = tmp_path / "source/skills/typescript"
    code.mkdir()
    (code / "SKILL.md").write_text(
        "---\nname: typescript\ndescription: TypeScript best practices when editing code.\n---\n"
    )
    result = recommend(
        root, catalog, "Write clear prose documentation for this TypeScript repo", count=2
    )
    assert [s["name"] for s in result["selected"]] == ["writing"]


def test_missing_resources_block_and_deleted_install_recovers(tmp_path: Path) -> None:
    root, catalog = fixture(tmp_path)
    selection = recommend(root, catalog, "Isolate test failures", count=1)
    reconcile(root, selection)
    installed = root / ".agents/skills/debug/guide.md"
    installed.unlink()
    assert reconcile(root, selection)["written"] == 1
    source = Path(selection["selected"][0]["path"]) / "guide.md"
    source.unlink()
    bad = recommend(root, catalog, "Isolate test failures", count=1)
    assert bad["blocked"]
    assert reconcile(root, bad)["status"] == "deferred_update"


def test_external_edits_pause_without_overwrite_and_cleanup_is_scoped(tmp_path: Path) -> None:
    root, catalog = fixture(tmp_path)
    selection = recommend(root, catalog, "Isolate test failures", count=1)
    reconcile(root, selection)
    edited = root / ".agents/skills/debug/SKILL.md"
    edited.write_text("Concurrent owner edit")
    assert reconcile(root, selection)["status"] == "paused_external_edit"
    assert edited.read_text() == "Concurrent owner edit"
    assert (
        reconcile(root, recommend(root, catalog, "Nothing needed", count=0))["status"]
        == "paused_external_edit"
    )


def test_interrupted_write_resumes_and_changed_source_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    root, catalog = fixture(tmp_path)
    selection = recommend(root, catalog, "Isolate test failures", count=1)
    original = os.replace
    calls = 0

    def interrupt(source: Any, destination: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("Interrupted publication")
        original(source, destination)

    monkeypatch.setattr(os, "replace", interrupt)
    with pytest.raises(OSError):
        reconcile(root, selection)
    monkeypatch.setattr(os, "replace", original)
    assert reconcile(root, selection)["status"] == "ready"
    assert not (root / ".temper-hub-pending.json").exists()
    (Path(selection["selected"][0]["path"]) / "guide.md").write_text("Changed upstream")
    with pytest.raises(ValueError, match="Source changed"):
        reconcile(root, selection)


def test_scanner_uses_real_sources_and_rejects_escape(tmp_path: Path) -> None:
    root, catalog = fixture(tmp_path)
    rows = discover(catalog)
    assert len(rows) == 2
    assert rows[0]["files"]["guide.md"] == sha(b"Public supporting resource\n")
    selection = recommend(root, catalog, "Isolate test failures", count=1)
    selection["selected"][0]["name"] = "../../escape"
    with pytest.raises(ValueError, match="Invalid native"):
        reconcile(root, selection)
    (root / MARKER).unlink()
    with pytest.raises(ValueError, match="marked disposable"):
        recommend(root, catalog, "test")


def test_abrupt_child_exit_recovers_complete_profile(tmp_path: Path) -> None:
    root, catalog = fixture(tmp_path)
    selection = recommend(root, catalog, "Isolate test failures", count=1)
    incoming = tmp_path / "selection.json"
    incoming.write_text(json.dumps(selection))
    child = """
import json,os,sys
from pathlib import Path
import scripts.discovery_maintenance as hub
original=hub.os.replace
calls=0
def stop(source,destination):
 global calls
 original(source,destination)
 calls+=1
 if calls==2: os._exit(86)
hub.os.replace=stop
hub.reconcile(Path(sys.argv[1]),json.loads(Path(sys.argv[2]).read_text()))
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(root), str(incoming)], capture_output=True, timeout=15
    )
    assert result.returncode == 86
    assert (root / ".temper-hub-pending.json").is_file()
    assert sum(p.is_file() for p in (root / ".agents/skills/debug").iterdir()) == 1
    assert reconcile(root, selection)["status"] == "ready"
    assert (root / ".agents/skills/debug/guide.md").read_bytes() == b"Public supporting resource\n"


def test_live_intake_binds_cached_content_and_rejects_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    (tmp_path / MARKER).touch()
    commit = "a" * 40
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as stream:
        member = tarfile.TarInfo("repo-commit/skills/example/SKILL.md")
        data = b"---\nname: example\ndescription: Example.\n---\nPublic source\n"
        member.size = len(data)
        stream.addfile(member, io.BytesIO(data))
    calls = []

    def fetch(request: Any, **kwargs: Any) -> io.BytesIO:
        url = request.full_url if hasattr(request, "full_url") else request
        calls.append(url)
        return io.BytesIO(
            json.dumps({"sha": commit}).encode() if "api.github.com" in url else archive.getvalue()
        )

    monkeypatch.setattr(urllib.request, "urlopen", fetch)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"sources": [{"url": "https://github.com/owner/repo"}]}))
    first = refresh(catalog, tmp_path)
    assert first["sources"][0]["http_requests"] == 2
    assert refresh(catalog, tmp_path)["sources"][0]["reused"] is True
    assert len(calls) == 3
    target = tmp_path / "owner/repo" / commit / "skills/example/SKILL.md"
    target.write_text("Changed cache")
    with pytest.raises(ValueError, match="Cached source differs"):
        refresh(catalog, tmp_path)


@pytest.mark.parametrize("member_name", ["../escape", "/absolute", "root/../../escape"])
def test_intake_rejects_noncanonical_archive_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, member_name: str
) -> None:

    (tmp_path / MARKER).touch()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as stream:
        member = tarfile.TarInfo(member_name)
        member.size = 1
        stream.addfile(member, io.BytesIO(b"x"))

    def fetch(request: Any, **kwargs: Any) -> io.BytesIO:
        url = request.full_url if hasattr(request, "full_url") else request
        return io.BytesIO(
            json.dumps({"sha": "a" * 40}).encode()
            if "api.github.com" in url
            else archive.getvalue()
        )

    monkeypatch.setattr(urllib.request, "urlopen", fetch)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"sources": [{"url": "https://github.com/owner/repo"}]}))
    with pytest.raises(ValueError, match="noncanonical"):
        refresh(catalog, tmp_path)
