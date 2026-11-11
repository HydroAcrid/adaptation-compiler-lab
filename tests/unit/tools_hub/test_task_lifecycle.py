import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.tools_hub.controller import MARKER, PROJECT_MARKER, Hub, b64
from adaptation_compiler_lab.tools_hub.sealed import Seals
from adaptation_compiler_lab.tools_hub.task_lifecycle import TaskOwner
from adaptation_compiler_lab.tools_hub.workflow_runtime import (
    MAX_RUN_BYTES,
    MotionVideo,
    RemotionRuntime,
    runtime_directory,
)


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    home, repo = tmp_path / "hub", tmp_path / "fictional-repo"
    home.mkdir()
    repo.mkdir()
    (home / MARKER).touch()
    (repo / PROJECT_MARKER).touch()
    with Hub(home).transaction() as hub:
        hub.register("fiction", repo)
    return home, repo


def test_switch_rotates_token_and_removes_owned_files_without_replaying_previous(
    workspace: tuple[Path, Path],
) -> None:
    home, repo = workspace
    owner, other = TaskOwner.current(), TaskOwner.current()
    with Hub(home).transaction() as hub:
        first = hub.begin_task("fiction", owner, "a" * 64, now=100, expires_at=200)
        hub.publish(
            "fiction",
            {
                "selected": [],
                "files": {
                    ".agents/skills/fiction/edited.md": b64(b"old data"),
                    ".agents/skills/fiction/owned.md": b64(b"old generated file"),
                },
            },
        )
    edited = repo / ".agents/skills/fiction/edited.md"
    edited.write_bytes(b"personal")
    with Hub(home).transaction() as hub:
        with pytest.raises(ValueError, match="Another active task"):
            hub.begin_task("fiction", other, "b" * 64, now=101, expires_at=250)
        resumed = hub.begin_task(
            "fiction", owner, "a" * 64, prior_token=first["task_token"], now=101, expires_at=250
        )
        assert resumed["task_token"] == first["task_token"]
        assert resumed["expires_at"] == 250
        second = hub.begin_task(
            "fiction", owner, "b" * 64, prior_token=first["task_token"], now=102, expires_at=250
        )
        assert second["task_token"] != first["task_token"]
        assert second["retained_owner_files"] == [".agents/skills/fiction/edited.md"]
        with pytest.raises(ValueError, match="stale"):
            hub.end_task("fiction", owner, first["task_token"], "completed")
    assert edited.read_bytes() == b"personal"
    assert not (repo / ".agents/skills/fiction/owned.md").exists()
    with Hub(home).transaction() as hub:
        assert hub.get("previous:fiction") is None
        assert hub.require_task("fiction", owner, second["task_token"], now=103)["task_digest"] == (
            "b" * 64
        )


def test_expiry_and_retry_only_clean_exact_owned_task(workspace: tuple[Path, Path]) -> None:
    home, _ = workspace
    owner = TaskOwner.current()
    with Hub(home).transaction() as hub:
        task = hub.begin_task("fiction", owner, "a" * 64, now=100, expires_at=200)
    cleaned: list[str] = []
    token = task["task_token"]
    with Hub(home, task_cleanup=cleaned.append).transaction() as hub:
        assert hub.reap_tasks(["fiction"], now=199) == []
        with pytest.raises(ValueError, match="expired"):
            hub.require_task("fiction", owner, token, now=200)
        assert hub.reap_tasks(["fiction"], now=200) == [
            {
                "project": "fiction",
                "status": "task_finished",
                "outcome": "cancelled",
                "files_changed": 0,
                "retained_owner_files": [],
            }
        ]
        assert hub.end_task("fiction", owner, token, "cancelled")["status"] == "task_finished"
        assert cleaned == [token]


def test_second_publication_requires_commit_and_rollback_recovers_first(
    workspace: tuple[Path, Path],
) -> None:
    home, repo = workspace
    profile = {
        "selected": [],
        "files": {".agents/skills/fiction/owned.md": b64(b"temporary")},
    }
    with pytest.raises(ValueError, match="Commit the previous"), Hub(home).transaction() as hub:
        hub.publish("fiction", profile)
        hub.release_task_profile("fiction")
    resource = repo / ".agents/skills/fiction/owned.md"
    assert resource.read_bytes() == b"temporary"
    with Hub(home).transaction() as hub:
        hub.recover("fiction")
    assert not resource.exists()
    assert not (home / "fiction.pending.json").exists()


