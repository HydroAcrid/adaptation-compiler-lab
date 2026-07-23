"""Exactly-eight consented source-corpus invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.corpus import ConsentedCorpusManifest, CorpusTask
from adaptation_compiler_lab.domain.references import CaptureReceiptRef, ConsentReceiptRef

NOW = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def _tasks(*, families: int = 4) -> tuple[CorpusTask, ...]:
    return tuple(
        CorpusTask(
            task_id=f"task-{index}",
            source_family=f"family-{index % families}",
            created_at=NOW - timedelta(days=8 - index),
            updated_at=NOW - timedelta(days=7 - index),
            consent_ref=ConsentReceiptRef(
                object_id=f"consent-{index}",
                content_digest=DIGEST,
            ),
            capture_ref=CaptureReceiptRef(
                object_id=f"capture-{index}",
                content_digest=DIGEST,
            ),
            payload_digest=DIGEST,
        )
        for index in range(8)
    )


def test_exactly_eight_tasks_and_four_families_freeze() -> None:
    manifest = ConsentedCorpusManifest(
        corpus_id="corpus-1",
        source_runtime_version="0.145.0-alpha.30",
        source_schema_digest=DIGEST,
        construction_cutoff=NOW,
        frozen_at=NOW + timedelta(minutes=1),
        tasks=_tasks(),
    )

    assert len(manifest.tasks) == 8
    assert len({item.source_family for item in manifest.tasks}) == 4
    assert manifest.content_digest.startswith("sha256:")


def test_too_few_families_or_post_cutoff_task_fails() -> None:
    with pytest.raises(ValidationError, match="four task families"):
        ConsentedCorpusManifest(
            corpus_id="corpus-1",
            source_runtime_version="0.145.0-alpha.30",
            source_schema_digest=DIGEST,
            construction_cutoff=NOW,
            frozen_at=NOW + timedelta(minutes=1),
            tasks=_tasks(families=3),
        )

    tasks = list(_tasks())
    tasks[-1] = tasks[-1].model_copy(
        update={
            "created_at": NOW + timedelta(seconds=1),
            "updated_at": NOW + timedelta(seconds=2),
        }
    )
    with pytest.raises(ValidationError, match="after the construction cutoff"):
        ConsentedCorpusManifest(
            corpus_id="corpus-1",
            source_runtime_version="0.145.0-alpha.30",
            source_schema_digest=DIGEST,
            construction_cutoff=NOW,
            frozen_at=NOW + timedelta(minutes=1),
            tasks=tuple(tasks),
        )
