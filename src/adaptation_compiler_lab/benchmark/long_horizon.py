"""Typed design and scoring records for the Milestone 6A.5 conversation gate."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.serialization import canonical_digest

LONG_HORIZON_CONDITIONS = (
    BenchmarkCondition.STRONG_STATIC_PROFILE,
    BenchmarkCondition.COMPILED_ADAPTATION,
)
LONG_HORIZON_CHECKPOINTS = (3, 10, 15)
LONG_HORIZON_UPDATE_TURNS = (1, 5, 12)


class LongHorizonTurnKind(StrEnum):
    """Kinds of user turns allowed in the constrained conversation grammar."""

    DIAGNOSTIC = "diagnostic"
    NEUTRAL_CONTROL = "neutral_control"
    EXPLICIT_FEEDBACK = "explicit_feedback"


class LongHorizonTask(FrozenModel):
    """One natural, non-held-out task eligible for a grammar slot."""

    task_id: Identifier
    family: ApprovedSourceFamily | None
    stage: Annotated[int, Field(ge=1, le=3)]
    kind: LongHorizonTurnKind
    prompt: NonEmptyStr
    allowed_change_paths: tuple[NonEmptyStr, ...]
    visible_test_command: tuple[NonEmptyStr, ...]
    behavior_keys: tuple[Identifier, ...]
    fixture_digest: Sha256Digest
    scorer_digest: Sha256Digest
    held_out: Literal[False] = False

    @field_validator(
        "allowed_change_paths",
        "visible_test_command",
        "behavior_keys",
    )
    @classmethod
    def sequences_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("long-horizon task sequences must be unique")
        return value

    @model_validator(mode="after")
    def task_shape_is_exact(self) -> Self:
        if self.kind is LongHorizonTurnKind.EXPLICIT_FEEDBACK:
            if (
                self.family is not None
                or self.allowed_change_paths
                or self.visible_test_command
                or self.behavior_keys
            ):
                raise ValueError("feedback turns cannot contain a target task or scorer")
        elif (
            self.family is None
            or len(self.allowed_change_paths) != 1
            or not self.visible_test_command
            or not self.behavior_keys
        ):
            raise ValueError("work turns require one writable file, tests, and behavior keys")
        if self.kind is LongHorizonTurnKind.NEUTRAL_CONTROL and self.family is None:
            raise ValueError("neutral controls still require a source-family classification")
        return self


class LongHorizonTurn(FrozenModel):
    """One scheduled turn in a 15-turn persistent episode."""

    turn: Annotated[int, Field(ge=1, le=15)]
    task: LongHorizonTask
    adaptation_stage: Annotated[int, Field(ge=1, le=3)]
    delivers_material_update: bool
    horizon_checkpoint: bool


class LongHorizonScenario(FrozenModel):
    """A seed-ordered scenario with fixed feedback and horizon positions."""

    scenario_version: Literal["1.0.0"] = "1.0.0"
    scenario_id: Identifier
    turns: Annotated[tuple[LongHorizonTurn, ...], Field(min_length=15, max_length=15)]
    task_order_seed_commitment: Sha256Digest
    grammar: Literal["stage_block_shuffle_v1"] = "stage_block_shuffle_v1"
    held_out: Literal[False] = False
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def scenario_is_complete(self) -> Self:
        if tuple(item.turn for item in self.turns) != tuple(range(1, 16)):
            raise ValueError("long-horizon turns must be contiguous")
        if len({item.task.task_id for item in self.turns}) != 15:
            raise ValueError("long-horizon turn task IDs must be unique")
        if tuple(
            item.turn
            for item in self.turns
            if item.task.kind is LongHorizonTurnKind.EXPLICIT_FEEDBACK
        ) != (4, 11):
            raise ValueError("feedback turns must remain fixed at turns 4 and 11")
        if tuple(item.turn for item in self.turns if item.delivers_material_update) != (
            LONG_HORIZON_UPDATE_TURNS
        ):
            raise ValueError("material updates must occur at turns 1, 5, and 12")
        if tuple(item.turn for item in self.turns if item.horizon_checkpoint) != (
            LONG_HORIZON_CHECKPOINTS
        ):
            raise ValueError("horizon checkpoints must be turns 3, 10, and 15")
        expected_stages = (
            *((1,) * 4),
            *((2,) * 7),
            *((3,) * 4),
        )
        if tuple(item.adaptation_stage for item in self.turns) != expected_stages:
            raise ValueError("adaptation stages do not match the frozen update schedule")
        family_counts = Counter(
            item.task.family
            for item in self.turns
            if item.task.kind is not LongHorizonTurnKind.EXPLICIT_FEEDBACK
        )
        if set(family_counts) != set(ApprovedSourceFamily):
            raise ValueError("long-horizon scenario must cover all four source families")
        if any(family_counts[family] < 2 for family in ApprovedSourceFamily):
            raise ValueError("every source family requires at least two work turns")
        if sum(item.task.kind is LongHorizonTurnKind.NEUTRAL_CONTROL for item in self.turns) != 1:
            raise ValueError("long-horizon scenario requires exactly one neutral control")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class LongHorizonMaterialSet(FrozenModel):
    """Three cumulative snapshots for one condition."""

    material_version: Literal["1.0.0"] = "1.0.0"
    condition: BenchmarkCondition
    stages: Annotated[tuple[NonEmptyStr, ...], Field(min_length=3, max_length=3)]
    eligible_evidence_digest: Sha256Digest
    independently_maintained: bool

    @field_validator("stages")
    @classmethod
    def snapshots_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(len(item.encode("utf-8")) > 3_000 for item in value):
            raise ValueError("long-horizon material exceeds the 3,000-byte ceiling")
        return value

    @model_validator(mode="after")
    def condition_is_supported(self) -> Self:
        if self.condition not in LONG_HORIZON_CONDITIONS:
            raise ValueError("long-horizon comparison supports only profile and compiled")
        if self.condition is BenchmarkCondition.STRONG_STATIC_PROFILE:
            if not self.independently_maintained:
                raise ValueError("strong profile must be independently maintained")
        elif self.independently_maintained:
            raise ValueError("compiled material must be deterministic, not independently authored")
        return self

    @property
    def stage_digests(self) -> tuple[Sha256Digest, ...]:
        return tuple(
            "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest() for value in self.stages
        )


class LongHorizonEpisodeCell(FrozenModel):
    """One anonymous persistent episode in randomized execution order."""

    sequence: Annotated[int, Field(ge=1, le=2)]
    episode_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class LongHorizonPublicPlan(FrozenModel):
    """Public execution commitment with condition identity withheld."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    scenario_digest: Sha256Digest
    seed_commitment: Sha256Digest
    episodes: Annotated[tuple[LongHorizonEpisodeCell, ...], Field(min_length=2, max_length=2)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def public_plan_is_complete(self) -> Self:
        if tuple(item.sequence for item in self.episodes) != (1, 2):
            raise ValueError("long-horizon episode sequence must be contiguous")
        if len({item.episode_id for item in self.episodes}) != 2:
            raise ValueError("long-horizon episode IDs must be unique")
        if len({item.blind_condition_id for item in self.episodes}) != 2:
            raise ValueError("long-horizon condition IDs must be unique")
        if len({item.blind_output_id for item in self.episodes}) != 2:
            raise ValueError("long-horizon output IDs must be unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class LongHorizonPrivateAssignment(FrozenModel):
    """Private condition mapping for one blinded episode."""

    episode_id: Identifier
    blind_condition_id: Identifier
    condition: BenchmarkCondition


class LongHorizonPrivatePlan(FrozenModel):
    """Secret mapping retained outside blind result construction."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    public_plan_digest: Sha256Digest
    assignments: Annotated[
        tuple[LongHorizonPrivateAssignment, ...],
        Field(min_length=2, max_length=2),
    ]
    seed_hex: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] = Field(repr=False)
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def private_plan_is_complete(self) -> Self:
        if {item.condition for item in self.assignments} != set(LONG_HORIZON_CONDITIONS):
            raise ValueError("long-horizon private plan must map both conditions")
        if len({item.episode_id for item in self.assignments}) != 2:
            raise ValueError("long-horizon private assignments must be unique")
        return self


class LongHorizonTurnScore(FrozenModel):
    """Independent, condition-blind result for one work or feedback turn."""

    turn: Annotated[int, Field(ge=1, le=15)]
    task_id: Identifier
    kind: LongHorizonTurnKind
    objective_passed: int = Field(ge=0)
    objective_total: int = Field(ge=0)
    adaptation_passed: int = Field(ge=0)
    adaptation_total: int = Field(ge=0)
    neutral_passed: int = Field(ge=0)
    neutral_total: int = Field(ge=0)
    unsupported_verification_claim: bool = False
    correction_required: bool = False

    @model_validator(mode="after")
    def counts_are_coherent(self) -> Self:
        for passed, total in (
            (self.objective_passed, self.objective_total),
            (self.adaptation_passed, self.adaptation_total),
            (self.neutral_passed, self.neutral_total),
        ):
            if passed > total:
                raise ValueError("long-horizon passed count exceeds total")
        if self.kind is LongHorizonTurnKind.EXPLICIT_FEEDBACK and any(
            (
                self.objective_total,
                self.adaptation_total,
                self.neutral_total,
                self.correction_required,
            )
        ):
            raise ValueError("feedback turns cannot carry task scores")
        return self


class LongHorizonEpisodeResult(FrozenModel):
    """Sanitized anonymous result for one complete persistent episode."""

    result_version: Literal["1.0.0"] = "1.0.0"
    episode_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier
    scenario_digest: Sha256Digest
    material_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=3, max_length=3)]
    turn_scores: Annotated[tuple[LongHorizonTurnScore, ...], Field(min_length=15, max_length=15)]
    trace_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=15, max_length=15)]
    encrypted_raw_ref: Sha256Digest
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    all_turns_conformant: bool
    config_destroyed: bool
    session_destroyed: bool
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def result_is_complete(self) -> Self:
        if tuple(item.turn for item in self.turn_scores) != tuple(range(1, 16)):
            raise ValueError("long-horizon result must score every turn")
        return self

    def cumulative_at(self, horizon: int) -> dict[str, int]:
        """Return preregistered cumulative metrics at a 3/10/15-turn horizon."""

        if horizon not in LONG_HORIZON_CHECKPOINTS:
            raise ValueError("unsupported long-horizon checkpoint")
        scores = self.turn_scores[:horizon]
        return {
            "objective_passed": sum(item.objective_passed for item in scores),
            "objective_total": sum(item.objective_total for item in scores),
            "adaptation_passed": sum(item.adaptation_passed for item in scores),
            "adaptation_total": sum(item.adaptation_total for item in scores),
            "neutral_passed": sum(item.neutral_passed for item in scores),
            "neutral_total": sum(item.neutral_total for item in scores),
            "corrections": sum(item.correction_required for item in scores),
            "unsupported_verification_claims": sum(
                item.unsupported_verification_claim for item in scores
            ),
        }


class LongHorizonDesign(FrozenModel):
    """Frozen two-condition, 15-turn, persistent-session comparison."""

    design_version: Literal["1.0.0"] = "1.0.0"
    design_id: Literal["milestone-6a5-long-horizon-v1"] = "milestone-6a5-long-horizon-v1"
    conditions: Annotated[
        tuple[BenchmarkCondition, ...],
        Field(min_length=2, max_length=2),
    ] = LONG_HORIZON_CONDITIONS
    horizons: tuple[Literal[3], Literal[10], Literal[15]] = (3, 10, 15)
    adaptation_update_turns: tuple[Literal[1], Literal[5], Literal[12]] = (
        1,
        5,
        12,
    )
    target_sessions: Literal[2] = 2
    target_turns: Literal[30] = 30
    repetitions_per_condition: Literal[1] = 1
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["medium"] = "medium"
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    provider_billed_calls: Literal[0] = 0
    scenario: LongHorizonScenario
    materials: Annotated[tuple[LongHorizonMaterialSet, ...], Field(min_length=2, max_length=2)]
    frozen_at: UtcDateTime
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def design_is_fair(self) -> Self:
        if self.conditions != LONG_HORIZON_CONDITIONS:
            raise ValueError("long-horizon condition order is frozen")
        if tuple(item.condition for item in self.materials) != self.conditions:
            raise ValueError("long-horizon materials must follow condition order")
        evidence_digests = {item.eligible_evidence_digest for item in self.materials}
        if len(evidence_digests) != 1:
            raise ValueError("conditions must receive the same eligible evidence")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def _shuffle(
    values: tuple[LongHorizonTask, ...], *, seed: bytes, label: str
) -> tuple[LongHorizonTask, ...]:
    ranked = sorted(
        values,
        key=lambda value: hmac.new(
            seed,
            f"{label}:{value.task_id}".encode(),
            hashlib.sha256,
        ).digest(),
    )
    return tuple(ranked)


def long_horizon_seed_commitment(seed: bytes) -> Sha256Digest:
    """Commit a 32-byte seed without exposing its condition mapping."""

    if len(seed) != 32:
        raise ValueError("long-horizon seed must contain exactly 32 bytes")
    return "sha256:" + hashlib.sha256(b"acl-long-horizon-v1:" + seed).hexdigest()


def build_long_horizon_scenario(
    tasks: tuple[LongHorizonTask, ...],
    *,
    seed: bytes,
) -> LongHorizonScenario:
    """Shuffle work tasks only within stage blocks while feedback positions stay fixed."""

    commitment = long_horizon_seed_commitment(seed)
    feedback = {
        item.stage: item for item in tasks if item.kind is LongHorizonTurnKind.EXPLICIT_FEEDBACK
    }
    work = {
        stage: _shuffle(
            tuple(
                item
                for item in tasks
                if item.stage == stage and item.kind is not LongHorizonTurnKind.EXPLICIT_FEEDBACK
            ),
            seed=seed,
            label=f"stage-{stage}",
        )
        for stage in (1, 2, 3)
    }
    if tuple(len(work[stage]) for stage in (1, 2, 3)) != (3, 6, 4):
        raise ValueError("long-horizon task catalog must have 3/6/4 work tasks by stage")
    if set(feedback) != {1, 2} or len(feedback) != 2:
        raise ValueError("long-horizon task catalog requires Stage 1 and 2 feedback turns")

    ordered = (
        *work[1],
        feedback[1],
        *work[2],
        feedback[2],
        *work[3],
    )
    stages = (*((1,) * 4), *((2,) * 7), *((3,) * 4))
    turns = tuple(
        LongHorizonTurn(
            turn=index,
            task=task,
            adaptation_stage=stages[index - 1],
            delivers_material_update=index in LONG_HORIZON_UPDATE_TURNS,
            horizon_checkpoint=index in LONG_HORIZON_CHECKPOINTS,
        )
        for index, task in enumerate(ordered, start=1)
    )
    return LongHorizonScenario(
        scenario_id="long-horizon-public-scenario-v1",
        turns=turns,
        task_order_seed_commitment=commitment,
    )


def build_long_horizon_plan(
    design: LongHorizonDesign,
    *,
    seed: bytes,
) -> tuple[LongHorizonPublicPlan, LongHorizonPrivatePlan]:
    """Blind and seed-order the two persistent condition episodes."""

    commitment = long_horizon_seed_commitment(seed)
    ranked = sorted(
        LONG_HORIZON_CONDITIONS,
        key=lambda condition: hmac.new(
            seed,
            f"condition:{condition.value}".encode(),
            hashlib.sha256,
        ).digest(),
    )
    cells = tuple(
        LongHorizonEpisodeCell(
            sequence=index,
            episode_id=f"long-horizon-episode-{index:02d}",
            blind_condition_id=f"condition-{hashlib.sha256(f'{commitment}:{index}'.encode()).hexdigest()[:12]}",
            blind_output_id=f"output-{hashlib.sha256(f'{commitment}:output:{index}'.encode()).hexdigest()[:12]}",
        )
        for index in range(1, 3)
    )
    provisional = LongHorizonPublicPlan(
        design_digest=design.content_digest,
        scenario_digest=design.scenario.content_digest,
        seed_commitment=commitment,
        episodes=cells,
    )
    private = LongHorizonPrivatePlan(
        public_plan_digest=provisional.content_digest,
        assignments=tuple(
            LongHorizonPrivateAssignment(
                episode_id=cell.episode_id,
                blind_condition_id=cell.blind_condition_id,
                condition=condition,
            )
            for cell, condition in zip(cells, ranked, strict=True)
        ),
        seed_hex=seed.hex(),
    )
    return provisional, private
