"""Publish one local directory tree."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class PublishConflictError(RuntimeError):
    """The destination differs from the source."""


class UnsafeLayoutError(ValueError):
    """The source and destination layout is unsafe."""


@dataclass(frozen=True)
class PublishPlan:
    destination_exists: bool
    content_differs: bool
    overwrite_risk: bool
    backup_path: Path | None


@dataclass(frozen=True)
class PublishResult:
    backup_path: Path | None


def preflight_publish(source: Path, destination: Path) -> PublishPlan:
    """Describe a local publish without modifying either tree."""

    return PublishPlan(
        destination_exists=destination.exists(),
        content_differs=destination.exists(),
        overwrite_risk=False,
        backup_path=None,
    )


def publish_local(
    source: Path,
    destination: Path,
    *,
    replace: bool = False,
) -> PublishResult:
    """Publish source into destination."""

    del replace
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return PublishResult(backup_path=None)


def restore_publish(backup_path: Path, destination: Path) -> None:
    """Restore a destination from a previous backup."""

    shutil.copytree(backup_path, destination, dirs_exist_ok=True)
