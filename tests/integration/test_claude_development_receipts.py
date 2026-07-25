from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from adaptation_compiler_lab.benchmark.claude_development import (
    ClaudeDevelopmentCompletionReceipt,
    ClaudeDevelopmentEncryptedPayloadRef,
    ClaudeDevelopmentProgressReceipt,
)
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.claude_code import serialize_target_trace
from adaptation_compiler_lab.serialization import canonical_json

DIGEST = "sha256:" + "a" * 64


def test_fake_target_trace_persists_through_progress_and_completion(tmp_path: Path) -> None:
    events: tuple[JsonObject, ...] = (
        {"type": "system", "subtype": "init", "model": "claude-haiku-4-5-20251001"},
        {
            "type": "result",
            "result": "synthetic completed output",
            "total_cost_usd": 0.01,
        },
    )
    trace_bytes = serialize_target_trace(events)
    store = LocalRawPayloadStore(
        tmp_path / "encrypted",
        encryption_key=RawEncryptionKey(b"k" * 32),
    )
    raw_ref = store.put(
        trace_bytes,
        media_type="application/vnd.adaptation-compiler-lab.synthetic-claude-run+json",
    )
    encrypted_ref = ClaudeDevelopmentEncryptedPayloadRef(
        sha256=raw_ref.sha256,
        size_bytes=raw_ref.size_bytes,
        media_type=raw_ref.media_type,
        relative_path=raw_ref.relative_path,
    )
    progress = ClaudeDevelopmentProgressReceipt(
        run_id="run-111111111111",
        task_id="claude-development-communication",
        blind_condition_id="cond-111111111111111111111111",
        blind_output_id="output-111111111111111111111111",
        bundle_ref=encrypted_ref,
        completed=1,
        valid=True,
    )
    now = datetime(2026, 7, 24, tzinfo=UTC)
    completion = ClaudeDevelopmentCompletionReceipt(
        blind_packet_digest=DIGEST,
        blind_report_digest=DIGEST,
        blind_report_ref=encrypted_ref,
        completed_at=now,
        private_plan_ref=encrypted_ref,
        raw_retention_deadline=now + timedelta(days=30),
        total_cost_usd=0.01,
    )

    reloaded_progress = ClaudeDevelopmentProgressReceipt.model_validate_json(
        canonical_json(progress)
    )
    reloaded_completion = ClaudeDevelopmentCompletionReceipt.model_validate_json(
        canonical_json(completion)
    )

    assert reloaded_progress.bundle_ref == encrypted_ref
    assert reloaded_completion.private_plan_ref == encrypted_ref
    assert store.read(raw_ref) == trace_bytes
