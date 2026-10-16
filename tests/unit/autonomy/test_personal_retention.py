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
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_autonomy import episode


def test_interrupted_episode_ciphertext_expires_without_a_signed_reference(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, clock = app
    append = service.store.append

    def interrupt(*args: Any, **kwargs: Any) -> bool:
        if args[1] == "episode":
            raise RuntimeError("fictional interruption after raw write")
        return append(*args, **kwargs)

    monkeypatch.setattr(service.store, "append", interrupt)
    with pytest.raises(RuntimeError, match="fictional interruption"):
        service.ingest_episode(episode(0, clock))
    monkeypatch.setattr(service.store, "append", append)
    assert not service.episodes()
    paths = list(service.store.raw_store.root.glob("sha256/*/*"))
    assert len(paths) == 1
    os.utime(paths[0], (clock().timestamp(), clock().timestamp()))
    clock.value += timedelta(days=30) - timedelta(microseconds=1)
    assert purge_expired_raw(service.store, now=clock()) == 0
    clock.value += timedelta(microseconds=1)
    fresh = service.store.save_raw(b"recent interrupted write")
    recent = service.store.raw_store.root / fresh.relative_path
    os.utime(recent, (clock().timestamp(), clock().timestamp()))
    assert purge_expired_raw(service.store, now=clock()) == 1
    assert not paths[0].exists()
    assert service.store.raw(asdict(fresh)) == b"recent interrupted write"
    assert not service.episodes()
    assert purge_expired_raw(service.store, now=clock()) == 0


def test_fresh_signed_reference_preserves_old_shared_ciphertext(app: Any) -> None:
    service, clock = app
    old = clock() - timedelta(days=31)
    ref = asdict(service.store.save_raw(b"shared encrypted evidence"))
    path = service.store.raw_store.root / ref["relative_path"]
    os.utime(path, (old.timestamp(), old.timestamp()))
    for key, stamp in (("old", old), ("recent", clock())):
        service.store.append(
            key,
            "analysis_completed",
            {"raw_ref": ref, "completed_at": stamp.isoformat()},
            at=stamp,
        )
    assert purge_expired_raw(service.store, now=clock()) == 0
    assert service.store.raw(ref) == b"shared encrypted evidence"


def test_personal_retention_supports_long_windows_ciphertext_paths(
    app: Any, tmp_path: Path
) -> None:
    service, clock = app
    root = tmp_path / ("r" * max(1, 220 - len(str(tmp_path))))
    raw = LocalRawPayloadStore(root / "raw", encryption_key=RawEncryptionKey(b"k" * 32))
    store = AutonomyStore(root / "events.sqlite3", signer=service.store.signer, raw_store=raw)
    ref = raw.put(b"interrupted long-path evidence", media_type="text/plain")
    path = raw.root / ref.relative_path
    old = clock() - timedelta(days=31)
    os.utime(path, (old.timestamp(), old.timestamp()))
    assert len(str(path)) > 260
    assert purge_expired_raw(store, now=clock()) == 1
    assert not path.exists()


def test_personal_retention_rejects_prefix_junction_before_deletion(
    app: Any, tmp_path: Path
) -> None:
    service, clock = app
    outside = LocalRawPayloadStore(
        tmp_path / "unrelated-raw", encryption_key=RawEncryptionKey(b"k" * 32)
    )
    ref = outside.put(b"unrelated encrypted owner data", media_type="text/plain")
    target = outside.root / ref.relative_path
    old = clock() - timedelta(days=31)
    os.utime(target, (old.timestamp(), old.timestamp()))
    namespace = service.store.raw_store.root / "sha256"
    namespace.mkdir(exist_ok=True)
    alias = namespace / ref.sha256[:2]
    if sys.platform == "win32":
        subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(alias), str(target.parent)],
            check=True,
            capture_output=True,
        )
    else:
        alias.symlink_to(target.parent, target_is_directory=True)
    try:
        with pytest.raises(AutonomyIntegrityError, match="escaped"):
            purge_expired_raw(service.store, now=clock())
        assert target.exists() and outside.read(ref) == b"unrelated encrypted owner data"
    finally:
        assert alias.parent == namespace and alias.samefile(target.parent)
        if alias.is_symlink():
            alias.unlink()
        else:
            assert alias.is_junction()
            alias.rmdir()
