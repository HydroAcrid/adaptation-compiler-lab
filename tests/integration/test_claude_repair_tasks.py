from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).parents[2] / "development_benchmark_claude_repair"
TARGET_FILES = {
    "communication": "incident_handoff.py",
    "environment_safety": "local_publish.py",
}


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _workspace(tmp_path: Path, family: str) -> Path:
    workspace = tmp_path / family
    shutil.copytree(ROOT / "tasks" / family / "fixture", workspace)
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "fixture@example.invalid"],
        ["git", "config", "user.name", "Fixture"],
        ["git", "add", "--all"],
        ["git", "commit", "--quiet", "-m", "fixture"],
    ):
        completed = _run(command, cwd=workspace)
        assert completed.returncode == 0, completed.stderr
    return workspace


def _score(family: str, workspace: Path) -> dict[str, dict[str, bool]]:
    scorer = ROOT / "tasks" / family / "independent" / "score.py"
    completed = _run(["python3", str(scorer), str(workspace)], cwd=workspace)
    assert completed.returncode == 0, completed.stderr
    return cast(dict[str, dict[str, bool]], json.loads(completed.stdout))


def _visible(family: str, workspace: Path) -> subprocess.CompletedProcess[str]:
    task = cast(
        dict[str, Any],
        json.loads((ROOT / "tasks" / family / "task.json").read_text(encoding="utf-8")),
    )
    return _run(cast(list[str], task["visible_test_command"]), cwd=workspace)


@pytest.mark.parametrize("family", tuple(TARGET_FILES))
def test_repaired_baselines_fail_visible_and_independent_checks(
    tmp_path: Path,
    family: str,
) -> None:
    workspace = _workspace(tmp_path, family)

    visible = _visible(family, workspace)
    scored = _score(family, workspace)

    assert visible.returncode != 0
    assert not all(scored["objective"].values())
    assert not all(scored["diagnostic"].values())
    assert all(scored["neutral"].values())


@pytest.mark.parametrize("family", tuple(TARGET_FILES))
def test_repaired_references_pass_every_check(tmp_path: Path, family: str) -> None:
    workspace = _workspace(tmp_path, family)
    source = ROOT / "conformance" / family / "reference.py"
    shutil.copyfile(source, workspace / TARGET_FILES[family])

    visible = _visible(family, workspace)
    scored = _score(family, workspace)

    assert visible.returncode == 0, visible.stdout + visible.stderr
    assert all(all(group.values()) for group in scored.values())


def test_double_quoted_paths_are_rejected_without_collapsing_other_checks(
    tmp_path: Path,
) -> None:
    family = "communication"
    workspace = _workspace(tmp_path, family)
    shutil.copyfile(
        ROOT / "conformance" / family / "double_quoted.py",
        workspace / TARGET_FILES[family],
    )

    visible = _visible(family, workspace)
    scored = _score(family, workspace)

    assert visible.returncode != 0
    assert scored["objective"]["adversarial_paths_are_shell_literals"] is False
    assert scored["objective"]["deterministic_for_identical_inputs"] is True
    assert scored["objective"]["public_signature_is_preserved"] is True
    assert scored["diagnostic"]["purpose_precedes_procedure"] is True


def test_shallow_reusable_backup_is_rejected_without_all_zero_collapse(
    tmp_path: Path,
) -> None:
    family = "environment_safety"
    workspace = _workspace(tmp_path, family)
    shutil.copyfile(
        ROOT / "conformance" / family / "shallow_reusable_backup.py",
        workspace / TARGET_FILES[family],
    )

    visible = _visible(family, workspace)
    scored = _score(family, workspace)

    assert visible.returncode != 0
    assert scored["objective"]["new_destination_is_copied_exactly"] is True
    assert scored["objective"]["public_operations_remain_available"] is True
    assert scored["diagnostic"]["nested_content_difference_is_detected"] is False
    assert scored["diagnostic"]["explicit_replace_uses_unused_exact_backup"] is False
    assert any(scored["diagnostic"].values())
