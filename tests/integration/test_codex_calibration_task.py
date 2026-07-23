from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast


def _task_root() -> Path:
    return Path(__file__).parents[2] / "development_benchmark_v2" / "tasks" / "research_integrity"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(_task_root() / "fixture", workspace)
    for command in (
        ("git", "init", "--quiet"),
        ("git", "config", "user.name", "Test"),
        ("git", "config", "user.email", "test@invalid.local"),
        ("git", "add", "--all"),
        ("git", "commit", "--quiet", "-m", "fixture"),
    ):
        subprocess.run(command, cwd=workspace, check=True)
    return workspace


def _score(workspace: Path) -> dict[str, dict[str, bool]]:
    completed = subprocess.run(
        (
            sys.executable,
            str(_task_root() / "independent" / "score.py"),
            str(workspace),
        ),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return cast(dict[str, dict[str, bool]], json.loads(completed.stdout))


def test_v2_scorer_is_structural_and_bytecode_deterministic(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "runtime.pyc").write_bytes(b"runtime")
    cache = workspace / "__pycache__"
    cache.mkdir()
    (cache / "runtime.cpython-312.pyc").write_bytes(b"runtime")

    score = _score(workspace)

    assert set(score) == {"diagnostic", "neutral", "objective"}
    assert score["neutral"]["only_allowed_source_changed"]
    assert not all(score["objective"].values())


def test_v2_scorer_rejects_material_untracked_files(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "unrelated.txt").write_text("material\n", encoding="utf-8")

    assert not _score(workspace)["neutral"]["only_allowed_source_changed"]


def test_v2_scorer_accepts_exact_semantic_solution(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "readiness.py").write_text(
        '''"""Build a frozen-protocol readiness report."""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

def build_report(
    snapshots: Sequence[dict[str, Any]],
    protocol: dict[str, Any],
    trials: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    eligible = [
        item for item in snapshots
        if item.get("applicable_scope") == "release-readiness"
        and item.get("authority") == "release-owner"
        and item.get("signed") is True
    ]
    selected = max(eligible, key=lambda item: str(item["observed_at"]))
    non_evaluable = set(protocol["non_evaluable_statuses"])
    valid = [item for item in trials if item["status"] not in non_evaluable]
    passed = [item for item in valid if item["status"] == "passed"]
    total = len(trials)
    valid_rate = len(valid) / total if total else 0.0
    pass_rate = len(passed) / len(valid) if valid else 0.0
    if valid_rate < protocol["minimum_valid_rate"]:
        classification = "inconclusive"
    elif pass_rate >= protocol["minimum_pass_rate"]:
        classification = "ready"
    else:
        classification = "not_ready"
    return {
        "source": {
            "snapshot_id": selected["snapshot_id"],
            "observed_at": selected["observed_at"],
            "status": selected["status"],
        },
        "protocol": {
            "protocol_id": protocol["protocol_id"],
            "minimum_pass_rate": protocol["minimum_pass_rate"],
            "minimum_valid_rate": protocol["minimum_valid_rate"],
        },
        "trials": [dict(item) for item in trials],
        "metrics": {
            "total_trials": total,
            "valid_trials": len(valid),
            "valid_rate": valid_rate,
            "pass_rate": pass_rate,
        },
        "classification": classification,
    }

def main() -> None:
    root = Path(__file__).resolve().parent
    snapshots = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "source_snapshots").glob("*.json"))
    ]
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    trials = json.loads((root / "trial_ledger.json").read_text(encoding="utf-8"))
    print(json.dumps(build_report(snapshots, protocol, trials), sort_keys=True))

if __name__ == "__main__":
    main()
''',
        encoding="utf-8",
    )

    score = _score(workspace)

    assert all(score["objective"].values())
    assert all(score["diagnostic"].values())
    assert all(score["neutral"].values())
