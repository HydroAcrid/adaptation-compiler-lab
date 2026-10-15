"""Benchmark-only project-file lifecycle prototype; not a shipping Temper installer.

Runs no upstream code and changes no personal runtime. The caller prepares a
complete staging tree with normal upstream tools. This prototype publishes exact
files under explicitly named project paths, journals undo, and preserves edits.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

MARKER = ".temper-lifecycle-sandbox"


def digest(value: bytes | None) -> str | None:
    return None if value is None else hashlib.sha256(value).hexdigest()


def read(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError("symlink destinations are outside this prototype")
    return path.read_bytes() if path.is_file() else None


def checked(root: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or "\\" in relative:
        raise ValueError("destination must be a normalized relative path")
    target = root / str(name)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("destination escapes the sandbox project")
    if any(p.is_symlink() for p in (target, *target.parents) if p != root.parent):
        raise ValueError("symlink destination is unsupported")
    return target


def atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save(path: Path, value: Any) -> None:
    atomic(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def encode(value: bytes | None) -> str | None:
    return None if value is None else base64.b64encode(value).decode()


def decode(value: str | None) -> bytes | None:
    return None if value is None else base64.b64decode(value, validate=True)


def project(root: Path) -> Path:
    resolved = root.resolve()
    if not (resolved / MARKER).is_file():
        raise ValueError("only explicitly marked disposable benchmark projects are supported")
    return resolved


def plan(
    root: Path,
    incoming: Path,
    state: Path,
    prefixes: list[str],
    replacements: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = project(root)
    if state.exists():
        raise ValueError("use a fresh state path for each plan")
    changes, conflicts = [], []
    for path in sorted(incoming.rglob("*")):
        if path.is_symlink():
            raise ValueError("staging symlinks must be materialized explicitly")
        if not path.is_file():
            continue
        name = path.relative_to(incoming).as_posix()
        if not any(name == p or name.startswith(p.rstrip("/") + "/") for p in prefixes):
            continue
        destination = checked(root, name)
        before, after = read(destination), path.read_bytes()
        if before == after:
            continue
        if before is not None and (replacements or {}).get(name) != digest(before):
            conflicts.append(name)
        changes.append(
            {
                "path": name,
                "before": encode(before),
                "after": encode(after),
                "before_digest": digest(before),
                "after_digest": digest(after),
            }
        )
    value = {
        "version": 1,
        "root": str(root),
        "changes": changes,
        "conflicts": conflicts,
        "phase": "planned",
        "applied": 0,
    }
    save(state, value)
    return {"phase": value["phase"], "files": len(changes), "conflicts": conflicts}


def apply(state: Path, *, fail_after: int | None = None) -> dict[str, Any]:
    value = json.loads(state.read_text())
    root = project(Path(value["root"]))
    if value["phase"] == "applied":
        if not all(read(checked(root, c["path"])) == decode(c["after"]) for c in value["changes"]):
            raise ValueError("published files changed; inspect and plan a new version")
        return {"phase": "applied", "idempotent": True}
    if value["phase"] != "planned" or value["conflicts"]:
        raise ValueError("conflicting or interrupted plans require inspection/recovery")
    if any(digest(read(checked(root, c["path"]))) != c["before_digest"] for c in value["changes"]):
        raise ValueError("project changed after preview; replan")
    value["phase"] = "applying"
    save(state, value)
    for index, change in enumerate(value["changes"], 1):
        atomic(checked(root, change["path"]), decode(change["after"]) or b"")
        value["applied"] = index
        save(state, value)
        if fail_after == index:
            os._exit(86)  # Explicit fault injection for admission controls only.
    value["phase"] = "applied"
    save(state, value)
    return {"phase": "applied", "files": value["applied"]}


def restore(state: Path) -> dict[str, Any]:
    value = json.loads(state.read_text())
    root = project(Path(value["root"]))
    conflicts = []
    # Include the next entry: a crash may occur after replacement, before the
    # journal's applied counter is persisted. Exact before/after hashes decide.
    for change in reversed(value["changes"]):
        target = checked(root, change["path"])
        current, before, after = read(target), decode(change["before"]), decode(change["after"])
        if current == before:
            continue
        if current != after:
            conflicts.append(change["path"])
            continue
        if before is None:
            target.unlink()
        else:
            atomic(target, before)
    value["phase"] = "restore_conflict" if conflicts else "restored"
    value["restore_conflicts"] = sorted(conflicts)
    save(state, value)
    return {"phase": value["phase"], "conflicts": sorted(conflicts)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    prepare = sub.add_parser("plan")
    for name in ("root", "incoming", "state"):
        prepare.add_argument("--" + name, type=Path, required=True)
    prepare.add_argument("--prefix", action="append", required=True)
    prepare.add_argument("--replace", action="append", default=[], metavar="PATH=SHA256")
    for name in ("apply", "restore"):
        action = sub.add_parser(name)
        action.add_argument("--state", type=Path, required=True)
        if name == "apply":
            action.add_argument("--fail-after", type=int)
    args = parser.parse_args()
    try:
        result = (
            plan(
                args.root,
                args.incoming,
                args.state,
                args.prefix,
                dict(item.rsplit("=", 1) for item in args.replace),
            )
            if args.operation == "plan"
            else apply(args.state, fail_after=args.fail_after)
            if args.operation == "apply"
            else restore(args.state)
        )
        print(json.dumps(result))
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"error": str(error)}))
        raise SystemExit(3) from error


if __name__ == "__main__":
    main()
