"""Thirty-day ciphertext retention in this lane's separate raw namespace."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.autonomy.defaults import RAW_RETENTION_DAYS
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore


def purge_expired_raw(store: AutonomyStore, *, now: datetime) -> int:
    expected_root = store.path.parent / "raw"
    if expected_root.is_symlink() or expected_root.resolve() != expected_root:
        raise AutonomyIntegrityError("raw retention root escaped its private namespace")
    if not expected_root.samefile(store.raw_store.root):
        raise AutonomyIntegrityError("raw retention store belongs to another namespace")
    events = store.events()
    references: dict[str, tuple[dict[str, Any], datetime]] = {}
    for event in events:
        payload = event["payload"]
        if event["type"] in {"episode", "analysis_completed", "evaluation_wire"}:
            ref, timestamp = payload["raw_ref"], payload["completed_at"]
        elif event["type"] == "publication":
            ref, timestamp = payload["backup"], payload["published_at"]
        else:
            continue
        digest = ref["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise AutonomyIntegrityError("raw retention reference is invalid")
        if ref["relative_path"] != f"sha256/{digest[:2]}/{digest}":
            raise AutonomyIntegrityError("raw retention path escaped its private namespace")
        created = datetime.fromisoformat(timestamp)
        previous = references.get(ref["sha256"])
        if previous is None or created > previous[1]:
            references[ref["sha256"]] = (ref, created)
    # Preserve the raw store's extended Windows I/O path for long payload names.
    namespace = store.raw_store.root / "sha256"
    if namespace.is_symlink() or namespace.resolve() != namespace:
        raise AutonomyIntegrityError("raw retention namespace escaped its private namespace")
    if not namespace.exists():
        return 0
    candidates: list[tuple[Path, str, datetime]] = []
    for prefix in namespace.iterdir():
        if (
            prefix.is_symlink()
            or prefix.resolve() != prefix
            or not prefix.is_dir()
            or not re.fullmatch(r"[0-9a-f]{2}", prefix.name)
        ):
            raise AutonomyIntegrityError("raw retention prefix escaped its private namespace")
        for path in prefix.iterdir():
            digest = path.name
            if (
                not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not digest.startswith(prefix.name)
                or path.is_symlink()
                or path.resolve() != path
                or not path.is_file()
            ):
                raise AutonomyIntegrityError("raw retention path escaped its private namespace")
            # Signed references take precedence over old content-addressed file ages.
            # Interrupted raw-before-append writes have only their filesystem age.
            reference = references.get(digest)
            created = (
                reference[1]
                if reference is not None
                else datetime.fromtimestamp(path.stat().st_mtime, UTC)
            )
            if created <= now - timedelta(days=RAW_RETENTION_DAYS):
                candidates.append((path, digest, created))
    head = events[-1]["digest"] if events else "sha256:" + "0" * 64
    for path, digest, created in candidates:
        if store.head_digest != head:
            raise AutonomyIntegrityError("raw retention state changed during inspection")
        if (
            expected_root.resolve() != expected_root
            or namespace.resolve() != namespace
            or path.parent.resolve() != path.parent
            or path.is_symlink()
            or path.resolve() != path
        ):
            raise AutonomyIntegrityError("raw retention path escaped its private namespace")
        path.unlink(missing_ok=True)
        store.append(
            f"raw-purged-{digest}-{int(created.timestamp())}",
            "raw_purged",
            {"sha256": digest, "last_reference_at": created.isoformat()},
            at=now,
        )
        head = store.head_digest
    return len(candidates)
