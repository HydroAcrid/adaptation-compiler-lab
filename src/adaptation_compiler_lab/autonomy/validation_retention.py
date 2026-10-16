"""Bounded maintenance for completed and interrupted validation ciphertext stores."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.autonomy.defaults import RAW_RETENTION_DAYS
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.governance.models import SignatureEnvelope


def _references(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, dict):
        if {"sha256", "relative_path", "size_bytes", "media_type"} <= value.keys():
            yield value
        else:
            for child in value.values():
                yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


def purge_validation_raw(store: AutonomyStore, *, now: datetime) -> int:
    """Use verified reference times; orphaned interrupted writes use file age.

    Native turn records predate explicit payload timestamps. Their signed envelope
    provides the time without rewriting historical producer/protocol evidence.
    """
    events = store.events()
    with closing(sqlite3.connect(store.path)) as connection:
        rows = connection.execute(
            "SELECT content_digest,envelope FROM autonomy_events ORDER BY sequence"
        ).fetchall()
    if [row[0] for row in rows] != [event["digest"] for event in events]:
        raise AutonomyIntegrityError("validation changed during retention inspection")
    references: dict[str, datetime] = {}
    for event, (_digest, envelope) in zip(events, rows, strict=True):
        recorded = SignatureEnvelope.model_validate_json(envelope, strict=True).signed_at
        for ref in _references(event["payload"]):
            digest = ref["sha256"]
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise AutonomyIntegrityError("validation raw reference is invalid")
            if ref["relative_path"] != f"sha256/{digest[:2]}/{digest}":
                raise AutonomyIntegrityError("validation raw reference escaped its namespace")
            references[digest] = max(recorded, references.get(digest, recorded))
    root = store.raw_store.root.resolve()
    namespace = root / "sha256"
    if not namespace.exists():
        return 0
    if namespace.is_symlink() or namespace.resolve() != namespace:
        raise AutonomyIntegrityError("validation raw namespace changed")
    paths: list[tuple[Path, str, datetime]] = []
    for prefix in namespace.iterdir():
        if prefix.is_symlink() or prefix.resolve().parent != namespace:
            raise AutonomyIntegrityError("validation raw prefix escaped its namespace")
        if not prefix.is_dir() or not re.fullmatch(r"[0-9a-f]{2}", prefix.name):
            raise AutonomyIntegrityError("validation raw prefix is invalid")
        for path in prefix.iterdir():
            digest = path.name
            if (
                not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not digest.startswith(prefix.name)
                or path.is_symlink()
                or path.resolve().parent != prefix
                or not path.is_file()
            ):
                raise AutonomyIntegrityError("validation raw path escaped its namespace")
            recorded = references.get(digest) or datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if recorded <= now - timedelta(days=RAW_RETENTION_DAYS):
                paths.append((path, digest, recorded))
    # Recheck the signed chain before deleting anything; processing may be active.
    head = events[-1]["digest"] if events else "sha256:" + "0" * 64
    if store.head_digest != head:
        raise AutonomyIntegrityError("validation changed during retention inspection")
    for path, digest, recorded in paths:
        path.unlink(missing_ok=True)
        store.append(
            f"validation-raw-purged-{digest}-{int(recorded.timestamp())}",
            "validation_raw_purged",
            {"sha256": digest, "last_reference_at": recorded.isoformat()},
            at=now,
        )
    return len(paths)


def sweep_validation_raw(
    base: Path,
    open_run: Callable[[str], AutonomyStore],
    *,
    now: datetime,
) -> int:
    """Only the two governed validation run families, never arbitrary owner folders."""
    if not base.exists():
        return 0
    if base.is_symlink():
        raise AutonomyIntegrityError("validation namespace changed")
    total = 0
    for root in sorted(base.iterdir()):
        if not re.fullmatch(r"(?:owner-eval-|native-delivery-)[a-z0-9-]{1,160}", root.name):
            continue
        if root.is_symlink() or root.resolve().parent != base.resolve():
            raise AutonomyIntegrityError("validation run escaped its namespace")
        if (root / "events.sqlite3").is_file():
            total += purge_validation_raw(open_run(root.name), now=now)
    return total
