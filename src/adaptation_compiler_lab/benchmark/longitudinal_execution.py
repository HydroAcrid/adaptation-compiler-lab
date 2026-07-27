"""Execution contracts for the subscription-only longitudinal comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
)
from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.serialization import canonical_digest

ProfileText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=40, max_length=12000),
]
RationaleText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=2000),
]


class LongitudinalEvidenceScope(FrozenModel):
    destination_kind: Literal[
        "persistent_user_managed",
        "disposable_generated_cache",
    ]
    target_family: Literal["codex"]
    project_id: Identifier | None = None


class LongitudinalEvidenceItem(FrozenModel):
    evidence_id: Identifier
    observed_order: Annotated[int, Field(ge=1, le=3)]
    status: Literal[
        "active",
        "active_scoped_exception",
        "superseded",
        "active_supersession",
    ]
    scope: LongitudinalEvidenceScope
    approved_behavior: NonEmptyStr
    verification: NonEmptyStr
    superseded_by: Identifier | None = None
    supersedes: Identifier | None = None

    @model_validator(mode="after")
    def supersession_shape_is_exact(self) -> Self:
        if (self.status == "superseded") != (self.superseded_by is not None):
            raise ValueError("superseded evidence requires exactly one replacement")
        if (self.status == "active_supersession") != (self.supersedes is not None):
            raise ValueError("active supersession requires exactly one replaced evidence ID")
        return self


class LongitudinalEvidencePacket(FrozenModel):
    packet_version: Literal["1.0.0"] = "1.0.0"
    stage: Annotated[int, Field(ge=1, le=3)]
    items: Annotated[tuple[LongitudinalEvidenceItem, ...], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def items_are_exact_cumulative_history(self) -> Self:
        expected = tuple(f"dogfood-evidence-{index}" for index in range(1, self.stage + 1))
        actual = tuple(item.evidence_id for item in self.items)
        if actual != expected:
            raise ValueError("longitudinal evidence packet is not exact cumulative history")
        if tuple(item.observed_order for item in self.items) != tuple(range(1, self.stage + 1)):
            raise ValueError("longitudinal evidence order drifted")
        if self.stage < 3 and any(
            item.status in {"superseded", "active_supersession"} for item in self.items
        ):
            raise ValueError("supersession appeared before Stage 3")
        if self.stage == 3:
            if self.items[0].superseded_by != "dogfood-evidence-3":
                raise ValueError("Stage 3 did not supersede the original broad behavior")
            if self.items[2].supersedes != "dogfood-evidence-1":
                raise ValueError("Stage 3 replacement did not bind the original behavior")
        return self

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(item.evidence_id for item in self.items)

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class StaticProfileAuthorOutput(FrozenModel):
    output_version: Literal["1.0.0"] = "1.0.0"
    stage: Annotated[int, Field(ge=1, le=3)]
    evidence_ids: tuple[Identifier, ...]
    profile_text: ProfileText
    change_summary: RationaleText
    intentional_edit_operations: int = Field(ge=1, le=100)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("profile evidence IDs must be sorted and unique")
        return value


class StaticProfileReviewOutput(FrozenModel):
    output_version: Literal["1.0.0"] = "1.0.0"
    stage: Annotated[int, Field(ge=1, le=3)]
    evidence_ids: tuple[Identifier, ...]
    approved_profile_text: ProfileText
    review_summary: RationaleText
    intentional_edit_operations: int = Field(ge=1, le=100)
    unsupported_content_removed: bool

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("review evidence IDs must be sorted and unique")
        return value


class LongitudinalJudgePair(FrozenModel):
    task_id: Identifier
    ordered_output_ids: tuple[Identifier, Identifier]
    preference: Literal["first_better", "second_better", "tie"]
    preferred_output_id: Identifier | None
    rationale: RationaleText

    @model_validator(mode="after")
    def preference_matches_output(self) -> Self:
        if len(set(self.ordered_output_ids)) != 2:
            raise ValueError("judge pair requires two distinct output IDs")
        expected = {
            "first_better": self.ordered_output_ids[0],
            "second_better": self.ordered_output_ids[1],
            "tie": None,
        }[self.preference]
        if self.preferred_output_id != expected:
            raise ValueError("judge preference does not match its selected output")
        return self


class LongitudinalJudgeDecision(FrozenModel):
    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[tuple[LongitudinalJudgePair, ...], Field(min_length=6, max_length=6)]
    overall_assessment: RationaleText
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=6)]

    @model_validator(mode="after")
    def tasks_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 6:
            raise ValueError("longitudinal judge must cover all six unique tasks")
        return self


class LongitudinalBlindReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    execution_protocol_digest: Sha256Digest
    execution_amendment_digest: Sha256Digest
    profile_construction_receipt_digest: Sha256Digest
    source_commit: NonEmptyStr
    observations: Annotated[
        tuple[CodexDevelopmentRunObservation, ...],
        Field(min_length=12, max_length=12),
    ]
    created_at: UtcDateTime
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0

    @model_validator(mode="after")
    def grid_is_complete(self) -> Self:
        run_ids = {item.run_id for item in self.observations}
        output_ids = {item.blind_output_id for item in self.observations}
        if len(run_ids) != 12 or len(output_ids) != 12:
            raise ValueError("longitudinal blind report contains duplicate cells")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class LongitudinalExecutionProtocol(FrozenModel):
    protocol_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    preregistration_sha256: Sha256Digest
    evidence_packet_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    compiled_material_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    task_fixture_digests: Annotated[
        tuple[Sha256Digest, ...],
        Field(min_length=6, max_length=6),
    ]
    independent_scorer_digest: Sha256Digest
    dogfood_metrics_digest: Sha256Digest
    profile_author_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    profile_author_reasoning: Literal["medium"] = "medium"
    profile_reviewer_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    profile_reviewer_reasoning: Literal["medium"] = "medium"
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    target_reasoning: Literal["medium"] = "medium"
    judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    judge_reasoning: Literal["xhigh"] = "xhigh"
    maximum_profile_author_sessions: Literal[3] = 3
    maximum_profile_review_sessions: Literal[3] = 3
    maximum_target_sessions: Literal[12] = 12
    maximum_judge_sessions: Literal[1] = 1
    maximum_total_sessions: Literal[19] = 19
    compiled_stage_maintenance_actions: tuple[
        Literal[3],
        Literal[4],
        Literal[5],
    ] = (3, 4, 5)
    compiled_stage_maintenance_seconds: tuple[float, float, float] = (30.0, 30.0, 30.0)
    compiled_stage_update_latency_seconds: tuple[float, float, float] = (40.0, 40.0, 40.0)
    retries_allowed: Literal[False] = False
    api_keys_allowed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_validation_access_allowed: Literal[False] = False

    @model_validator(mode="after")
    def compiled_measurements_are_frozen(self) -> Self:
        if self.compiled_stage_maintenance_seconds != (30.0, 30.0, 30.0):
            raise ValueError("compiled maintenance-time measurements drifted")
        if self.compiled_stage_update_latency_seconds != (40.0, 40.0, 40.0):
            raise ValueError("compiled update-latency measurements drifted")
        return self


class LongitudinalPriorAttempt(FrozenModel):
    source_commit: NonEmptyStr
    sessions_attempted: Literal[6] = 6
    validated_encrypted_role_outputs: Literal[5] = 5
    rejected_role_outputs: Literal[1] = 1
    target_sessions_started: Literal[0] = 0
    judge_sessions_started: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False
    failure_receipt_digest: Sha256Digest
    stdout_log_digest: Sha256Digest
    stderr_log_digest: Sha256Digest


class LongitudinalRecoveryConstraints(FrozenModel):
    reuse_only_validated_encrypted_outputs: Literal[True] = True
    preserve_rejected_attempt_evidence_without_promotion: Literal[True] = True
    replacement_sessions: Literal[1] = 1
    further_retries_allowed: Literal[False] = False
    target_grid_unchanged: Literal[True] = True
    condition_materials_unchanged: Literal[True] = True
    task_fixtures_unchanged: Literal[True] = True
    randomization_unchanged: Literal[True] = True
    sealed_external_validation_access_allowed: Literal[False] = False
    api_keys_allowed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0


class LongitudinalExecutionAmendment(FrozenModel):
    amendment_version: Literal["1.1.0"] = "1.1.0"
    amends_protocol_version: Literal["1.0.0"] = "1.0.0"
    authorized_at: UtcDateTime
    authorization_kind: Literal["explicit_user_authorization_in_project_task"]
    reason: RationaleText
    original_maximum_total_sessions: Literal[19] = 19
    maximum_valid_sessions: Literal[19] = 19
    maximum_attempted_sessions: Literal[20] = 20
    additional_authorized_sessions: Literal[1] = 1
    replacement_role_id: Literal["longitudinal-profile-reviewer-stage-3"]
    replacement_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    replacement_reasoning_effort: Literal["medium"] = "medium"
    replacement_service_mode: Literal["standard"] = "standard"
    prior_attempt: LongitudinalPriorAttempt
    recovery_constraints: LongitudinalRecoveryConstraints

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def static_profile_author_schema() -> dict[str, object]:
    return _profile_schema(review=False)


def static_profile_review_schema() -> dict[str, object]:
    return _profile_schema(review=True)


def _profile_schema(*, review: bool) -> dict[str, object]:
    text_name = "approved_profile_text" if review else "profile_text"
    summary_name = "review_summary" if review else "change_summary"
    properties: dict[str, object] = {
        "output_version": {"type": "string", "enum": ["1.0.0"]},
        "stage": {"type": "integer", "minimum": 1, "maximum": 3},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        text_name: {"type": "string"},
        summary_name: {"type": "string"},
        "intentional_edit_operations": {"type": "integer", "minimum": 1, "maximum": 100},
    }
    required = [
        "output_version",
        "stage",
        "evidence_ids",
        text_name,
        summary_name,
        "intentional_edit_operations",
    ]
    if review:
        properties["unsupported_content_removed"] = {"type": "boolean"}
        required.append("unsupported_content_removed")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def longitudinal_judge_schema() -> dict[str, object]:
    pair = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "task_id": {"type": "string"},
            "ordered_output_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "preference": {
                "type": "string",
                "enum": ["first_better", "second_better", "tie"],
            },
            "preferred_output_id": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
            },
            "rationale": {"type": "string"},
        },
        "required": [
            "task_id",
            "ordered_output_ids",
            "preference",
            "preferred_output_id",
            "rationale",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision_version": {"type": "string", "enum": ["1.0.0"]},
            "pair_ratings": {
                "type": "array",
                "minItems": 6,
                "maxItems": 6,
                "items": pair,
            },
            "overall_assessment": {"type": "string"},
            "evaluator_limitations": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "decision_version",
            "pair_ratings",
            "overall_assessment",
            "evaluator_limitations",
        ],
    }


def load_evidence_packets(
    root: Path,
) -> tuple[
    LongitudinalEvidencePacket,
    LongitudinalEvidencePacket,
    LongitudinalEvidencePacket,
]:
    packets = tuple(
        LongitudinalEvidencePacket.model_validate_json(
            (root / "evidence" / f"stage-{stage}.json").read_bytes()
        )
        for stage in (1, 2, 3)
    )
    return packets  # type: ignore[return-value]


def load_execution_protocol(root: Path) -> LongitudinalExecutionProtocol:
    return LongitudinalExecutionProtocol.model_validate_json(
        (root / "EXECUTION_PROTOCOL-v1.0.json").read_bytes()
    )


def load_execution_amendment(root: Path) -> LongitudinalExecutionAmendment:
    return LongitudinalExecutionAmendment.model_validate_json(
        (root / "EXECUTION_AMENDMENT-v1.1.json").read_bytes()
    )


def load_compiled_materials(root: Path) -> tuple[str, str, str]:
    values = tuple(
        (root / "condition-materials" / f"compiled-stage-{stage}.md").read_text(encoding="utf-8")
        for stage in (1, 2, 3)
    )
    if any(len(value.encode("utf-8")) > 12000 for value in values):
        raise ValueError("compiled longitudinal material exceeds the common byte ceiling")
    return values  # type: ignore[return-value]


def load_json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return value


def validate_static_profile(
    *,
    stage: int,
    evidence_ids: tuple[str, ...],
    profile_text: str,
    packet: LongitudinalEvidencePacket,
) -> None:
    """Fail closed on evidence substitution, leakage, budget, or obvious semantic omission."""

    if stage != packet.stage or evidence_ids != packet.evidence_ids:
        raise ValueError("static profile did not bind the exact cumulative evidence packet")
    raw = profile_text.encode("utf-8")
    if len(raw) > 12000:
        raise ValueError("static profile exceeded the common byte ceiling")
    lowered = profile_text.casefold()
    forbidden = (
        "compiled adaptation",
        "development task",
        "condition mapping",
        "held-out",
        "milestone 6",
        "dogfood-evaluation",
    )
    if any(value in lowered for value in forbidden):
        raise ValueError("static profile leaked a forbidden construction or study concept")
    required_groups: list[tuple[str, ...]] = [
        ("persistent",),
        ("backup",),
    ]
    if stage >= 2:
        required_groups.extend(
            [
                ("generated", "cache"),
                ("atomic",),
                ("without", "no backup"),
            ]
        )
    if stage == 3:
        required_groups.extend(
            [
                ("refuse", "do not overwrite", "must not overwrite"),
                ("explicit", "requested"),
            ]
        )
    for alternatives in required_groups:
        if not any(value in lowered for value in alternatives):
            raise ValueError(
                "static profile omitted a registered behavior: " + " | ".join(alternatives)
            )
