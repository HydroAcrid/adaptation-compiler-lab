"""Deterministic repository-state helpers for the instrument-canary scorer."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

_BYTECODE_DIRECTORIES = frozenset({"__pycache__"})
_BYTECODE_SUFFIXES = frozenset({".pyc", ".pyo"})


def _is_interpreter_generated_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return bool(_BYTECODE_DIRECTORIES.intersection(path.parts)) or path.suffix in _BYTECODE_SUFFIXES


def repository_changed_paths(workspace: Path) -> set[str]:
    commands = (
        ("git", "diff", "--name-only", "-z", "--no-renames", "HEAD", "--"),
        ("git", "ls-files", "--others", "--exclude-standard", "-z"),
    )
    changed: set[str] = set()
    for command in commands:
        completed = subprocess.run(command, cwd=workspace, check=True, capture_output=True)
        changed.update(
            item.decode("utf-8")
            for item in completed.stdout.split(b"\0")
            if item and not _is_interpreter_generated_path(item.decode("utf-8"))
        )
    return changed
