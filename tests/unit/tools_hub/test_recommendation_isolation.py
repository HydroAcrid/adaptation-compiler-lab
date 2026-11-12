"""Native recommendation scratch state stays outside the registered repository."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.tools_hub.manager import bounded_run
from adaptation_compiler_lab.tools_hub.service import HubService

from .test_integration import prepare

WORKER = """
import sys
import time
from pathlib import Path

context = Path('.skillkit/context.yaml')
context.parent.mkdir(exist_ok=True)
context.write_text('native scratch context', encoding='utf-8')
outcome = sys.argv[1]
if outcome == 'failure':
    sys.exit(1)
if outcome == 'cancelled':
    time.sleep(30)
print('[{"skill": {"name": "debugging"}, "relevance": 80}]')
"""


class Cancelled(Exception):
    pass


@pytest.mark.parametrize("owner_context", [False, True])
@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
def test_recommendation_uses_disposable_workspace(
    service: HubService, monkeypatch: pytest.MonkeyPatch, owner_context: bool, outcome: str
) -> None:
    repo = service.home.parent / "repo"
    (repo / ".env").write_bytes(b"PRIVATE_FIXTURE=true")
    (repo / "AGENTS.md").write_bytes(b"Private native instructions")
    if owner_context:
        (repo / ".skillkit").mkdir()
        (repo / ".skillkit/context.yaml").write_bytes(b"Owner context")
        (repo / ".skillkit/owner-file").write_bytes(b"Owner data")

    def snapshot() -> dict[Path, bytes | None]:
        return {
            path.relative_to(repo): path.read_bytes() if path.is_file() else None
            for path in repo.rglob("*")
        }

    original = snapshot()
    workspaces: list[tuple[Path, list[Path]]] = []

    def run(argv: list[str], cwd: Path, command_home: Path) -> dict[str, Any]:
        assert argv == [
            "skillkit",
            "recommend",
            "--task=Fix the failing tests",
            "--json",
            "--limit",
            "8",
        ]
        workspaces.append((cwd, list(cwd.iterdir())))
        assert command_home == service.home / "manager-home"

        def cancel_after_write() -> None:
            context = cwd / ".skillkit/context.yaml"
            if (
                outcome == "cancelled"
                and context.is_file()
                and context.read_bytes() == b"native scratch context"
            ):
                raise Cancelled

        return bounded_run(
            [sys.executable, "-c", WORKER, outcome],
            cwd,
            command_home,
            timeout=8,
            guard=cancel_after_write,
        )

    monkeypatch.setattr(service.manager, "run", run)
    if outcome == "success":
        result = prepare(service)
        assert result["native_recommendations"] == [
            {"name": "debugging", "source": "", "relevance": 80}
        ]
    elif outcome == "failure":
        with pytest.raises(ValueError, match="Native manager failed"):
            prepare(service)
    else:
        with pytest.raises(Cancelled):
            prepare(service)
    assert snapshot() == original
    assert len(workspaces) == 1
    workspace, initial_files = workspaces[0]
    assert workspace.is_relative_to(service.home)
    assert initial_files == []
    assert not workspace.exists()
