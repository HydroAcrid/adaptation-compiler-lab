"""Typed values crossing the source, target-runner, and scorer ports."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique

type JsonPrimitive = None | bool | int | float | str
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

BlindRunId = Annotated[
    str,
    StringConstraints(pattern=r"^run-[0-9a-f]{12,64}$"),
]


class TerminalTurnStatus(StrEnum):
    """Terminal states accepted as completed source work."""

    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class SourceTurnDescriptor(FrozenModel):
    """Minimal turn metadata retained beside an encrypted raw snapshot."""

    turn_id: Identifier
    status: TerminalTurnStatus
    item_count: int = Field(ge=0)


class SourceTaskSummary(FrozenModel):
    """Privacy-minimized source inventory item.

    The source preview, working-directory path, and thread body are deliberately absent. A local
    caller may display the optional user-assigned name, but it must not persist an inventory as
    research evidence without consent.
    """

    task_id: Identifier
    created_at_epoch_seconds: int = Field(ge=0)
    updated_at_epoch_seconds: int = Field(ge=0)
    cli_version: NonEmptyStr
    status: Literal["idle", "notLoaded"]
    source_digest: Sha256Digest
    cwd_digest: Sha256Digest
    display_name: NonEmptyStr | None = None

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> SourceTaskSummary:
        if self.updated_at_epoch_seconds < self.created_at_epoch_seconds:
            raise ValueError("source task cannot be updated before it was created")
        return self


class SourceTaskPage(FrozenModel):
    """One opaque source inventory page."""

    tasks: tuple[SourceTaskSummary, ...]
    next_cursor: str | None = None

    @field_validator("tasks")
    @classmethod
    def task_ids_are_unique(
        cls,
        value: tuple[SourceTaskSummary, ...],
    ) -> tuple[SourceTaskSummary, ...]:
        task_ids = [item.task_id for item in value]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("source inventory page contains duplicate task IDs")
        return value


class SourceTaskSnapshot(FrozenModel):
    """Canonical full-thread payload returned only after a separately authorized read.

    ``raw_payload`` remains untrusted context. It does not acquire user authority merely because
    it came from a source agent, repository, tool call, or retrieved document.
    """

    task_id: Identifier
    source_version: NonEmptyStr
    source_schema_digest: Sha256Digest
    raw_payload: bytes = Field(min_length=1, repr=False)
    payload_digest: Sha256Digest
    turns: Annotated[tuple[SourceTurnDescriptor, ...], Field(min_length=1)]
    untrusted_context: Literal[True] = True

    @model_validator(mode="after")
    def payload_digest_matches(self) -> SourceTaskSnapshot:
        digest = f"sha256:{hashlib.sha256(self.raw_payload).hexdigest()}"
        if digest != self.payload_digest:
            raise ValueError("source snapshot payload digest mismatch")
        if len({item.turn_id for item in self.turns}) != len(self.turns):
            raise ValueError("source snapshot contains duplicate turn IDs")
        return self


class TargetRunRequest(FrozenModel):
    """One isolated target invocation with a single blinded condition file."""

    run_id: BlindRunId
    workspace_root: Path
    prompt: NonEmptyStr
    condition_file: Path
    condition_digest: Sha256Digest
    allowed_bash_commands: tuple[NonEmptyStr, ...] = ()
    max_seconds: int = Field(gt=0, le=1800)
    max_turns: int = Field(gt=0, le=40)
    max_usd: float = Field(gt=0.0, le=5.0, allow_inf_nan=False)
    model_id: Literal["claude-sonnet-5", "claude-haiku-4-5-20251001"] = "claude-sonnet-5"

    @field_validator("allowed_bash_commands")
    @classmethod
    def bash_rules_are_deterministic(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("approved Bash commands must be sorted and unique")
        if any("\n" in item or "\r" in item or "\x00" in item for item in value):
            raise ValueError("approved Bash commands cannot contain control-line separators")
        return value


class TargetRunResult(FrozenModel):
    """Structured target trace returned to the sealed pilot coordinator."""

    run_id: BlindRunId
    runner_version: NonEmptyStr
    model_id: NonEmptyStr
    condition_digest: Sha256Digest
    command_digest: Sha256Digest
    started_at: UtcDateTime
    finished_at: UtcDateTime
    exit_code: int | None
    timed_out: bool
    events: tuple[JsonObject, ...]
    stderr: str
    config_destroyed: bool

    @model_validator(mode="after")
    def terminal_state_is_coherent(self) -> TargetRunResult:
        if self.finished_at < self.started_at:
            raise ValueError("target run cannot finish before it starts")
        if self.timed_out and self.exit_code is not None:
            raise ValueError("a timed-out run cannot claim a normal exit code")
        if not self.timed_out and self.exit_code is None:
            raise ValueError("a completed run requires an exit code")
        return self


class ScoringRequest(FrozenModel):
    """Condition-blind scorer input.

    The port has no condition label field. Metadata keys that could encode a condition identity are
    rejected so a caller cannot silently smuggle the label through an extension map.
    """

    trial_id: Identifier
    blind_task_id: Identifier
    blind_run_id: BlindRunId
    diff_payload: bytes
    independent_test_payload: bytes
    rubric_payload: bytes = Field(min_length=1)
    allowed_metadata: JsonObject = Field(default_factory=dict)

    @field_validator("allowed_metadata")
    @classmethod
    def metadata_is_condition_blind(cls, value: JsonObject) -> JsonObject:
        forbidden_fragments = ("condition", "bundle", "adaptation", "profile", "memory")
        for key in value:
            folded = key.casefold()
            if any(fragment in folded for fragment in forbidden_fragments):
                raise ValueError("scorer metadata cannot encode condition identity")
        return value


class ScoringResult(FrozenModel):
    """Independent scorer output; weighting and adjudication remain external."""

    trial_id: Identifier
    automated_correctness: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    requirement_coverage: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    change_discipline: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    guardrails: JsonObject = Field(default_factory=dict)
