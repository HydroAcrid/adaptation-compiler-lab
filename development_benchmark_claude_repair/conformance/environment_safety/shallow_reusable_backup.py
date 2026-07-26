"""Intentionally defective publish helper used by benchmark conformance tests."""

from __future__ import annotations

import filecmp
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


def _trees_differ(source: Path, destination: Path) -> bool:
    comparison = filecmp.dircmp(str(source), str(destination))
    return bool(comparison.left_only or comparison.right_only or comparison.diff_files)


def _validate_layout(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if (
        source == destination
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise UnsafeLayoutError("source and destination must be disjoint")


def preflight_publish(source: Path, destination: Path) -> PublishPlan:
    """Describe a local publish without modifying either tree."""

    _validate_layout(source, destination)
    if not source.is_dir():
        raise UnsafeLayoutError("source must be a directory")
    exists = destination.exists()
    differs = exists and _trees_differ(source, destination)
    backup = destination.with_name(destination.name + ".backup") if differs else None
    return PublishPlan(exists, differs, differs, backup)


def publish_local(
    source: Path,
    destination: Path,
    *,
    replace: bool = False,
) -> PublishResult:
    """Publish source into destination."""

    plan = preflight_publish(source, destination)
    if plan.content_differs and not replace:
        raise PublishConflictError("destination differs")
    if not plan.destination_exists:
        shutil.copytree(source, destination)
        return PublishResult(None)
    if not plan.content_differs:
        return PublishResult(None)
    assert plan.backup_path is not None
    if plan.backup_path.exists():
        shutil.rmtree(plan.backup_path)
    shutil.copytree(destination, plan.backup_path)
    shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return PublishResult(plan.backup_path)


def restore_publish(backup_path: Path, destination: Path) -> None:
    """Restore a destination from a previous backup."""

    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(backup_path, destination)
