"""Comparator rendering, equal-information, and budget tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.materials import (
    ApprovedFeedbackItem,
    ConditionConstructionInput,
    ConditionMaterialError,
    StrongProfileSubmission,
    freeze_condition_set,
    render_ordinary_memory,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.domain import ActorKind, ActorRef, EvidenceRef

NOW = datetime(2026, 7, 23, 14, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


class WordCounter:
    counter_id = "synthetic-word-counter-1"

    def count(self, text: str) -> int:
        return len(text.split())


def _evidence(index: int) -> EvidenceRef:
    return EvidenceRef(
        record_id=f"evidence-{index}",
        record_version="1.0.0",
        content_digest=DIGEST,
    )


def _profile(*, text: str = "Use concise, evidence-backed responses.") -> StrongProfileSubmission:
    return StrongProfileSubmission(
        profile_id="profile-1",
        author=ActorRef(
            actor_id="independent-author",
            kind=ActorKind.HUMAN_REVIEWER,
        ),
        corpus_digest=DIGEST,
        started_at=NOW,
        completed_at=NOW + timedelta(minutes=30),
        text=text,
    )


def _inputs() -> ConditionConstructionInput:
    return ConditionConstructionInput(
        corpus_digest=DIGEST,
        source_task_ids=tuple(f"task-{index}" for index in range(8)),
        source_evaluation_case_ids=("eval-1",),
    )


def test_ordinary_memory_is_chronological_and_exact_deduplicated() -> None:
    memory = render_ordinary_memory(
        (
            ApprovedFeedbackItem(
                evidence_ref=_evidence(2),
                observed_at=NOW + timedelta(minutes=2),
                text="Second correction.",
            ),
            ApprovedFeedbackItem(
                evidence_ref=_evidence(1),
                observed_at=NOW,
                text="First correction.",
            ),
            ApprovedFeedbackItem(
                evidence_ref=_evidence(3),
                observed_at=NOW + timedelta(minutes=3),
                text="First correction.",
            ),
        )
    )

    assert memory.text.index("First correction.") < memory.text.index("Second correction.")
    assert memory.text.count("First correction.") == 1
    assert len(memory.exact_item_digests) == 2


def test_four_materials_freeze_without_padding() -> None:
    memory = render_ordinary_memory(
        (
            ApprovedFeedbackItem(
                evidence_ref=_evidence(1),
                observed_at=NOW,
                text="Ask before changing external state.",
            ),
        )
    )

    frozen = freeze_condition_set(
        ordinary_memory=memory,
        strong_profile=_profile(),
        compiled_adaptation="Apply the reviewed scoped procedure.",
        construction_input=_inputs(),
        wrapper_digest=DIGEST,
        frozen_at=NOW + timedelta(hours=2),
        token_counter=WordCounter(),
    )

    assert tuple(item.condition for item in frozen.materials) == tuple(BenchmarkCondition)
    assert frozen.materials[0].target_tokens == 0
    assert all(not item.padded for item in frozen.materials)
    assert len({item.construction_input for item in frozen.materials[1:]}) == 1


def test_budget_secret_and_profile_separation_fail_closed() -> None:
    memory = render_ordinary_memory(
        (
            ApprovedFeedbackItem(
                evidence_ref=_evidence(1),
                observed_at=NOW,
                text="Keep changes scoped.",
            ),
        )
    )
    with pytest.raises(ConditionMaterialError, match="12,000-byte"):
        freeze_condition_set(
            ordinary_memory=memory,
            strong_profile=_profile(),
            compiled_adaptation="x" * 12_001,
            construction_input=_inputs(),
            wrapper_digest=DIGEST,
            frozen_at=NOW + timedelta(hours=2),
            token_counter=WordCounter(),
        )
    with pytest.raises(ValueError, match="provider_token"):
        freeze_condition_set(
            ordinary_memory=memory,
            strong_profile=_profile(text="Use sk-" + "a" * 24),
            compiled_adaptation="Scoped adaptation.",
            construction_input=_inputs(),
            wrapper_digest=DIGEST,
            frozen_at=NOW + timedelta(hours=2),
            token_counter=WordCounter(),
        )
    with pytest.raises(ValidationError, match="90 minutes"):
        StrongProfileSubmission(
            profile_id="profile-1",
            author=ActorRef(
                actor_id="independent-author",
                kind=ActorKind.HUMAN_REVIEWER,
            ),
            corpus_digest=DIGEST,
            started_at=NOW,
            completed_at=NOW + timedelta(minutes=91),
            text="Profile.",
        )
