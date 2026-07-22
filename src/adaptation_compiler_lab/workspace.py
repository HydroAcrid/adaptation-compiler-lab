"""Local workspace layout and initialization.

The workspace is an explicit research data root. It is not searched implicitly and never points
at Codex or Claude configuration directories.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

WORKSPACE_CONFIG: Final = "workspace.json"
WORKSPACE_FORMAT_VERSION: Final = 1


class WorkspaceError(ValueError):
    """Raised when a local workspace is missing, unsafe, or incompatible."""


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    """Resolved paths owned by one local prototype workspace."""

    root: Path
    config: Path
    database: Path
    raw_evidence: Path
    packs: Path
    exports: Path


def _paths(root: Path) -> WorkspacePaths:
    resolved = root.expanduser().resolve()
    return WorkspacePaths(
        root=resolved,
        config=resolved / WORKSPACE_CONFIG,
        database=resolved / "ledger.sqlite3",
        raw_evidence=resolved / "raw-evidence",
        packs=resolved / "packs",
        exports=resolved / "exports",
    )


def initialize_workspace(root: Path, *, subject_id: str) -> WorkspacePaths:
    """Create an inspectable local workspace without touching an agent installation."""

    if not subject_id.strip():
        raise WorkspaceError("subject_id must not be empty")

    paths = _paths(root)
    paths.root.mkdir(parents=True, exist_ok=True)
    if paths.config.exists():
        raise WorkspaceError(f"workspace already exists: {paths.root}")

    unexpected = [item for item in paths.root.iterdir() if item.name not in {".gitignore"}]
    if unexpected:
        names = ", ".join(sorted(item.name for item in unexpected))
        raise WorkspaceError(f"refusing to initialize a non-empty directory: {names}")

    for directory in (paths.raw_evidence, paths.packs, paths.exports):
        directory.mkdir(mode=0o700)

    payload = {
        "format_version": WORKSPACE_FORMAT_VERSION,
        "mode": "local_single_subject",
        "subject_id": subject_id,
    }
    paths.config.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _restrict(paths.config, 0o600)
    return paths


def load_workspace(root: Path) -> tuple[WorkspacePaths, str]:
    """Load and validate an existing workspace configuration."""

    paths = _paths(root)
    try:
        payload = json.loads(paths.config.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WorkspaceError(f"workspace config not found: {paths.config}") from error
    except json.JSONDecodeError as error:
        raise WorkspaceError(f"workspace config is not valid JSON: {error}") from error

    if not isinstance(payload, dict):
        raise WorkspaceError("workspace config must be a JSON object")
    if payload.get("format_version") != WORKSPACE_FORMAT_VERSION:
        raise WorkspaceError("unsupported workspace format version")
    if payload.get("mode") != "local_single_subject":
        raise WorkspaceError("unsupported workspace mode")
    subject_id = payload.get("subject_id")
    if not isinstance(subject_id, str) or not subject_id:
        raise WorkspaceError("workspace subject_id is missing")

    for directory in (paths.raw_evidence, paths.packs, paths.exports):
        if not directory.is_dir():
            raise WorkspaceError(f"workspace directory is missing: {directory}")
    return paths, subject_id


def prepare_new_output_directory(base: Path, name: str) -> Path:
    """Create a new output directory below ``base`` and refuse overwrite or traversal."""

    if not name or name in {".", ".."} or Path(name).name != name:
        raise WorkspaceError("output name must be one plain path segment")
    base_resolved = base.resolve()
    destination = (base_resolved / name).resolve()
    if destination.parent != base_resolved:
        raise WorkspaceError("output directory escapes its configured root")
    if destination.exists():
        raise WorkspaceError(f"output already exists: {destination}")
    destination.mkdir(mode=0o700)
    return destination


def _restrict(path: Path, mode: int) -> None:
    """Apply local-user permissions where the platform supports POSIX modes."""

    try:
        os.chmod(path, mode)
    except OSError:
        # Windows ACLs do not map reliably to POSIX modes. The workspace remains local and its
        # limitation is reported by the platform rather than pretending chmod is enforcement.
        return
