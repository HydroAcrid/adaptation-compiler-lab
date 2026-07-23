"""Deterministic comparator construction and four-condition freeze gates."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Annotated, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.domain.base import (
    ActorRef,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.enums import ActorKind, SourceClass
from adaptation_compiler_lab.domain.references import EvidenceRef
from adaptation_compiler_lab.domain.values import refs_are_sorted_unique, strings_are_sorted_unique
from adaptation_compiler_lab.sanitization import assert_condition_material_safe, assert_export_safe
from adaptation_compiler_lab.serialization import canonical_digest

TOKEN_CEILING = 3_000
UTF8_BYTE_CEILING = 12_000


class ConditionMaterialError(ValueError):
    """Condition material cannot be frozen without violating the protocol."""


class TokenCounter(Protocol):
    """Pinned target-model token counter supplied by the sealed operator."""

    @property
    def counter_id(self) -> str:
        """Return the immutable tokenizer/counting endpoint identity."""

    def count(self, text: str) -> int:
        """Count target-visible tokens for exact UTF-8 text."""


class ApprovedFeedbackItem(FrozenModel):
    """One verbatim, explicitly approved user-feedback item."""

    evidence_ref: EvidenceRef
    observed_at: UtcDateTime
    source_class: Literal[SourceClass.EXPLICIT_USER_FEEDBACK] = SourceClass.EXPLICIT_USER_FEEDBACK
    approved: Literal[True] = True
    text: NonEmptyStr


class OrdinaryMemoryMaterial(FrozenModel):
    """Deterministic comparator output; it contains no inferred procedure."""

    renderer_version: Literal["1.0.0"] = "1.0.0"
    text: NonEmptyStr
    source_evidence_refs: Annotated[tuple[EvidenceRef, ...], Field(min_length=1)]
    exact_item_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=1)]

    @field_validator("source_evidence_refs")
    @classmethod
    def evidence_is_canonical(
        cls,
        value: tuple[EvidenceRef, ...],
    ) -> tuple[EvidenceRef, ...]:
        if not refs_are_sorted_unique(value):
            raise ValueError("ordinary-memory evidence references must be sorted and unique")
        return value

    @field_validator("exact_item_digests")
    @classmethod
    def item_digests_are_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("ordinary-memory item digests must be unique")
        return value


class StrongProfileSubmission(FrozenModel):
    """Independent-human comparator submission and separation attestation."""

    profile_id: Identifier
    author: ActorRef
    corpus_digest: Sha256Digest
    started_at: UtcDateTime
    completed_at: UtcDateTime
    held_out_access: Literal[False] = False
    author_may_score_results: Literal[False] = False
    text: NonEmptyStr

    @model_validator(mode="after")
    def author_and_window_match_protocol(self) -> StrongProfileSubmission:
        if self.author.kind is not ActorKind.HUMAN_REVIEWER:
            raise ValueError("strong profile author must be an independent human reviewer")
        if self.completed_at < self.started_at:
            raise ValueError("strong profile completion cannot precede its start")
        if self.completed_at - self.started_at > timedelta(minutes=90):
            raise ValueError("strong profile authoring exceeded 90 minutes")
        return self


class ConditionConstructionInput(FrozenModel):
    """Equal-information source set bound into every non-base condition."""

    corpus_digest: Sha256Digest
    source_task_ids: Annotated[tuple[Identifier, ...], Field(min_length=8, max_length=8)]
    source_evaluation_case_ids: tuple[Identifier, ...]

    @field_validator("source_task_ids", "source_evaluation_case_ids")
    @classmethod
    def ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("condition construction IDs must be sorted and unique")
        return value


class FrozenConditionMaterial(FrozenModel):
    """Exact target-visible text and measurements for one condition."""

    condition: BenchmarkCondition
    text: str
    content_digest: Sha256Digest
    utf8_bytes: int = Field(ge=0, le=UTF8_BYTE_CEILING)
    target_tokens: int = Field(ge=0, le=TOKEN_CEILING)
    token_counter_id: NonEmptyStr
    construction_input: ConditionConstructionInput | None
    frozen_at: UtcDateTime
    padded: Literal[False] = False

    @model_validator(mode="after")
    def content_and_condition_match(self) -> FrozenConditionMaterial:
        raw = self.text.encode("utf-8")
        expected = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        if self.content_digest != expected or self.utf8_bytes != len(raw):
            raise ValueError("condition material digest or byte count mismatch")
        if self.condition is BenchmarkCondition.BASE:
            if self.text or self.target_tokens or self.construction_input is not None:
                raise ValueError("base condition must contain no adaptation material")
        elif not self.text or self.target_tokens == 0 or self.construction_input is None:
            raise ValueError("source-derived condition requires material and construction inputs")
        return self


class FrozenConditionSet(FrozenModel):
    """Exactly four condition materials with equal construction access."""

    materials: Annotated[tuple[FrozenConditionMaterial, ...], Field(min_length=4, max_length=4)]
    wrapper_digest: Sha256Digest
    frozen_at: UtcDateTime

    @model_validator(mode="after")
    def conditions_are_complete_and_equal_information(self) -> FrozenConditionSet:
        expected = tuple(BenchmarkCondition)
        observed = tuple(material.condition for material in self.materials)
        if observed != expected:
            raise ValueError("condition materials must contain the four frozen conditions in order")
        if any(material.frozen_at != self.frozen_at for material in self.materials):
            raise ValueError("all condition materials must share one freeze timestamp")
        source_inputs = {
            material.construction_input
            for material in self.materials
            if material.condition is not BenchmarkCondition.BASE
        }
        if len(source_inputs) != 1:
            raise ValueError("all source-derived conditions require equal construction access")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def render_ordinary_memory(
    items: tuple[ApprovedFeedbackItem, ...],
) -> OrdinaryMemoryMaterial:
    """Render approved feedback chronologically with exact digest deduplication."""

    if not items:
        raise ConditionMaterialError("ordinary memory requires approved explicit feedback")
    ordered = sorted(
        items,
        key=lambda item: (
            item.observed_at,
            item.evidence_ref.record_id,
            item.evidence_ref.record_version,
        ),
    )
    selected: list[ApprovedFeedbackItem] = []
    item_digests: list[Sha256Digest] = []
    seen: set[Sha256Digest] = set()
    for item in ordered:
        digest = canonical_digest(
            {
                "source_class": item.source_class.value,
                "text": item.text,
            }
        )
        if digest in seen:
            continue
        seen.add(digest)
        selected.append(item)
        item_digests.append(digest)
    text = "# Approved user feedback\n\n" + "\n".join(f"- {item.text}" for item in selected)
    assert_export_safe(text, label="ordinary memory")
    evidence_refs = tuple(
        sorted(
            {item.evidence_ref for item in selected},
            key=lambda item: (
                item.record_type.value,
                item.record_id,
                item.record_version,
                item.content_digest or "",
            ),
        )
    )
    return OrdinaryMemoryMaterial(
        text=text,
        source_evidence_refs=evidence_refs,
        exact_item_digests=tuple(item_digests),
    )


def freeze_condition_set(
    *,
    ordinary_memory: OrdinaryMemoryMaterial,
    strong_profile: StrongProfileSubmission,
    compiled_adaptation: str,
    construction_input: ConditionConstructionInput,
    wrapper_digest: Sha256Digest,
    frozen_at: UtcDateTime,
    token_counter: TokenCounter,
) -> FrozenConditionSet:
    """Measure, scan, and freeze the exact four target-visible materials."""

    if strong_profile.corpus_digest != construction_input.corpus_digest:
        raise ConditionMaterialError("strong profile used a different construction corpus")
    texts = {
        BenchmarkCondition.BASE: "",
        BenchmarkCondition.ORDINARY_MEMORY: ordinary_memory.text,
        BenchmarkCondition.STRONG_STATIC_PROFILE: strong_profile.text,
        BenchmarkCondition.COMPILED_ADAPTATION: compiled_adaptation,
    }
    materials: list[FrozenConditionMaterial] = []
    for condition in BenchmarkCondition:
        text = texts[condition]
        if condition is not BenchmarkCondition.BASE:
            assert_condition_material_safe(text)
        raw = text.encode("utf-8")
        token_count = token_counter.count(text) if text else 0
        if token_count < 0:
            raise ConditionMaterialError("token counter returned a negative value")
        if token_count > TOKEN_CEILING:
            raise ConditionMaterialError(f"{condition.value} exceeds the 3,000-token ceiling")
        if len(raw) > UTF8_BYTE_CEILING:
            raise ConditionMaterialError(f"{condition.value} exceeds the 12,000-byte ceiling")
        materials.append(
            FrozenConditionMaterial(
                condition=condition,
                text=text,
                content_digest=f"sha256:{hashlib.sha256(raw).hexdigest()}",
                utf8_bytes=len(raw),
                target_tokens=token_count,
                token_counter_id=token_counter.counter_id,
                construction_input=(
                    None if condition is BenchmarkCondition.BASE else construction_input
                ),
                frozen_at=frozen_at,
            )
        )
    return FrozenConditionSet(
        materials=tuple(materials),
        wrapper_digest=wrapper_digest,
        frozen_at=frozen_at,
    )
