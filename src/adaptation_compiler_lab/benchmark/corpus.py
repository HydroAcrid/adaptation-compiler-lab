"""Payload-free eligibility manifest for the exactly eight-task source corpus."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.references import CaptureReceiptRef, ConsentReceiptRef
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest


class CorpusTask(FrozenModel):
    """One consented completed task represented without payload text or paths."""

    task_id: Identifier
    created_at: UtcDateTime
    updated_at: UtcDateTime
    consent_ref: ConsentReceiptRef
    capture_ref: CaptureReceiptRef
    payload_digest: Sha256Digest

    @model_validator(mode="after")
    def source_timestamps_are_ordered(self) -> CorpusTask:
        if self.updated_at < self.created_at:
            raise ValueError("corpus task update cannot precede creation")
        return self


class SourceFamilyAssignment(FrozenModel):
    """Owner-confirmed behavioral family linked to reviewed evaluation cases."""

    family_id: Identifier
    evaluation_case_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]

    @field_validator("evaluation_case_ids")
    @classmethod
    def evaluation_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("source-family evaluation IDs must be sorted and unique")
        return value


class ConsentedCorpusManifest(FrozenModel):
    """Frozen, digestible source-corpus identity with no raw source content."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    corpus_id: Identifier
    source_system: Literal["codex_app_server"] = "codex_app_server"
    source_runtime_version: NonEmptyStr
    source_schema_digest: Sha256Digest
    construction_cutoff: UtcDateTime
    frozen_at: UtcDateTime
    tasks: Annotated[tuple[CorpusTask, ...], Field(min_length=8, max_length=8)]
    source_family_assignments: Annotated[
        tuple[SourceFamilyAssignment, ...],
        Field(min_length=4, max_length=4),
    ]
    raw_payload_location: Literal["encrypted_external_local_store"] = (
        "encrypted_external_local_store"
    )
    remote_raw_storage: Literal[False] = False
    public_release: Literal[False] = False

    @field_validator("tasks")
    @classmethod
    def tasks_are_sorted_unique(
        cls,
        value: tuple[CorpusTask, ...],
    ) -> tuple[CorpusTask, ...]:
        task_ids = tuple(item.task_id for item in value)
        if not strings_are_sorted_unique(task_ids):
            raise ValueError("corpus tasks must be sorted by unique task ID")
        consent_ids = tuple(item.consent_ref.object_id for item in value)
        capture_ids = tuple(item.capture_ref.object_id for item in value)
        if len(consent_ids) != len(set(consent_ids)):
            raise ValueError("every source task requires its own consent receipt")
        if len(capture_ids) != len(set(capture_ids)):
            raise ValueError("every source task requires its own capture receipt")
        return value

    @model_validator(mode="after")
    def corpus_is_eligible_and_frozen(self) -> ConsentedCorpusManifest:
        if self.frozen_at <= self.construction_cutoff:
            raise ValueError("corpus freeze must follow the construction cutoff")
        if any(task.created_at > self.construction_cutoff for task in self.tasks):
            raise ValueError("corpus contains a task created after the construction cutoff")
        family_ids = tuple(item.family_id for item in self.source_family_assignments)
        if not strings_are_sorted_unique(family_ids):
            raise ValueError("source-family assignments must be sorted and unique")
        evaluation_ids = tuple(
            evaluation_id
            for item in self.source_family_assignments
            for evaluation_id in item.evaluation_case_ids
        )
        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("an evaluation case cannot belong to multiple source families")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        """Canonical payload-free identity used by condition builders."""

        return canonical_digest(self)
