"""Typed receipts for internally blinded, functionally separated study roles."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.models import BlindTaskId
from adaptation_compiler_lab.domain.base import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest


class InternalStudyRole(StrEnum):
    """Functionally separated roles used by the internal feasibility pilot."""

    PROFILE_AUTHOR = "profile_author"
    PROFILE_REVIEWER = "profile_reviewer"
    HELDOUT_TASK_AUTHOR = "heldout_task_author"
    SOFTWARE_CUSTODIAN = "software_custodian"
    PREFERENCE_SCORER = "preference_scorer"
    SECONDARY_AI_JUDGE = "secondary_ai_judge"


class ApprovedSourceFamily(StrEnum):
    """Kevin-confirmed source families for the eight-task construction corpus."""

    COMMUNICATION = "communication"
    ENVIRONMENT_SAFETY = "environment_safety"
    DEBUGGING_AND_VERIFICATION = "debugging_and_verification"
    RESEARCH_INTEGRITY = "research_integrity"


class ApprovedCorpusItem(FrozenModel):
    """One consent-eligible explicit user message supplied to profile contexts."""

    evidence_id: Identifier
    task_id: Identifier
    observed_at: UtcDateTime
    text: NonEmptyStr
    authority: Literal["explicit_user_feedback"] = "explicit_user_feedback"


class ApprovedBehavioralEvaluation(FrozenModel):
    """One Kevin-confirmed behavioral evaluation, not a compiled artifact."""

    evaluation_id: Identifier
    source_task_id: Identifier
    source_family: ApprovedSourceFamily
    statement: NonEmptyStr
    approval_digest: Sha256Digest


class ApprovedTrainingCorpus(FrozenModel):
    """Exact profile-author corpus containing user-authority content only."""

    corpus_version: Literal["1.0.0"] = "1.0.0"
    corpus_id: Identifier
    source_task_count: Literal[8] = 8
    source_families: Annotated[
        tuple[ApprovedSourceFamily, ...],
        Field(min_length=4, max_length=4),
    ] = (
        ApprovedSourceFamily.COMMUNICATION,
        ApprovedSourceFamily.ENVIRONMENT_SAFETY,
        ApprovedSourceFamily.DEBUGGING_AND_VERIFICATION,
        ApprovedSourceFamily.RESEARCH_INTEGRITY,
    )
    items: Annotated[tuple[ApprovedCorpusItem, ...], Field(min_length=1)]
    approved_evaluations: Annotated[
        tuple[ApprovedBehavioralEvaluation, ...],
        Field(min_length=8, max_length=8),
    ]
    agent_content_included: Literal[False] = False
    tool_content_included: Literal[False] = False
    web_content_included: Literal[False] = False
    repository_content_included: Literal[False] = False
    compiled_artifact_content_included: Literal[False] = False
    created_at: UtcDateTime

    @model_validator(mode="after")
    def corpus_is_complete_and_canonical(self) -> ApprovedTrainingCorpus:
        if self.source_families != tuple(ApprovedSourceFamily):
            raise ValueError("approved source families must be complete and ordered")
        evidence_ids = tuple(item.evidence_id for item in self.items)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("approved corpus Evidence IDs must be unique")
        task_ids = {item.task_id for item in self.items}
        if len(task_ids) != self.source_task_count:
            raise ValueError("approved corpus must contain exactly eight source tasks")
        evaluation_ids = tuple(item.evaluation_id for item in self.approved_evaluations)
        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("approved behavioral evaluation IDs must be unique")
        if not {item.source_task_id for item in self.approved_evaluations} <= task_ids:
            raise ValueError("approved evaluation references a task outside the corpus")
        if {item.source_family for item in self.approved_evaluations} != set(self.source_families):
            raise ValueError("approved evaluations must span all confirmed source families")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ProfileAuthorTaskPacket(FrozenModel):
    """Complete allowed input to the first isolated profile context."""

    packet_version: Literal["1.0.0"] = "1.0.0"
    role_packet: IsolatedRolePacket
    corpus: ApprovedTrainingCorpus
    objective: Literal[
        "produce_the_strongest_concise_static_profile_supported_by_the_approved_corpus"
    ] = "produce_the_strongest_concise_static_profile_supported_by_the_approved_corpus"
    required_sections: tuple[NonEmptyStr, ...]
    maximum_utf8_bytes: Literal[12000] = 12000
    maximum_target_tokens: Literal[3000] = 3000

    @model_validator(mode="after")
    def packet_matches_author_role_and_corpus(self) -> ProfileAuthorTaskPacket:
        if self.role_packet.role is not InternalStudyRole.PROFILE_AUTHOR:
            raise ValueError("profile-author task packet has the wrong role")
        if self.role_packet.eligible_input_digests != (self.corpus.content_digest,):
            raise ValueError("profile-author role packet does not bind its only corpus input")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ProfileReviewTaskPacket(FrozenModel):
    """Allowed input to the distinct strengthening/review context."""

    packet_version: Literal["1.0.0"] = "1.0.0"
    role_packet: IsolatedRolePacket
    corpus: ApprovedTrainingCorpus
    draft_text: NonEmptyStr
    draft_digest: Sha256Digest
    objective: Literal["strengthen_the_static_profile_without_adding_unsupported_behavior"] = (
        "strengthen_the_static_profile_without_adding_unsupported_behavior"
    )
    maximum_utf8_bytes: Literal[12000] = 12000
    maximum_target_tokens: Literal[3000] = 3000

    @model_validator(mode="after")
    def packet_matches_review_role_and_draft(self) -> ProfileReviewTaskPacket:
        if self.role_packet.role is not InternalStudyRole.PROFILE_REVIEWER:
            raise ValueError("profile-review task packet has the wrong role")
        expected_draft = canonical_digest({"draft_text": self.draft_text})
        if self.draft_digest != expected_draft:
            raise ValueError("profile-review draft digest does not match text")
        expected_inputs = tuple(sorted((self.corpus.content_digest, self.draft_digest)))
        if self.role_packet.eligible_input_digests != expected_inputs:
            raise ValueError("profile-review role packet does not bind corpus and draft")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class IsolatedRolePacket(FrozenModel):
    """Digest-bound allowed inputs and forbidden knowledge for one isolated context."""

    packet_version: Literal["1.0.0"] = "1.0.0"
    packet_id: Identifier
    benchmark_id: Identifier
    role: InternalStudyRole
    eligible_input_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=1)]
    allowed_outputs: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    held_out_content_allowed: bool
    compiled_adaptation_allowed: bool
    condition_mapping_allowed: bool
    trial_results_allowed: bool
    network_access_allowed: Literal[False] = False
    ambient_memory_allowed: Literal[False] = False
    created_at: UtcDateTime

    @field_validator("eligible_input_digests", "allowed_outputs")
    @classmethod
    def values_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("role-packet values must be sorted and unique")
        return value

    @model_validator(mode="after")
    def role_has_exact_knowledge_boundary(self) -> IsolatedRolePacket:
        expected = {
            InternalStudyRole.PROFILE_AUTHOR: (False, False, False, False),
            InternalStudyRole.PROFILE_REVIEWER: (False, False, False, False),
            InternalStudyRole.HELDOUT_TASK_AUTHOR: (True, False, False, False),
            InternalStudyRole.SOFTWARE_CUSTODIAN: (True, False, True, False),
            InternalStudyRole.PREFERENCE_SCORER: (True, False, False, True),
            InternalStudyRole.SECONDARY_AI_JUDGE: (True, False, False, True),
        }[self.role]
        observed = (
            self.held_out_content_allowed,
            self.compiled_adaptation_allowed,
            self.condition_mapping_allowed,
            self.trial_results_allowed,
        )
        if observed != expected:
            raise ValueError("role packet grants knowledge outside the frozen role boundary")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class IsolatedContextReceipt(FrozenModel):
    """Minimized proof that one fresh context stayed inside its role packet."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    benchmark_id: Identifier
    context_id: Identifier
    actor_identity: NonEmptyStr
    role: InternalStudyRole
    packet_digest: Sha256Digest
    consumed_input_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=1)]
    output_digest: Sha256Digest
    started_at: UtcDateTime
    completed_at: UtcDateTime
    held_out_content_accessed: bool
    compiled_adaptation_accessed: Literal[False] = False
    condition_mapping_accessed: bool
    trial_results_accessed: bool
    ambient_memory_accessed: Literal[False] = False
    network_accessed: Literal[False] = False

    @field_validator("consumed_input_digests")
    @classmethod
    def inputs_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("context input digests must be sorted and unique")
        return value

    @model_validator(mode="after")
    def receipt_is_coherent(self) -> IsolatedContextReceipt:
        if self.completed_at < self.started_at:
            raise ValueError("context completion cannot precede its start")
        expected = {
            InternalStudyRole.PROFILE_AUTHOR: (False, False, False),
            InternalStudyRole.PROFILE_REVIEWER: (False, False, False),
            InternalStudyRole.HELDOUT_TASK_AUTHOR: (True, False, False),
            InternalStudyRole.SOFTWARE_CUSTODIAN: (True, True, False),
            InternalStudyRole.PREFERENCE_SCORER: (True, False, True),
            InternalStudyRole.SECONDARY_AI_JUDGE: (True, False, True),
        }[self.role]
        observed = (
            self.held_out_content_accessed,
            self.condition_mapping_accessed,
            self.trial_results_accessed,
        )
        if observed != expected:
            raise ValueError("context receipt does not match its functional role")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BlindOutputDescriptor(FrozenModel):
    """One condition-free output reference shown to the preference scorer."""

    blind_output_id: Identifier
    trial_id: Identifier
    diff_digest: Sha256Digest
    independent_test_digest: Sha256Digest
    rubric_digest: Sha256Digest
    presentation_digest: Sha256Digest


