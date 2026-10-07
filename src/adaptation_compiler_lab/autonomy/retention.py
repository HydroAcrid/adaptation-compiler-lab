"""Thirty-day ciphertext retention in this lane's separate raw namespace."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from adaptation_compiler_lab.autonomy.defaults import RAW_RETENTION_DAYS
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore


def purge_expired_raw(store: AutonomyStore, *, now: datetime) -> int:
    references: dict[str, tuple[dict[str, Any], datetime]] = {}
    for event in store.events():
        payload = event["payload"]
        if event["type"] in {"episode", "analysis_completed"}:
            ref, timestamp = payload["raw_ref"], payload["completed_at"]
        elif event["type"] == "publication":
            ref, timestamp = payload["backup"], payload["published_at"]
        else:
            continue
        created = datetime.fromisoformat(timestamp)
        previous = references.get(ref["sha256"])
        if previous is None or created > previous[1]:
            references[ref["sha256"]] = (ref, created)
    count = 0
    root = store.raw_store.root.resolve()
    for digest, (ref, created) in references.items():
        if created > now - timedelta(days=RAW_RETENTION_DAYS):
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise AutonomyIntegrityError("raw retention reference is invalid")
        path = root / ref["relative_path"]
        resolved = path.resolve()
        if ref["relative_path"] != f"sha256/{digest[:2]}/{digest}" or (
            not resolved.is_relative_to(root) or path.is_symlink() or path.name != digest
        ):
            raise AutonomyIntegrityError("raw retention path escaped its private namespace")
        if path.exists():
            path.unlink()
            count += 1
        store.append(
            f"raw-purged-{digest}-{int(created.timestamp())}",
            "raw_purged",
            {"sha256": digest, "last_reference_at": created.isoformat()},
            at=now,
        )
    return count
