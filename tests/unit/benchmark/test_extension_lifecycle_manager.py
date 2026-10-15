from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.extension_lifecycle_manager import MARKER, apply, checked, plan, restore


def fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root, stage = tmp_path / "project", tmp_path / "stage"
    root.mkdir()
    (root / MARKER).touch()
    for name in ("a", "b", "c"):
        file = stage / ".agents/skills" / name / "SKILL.md"
        file.parent.mkdir(parents=True)
        file.write_text("upstream " + name)
    return root, stage, tmp_path / "state.json"


def test_real_interrupted_publish_can_restore_without_touching_owner_edits(tmp_path: Path) -> None:
    root, stage, state = fixture(tmp_path)
    manual = root / "AGENTS.md"
    manual.write_text("owner policy")
    plan(root, stage, state, [".agents"])
    script = Path(__file__).resolve().parents[3] / "scripts/extension_lifecycle_manager.py"
    result = subprocess.run(
        [sys.executable, str(script), "apply", "--state", str(state), "--fail-after", "2"],
        check=False,
    )
    assert result.returncode == 86
    assert len(list(root.rglob("SKILL.md"))) == 2
    edited = root / ".agents/skills/a/SKILL.md"
    edited.write_text("owner changed this after the crash")
    outcome = restore(state)
    assert outcome["phase"] == "restore_conflict"
    assert edited.read_text() == "owner changed this after the crash"
    assert not (root / ".agents/skills/b/SKILL.md").exists()
    assert manual.read_text() == "owner policy"


def test_changed_project_rejects_before_any_publication(tmp_path: Path) -> None:
    root, stage, state = fixture(tmp_path)
    plan(root, stage, state, [".agents"])
    target = root / ".agents/skills/c/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("new owner content after preview")
    with pytest.raises(ValueError, match="changed after preview"):
        apply(state)
    assert list(root.rglob("SKILL.md")) == [target]


def test_recovery_handles_replace_before_journal_counter_and_is_idempotent(tmp_path: Path) -> None:
    root, stage, state = fixture(tmp_path)
    plan(root, stage, state, [".agents"])
    apply(state)
    value = json.loads(state.read_text())
    value["applied"], value["phase"] = 0, "applying"
    state.write_text(json.dumps(value))
    assert restore(state)["phase"] == "restored"
    assert not list(root.rglob("SKILL.md"))
    assert restore(state)["phase"] == "restored"


def test_foreign_files_survive_install_and_removal(tmp_path: Path) -> None:
    root, stage, state = fixture(tmp_path)
    note = root / ".agents/skills/a/owner-note.md"
    note.parent.mkdir(parents=True)
    note.write_text("manual notes")
    plan(root, stage, state, [".agents"])
    apply(state)
    apply(state)
    restore(state)
    assert note.read_text() == "manual notes"


def test_paths_and_existing_content_require_explicit_preconditions(tmp_path: Path) -> None:
    root, stage, state = fixture(tmp_path)
    with pytest.raises(ValueError):
        checked(root, "../outside")
    existing = root / ".agents/skills/a/SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("owner version")
    assert plan(root, stage, state, [".agents"])["conflicts"]
    with pytest.raises(ValueError, match="conflicting"):
        apply(state)
    assert existing.read_text() == "owner version"
