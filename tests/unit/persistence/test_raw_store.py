"""Content-addressed raw payload path and integrity tests."""

from dataclasses import replace
from pathlib import Path

import pytest

from adaptation_compiler_lab.persistence.errors import IntegrityError
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore


def test_raw_payload_round_trip_uses_digest_only_path(tmp_path: Path) -> None:
    store = LocalRawPayloadStore(tmp_path / "raw-evidence")
    payload = b"sensitive synthetic transcript"

    reference = store.put(payload, media_type="text/plain")

    assert reference.relative_path == (f"sha256/{reference.sha256[:2]}/{reference.sha256}")
    assert store.read(reference) == payload
    assert store.put(payload, media_type="text/plain") == reference


def test_raw_reference_cannot_escape_store_root(tmp_path: Path) -> None:
    store = LocalRawPayloadStore(tmp_path / "raw-evidence")
    reference = store.put(b"payload", media_type="application/octet-stream")

    with pytest.raises(IntegrityError, match="path does not match"):
        store.read(replace(reference, relative_path="../../outside"))
    with pytest.raises(IntegrityError, match="lowercase hexadecimal"):
        store.read(replace(reference, sha256="../escape"))


def test_raw_payload_tampering_is_detected(tmp_path: Path) -> None:
    store = LocalRawPayloadStore(tmp_path / "raw-evidence")
    reference = store.put(b"original", media_type="text/plain")
    stored_path = store.root / reference.relative_path
    stored_path.write_bytes(b"tampered")

    with pytest.raises(IntegrityError):
        store.read(reference)
