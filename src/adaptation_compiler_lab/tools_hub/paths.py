"""Closed filesystem boundaries for controller-owned caches and approved repositories."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePath
from typing import Any, cast

RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def check_root(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.resolve() != path:
        raise ValueError("Hub paths must not be redirected")
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Hub paths must not be redirected")
    return path


def safe(root: Path, relative: str) -> Path:
    root = check_root(root)
    parts = relative.split("/")
    if not relative or any(
        not part
        or part in {".", ".."}
        or part.endswith((".", " "))
        or any(c in part for c in '\\<>:"|?*')
        or part.casefold().split(".")[0] in RESERVED
        for part in parts
    ):
        raise ValueError("Noncanonical Hub resource path")
    path = root.joinpath(*parts)
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink() or item.is_junction():
            raise ValueError("Hub resources must not be redirected")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Hub path escapes its approved root")
    return path


def check_windows_path(
    path: PurePath, *, directory: bool, operation: str, relative: str = "."
) -> None:
    """Admit only paths compatible with ordinary Win32 file and directory APIs."""

    def units(value: str) -> int:
        return len(value.encode("utf-16-le", errors="surrogatepass")) // 2

    def check(value: str, limit: int, kind: str) -> None:
        length = units(value)
        if length > limit:
            label = ascii(relative)[:96]
            raise ValueError(
                f"Windows {operation} {label}: {kind} uses {length} UTF-16 units (limit {limit})"
            )

    # MAX_PATH includes the NUL. Leave another 12 units for directory creation.
    if not directory:
        check(str(path), 259, "file path")
    for parent in (path, *path.parents) if directory else path.parents:
        check(str(parent), 247, "directory path")
    for component in path.parts[bool(path.anchor) :]:
        check(component, 255, "path component")


def files(
    root: Path,
    *,
    maximum_bytes: int,
    maximum_entries: int = 20_000,
    enforce_windows_budget: bool = False,
) -> list[Path]:
    """Bound traversal and fail on any unavailable or unsupported resource."""
    root = check_root(root)
    windows_budget = enforce_windows_budget and os.name == "nt"
    pending = [root]
    result = []
    count = total = 0
    while pending:
        path = pending.pop()
        count += 1
        if count > maximum_entries:
            raise ValueError("Hub resource entry limit reached")
        if windows_budget:
            relative = path.relative_to(root).as_posix()
            check_windows_path(
                path, directory=path == root, operation="snapshot resource", relative=relative
            )
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT
        ):
            raise ValueError("Hub resources must not be redirected")
        if stat.S_ISDIR(info.st_mode):
            if windows_budget and path != root:
                check_windows_path(
                    path, directory=True, operation="snapshot resource", relative=relative
                )
            pending.extend(path.iterdir())
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if total > maximum_bytes:
                raise ValueError("Hub resource storage limit reached")
            result.append(path)
        else:
            raise ValueError("Hub resources must be regular files or directories")
    return sorted(result)


def remove_owned_tree(path: Path, *, cache: Path, maximum_bytes: int) -> None:
    """Validate the complete literal cache partition before deleting public cached files."""
    cache, path = check_root(cache), check_root(path)
    if path == cache or not path.is_relative_to(cache):
        raise ValueError("Only an inactive owned cache partition may be removed")
    leaves = files(path, maximum_bytes=maximum_bytes)
    directories = {path}
    for leaf in leaves:
        directories.update(p for p in leaf.parents if p != cache and p.is_relative_to(path))
    for leaf in leaves:
        safe(cache, leaf.relative_to(cache).as_posix()).unlink()
    # Empty directories also need validation; never follow a redirected subtree.
    pending = [path]
    while pending:
        item = pending.pop()
        if item.is_symlink() or item.is_junction():
            raise ValueError("Hub cache changed during cleanup")
        if item.is_dir():
            children = list(item.iterdir())
            directories.add(item)
            pending.extend(children)
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        directory.rmdir()


@contextmanager
def writer_lock(home: Path, *, name: str = "writer.lock") -> Iterator[None]:
    """One cross-process writer; the OS releases this lock after a dead worker."""
    home = check_root(home)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if name not in {"writer.lock", "permission.lock"}:
        raise ValueError("Invalid Hub lock")
    path = safe(home, name)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                cast(Any, fcntl).flock(
                    stream.fileno(), cast(Any, fcntl).LOCK_EX | cast(Any, fcntl).LOCK_NB
                )
        except OSError:
            raise ValueError("Hub maintenance is already running; retry shortly") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                cast(Any, fcntl).flock(stream.fileno(), cast(Any, fcntl).LOCK_UN)
