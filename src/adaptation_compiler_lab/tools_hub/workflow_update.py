"""Read the one approved local workflow catalog and its independently pinned replay."""

from __future__ import annotations

import ctypes
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .paths import check_root, safe
from .portable_setup import (
    MAX_PACKAGE,
    SetupError,
    SetupPackage,
    UpdateSource,
    parse_package,
    read_regular,
)
from .workflow_evaluation import ReplayManifest, admit_replay_baseline, read_replay

CANDIDATE_NAME = "workflow.temper-setup"
UpdateDirection = Literal["update", "rollback"]


@dataclass(frozen=True)
class UpdateReview:
    direction: UpdateDirection
    grant_id: str
    project: dict[str, Any]
    revision: str | None
    source: UpdateSource | None
    active_digest: str
    package: SetupPackage
    counts: dict[str, int]

    def preview(self, review_id: str) -> dict[str, Any]:
        return {
            **self.package.preview(),
            "project_id": self.project["id"],
            "active_digest": self.active_digest,
            "source_name": CANDIDATE_NAME if self.direction == "update" else "Previous setup",
            "review_id": review_id,
            "direction": self.direction,
            **self.counts,
        }


def _local_path(path: Path) -> Path:
    if not path.is_absolute() or path.drive.startswith(("\\", "//")):
        raise SetupError("Choose an absolute path on this computer")
    if os.name == "nt" and ctypes.windll.kernel32.GetDriveTypeW(path.anchor) == 4:
        raise SetupError("Choose a local folder or file on this computer")
    return check_root(path)


def _directory_identity(directory: Path) -> tuple[int, int]:
    if not directory.is_dir():
        raise SetupError("The workflow source folder is unavailable")
    stat = directory.stat()
    return stat.st_dev, stat.st_ino


def connect_source(directory: Path, replay: Path, active: SetupPackage) -> UpdateSource:
    try:
        directory, replay = _local_path(directory), _local_path(replay)
        identity = _directory_identity(directory)
    except (OSError, ValueError, RuntimeError):
        raise SetupError("Choose an available local workflow folder and replay file") from None

    directory_parts = tuple(part.casefold() for part in directory.parts)
    replay_parts = tuple(part.casefold() for part in replay.parts)
    if (
        replay_parts[: len(directory_parts)] == directory_parts
        or replay.suffix.casefold() != ".json"
    ):
        raise SetupError("Choose a trusted replay JSON file outside the workflow source folder")

    manifest, digest = read_replay(replay)
    admit_replay_baseline(active, manifest)
    return UpdateSource(
        directory=str(directory),
        directory_device=identity[0],
        directory_inode=identity[1],
        replay=str(replay),
        replay_digest=digest,
        revision=secrets.token_hex(16),
    )


def _catalog_root(source: UpdateSource) -> Path:
    try:
        directory = _local_path(Path(source.directory))
        if _directory_identity(directory) != (source.directory_device, source.directory_inode):
            raise ValueError("Selected directory changed")
    except (OSError, ValueError, RuntimeError):
        raise SetupError(
            "The workflow source folder changed or is unavailable. Reconnect it."
        ) from None
    return directory


def source_candidate(source: UpdateSource) -> SetupPackage | None:
    directory = _catalog_root(source)
    try:
        raw = read_regular(safe(directory, CANDIDATE_NAME), MAX_PACKAGE)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RuntimeError):
        raise SetupError("The workflow update file could not be read safely") from None
    _catalog_root(source)
    try:
        return parse_package(raw)
    except SetupError:
        raise SetupError("The workflow update file has an invalid setup or signature") from None


def source_replay(source: UpdateSource) -> ReplayManifest:
    try:
        replay = _local_path(Path(source.replay))
        manifest, digest = read_replay(replay)
    except (OSError, ValueError, RuntimeError):
        raise SetupError(
            "The trusted replay file is unavailable or invalid. Reconnect it."
        ) from None
    if digest != source.replay_digest:
        raise SetupError("The trusted replay file changed. Reconnect it before checking updates.")
    return manifest
