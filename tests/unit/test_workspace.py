from __future__ import annotations

import json
from pathlib import Path

import pytest

from adaptation_compiler_lab.workspace import (
    WorkspaceError,
    initialize_workspace,
    load_workspace,
    prepare_new_output_directory,
)


def test_workspace_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "prototype-data"
    created = initialize_workspace(root, subject_id="synthetic-user")

    loaded, subject_id = load_workspace(root)

    assert loaded == created
    assert subject_id == "synthetic-user"
    assert loaded.raw_evidence.is_dir()
    assert loaded.packs.is_dir()
    assert loaded.exports.is_dir()


def test_workspace_refuses_nonempty_directory(tmp_path: Path) -> None:
    root = tmp_path / "not-empty"
    root.mkdir()
    (root / "unrelated.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="non-empty"):
        initialize_workspace(root, subject_id="synthetic-user")


def test_workspace_rejects_unknown_version(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    paths = initialize_workspace(root, subject_id="synthetic-user")
    payload = json.loads(paths.config.read_text(encoding="utf-8"))
    payload["format_version"] = 999
    paths.config.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceError, match="unsupported workspace format"):
        load_workspace(root)


@pytest.mark.parametrize("name", ["../escape", "nested/path", "", ".", ".."])
def test_output_path_cannot_escape(tmp_path: Path, name: str) -> None:
    with pytest.raises(WorkspaceError):
        prepare_new_output_directory(tmp_path, name)


def test_output_directory_is_never_overwritten(tmp_path: Path) -> None:
    prepare_new_output_directory(tmp_path, "pack-1")

    with pytest.raises(WorkspaceError, match="already exists"):
        prepare_new_output_directory(tmp_path, "pack-1")
