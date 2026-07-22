"""Deterministic, payload-free benchmark manifest serialization."""

from __future__ import annotations

import hashlib
import json

from adaptation_compiler_lab.benchmark.models import BenchmarkConfig


def canonical_benchmark_manifest(config: BenchmarkConfig) -> str:
    """Return stable JSON containing only registered metadata and opaque digests."""

    payload = config.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def benchmark_manifest_digest(config: BenchmarkConfig) -> str:
    """Digest the exact canonical manifest."""

    content = canonical_benchmark_manifest(config).encode("utf-8")
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
