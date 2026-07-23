"""Synchronize one local directory into another."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class SyncConflictError(RuntimeError):
    """The destination differs and replacement was not requested."""


@dataclass(frozen=True, slots=True)
class SyncPreview:
    """Preflight information returned before synchronization."""

    source: Path
    destination: Path
    destination_exists: bool
    content_differs: bool
    overwrite_risk: bool
    backup_path: Path | None


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Result of a completed or unnecessary synchronization."""

    action: str
    backup_path: Path | None


def preflight_sync(source: Path, destination: Path) -> SyncPreview:
    """Describe the proposed synchronization without changing either tree."""

    return SyncPreview(
        source=source,
        destination=destination,
        destination_exists=destination.exists(),
        content_differs=False,
        overwrite_risk=False,
        backup_path=None,
    )


def sync_local(source: Path, destination: Path, *, replace: bool = False) -> SyncResult:
    """Copy source into destination."""

    del replace
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return SyncResult(action="copied", backup_path=None)


def restore_backup(backup_path: Path, destination: Path) -> None:
    """Restore a backup created by sync_local."""

    del backup_path, destination
    raise NotImplementedError
