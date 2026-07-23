"""Strict plaintext schema used only inside the sealed software-custody context."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.models import (
    BenchmarkCondition,
    BlindTaskId,
    TaskStratum,
)
from adaptation_compiler_lab.benchmark.randomization import SoftwareCustodyPlan
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest


class HeldOutFile(FrozenModel):
    """One UTF-8 fixture or independent-test file inside a disposable task tree."""

    relative_path: NonEmptyStr
    content: str

    @field_validator("relative_path")
    @classmethod
    def path_is_relative_and_canonical(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or value != path.as_posix()
            or value.startswith(".git/")
            or value == ".git"
        ):
            raise ValueError("held-out file path must be safe POSIX-relative content")
        return value


class HeldOutRubric(FrozenModel):
    """Task-specific rubric shown without condition labels during scoring."""

    objective_requirements: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    preference_requirements: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    forbidden_changes: tuple[NonEmptyStr, ...] = ()

    @field_validator(
        "objective_requirements",
        "preference_requirements",
        "forbidden_changes",
    )
    @classmethod
    def rubric_items_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("held-out rubric items must be unique")
        return value


class HeldOutTaskDraft(FrozenModel):
    """Hidden task authored before the software custodian assigns blind IDs."""

    task_key: Identifier
    stratum: TaskStratum
    prompt: NonEmptyStr
    fixture_files: Annotated[tuple[HeldOutFile, ...], Field(min_length=1)]
    independent_test_files: Annotated[tuple[HeldOutFile, ...], Field(min_length=1)]
    test_command: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    allowed_bash_commands: tuple[NonEmptyStr, ...]
    rubric: HeldOutRubric
    network_required: Literal[False] = False
    created_at: UtcDateTime

    @field_validator("fixture_files", "independent_test_files")
    @classmethod
    def file_paths_are_unique(
        cls,
        value: tuple[HeldOutFile, ...],
    ) -> tuple[HeldOutFile, ...]:
        paths = tuple(item.relative_path for item in value)
        if len(paths) != len(set(paths)):
            raise ValueError("held-out file paths must be unique within their collection")
        return value

    @field_validator("allowed_bash_commands")
    @classmethod
    def bash_commands_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("held-out Bash commands must be sorted and unique")
        if any("\n" in item or "\r" in item or "\x00" in item for item in value):
            raise ValueError("held-out Bash commands cannot contain line separators")
        return value

    @model_validator(mode="after")
    def fixture_and_tests_are_separate(self) -> HeldOutTaskDraft:
        fixture_paths = {item.relative_path for item in self.fixture_files}
        test_paths = {item.relative_path for item in self.independent_test_files}
        if fixture_paths & test_paths:
            raise ValueError("independent tests cannot overwrite target-visible fixture files")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class HeldOutTaskPayload(HeldOutTaskDraft):
    """One finalized hidden task carrying its seed-derived blind task ID."""

    blind_task_id: BlindTaskId


class FrozenConditionPayload(FrozenModel):
    """Exact target-visible material copied into custody after construction freeze."""

    condition: BenchmarkCondition
    material_digest: Sha256Digest
    text: str
    target_tokens: int = Field(ge=0, le=3000)
    utf8_bytes: int = Field(ge=0, le=12000)

    @model_validator(mode="after")
    def payload_is_exact(self) -> FrozenConditionPayload:
        raw = self.text.encode("utf-8")
        if len(raw) != self.utf8_bytes:
            raise ValueError("condition UTF-8 byte count does not match text")
        if (self.condition is BenchmarkCondition.BASE) != (
            not self.text and self.target_tokens == 0 and self.utf8_bytes == 0
        ):
            raise ValueError("only the base condition may be empty")
        expected = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        if expected != self.material_digest:
            raise ValueError("condition material digest does not match text")
        return self


class SealedHeldOutPlanBundle(FrozenModel):
    """Hidden task payloads and mapping sealed before condition construction."""

    bundle_version: Literal["1.0.0"] = "1.0.0"
    benchmark_id: Identifier
    construction_cutoff: UtcDateTime
    held_out_tasks: Annotated[tuple[HeldOutTaskPayload, ...], Field(min_length=4, max_length=4)]
    software_custody_plan: SoftwareCustodyPlan
    held_out_author_packet_digest: Sha256Digest
    held_out_author_receipt_digest: Sha256Digest
    sealed_at: UtcDateTime

    @model_validator(mode="after")
    def bundle_is_complete_and_cross_bound(self) -> SealedHeldOutPlanBundle:
        if tuple(item.stratum for item in self.held_out_tasks) != (
            TaskStratum.DIRECT_TRANSFER,
            TaskStratum.FAILURE_RECURRENCE,
            TaskStratum.COMPOSITIONAL,
            TaskStratum.NEUTRAL_CONTROL,
        ):
            raise ValueError("held-out tasks must contain the four frozen strata in order")
        task_ids = tuple(item.blind_task_id for item in self.held_out_tasks)
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("held-out blind task IDs must be unique")
        plan_task_ids = {item.blind_task_id for item in self.software_custody_plan.trial_order}
        if plan_task_ids != set(task_ids):
            raise ValueError("software custody plan and held-out task IDs differ")
        if self.software_custody_plan.benchmark_id != self.benchmark_id:
            raise ValueError("software custody plan crossed the benchmark boundary")
        if self.software_custody_plan.construction_cutoff != self.construction_cutoff:
            raise ValueError("software custody plan crossed the construction cutoff")
        if self.sealed_at < self.software_custody_plan.created_at:
            raise ValueError("held-out bundle cannot seal before its custody plan exists")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SealedInternalPilotBundle(FrozenModel):
    """Complete secret study bundle encrypted outside construction and Git."""

    bundle_version: Literal["1.0.0"] = "1.0.0"
    benchmark_id: Identifier
    construction_cutoff: UtcDateTime
    source_corpus_digest: Sha256Digest
    held_out_tasks: Annotated[tuple[HeldOutTaskPayload, ...], Field(min_length=4, max_length=4)]
    condition_materials: Annotated[
        tuple[FrozenConditionPayload, ...],
        Field(min_length=4, max_length=4),
    ]
    software_custody_plan: SoftwareCustodyPlan
    frozen_at: UtcDateTime

    @model_validator(mode="after")
    def bundle_is_complete_and_cross_bound(self) -> SealedInternalPilotBundle:
        if tuple(item.stratum for item in self.held_out_tasks) != (
            TaskStratum.DIRECT_TRANSFER,
            TaskStratum.FAILURE_RECURRENCE,
            TaskStratum.COMPOSITIONAL,
            TaskStratum.NEUTRAL_CONTROL,
        ):
            raise ValueError("held-out tasks must contain the four frozen strata in order")
        task_ids = tuple(item.blind_task_id for item in self.held_out_tasks)
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("held-out blind task IDs must be unique")
        plan_task_ids = {item.blind_task_id for item in self.software_custody_plan.trial_order}
        if plan_task_ids != set(task_ids):
            raise ValueError("software custody plan and held-out task IDs differ")
        if tuple(item.condition for item in self.condition_materials) != tuple(BenchmarkCondition):
            raise ValueError("sealed bundle must contain the four conditions in order")
        if self.software_custody_plan.benchmark_id != self.benchmark_id:
            raise ValueError("software custody plan crossed the benchmark boundary")
        if self.software_custody_plan.construction_cutoff != self.construction_cutoff:
            raise ValueError("software custody plan crossed the construction cutoff")
        if self.frozen_at <= self.construction_cutoff:
            raise ValueError("sealed bundle must freeze after construction cutoff")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
