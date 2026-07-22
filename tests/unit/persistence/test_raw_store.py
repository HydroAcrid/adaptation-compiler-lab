"""Encrypted content-addressed raw-payload path and integrity tests."""

from __future__ import annotations

import base64
import os
from dataclasses import replace
from pathlib import Path

import pytest

from adaptation_compiler_lab.persistence.errors import IntegrityError
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadKeyError,
)


def _key(byte: int = 1) -> RawEncryptionKey:
    return RawEncryptionKey(bytes([byte]) * 32)


def test_raw_payload_round_trip_is_encrypted_and_content_addressed(tmp_path: Path) -> None:
    store = LocalRawPayloadStore(tmp_path / "raw-evidence", encryption_key=_key())
    payload = b"sensitive synthetic transcript"

    reference = store.put(payload, media_type="text/plain")
    stored = (store.root / reference.relative_path).read_bytes()

    assert reference.relative_path == (f"sha256/{reference.sha256[:2]}/{reference.sha256}")
    assert payload not in stored
    assert stored.startswith(b"ACLAB-RAW-1\n")
    assert store.read(reference) == payload
    assert store.put(payload, media_type="text/plain") == reference


def test_missing_or_wrong_key_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "raw-evidence"
    reference = LocalRawPayloadStore(root, encryption_key=_key()).put(
        b"payload", media_type="application/octet-stream"
    )

    with pytest.raises(RawPayloadKeyError, match="unavailable"):
        LocalRawPayloadStore(root).read(reference)
    with pytest.raises(IntegrityError, match="metadata mismatch"):
        LocalRawPayloadStore(root, encryption_key=_key(2)).read(reference)
    with pytest.raises(RawPayloadKeyError, match="unavailable"):
        LocalRawPayloadStore(tmp_path / "new").put(b"payload", media_type="text/plain")


def test_raw_reference_cannot_escape_store_root(tmp_path: Path) -> None:
    store = LocalRawPayloadStore(tmp_path / "raw-evidence", encryption_key=_key())
    reference = store.put(b"payload", media_type="application/octet-stream")

    with pytest.raises(IntegrityError, match="path does not match"):
        store.read(replace(reference, relative_path="../../outside"))
    with pytest.raises(IntegrityError, match="lowercase hexadecimal"):
        store.read(replace(reference, sha256="../escape"))


def test_ciphertext_tampering_is_detected(tmp_path: Path) -> None:
    store = LocalRawPayloadStore(tmp_path / "raw-evidence", encryption_key=_key())
    reference = store.put(b"original", media_type="text/plain")
    stored_path = store.root / reference.relative_path
    stored = bytearray(stored_path.read_bytes())
    stored[-1] ^= 1
    stored_path.write_bytes(stored)

    with pytest.raises(IntegrityError):
        store.read(reference)


def test_encrypted_envelope_rejects_unexpected_fields(tmp_path: Path) -> None:
    import json

    store = LocalRawPayloadStore(tmp_path / "raw-evidence", encryption_key=_key())
    reference = store.put(b"original", media_type="text/plain")
    stored_path = store.root / reference.relative_path
    magic, encoded = stored_path.read_bytes().split(b"\n", maxsplit=1)
    envelope = json.loads(encoded)
    envelope["ignored"] = "malleable"
    stored_path.write_bytes(magic + b"\n" + json.dumps(envelope).encode())

    with pytest.raises(IntegrityError, match="fields"):
        store.read(reference)


def test_external_key_file_policy_and_environment_loading(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "keys"
    outside.mkdir()
    key_file = outside / "raw.key"
    key_file.write_text(base64.b64encode(os.urandom(32)).decode("ascii") + "\n", encoding="ascii")

    loaded = RawEncryptionKey.from_environment(
        workspace_root=workspace,
        environ={"ACLAB_RAW_KEY_FILE": str(key_file)},
    )

    assert len(loaded.value) == 32
    inside = workspace / "raw.key"
    inside.write_text(key_file.read_text(encoding="ascii"), encoding="ascii")
    with pytest.raises(RawPayloadKeyError, match="outside"):
        RawEncryptionKey.from_file(inside, workspace_root=workspace)
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    repository_key = repository / "raw.key"
    repository_key.write_text(key_file.read_text(encoding="ascii"), encoding="ascii")
    with pytest.raises(RawPayloadKeyError, match="Git repository"):
        RawEncryptionKey.from_file(repository_key, workspace_root=workspace)
    with pytest.raises(RawPayloadKeyError, match="required"):
        RawEncryptionKey.from_environment(workspace_root=workspace, environ={})


def test_immutable_v1_plaintext_requires_explicit_compatibility_adapter(tmp_path: Path) -> None:
    root = tmp_path / "raw-evidence"
    compatibility = LocalRawPayloadStore.legacy_v1_synthetic(root)
    payload = b"immutable legacy synthetic fixture"
    reference = compatibility.reference_for(payload, media_type="text/plain")
    path = compatibility.root / reference.relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)

    assert compatibility.read(reference) == payload
    with pytest.raises(IntegrityError, match="not permitted"):
        LocalRawPayloadStore(root, encryption_key=_key()).read(reference)
