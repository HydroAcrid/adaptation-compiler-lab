"""Encrypted semantic cache with a raw-free local index."""

from __future__ import annotations

import json
import os
from pathlib import Path

from adaptation_compiler_lab.instruction_environment.semantic import (
    SemanticAnalysisEnvelopeV1,
    SemanticRelationEnvelopeV1,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.serialization import canonical_json


class EncryptedInstructionCache:
    """Persist semantic outputs encrypted while exposing only content-addressed metadata."""

    def __init__(self, state_root: Path, raw_store: LocalRawPayloadStore) -> None:
        self._root = state_root.expanduser().resolve() / "instruction-environment"
        self._index_path = self._root / "semantic-cache-index.json"
        self._raw_store = raw_store

    def get(self, cache_key: str) -> SemanticAnalysisEnvelopeV1 | None:
        index = self._load_index()
        raw = index.get(cache_key)
        if not isinstance(raw, dict):
            return None
        try:
            reference = RawPayloadRef(
                sha256=str(raw["sha256"]),
                size_bytes=int(raw["size_bytes"]),
                media_type=str(raw["media_type"]),
                relative_path=str(raw["relative_path"]),
            )
            envelope = SemanticAnalysisEnvelopeV1.model_validate_json(
                self._raw_store.read(reference), strict=True
            )
        except (KeyError, OSError, TypeError, ValueError):
            return None
        return envelope if envelope.cache_key == cache_key else None

    def put(self, envelope: SemanticAnalysisEnvelopeV1) -> None:
        payload = canonical_json(envelope).encode("utf-8")
        reference = self._raw_store.put(
            payload,
            media_type="application/vnd.temper.instruction-semantic-cache+json",
        )
        index = self._load_index()
        index[str(envelope.cache_key)] = {
            "media_type": reference.media_type,
            "relative_path": reference.relative_path,
            "sha256": reference.sha256,
            "size_bytes": reference.size_bytes,
        }
        self._write_index(index)

    def get_relations(self, cache_key: str) -> SemanticRelationEnvelopeV1 | None:
        reference = self._reference(cache_key)
        if reference is None:
            return None
        try:
            envelope = SemanticRelationEnvelopeV1.model_validate_json(
                self._raw_store.read(reference), strict=True
            )
        except (OSError, ValueError):
            return None
        return envelope if envelope.cache_key == cache_key else None

    def put_relations(self, envelope: SemanticRelationEnvelopeV1) -> None:
        payload = canonical_json(envelope).encode("utf-8")
        reference = self._raw_store.put(
            payload,
            media_type="application/vnd.temper.instruction-relation-cache+json",
        )
        index = self._load_index()
        index[str(envelope.cache_key)] = {
            "media_type": reference.media_type,
            "relative_path": reference.relative_path,
            "sha256": reference.sha256,
            "size_bytes": reference.size_bytes,
        }
        self._write_index(index)

    def purge(self) -> None:
        if not self._index_path.exists():
            return
        index = self._load_index()
        for raw in index.values():
            if not isinstance(raw, dict):
                continue
            try:
                self._raw_store.discard(
                    RawPayloadRef(
                        sha256=str(raw["sha256"]),
                        size_bytes=int(raw["size_bytes"]),
                        media_type=str(raw["media_type"]),
                        relative_path=str(raw["relative_path"]),
                    )
                )
            except (KeyError, OSError, TypeError, ValueError):
                continue
        self._index_path.unlink(missing_ok=True)

    def _load_index(self) -> dict[str, object]:
        if not self._index_path.exists():
            return {}
        try:
            value = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _reference(self, cache_key: str) -> RawPayloadRef | None:
        raw = self._load_index().get(cache_key)
        if not isinstance(raw, dict):
            return None
        try:
            return RawPayloadRef(
                sha256=str(raw["sha256"]),
                size_bytes=int(raw["size_bytes"]),
                media_type=str(raw["media_type"]),
                relative_path=str(raw["relative_path"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _write_index(self, value: dict[str, object]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        temporary = self._index_path.with_suffix(".tmp")
        temporary.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
        # Windows rejects ``fsync`` on a read-only CRT descriptor. Reopen the fully written
        # temporary index as writable so the durability barrier has the same behavior on both
        # supported desktop platforms.
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, self._index_path)
