from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.retention import purge_expired_raw
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.autonomy.validation_retention import (
    checked_validation_run,
    purge_validation_raw,
    sweep_validation_raw,
)
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker
from adaptation_compiler_lab.persistence.errors import RecordNotFoundError
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from tests.unit.autonomy.test_autonomy import app as app


def test_expired_native_and_completed_detector_raw_are_purged(app: Any) -> None:
    service, clock = app
    store = service.store
    before = clock() - timedelta(days=31)
    refs = []
    for kind, field in (
        ("native_turn", "raw_ref"),
        ("native_delivery_validation", "native_evidence_ref"),
        ("evaluation_wire", "raw_ref"),
    ):
        ref = asdict(store.save_raw(kind.encode()))
        refs.append(ref)
        store.append(kind, kind, {field: ref}, at=before)
    assert purge_validation_raw(store, now=clock()) == 3
    for ref in refs:
        with pytest.raises(RecordNotFoundError):
            store.raw(ref)
    assert purge_validation_raw(store, now=clock()) == 0


def test_current_shared_reference_survives_and_orphaned_old_ciphertext_expires(app: Any) -> None:
    service, clock = app
    store = service.store
    before = clock() - timedelta(days=31)
    ref = asdict(store.save_raw(b"shared"))
    store.append("old-turn", "native_turn", {"raw_ref": ref}, at=before)
    store.append("fresh-turn", "native_turn", {"raw_ref": ref}, at=clock())
    orphan = asdict(store.save_raw(b"interrupted unreferenced write"))
    path = store.raw_store.root / orphan["relative_path"]
    os.utime(path, (before.timestamp(), before.timestamp()))
    assert purge_validation_raw(store, now=clock()) == 1
    assert store.raw(ref) == b"shared"
    with pytest.raises(RecordNotFoundError):
        store.raw(orphan)


def test_validation_cleanup_rejects_escaped_reference_before_deleting(app: Any) -> None:
    service, clock = app
    store = service.store
    ref = asdict(store.save_raw(b"must remain safe"))
    store.append(
        "escaped-ref",
        "native_turn",
        {"raw_ref": {**ref, "relative_path": "../outside"}},
        at=clock() - timedelta(days=31),
    )
    with pytest.raises(AutonomyIntegrityError, match="escaped"):
        purge_validation_raw(store, now=clock())
    assert store.raw(ref) == b"must remain safe"


def test_validation_sweep_is_bounded_and_runs_while_learning_paused(
    app: Any, tmp_path: Path
) -> None:
    service, clock = app
    service.set_switch("learning", False, key="pause-fixture")
    seen = []
    base = tmp_path / "validation"
    for name in ("owner-eval-finished", "native-delivery-interrupted", "unrelated-owner-folder"):
        root = base / name
        root.mkdir(parents=True)
        (root / "events.sqlite3").touch()
    ref = asdict(service.store.save_raw(b"expired native result"))
    service.store.append(
        "old-native", "native_turn", {"raw_ref": ref}, at=clock() - timedelta(days=31)
    )

    def open_run(name: str) -> Any:
        seen.append(name)
        return service.store

    worker = BackgroundHabitWorker(
        service,
        read_completed=lambda *_: pytest.fail("Paused learning must not observe conversations"),
        maintenance=lambda now: sweep_validation_raw(base, open_run, now=now),
    )
    result = worker.poll()
    assert result["status"] == "paused" and result["purged"] == 1
    assert sorted(seen) == ["native-delivery-interrupted", "owner-eval-finished"]


@pytest.mark.parametrize("entry", ["sweep", "purge", "personal_purge", "qualification_read"])
def test_raw_root_junction_cannot_delete_or_open_unrelated_owner_data(
    app: Any, tmp_path: Path, entry: str
) -> None:
    service, clock = app
    outside = tmp_path / "unrelated-owner-store"
    raw = LocalRawPayloadStore(outside, encryption_key=RawEncryptionKey(b"k" * 32))
    ref = raw.put(b"unrelated ciphertext must survive", media_type="text/plain")
    target = raw.root / ref.relative_path
    old = clock() - timedelta(days=31)
    os.utime(target, (old.timestamp(), old.timestamp()))
    base = tmp_path / "validation"
    run = base / "native-delivery-junction"
    run.mkdir(parents=True)
    alias = run / "raw"
    if sys.platform == "win32":
        subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(alias), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        alias.symlink_to(outside, target_is_directory=True)
    try:
        store = AutonomyStore(
            run / "events.sqlite3",
            signer=service.store.signer,
            raw_store=LocalRawPayloadStore(alias, encryption_key=RawEncryptionKey(b"k" * 32)),
        )
        with pytest.raises(AutonomyIntegrityError, match="escaped"):
            if entry == "purge":
                purge_validation_raw(store, now=clock())
            elif entry == "personal_purge":
                purge_expired_raw(store, now=clock())
            elif entry == "qualification_read":
                checked_validation_run(base, run.name)
            else:
                sweep_validation_raw(base, lambda _: store, now=clock())
        assert target.exists() and raw.read(ref) == b"unrelated ciphertext must survive"
    finally:
        # Remove only this verified alias entry; never traverse/delete its target.
        assert alias.parent == run and alias.resolve() == outside.resolve()
        if alias.is_symlink():
            alias.unlink()
        else:
            assert alias.is_junction()
            alias.rmdir()
