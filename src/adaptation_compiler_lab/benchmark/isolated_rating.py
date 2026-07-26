"""Typed contracts for context-isolated AI blind preference ratings."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)

PairPreference = Literal["first_better", "second_better", "tie"]
RationaleText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=2000),
]


class BlindPairBinding(FrozenModel):
    """The exact public pair an isolated scorer must rate."""

    task_id: Identifier
    ordered_output_ids: Annotated[tuple[Identifier, Identifier], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def output_ids_are_distinct(self) -> Self:
        if len(set(self.ordered_output_ids)) != 2:
            raise ValueError("a blind rating pair requires two distinct outputs")
        return self


class IsolatedPairRating(FrozenModel):
    """One condition-blind comparison returned by the isolated scorer."""

    task_id: Identifier
    ordered_output_ids: Annotated[tuple[Identifier, Identifier], Field(min_length=2, max_length=2)]
    preference: PairPreference
    preferred_output_id: Identifier | None
    rationale: RationaleText

    @model_validator(mode="after")
    def preference_matches_output(self) -> Self:
        if len(set(self.ordered_output_ids)) != 2:
            raise ValueError("a blind rating pair requires two distinct outputs")
        expected = {
            "first_better": self.ordered_output_ids[0],
            "second_better": self.ordered_output_ids[1],
            "tie": None,
        }[self.preference]
        if self.preferred_output_id != expected:
            raise ValueError("preferred output does not match the pairwise preference")
        return self


class IsolatedBlindRatingDecision(FrozenModel):
    """Strict final JSON emitted from a blank rating context."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    pair_ratings: Annotated[
        tuple[IsolatedPairRating, IsolatedPairRating],
        Field(min_length=2, max_length=2),
    ]
    overall_assessment: RationaleText
    evaluator_limitations: Annotated[
        tuple[NonEmptyStr, ...],
        Field(min_length=1, max_length=6),
    ]

    @model_validator(mode="after")
    def pairs_are_unique(self) -> Self:
        if len({item.task_id for item in self.pair_ratings}) != 2:
            raise ValueError("isolated rating must cover two unique tasks")
        return self


class IsolatedAIRatingReceipt(FrozenModel):
    """Durable minimized rating evidence created before condition reveal."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    rating_id: Identifier
    benchmark_id: Identifier
    presentation_sha256: Sha256Digest
    blind_report_digest: Sha256Digest
    completion_receipt_digest: Sha256Digest
    rating_contract_digest: Sha256Digest
    output_schema_digest: Sha256Digest
    decision: IsolatedBlindRatingDecision
    scorer_kind: Literal["isolated_ai"] = "isolated_ai"
    scorer_provider: Literal["openai"] = "openai"
    scorer_surface: Literal["codex_cli"] = "codex_cli"
    scorer_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    scorer_reasoning_effort: Literal["xhigh"] = "xhigh"
    scorer_service_mode: Literal["standard"] = "standard"
    codex_cli_version: Literal["codex-cli 0.145.0"] = "codex-cli 0.145.0"
    codex_cli_digest: Sha256Digest
    execution_environment_digest: Sha256Digest
    command_digest: Sha256Digest
    trace_digest: Sha256Digest
    trace_ref_digest: Sha256Digest
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
    rated_at: UtcDateTime
    context_inputs: Literal["rating_contract_and_anonymous_packet_only"] = (
        "rating_contract_and_anonymous_packet_only"
    )
    fresh_ephemeral_session: Literal[True] = True
    empty_workspace: Literal[True] = True
    host_home_visible: Literal[False] = False
    project_repository_visible: Literal[False] = False
    user_config_loaded: Literal[False] = False
    user_rules_loaded: Literal[False] = False
    memories_loaded: Literal[False] = False
    skills_loaded: Literal[False] = False
    plugins_loaded: Literal[False] = False
    mcp_loaded: Literal[False] = False
    prior_transcripts_loaded: Literal[False] = False
    network_search_enabled: Literal[False] = False
    tool_use_observed: Literal[False] = False
    api_key_environment_present: Literal[False] = False
    saved_chatgpt_authentication: Literal[True] = True
    condition_mapping_seen: Literal[False] = False
    objective_scores_seen: Literal[False] = False
    milestone_6_custody_accessed: Literal[False] = False


def validate_blind_pair_coverage(
    decision: IsolatedBlindRatingDecision,
    expected_pairs: tuple[BlindPairBinding, BlindPairBinding],
) -> IsolatedBlindRatingDecision:
    """Fail closed unless the scorer rated each frozen public pair exactly once."""

    actual = {item.task_id: item.ordered_output_ids for item in decision.pair_ratings}
    expected = {item.task_id: item.ordered_output_ids for item in expected_pairs}
    if actual != expected:
        raise ValueError("isolated rating substituted or omitted a blind output pair")
    return decision
