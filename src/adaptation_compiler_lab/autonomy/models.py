"""Inferred habits are evidence-backed hypotheses, not invented user instructions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.autonomy.styles import StyleKey, style_contract
from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.governance.models import SignatureEnvelope
from adaptation_compiler_lab.serialization import canonical_digest


class StyleCategory(StrEnum):
    COMMUNICATION_DETAIL = "communication_detail"
    PRESENTATION_STYLE = "presentation_style"
    SUGGESTION_STYLE = "suggestion_style"


class HabitState(StrEnum):
    PROVISIONAL = "provisional"
    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class InputOrigin(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    DELEGATED = "delegated"
    COPIED = "copied"
    INJECTED = "injected"
    UNKNOWN = "unknown"


class TaskClass(StrEnum):
    PROGRESS_UPDATE = "progress_update"
    SUMMARY = "summary"
    PRESENTATION = "presentation"
    SUGGESTIONS = "suggestions"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("autonomy timestamps must include a timezone")
    return value


class LearningGrantV1(FrozenModel):
    grant_version: Literal["1.0.0"] = "1.0.0"
    grant_id: Identifier
    subject_id: Identifier
    project_ids: tuple[Identifier, ...] = Field(min_length=1)
    source_clients: tuple[NonEmptyStr, ...] = Field(min_length=1)
    categories: tuple[StyleCategory, ...] = Field(min_length=1)
    destination: NonEmptyStr
    issued_at: datetime
    permission_duration: Literal["until_disabled"] = "until_disabled"
    raw_retention_days: Literal[30] = 30
    automatic_publication: bool = True

    _issued_aware = field_validator("issued_at")(_aware)

    @field_validator("project_ids", "source_clients", "categories")
    @classmethod
    def unique_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or tuple(sorted(set(value))) != value:
            raise ValueError("grant selections must be nonempty, sorted, and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SignedLearningGrantV1(FrozenModel):
    grant: LearningGrantV1
    signature: SignatureEnvelope


class RuntimeLeaseV1(FrozenModel):
    lease_version: Literal["1.0.0"] = "1.0.0"
    grant_digest: Sha256Digest
    issued_at: datetime
    expires_at: datetime
    signature: SignatureEnvelope

    _lease_aware = field_validator("issued_at", "expires_at")(_aware)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        duration = self.expires_at - self.issued_at
        if not 0 < duration.total_seconds() <= 30 * 86_400:
            raise ValueError("runtime lease must be bounded to 30 days")
        return self


class StyleEpisodeV1(FrozenModel):
    episode_version: Literal["1.0.0"] = "1.0.0"
    episode_id: Identifier
    source_task_id: Identifier
    observation_ids: tuple[Identifier, ...] = Field(min_length=1)
    project_id: Identifier
    source_client: NonEmptyStr
    origin: InputOrigin
    provenance_digest: Sha256Digest | None = None
    completed_at: datetime
    created_at: datetime
    text: NonEmptyStr = Field(max_length=32_768)
    terminal: bool = True
    ephemeral: bool = False

    _episode_aware = field_validator("completed_at", "created_at")(_aware)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.completed_at < self.created_at:
            raise ValueError("episode completion precedes creation")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("episode observation IDs must be unique")
        return self


class HabitProposalV1(FrozenModel):
    proposal_version: Literal["1.0.0"] = "1.0.0"
    behavior: NonEmptyStr = Field(max_length=800)
    style_key: StyleKey
    category: StyleCategory
    task_class: TaskClass
    evidence_episode_ids: tuple[Identifier, ...] = Field(min_length=1)
    contradictory_episode_ids: tuple[Identifier, ...] = ()
    origin: Literal["inferred", "expressed_preference"] = "inferred"
    capability_change: Literal[False] = False
    evaluation_version: NonEmptyStr

    @model_validator(mode="after")
    def reviewed_style_only(self) -> Self:
        category, task, behavior = style_contract(self.style_key)
        if (self.category.value, self.task_class.value, self.behavior) != (
            category,
            task,
            behavior,
        ):
            raise ValueError("proposal does not match a reviewed v1 style default")
        if len(self.behavior.encode("utf-8")) > 800:
            raise ValueError("style default exceeds its UTF-8 byte limit")
        if set(self.evidence_episode_ids) & set(self.contradictory_episode_ids):
            raise ValueError("an episode cannot both support and contradict one habit")
        return self


class HabitHypothesisV1(FrozenModel):
    hypothesis_version: Literal["1.0.0"] = "1.0.0"
    habit_id: Identifier
    revision: int = Field(default=1, ge=1)
    behavior: NonEmptyStr = Field(max_length=800)
    style_key: StyleKey
    category: StyleCategory
    project_id: Identifier
    task_class: TaskClass
    origin: Literal["inferred", "expressed_preference"]
    support_episode_ids: tuple[Identifier, ...]
    support_dates: tuple[str, ...]
    evidence_strength: Literal["sparse", "repeated", "checked", "contradicted"] = "sparse"
    contradiction_episode_ids: tuple[Identifier, ...] = ()
    state: HabitState = HabitState.PROVISIONAL
    first_seen_at: datetime
    last_seen_at: datetime
    trial_started_at: datetime | None = None
    trial_expires_at: datetime | None = None
    evaluation_version: NonEmptyStr
    retirement_reason: str | None = None

    _habit_aware = field_validator("first_seen_at", "last_seen_at")(_aware)

    @model_validator(mode="after")
    def bounded_style(self) -> Self:
        category, task, behavior = style_contract(self.style_key)
        if (self.category.value, self.task_class.value, self.behavior) != (
            category,
            task,
            behavior,
        ):
            raise ValueError("hypothesis does not match a reviewed v1 style default")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("habit dates are reversed")
        if (self.trial_started_at is None) != (self.trial_expires_at is None):
            raise ValueError("trial dates must be paired")
        if self.trial_started_at is not None and self.trial_expires_at is not None:
            _aware(self.trial_started_at)
            _aware(self.trial_expires_at)
            if (self.trial_expires_at - self.trial_started_at).total_seconds() != 14 * 86_400:
                raise ValueError("trial duration is frozen to 14 days")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class HabitOutcomeV1(FrozenModel):
    outcome_version: Literal["1.0.0"] = "1.0.0"
    outcome_id: Identifier
    habit_id: Identifier
    habit_revision: int = Field(ge=1)
    episode_id: Identifier
    project_id: Identifier
    task_class: TaskClass
    occurred_at: datetime
    delivered: bool | None = None
    followed: bool | None = None
    helpful: bool | None = None
    harmful: bool | None = None
    scope_regression: bool = False
    check_digest: Sha256Digest | None = None
    assessment_origin: Literal["verified_check", "owner", "unknown"] = "unknown"

    _outcome_aware = field_validator("occurred_at")(_aware)

    @model_validator(mode="after")
    def claims_have_evidence(self) -> Self:
        known = any(
            value is not None
            for value in (self.delivered, self.followed, self.helpful, self.harmful)
        )
        if (known or self.scope_regression) and self.assessment_origin == "unknown":
            raise ValueError("unknown outcomes cannot claim observed results")
        if self.assessment_origin == "verified_check" and self.check_digest is None:
            raise ValueError("verified outcomes require a check digest")
        if self.followed is not None and self.delivered is not True:
            raise ValueError("compliance requires confirmed delivery")
        return self


class CalibrationReleaseV1(FrozenModel):
    release_version: Literal["1.0.0"] = "1.0.0"
    evaluation_version: NonEmptyStr
    dataset_digest: Sha256Digest
    analyzer_digest: Sha256Digest
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    disallowed_promotions: int = Field(ge=0)
    wrong_scope_activations: int = Field(ge=0)
    lifecycle_checks_passed: bool
    synthetic: bool
    recorded_at: datetime

    _calibration_aware = field_validator("recorded_at")(_aware)

    @property
    def admits_automatic_trials(self) -> bool:
        return (
            self.precision >= 0.95
            and self.recall >= 0.80
            and self.disallowed_promotions == 0
            and self.wrong_scope_activations == 0
            and self.lifecycle_checks_passed
        )
