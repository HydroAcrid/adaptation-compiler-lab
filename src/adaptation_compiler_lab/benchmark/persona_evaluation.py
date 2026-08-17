"""Synthetic persona evaluation contracts and deterministic blind-packet construction."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest


class PersonaDomain(StrEnum):
    COMMUNICATION = "communication"
    DEBUGGING = "debugging"
    ENVIRONMENT_SAFETY = "environment_safety"
    RESEARCH_INTEGRITY = "research_integrity"
    WORKFLOW = "workflow"
    INTERFACE = "interface"


class PersonaTraitKind(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    INVARIANT = "invariant"
    PROCEDURE = "procedure"


class PersonaTransition(StrEnum):
    ADDITION = "addition"
    CONTEXT_EXCEPTION = "context_exception"
    SUPERSESSION = "supersession"
    REVOCATION = "revocation"
    NEUTRAL_SENTINEL = "neutral_sentinel"


class PersonaCondition(StrEnum):
    COMPILED = "compiled_adaptation"
    STRONG_STATIC = "strong_static_profile"
    CONTROLLED_SENTINEL = "controlled_sentinel"


class PersonaTrack(StrEnum):
    LEARNING_STATE = "learning_state"
    TARGET_GUIDANCE = "target_guidance"


class PersonaPreference(StrEnum):
    FIRST = "first"
    SECOND = "second"
    TIE = "tie"


class PersonaTrait(FrozenModel):
    trait_id: Identifier
    statement: NonEmptyStr
    kind: PersonaTraitKind
    scope: NonEmptyStr
    durable: bool
    introduced_stage: Annotated[int, Field(ge=1, le=3)]
    retired_stage: Annotated[int, Field(ge=2, le=3)] | None = None
    supersedes_trait_id: Identifier | None = None

    @model_validator(mode="after")
    def lifecycle_is_coherent(self) -> Self:
        if self.retired_stage is not None and self.retired_stage < self.introduced_stage:
            raise ValueError("persona trait cannot retire before introduction")
        if self.supersedes_trait_id == self.trait_id:
            raise ValueError("persona trait cannot supersede itself")
        return self


class SyntheticPersona(FrozenModel):
    persona_id: Identifier
    display_name: Identifier
    domain: PersonaDomain
    judge_summary: NonEmptyStr
    project_id: Identifier
    traits: Annotated[tuple[PersonaTrait, ...], Field(min_length=3, max_length=6)]

    @model_validator(mode="after")
    def traits_are_unique(self) -> Self:
        trait_ids = tuple(item.trait_id for item in self.traits)
        if len(trait_ids) != len(set(trait_ids)):
            raise ValueError("persona trait IDs must be unique")
        known = set(trait_ids)
        if any(
            item.supersedes_trait_id is not None and item.supersedes_trait_id not in known
            for item in self.traits
        ):
            raise ValueError("persona supersession target must exist in the same persona")
        return self


class PersonaInteraction(FrozenModel):
    turn: Annotated[int, Field(ge=1, le=15)]
    message: NonEmptyStr
    expected_trait_ids: tuple[Identifier, ...] = ()
    synthetic: Literal[True] = True
    user_authority: Literal[False] = False

    @field_validator("expected_trait_ids")
    @classmethod
    def trait_ids_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("interaction trait IDs must be sorted and unique")
        return value


class PersonaEvidenceHistory(FrozenModel):
    persona_id: Identifier
    interactions: Annotated[
        tuple[PersonaInteraction, ...],
        Field(min_length=15, max_length=15),
    ]

    @model_validator(mode="after")
    def turns_are_contiguous(self) -> Self:
        if tuple(item.turn for item in self.interactions) != tuple(range(1, 16)):
            raise ValueError("persona history must contain turns 1 through 15")
        return self


class PersonaEvaluationCase(FrozenModel):
    case_id: Identifier
    persona_id: Identifier
    stage: Annotated[int, Field(ge=1, le=4)]
    checkpoint_turn: Literal[3, 7, 11, 15]
    transition: PersonaTransition
    current_context: NonEmptyStr
    scenario: NonEmptyStr
    expected_active_trait_ids: tuple[Identifier, ...]
    forbidden_trait_ids: tuple[Identifier, ...]
    sentinel: bool

    @model_validator(mode="after")
    def case_shape_is_exact(self) -> Self:
        expected_turn = (3, 7, 11, 15)[self.stage - 1]
        if self.checkpoint_turn != expected_turn:
            raise ValueError("persona stage/checkpoint mismatch")
        for value in (self.expected_active_trait_ids, self.forbidden_trait_ids):
            if value != tuple(sorted(set(value))):
                raise ValueError("persona case trait IDs must be sorted and unique")
        if set(self.expected_active_trait_ids) & set(self.forbidden_trait_ids):
            raise ValueError("expected and forbidden persona traits overlap")
        if self.sentinel is not (self.transition is PersonaTransition.NEUTRAL_SENTINEL):
            raise ValueError("only neutral cases may be sentinels")
        return self


class PersonaBenchmarkPlan(FrozenModel):
    plan_version: Literal["1.0.0"] = "1.0.0"
    benchmark_id: Literal["temper-6a2l-persona-evaluation-v1"] = "temper-6a2l-persona-evaluation-v1"
    personas: Annotated[tuple[SyntheticPersona, ...], Field(min_length=6, max_length=6)]
    histories: Annotated[tuple[PersonaEvidenceHistory, ...], Field(min_length=6, max_length=6)]
    cases: Annotated[tuple[PersonaEvaluationCase, ...], Field(min_length=24, max_length=24)]
    synthetic_only: Literal[True] = True
    counts_toward_ordinary_use_gate: Literal[False] = False
    external_validation_accessed: Literal[False] = False
    provider_billed_calls_permitted: Literal[False] = False
    one_persona_per_session: Literal[True] = True

    @model_validator(mode="after")
    def design_is_balanced(self) -> Self:
        persona_ids = tuple(item.persona_id for item in self.personas)
        if len(persona_ids) != len(set(persona_ids)):
            raise ValueError("persona IDs must be unique")
        if set(item.persona_id for item in self.histories) != set(persona_ids):
            raise ValueError("every persona requires one evidence history")
        if set(item.persona_id for item in self.cases) != set(persona_ids):
            raise ValueError("every persona requires evaluation cases")
        counts = Counter(item.persona_id for item in self.cases)
        if set(counts.values()) != {4}:
            raise ValueError("every persona requires four cases")
        for persona_id in persona_ids:
            selected = tuple(item for item in self.cases if item.persona_id == persona_id)
            if tuple(item.stage for item in selected) != (1, 2, 3, 4):
                raise ValueError("persona cases must be ordered by all four stages")
        if sum(item.sentinel for item in self.cases) != 6:
            raise ValueError("persona benchmark requires six sentinels")
        lifecycle = Counter(item.transition for item in self.cases)
        if lifecycle[PersonaTransition.ADDITION] != 6:
            raise ValueError("persona benchmark requires six additions")
        if lifecycle[PersonaTransition.CONTEXT_EXCEPTION] != 6:
            raise ValueError("persona benchmark requires six exceptions")
        if lifecycle[PersonaTransition.NEUTRAL_SENTINEL] != 6:
            raise ValueError("persona benchmark requires six neutral sentinels")
        if lifecycle[PersonaTransition.SUPERSESSION] != 3:
            raise ValueError("persona benchmark requires three supersessions")
        if lifecycle[PersonaTransition.REVOCATION] != 3:
            raise ValueError("persona benchmark requires three revocations")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PersonaConditionMaterial(FrozenModel):
    case_id: Identifier
    persona_id: Identifier
    condition: PersonaCondition
    learning_state: NonEmptyStr
    target_guidance: NonEmptyStr
    active_trait_ids: tuple[Identifier, ...]
    evidence_digest: Sha256Digest
    independently_maintained: bool

    @model_validator(mode="after")
    def condition_shape_is_valid(self) -> Self:
        if self.active_trait_ids != tuple(sorted(set(self.active_trait_ids))):
            raise ValueError("condition active trait IDs must be sorted and unique")
        expected_independence = self.condition is PersonaCondition.STRONG_STATIC
        if self.independently_maintained is not expected_independence:
            raise ValueError("only strong static material is independently maintained")
        if len(self.target_guidance.encode("utf-8")) > 3_000:
            raise ValueError("persona target guidance exceeds the frozen byte ceiling")
        return self


class PersonaProfileSnapshot(FrozenModel):
    stage: Annotated[int, Field(ge=1, le=4)]
    evidence_checkpoint_turn: Literal[3, 7, 11, 15]
    learning_state: NonEmptyStr
    target_guidance: NonEmptyStr

    @model_validator(mode="after")
    def checkpoint_matches_stage(self) -> Self:
        if self.evidence_checkpoint_turn != (3, 7, 11, 15)[self.stage - 1]:
            raise ValueError("profile snapshot checkpoint does not match stage")
        if len(self.target_guidance.encode("utf-8")) > 3_000:
            raise ValueError("profile snapshot exceeds the frozen byte ceiling")
        return self


class PersonaProfileAuthorOutput(FrozenModel):
    output_version: Literal["1.0.0"] = "1.0.0"
    persona_id: Identifier
    snapshots: Annotated[
        tuple[PersonaProfileSnapshot, ...],
        Field(min_length=4, max_length=4),
    ]
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def snapshots_are_complete(self) -> Self:
        if tuple(item.stage for item in self.snapshots) != (1, 2, 3, 4):
            raise ValueError("profile author must return four ordered snapshots")
        return self


def persona_profile_output_schema() -> dict[str, object]:
    """Return the closed schema for one independently maintained persona profile."""

    schema = PersonaProfileAuthorOutput.model_json_schema()

    def close(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for value in node:
                close(value)

    close(schema)
    return schema


class PersonaAlternative(FrozenModel):
    alternative_id: Identifier
    content: NonEmptyStr


class PersonaTrackPair(FrozenModel):
    track: PersonaTrack
    alternatives: Annotated[tuple[PersonaAlternative, PersonaAlternative], Field(min_length=2)]

    @model_validator(mode="after")
    def alternatives_are_distinct(self) -> Self:
        if len({item.alternative_id for item in self.alternatives}) != 2:
            raise ValueError("persona track alternatives must be distinct")
        return self


class PersonaJudgePacket(FrozenModel):
    packet_version: Literal["1.0.0"] = "1.0.0"
    packet_id: Identifier
    case_id: Identifier
    persona_id: Identifier
    persona_summary: NonEmptyStr
    scenario: NonEmptyStr
    replicate: Literal[1, 2, 3]
    track_pairs: Annotated[tuple[PersonaTrackPair, PersonaTrackPair], Field(min_length=2)]
    condition_mapping_withheld: Literal[True] = True
    expected_answers_withheld: Literal[True] = True
    one_persona_only: Literal[True] = True
    prior_judgments_visible: Literal[False] = False

    @model_validator(mode="after")
    def tracks_are_complete(self) -> Self:
        if {item.track for item in self.track_pairs} != set(PersonaTrack):
            raise ValueError("persona judge packet requires both tracks")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PersonaTrackDecision(FrozenModel):
    track: PersonaTrack
    ordered_alternative_ids: Annotated[
        tuple[Identifier, ...],
        Field(min_length=2, max_length=2),
    ]
    preference: PersonaPreference
    rationale: Annotated[str, Field(min_length=20, max_length=1500)]

    @model_validator(mode="after")
    def alternatives_are_distinct(self) -> Self:
        if len(set(self.ordered_alternative_ids)) != 2:
            raise ValueError("persona decision alternatives must be distinct")
        return self

    @property
    def preferred_alternative_id(self) -> Identifier | None:
        """Derive the binding instead of trusting a redundant model-authored field."""

        return {
            PersonaPreference.FIRST: self.ordered_alternative_ids[0],
            PersonaPreference.SECOND: self.ordered_alternative_ids[1],
            PersonaPreference.TIE: None,
        }[self.preference]


class PersonaJudgeDecision(FrozenModel):
    decision_version: Literal["1.0.0"] = "1.0.0"
    packet_id: Identifier
    case_id: Identifier
    persona_id: Identifier
    decisions: Annotated[
        tuple[PersonaTrackDecision, ...],
        Field(min_length=2, max_length=2),
    ]
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def tracks_are_complete(self) -> Self:
        if {item.track for item in self.decisions} != set(PersonaTrack):
            raise ValueError("persona judge decision requires both tracks")
        return self


class PersonaModelTrackDecision(FrozenModel):
    """Minimal fallible model output before trusted host binding."""

    track: PersonaTrack
    preference: PersonaPreference
    rationale: Annotated[str, Field(min_length=20, max_length=1500)]


class PersonaModelJudgeDecision(FrozenModel):
    """Identity-free model output; the host supplies every custody binding."""

    decisions: Annotated[
        tuple[PersonaModelTrackDecision, ...],
        Field(min_length=2, max_length=2),
    ]
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def tracks_are_complete(self) -> Self:
        if {item.track for item in self.decisions} != set(PersonaTrack):
            raise ValueError("persona model decision requires both tracks")
        return self


class PersonaExecutionReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    execution_id: Identifier
    role: Literal["profile_author", "semantic_sensor", "judge", "adjudicator"]
    persona_id: Identifier
    case_id: Identifier | None = None
    packet_digest: Sha256Digest
    model: Literal["gpt-5.6-luna", "gpt-5.6-sol"]
    reasoning_effort: Literal["medium", "xhigh", "max"]
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
    trace_digest: Sha256Digest
    command_digest: Sha256Digest
    environment_digest: Sha256Digest
    fresh_ephemeral_session: Literal[True] = True
    exactly_one_persona: Literal[True] = True
    empty_workspace: Literal[True] = True
    host_home_visible: Literal[False] = False
    repository_visible: Literal[False] = False
    user_config_loaded: Literal[False] = False
    rules_loaded: Literal[False] = False
    memories_loaded: Literal[False] = False
    skills_loaded: Literal[False] = False
    plugins_loaded: Literal[False] = False
    mcp_loaded: Literal[False] = False
    prior_transcripts_loaded: Literal[False] = False
    tools_used: Literal[False] = False
    web_search_enabled: Literal[False] = False
    api_key_environment_present: Literal[False] = False
    saved_chatgpt_authentication: Literal[True] = True
    session_destroyed: Literal[True] = True
    external_validation_accessed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0


class PersonaTrackOutcome(FrozenModel):
    case_id: Identifier
    track: PersonaTrack
    xhigh_agreed: bool
    adjudicated: bool
    resolved_preference: PersonaPreference | None
    winning_condition: PersonaCondition | None


class PersonaEvaluationReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    benchmark_id: Identifier
    plan_digest: Sha256Digest
    case_count: Literal[24] = 24
    comparison_case_count: Literal[18] = 18
    sentinel_case_count: Literal[6] = 6
    xhigh_session_count: int = Field(ge=0, le=54)
    max_session_count: int = Field(ge=0, le=24)
    luna_session_count: int = Field(ge=0, le=18)
    total_session_count: int = Field(ge=0, le=102)
    outcomes: Annotated[tuple[PersonaTrackOutcome, ...], Field(min_length=48, max_length=48)]
    sentinel_learning_correct: int = Field(ge=0, le=6)
    sentinel_guidance_correct: int = Field(ge=0, le=6)
    learning_agreement_rate: float = Field(ge=0, le=1)
    guidance_agreement_rate: float = Field(ge=0, le=1)
    adjudication_rate: float = Field(ge=0, le=1)
    instrument_valid: bool
    compiled_lineage_complete: bool
    false_activation_count: int = Field(ge=0)
    revoked_or_superseded_leak_count: int = Field(ge=0)
    compiled_max_bytes: int = Field(ge=0, le=3000)
    compiled_median_bytes: float = Field(ge=0, allow_inf_nan=False)
    static_median_bytes: float = Field(ge=0, allow_inf_nan=False)
    interpretation: Literal[
        "instrument_failure",
        "compiled_negative",
        "compiled_directional_tie",
        "compiled_directional_positive",
    ]
    counts_toward_ordinary_use_gate: Literal[False] = False
    cross_agent_transfer_established: Literal[False] = False
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def totals_are_exact(self) -> Self:
        if len({(item.case_id, item.track) for item in self.outcomes}) != 48:
            raise ValueError("persona report requires exactly two outcomes per case")
        if self.total_session_count != (
            self.xhigh_session_count + self.max_session_count + self.luna_session_count
        ):
            raise ValueError("persona report session totals are inconsistent")
        if not self.instrument_valid and self.interpretation != "instrument_failure":
            raise ValueError("invalid persona instrument cannot compare conditions")
        return self


def persona_judge_output_schema() -> dict[str, object]:
    """Return a strict model-facing schema for one two-track persona judgment."""

    schema = PersonaModelJudgeDecision.model_json_schema()

    def close(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for value in node:
                close(value)

    close(schema)
    return schema


def bind_judge_decision(
    packet: PersonaJudgePacket,
    model_decision: PersonaModelJudgeDecision,
) -> PersonaJudgeDecision:
    """Bind a minimal model choice to exact trusted packet identities and option order."""

    model_by_track = {item.track: item for item in model_decision.decisions}
    return PersonaJudgeDecision(
        packet_id=packet.packet_id,
        case_id=packet.case_id,
        persona_id=packet.persona_id,
        decisions=tuple(
            PersonaTrackDecision(
                track=pair.track,
                ordered_alternative_ids=tuple(item.alternative_id for item in pair.alternatives),
                preference=model_by_track[pair.track].preference,
                rationale=model_by_track[pair.track].rationale,
            )
            for pair in packet.track_pairs
        ),
        limitations=model_decision.limitations,
    )


def validate_judge_decision(
    packet: PersonaJudgePacket,
    decision: PersonaJudgeDecision,
) -> PersonaJudgeDecision:
    """Fail closed unless a decision preserves the exact persona, case, and pair bindings."""

    if (
        decision.packet_id != packet.packet_id
        or decision.case_id != packet.case_id
        or decision.persona_id != packet.persona_id
    ):
        raise ValueError("persona judge substituted its packet identity")
    expected = {
        pair.track: tuple(item.alternative_id for item in pair.alternatives)
        for pair in packet.track_pairs
    }
    actual = {item.track: item.ordered_alternative_ids for item in decision.decisions}
    if actual != expected:
        raise ValueError("persona judge substituted or reordered an alternative pair")
    return decision


def _blind_id(seed: bytes, *, label: str, prefix: str) -> Identifier:
    if len(seed) != 32:
        raise ValueError("persona randomization seed must be 32 bytes")
    digest = hmac.new(seed, label.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}-{digest[:24]}"


def build_judge_packet(
    *,
    seed: bytes,
    persona: SyntheticPersona,
    case: PersonaEvaluationCase,
    compiled: PersonaConditionMaterial,
    comparator: PersonaConditionMaterial,
    replicate: Literal[1, 2, 3],
) -> tuple[PersonaJudgePacket, dict[Identifier, PersonaCondition]]:
    """Build one counterbalanced packet and retain its private condition mapping separately."""

    if len({compiled.case_id, comparator.case_id, case.case_id}) != 1:
        raise ValueError("persona packet materials must bind the same case")
    if len({compiled.persona_id, comparator.persona_id, persona.persona_id}) != 1:
        raise ValueError("persona packet cannot contain multiple personas")
    if compiled.condition is not PersonaCondition.COMPILED:
        raise ValueError("persona packet requires compiled material first")
    if case.sentinel:
        if comparator.condition is not PersonaCondition.CONTROLLED_SENTINEL:
            raise ValueError("neutral persona case requires a controlled sentinel")
    elif comparator.condition is not PersonaCondition.STRONG_STATIC:
        raise ValueError("comparison persona case requires strong static material")
    contents = {
        PersonaTrack.LEARNING_STATE: (compiled.learning_state, comparator.learning_state),
        PersonaTrack.TARGET_GUIDANCE: (compiled.target_guidance, comparator.target_guidance),
    }
    pairs: list[PersonaTrackPair] = []
    mapping: dict[Identifier, PersonaCondition] = {}
    for track in PersonaTrack:
        alternatives = []
        for condition, content in zip(
            (compiled.condition, comparator.condition), contents[track], strict=True
        ):
            alternative_id = _blind_id(
                seed,
                label=f"{case.case_id}:{track.value}:{condition.value}",
                prefix="alternative",
            )
            alternatives.append(PersonaAlternative(alternative_id=alternative_id, content=content))
            mapping[alternative_id] = condition
        reverse_adjudicator = (
            replicate == 3 and int(hashlib.sha256(case.case_id.encode()).hexdigest(), 16) % 2
        )
        if replicate == 2 or reverse_adjudicator:
            alternatives.reverse()
        pairs.append(PersonaTrackPair(track=track, alternatives=tuple(alternatives)))  # type: ignore[arg-type]
    if replicate == 2:
        pairs.reverse()
    packet = PersonaJudgePacket(
        packet_id=_blind_id(
            seed,
            label=f"{case.case_id}:replicate:{replicate}",
            prefix="packet",
        ),
        case_id=case.case_id,
        persona_id=persona.persona_id,
        persona_summary=persona.judge_summary,
        scenario=case.scenario,
        replicate=replicate,
        track_pairs=tuple(pairs),  # type: ignore[arg-type]
    )
    return packet, mapping


def resolve_track_votes(
    *,
    case_id: Identifier,
    track: PersonaTrack,
    first: PersonaCondition | None,
    second: PersonaCondition | None,
    adjudicator: PersonaCondition | None = None,
) -> PersonaTrackOutcome:
    """Resolve two independent votes, using an unseen third vote only on disagreement."""

    agreed = first == second
    votes = (first, second) if agreed else (first, second, adjudicator)
    counts = Counter(votes)
    counts.pop(None, None)
    winner = None
    if counts:
        highest = max(counts.values())
        leaders = tuple(item for item, count in counts.items() if count == highest)
        if len(leaders) == 1 and highest >= 2:
            winner = leaders[0]
    preference = None
    if winner is PersonaCondition.COMPILED:
        preference = PersonaPreference.FIRST
    elif winner in {PersonaCondition.STRONG_STATIC, PersonaCondition.CONTROLLED_SENTINEL}:
        preference = PersonaPreference.SECOND
    elif first is None and second is None and adjudicator is None:
        preference = PersonaPreference.TIE
    return PersonaTrackOutcome(
        case_id=case_id,
        track=track,
        xhigh_agreed=agreed,
        adjudicated=not agreed,
        resolved_preference=preference,
        winning_condition=winner,
    )