def test_reap_after_process_crash_preserves_only_the_owner_edit(
    workspace: tuple[Path, Path],
) -> None:
    home, repo = workspace
    owner = TaskOwner.current()
    skills = repo / ".agents/skills/fiction"
    seals = Seals(
        GovernanceSigner(Ed25519PrivateKey.from_private_bytes(b"f" * 32), "fictional", "fixture")
    )

    def controller() -> Hub:
        return Hub(
            home,
            journal_pack=lambda value: seals.seal(value, "journal"),
            journal_unpack=lambda value: seals.open(value, "journal"),
        )

    with controller().transaction() as hub:
        hub.begin_task("fiction", owner, "a" * 64, now=100, expires_at=200)
        hub.publish(
            "fiction",
            {
                "selected": [],
                "files": {".agents/skills/fiction/a.md": b64(b"previous")},
            },
        )
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from adaptation_compiler_lab.governance.signing import GovernanceSigner
from adaptation_compiler_lab.tools_hub.controller import Hub, b64
from adaptation_compiler_lab.tools_hub.sealed import Seals
seals = Seals(GovernanceSigner(
    Ed25519PrivateKey.from_private_bytes(b'f' * 32), 'fictional', 'fixture'))
with Hub(Path(sys.argv[1]), journal_pack=lambda value: seals.seal(value, 'journal')
         ).transaction() as hub:
    files = {'.agents/skills/fiction/' + name: b64(b'partial')
             for name in ('a.md', 'b.md', 'c.md')}
    hub.publish('fiction', {'selected': [], 'files': files}, fault_after=3)
""",
            str(home),
        ],
        check=False,
    )
    assert crashed.returncode == 86
    assert len(seals.read(home / "fiction.pending.json", "journal")["changes"]) == 3
    assert (skills / "a.md").read_bytes() == b"partial"
    assert (skills / "c.md").read_bytes() == b"partial"
    (skills / "b.md").write_bytes(b"owner edit")
    (skills / "manual.md").write_bytes(b"unrelated")
    with controller().transaction() as hub:
        assert hub.reap_tasks(["fiction"], now=200)[0]["retained_owner_files"] == [
            ".agents/skills/fiction/b.md"
        ]
        assert hub.get("task:fiction") is None
    assert sorted(path.name for path in skills.iterdir()) == ["b.md", "manual.md"]
    assert (skills / "b.md").read_bytes() == b"owner edit"
    assert (skills / "manual.md").read_bytes() == b"unrelated"
    assert not (home / "fiction.pending.json").exists()


def test_oversized_scratch_does_not_strand_lease_or_skill_files(
    workspace: tuple[Path, Path],
) -> None:
    home, repo = workspace
    owner = TaskOwner.current()
    with Hub(home).transaction() as hub:
        task = hub.begin_task("fiction", owner, "a" * 64, now=100, expires_at=200)
        hub.publish(
            "fiction",
            {"selected": [], "files": {".agents/skills/fiction/owned.md": b64(b"owned")}},
        )
    runtime = home / "remotion"
    scratch = runtime_directory(runtime, task["task_token"])
    scratch.mkdir(parents=True)
    with (scratch / "oversize.tmp").open("wb") as stream:
        stream.truncate(MAX_RUN_BYTES + 1)
    sibling = runtime_directory(runtime, "f" * 64)
    sibling.mkdir()
    (sibling / "other.tmp").write_bytes(b"another task")

    def cleanup(token: str) -> None:
        RemotionRuntime.reap(runtime, token)

    with Hub(home, task_cleanup=cleanup).transaction() as hub:
        assert hub.reap_tasks(["fiction"], now=200)[0]["files_changed"] == 1
        assert hub.get("task:fiction") is None
    assert not scratch.exists()
    assert not (repo / ".agents/skills/fiction/owned.md").exists()
    assert (sibling / "other.tmp").read_bytes() == b"another task"


def test_running_renderer_checks_scratch_growth_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(
        argv: list[str], cwd: Path, home: Path, *, guard: Callable[[], None], **_: Any
    ) -> dict[str, Any]:
        guard()
        with (cwd / "growth.tmp").open("wb") as stream:
            stream.truncate(MAX_RUN_BYTES + 1)
        guard()
        pytest.fail("render guard accepted oversized scratch")

    monkeypatch.setattr(RemotionRuntime, "verify", lambda self: (tmp_path,) * 3)
    monkeypatch.setattr("adaptation_compiler_lab.tools_hub.workflow_runtime.bounded_run", run)
    token = "a" * 64
    with pytest.raises(ValueError, match="scratch exceeded its storage bound"):
        RemotionRuntime({}).render(
            tmp_path, token, MotionVideo(title="Fictional title"), allowed=lambda: None
        )
    assert not runtime_directory(tmp_path, token).exists()
    assert not (tmp_path / "artifacts").exists()


def test_reap_does_not_enter_redirected_children(tmp_path: Path) -> None:
    outside = tmp_path / "unrelated"
    outside.mkdir()
    (outside / "kept.txt").write_bytes(b"not scratch")
    runtime = tmp_path / "remotion"
    token = "b" * 64
    scratch = runtime_directory(runtime, token)
    scratch.mkdir(parents=True)
    link = scratch / "outside"
    if os.name == "nt":
        subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            check=True,
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    assert (link / "kept.txt").is_file()
    assert RemotionRuntime.reap(runtime, token)
    assert not scratch.exists()
    assert (outside / "kept.txt").read_bytes() == b"not scratch"
