"""Exactly-eight consented source-corpus invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.corpus import (
    ConsentedCorpusManifest,
    CorpusTask,
    SourceFamilyAssignment,
)
from adaptation_compiler_lab.domain.references import CaptureReceiptRef, ConsentReceiptRef

NOW = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def _tasks() -> tuple[CorpusTask, ...]:
    return tuple(
        CorpusTask(
            task_id=f"task-{index}",
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


def _families() -> tuple[SourceFamilyAssignment, ...]:
    return tuple(
        SourceFamilyAssignment(
            family_id=f"family-{index}",
            evaluation_case_ids=(f"evaluation-{index}",),
        )
        for index in range(4)
    )


def test_exactly_eight_tasks_and_four_families_freeze() -> None:
    manifest = ConsentedCorpusManifest(
        corpus_id="corpus-1",
        source_runtime_version="0.145.0-alpha.30",
        source_schema_digest=DIGEST,
        construction_cutoff=NOW,
        frozen_at=NOW + timedelta(minutes=1),
        tasks=_tasks(),
        source_family_assignments=_families(),
    )

    assert len(manifest.tasks) == 8
    assert len(manifest.source_family_assignments) == 4
    assert manifest.content_digest.startswith("sha256:")


def test_too_few_families_or_post_cutoff_task_fails() -> None:
    duplicate_families = list(_families())
    duplicate_families[-1] = duplicate_families[-1].model_copy(update={"family_id": "family-2"})
    with pytest.raises(ValidationError, match="sorted and unique"):
        ConsentedCorpusManifest(
            corpus_id="corpus-1",
            source_runtime_version="0.145.0-alpha.30",
            source_schema_digest=DIGEST,
            construction_cutoff=NOW,
            frozen_at=NOW + timedelta(minutes=1),
            tasks=_tasks(),
            source_family_assignments=tuple(duplicate_families),
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
            source_family_assignments=_families(),
        )