class BlindPreferenceScoringPacket(FrozenModel):
    """Randomized outputs for one task with no condition labels or mapping."""

    packet_version: Literal["1.0.0"] = "1.0.0"
    packet_id: Identifier
    benchmark_id: Identifier
    blind_task_id: BlindTaskId
    outputs: Annotated[tuple[BlindOutputDescriptor, ...], Field(min_length=8, max_length=8)]
    output_order_commitment: Sha256Digest
    condition_mapping_withheld: Literal[True] = True
    created_at: UtcDateTime

    @field_validator("outputs")
    @classmethod
    def outputs_are_unique(
        cls,
        value: tuple[BlindOutputDescriptor, ...],
    ) -> tuple[BlindOutputDescriptor, ...]:
        output_ids = tuple(item.blind_output_id for item in value)
        trial_ids = tuple(item.trial_id for item in value)
        if len(output_ids) != len(set(output_ids)) or len(trial_ids) != len(set(trial_ids)):
            raise ValueError("blind scoring outputs and trial IDs must be unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PreferenceRating(FrozenModel):
    """Kevin's condition-blind subjective rating for one anonymous output."""

    rating_id: Identifier
    scoring_packet_digest: Sha256Digest
    blind_output_id: Identifier
    requirement_and_preference_fit: int = Field(ge=0, le=4)
    change_discipline_and_maintainability: int = Field(ge=0, le=4)
    severe_behavioral_violation: bool
    notes_digest: Sha256Digest | None = None
    scorer_identity: Literal["kevin"] = "kevin"
    condition_label_seen: Literal[False] = False
    rated_at: UtcDateTime


class SecondaryAIQualityRating(FrozenModel):
    """Non-authoritative isolated-AI quality annotation."""

    rating_id: Identifier
    scoring_packet_digest: Sha256Digest
    blind_output_id: Identifier
    general_quality: int = Field(ge=0, le=4)
    requirement_coverage: int = Field(ge=0, le=4)
    maintainability: int = Field(ge=0, le=4)
    rationale_digest: Sha256Digest
    judge_context_receipt_digest: Sha256Digest
    may_override_preference_scorer: Literal[False] = False
    rated_at: UtcDateTime


ProfileAuthorTaskPacket.model_rebuild()
ProfileReviewTaskPacket.model_rebuild()
