"""Small local file synchronization helper."""

from __future__ import annotations

import shutil
from pathlib import Path


def sync_file(source: Path, destination: Path) -> str:
    """Copy source to destination and return a status string."""

    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return "copied"
