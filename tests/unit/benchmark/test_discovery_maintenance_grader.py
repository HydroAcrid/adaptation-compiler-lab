from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from scripts.run_discovery_maintenance_screen import POLICY, DiscoveryShell
from scripts.run_extension_lifecycle_screen import files


@pytest.mark.parametrize(
    "mutation,check",
    [
        ("app", "python_app_source_unchanged"),
        ("owner", "python_owner_policy_preserved"),
        ("resource", "complete_source_resources"),
        ("source", "source_feed_preserved"),
        ("catalog", "catalog_preserved"),
        ("scope", "small_applicable_profile"),
    ],
)
def test_checkpoint_rejects_representative_regressions(
    tmp_path: Path, mutation: str, check: str
) -> None:
    initial: dict[str, Any] = {"files": {}}
    for project in ("python", "typescript"):
        root = tmp_path / project
        owner = root / ".agents/skills/owner-guidance/SKILL.md"
        owner.parent.mkdir(parents=True)
        owner.write_text("---\nname: owner-guidance\ndescription: Owner.\n---\n")
        (root / "AGENTS.md").write_text(POLICY)
        (root / "app.py").write_text("original = True\n")
        initial["files"][project] = files(root)
    config = tmp_path / "home/.codex/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("# Owner config\n")
    source = tmp_path / "sources/source/skills/systematic-debugging"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: systematic-debugging\ndescription: Debug failures.\n---\nSource body\n"
    )
    (source / "guide.md").write_text("Supporting resource")
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "source",
                        "url": "https://example.invalid/source",
                        "revision": "first",
                        "path": "/work/sources/source",
                        "roots": ["skills"],
                    }
                ]
            }
        )
    )
    installed = tmp_path / "python/.agents/skills/systematic-debugging"
    shutil.copytree(source, installed)
    shell = DiscoveryShell(tmp_path, initial, "temper_prototype")
    assert shell.check()["passed"] is True
    if mutation == "app":
        (tmp_path / "python/app.py").write_text("Changed")
    elif mutation == "owner":
        (tmp_path / "python/AGENTS.md").write_text("Lost owner policy")
    elif mutation == "resource":
        (installed / "guide.md").unlink()
    elif mutation == "source":
        (source / "guide.md").write_text("Tampered source")
    elif mutation == "catalog":
        (tmp_path / "catalog.json").write_text(json.dumps({"sources": []}))
    else:
        irrelevant = tmp_path / "python/.agents/skills/technical-writing"
        irrelevant.mkdir()
        (irrelevant / "SKILL.md").write_text(
            "---\nname: technical-writing\ndescription: Write docs.\n---\n"
        )
    result = shell.check()
    assert result["passed"] is False
    assert result["checks"][check] is False
