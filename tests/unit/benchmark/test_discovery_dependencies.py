from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.discovery_maintenance import MARKER, discover
from scripts.discovery_maintenance_v2 import dependencies, recommend, reconcile


def corpus(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    (root / MARKER).touch()
    sources = tmp_path / "sources"
    for name, description, body in (
        (
            "documentation",
            "Write clear documentation and readmes",
            "Apply the **clarity** skill to every document.",
        ),
        ("clarity", "Remove needless words", "Use concrete language."),
    ):
        skill = sources / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n"
            f"disable-model-invocation: true\n---\n{body}\n"
        )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "source",
                        "path": str(sources),
                        "url": "https://example.invalid/source",
                        "revision": "one",
                    }
                ]
            }
        )
    )
    return root, catalog


def test_dependency_is_included_even_when_metadata_does_not_match_goal(tmp_path: Path) -> None:
    root, catalog = corpus(tmp_path)
    selection = recommend(root, catalog, "Write clear documentation and readmes", count=2)
    assert {s["name"] for s in selection["selected"]} == {"documentation", "clarity"}
    result = reconcile(root, selection)
    assert result["status"] == "ready"
    assert result["source_restricts_implicit_invocation"] == ["clarity", "documentation"]
    assert result["instruction_delivery_verified"] is False
    for name in ("documentation", "clarity"):
        assert (root / ".agents/skills" / name / "SKILL.md").is_file()


def test_budget_cannot_silently_drop_required_dependency(tmp_path: Path) -> None:
    root, catalog = corpus(tmp_path)
    selection = recommend(root, catalog, "Write clear documentation and readmes", count=1)
    assert selection["selected"] == []
    assert reconcile(root, selection)["status"] == "blocked_dependency"
    assert not (root / ".agents").exists()


def test_cycle_and_unknown_declared_dependency_fail(tmp_path: Path) -> None:
    root, catalog = corpus(tmp_path)
    config = json.loads(catalog.read_text())
    source = Path(config["sources"][0]["path"])
    (source / "clarity/SKILL.md").write_text(
        "---\nname: clarity\ndescription: Remove needless words\n---\n"
        "Apply the documentation skill.\n"
    )
    selection = recommend(root, catalog, "Write clear documentation and readmes", count=2)
    assert selection["unresolved"]
    assert not selection["selected"]
    (source / "clarity/SKILL.md").write_text(
        "---\nname: clarity\ndescription: Remove needless words\nrequires: unavailable\n---\n"
    )
    rows = discover(catalog)
    row = next(r for r in rows if r["name"] == "clarity")
    with pytest.raises(ValueError, match="Unresolved declared"):
        dependencies(row, rows)


def test_incompatible_feed_cannot_claim_a_damaged_previous_profile_is_working(
    tmp_path: Path,
) -> None:
    root, catalog = corpus(tmp_path)
    goal = "Write clear documentation and readmes"
    reconcile(root, recommend(root, catalog, goal, count=2))
    config = json.loads(catalog.read_text())
    config["sources"][0]["node_min"] = 99
    catalog.write_text(json.dumps(config))
    (root / ".agents/skills/clarity/SKILL.md").unlink()
    result = reconcile(root, recommend(root, catalog, goal, count=2))
    assert result["status"] == "blocked_recovery_requires_compatible_source"
    assert result["retained_previous_profile"] is False
