"""Publish one local directory tree safely."""

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


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _validate_layout(source: Path, destination: Path) -> None:
    resolved_source = source.resolve()
    resolved_destination = destination.resolve()
    if (
        resolved_source == resolved_destination
        or resolved_destination.is_relative_to(resolved_source)
        or resolved_source.is_relative_to(resolved_destination)
    ):
        raise UnsafeLayoutError("source and destination must be disjoint")


def _next_backup_path(destination: Path) -> Path:
    base = destination.with_name(destination.name + ".backup")
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = destination.with_name(f"{destination.name}.backup.{counter}")
        counter += 1
    return candidate


def preflight_publish(source: Path, destination: Path) -> PublishPlan:
    """Describe a local publish without modifying either tree."""

    _validate_layout(source, destination)
    if not source.is_dir():
        raise UnsafeLayoutError("source must be an existing directory")
    if destination.exists() and not destination.is_dir():
        raise UnsafeLayoutError("destination must be a directory")
    destination_exists = destination.exists()
    differs = destination_exists and _snapshot(source) != _snapshot(destination)
    return PublishPlan(
        destination_exists=destination_exists,
        content_differs=differs,
        overwrite_risk=differs,
        backup_path=_next_backup_path(destination) if differs else None,
    )


def publish_local(
    source: Path,
    destination: Path,
    *,
    replace: bool = False,
) -> PublishResult:
    """Publish source into destination without silent replacement."""

    plan = preflight_publish(source, destination)
    if not plan.destination_exists:
        shutil.copytree(source, destination)
        return PublishResult(None)
    if not plan.content_differs:
        return PublishResult(None)
    if not replace:
        raise PublishConflictError("destination differs; use replace=True")
    backup = _next_backup_path(destination)
    shutil.copytree(destination, backup)
    shutil.rmtree(destination)
    try:
        shutil.copytree(source, destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(backup, destination)
        raise
    return PublishResult(backup)


def restore_publish(backup_path: Path, destination: Path) -> None:
    """Restore a destination from a previous backup."""

    _validate_layout(backup_path, destination)
    if not backup_path.is_dir():
        raise FileNotFoundError(f"backup is unavailable: {backup_path}")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(backup_path, destination)
