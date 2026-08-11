"""Synthetic, repository-informed calibration for the semantic feedback sensor.

The stimulation lane is deliberately separate from dogfood evidence. Repository archetypes are
privacy-minimized before scenario construction, generated messages are synthetic, and every
persistent receipt states that the material is neither user authority nor promotion eligible.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticScopeHint,
)
from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticCaseEvaluation,
    SemanticEvaluationReport,
    SemanticFeedbackCase,
    SemanticFeedbackCorpus,
    SemanticFeedbackExpectation,
)
from adaptation_compiler_lab.domain import (
    ArtifactRoute,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest


class StimulationPolarity(StrEnum):
    """Whether one case should or should not yield an evaluation candidate."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


class StimulationStyle(StrEnum):
    """Controlled surface-form variations used across the corpus."""

    ACRONYM = "acronym"
    BAD_GRAMMAR = "bad_grammar"
    CLEAN = "clean"
    EMPHATIC = "emphatic"
    FRAGMENT = "fragment"
    INDIRECT = "indirect"
    MIXED_INTENT = "mixed_intent"
    NEGATION = "negation"
    SLANG = "slang"
    TYPO = "typo"


class StimulationSemanticClass(StrEnum):
    """Controlled behavioral distinction a scenario is intended to exercise."""

    CORRECTION = "correction"
    HYPOTHETICAL = "hypothetical"
    IMMEDIATE_TASK = "immediate_task"
    INFERRED_TOPIC = "inferred_topic"
    MEMORY = "memory"
    PAST_PREFERENCE = "past_preference"
    POSITIVE_EXAMPLE = "positive_example"
    PREFERENCE = "preference"
    PROMPT_INJECTION_QUOTE = "prompt_injection_quote"
    PROMPT_RULE = "prompt_rule"
    PROCEDURE = "procedure"
    QUOTED_AUTHORITY = "quoted_authority"
    REVOCATION = "revocation"
    TASK_REQUEST = "task_request"
    UNDECIDED = "undecided"


class RepositoryArchetype(FrozenModel):
    """Privacy-minimized categories derived from one repository under read-only access."""

    context_id: Identifier
    project_family: Literal[
        "developer_tool",
        "web_application",
        "service",
        "library",
        "data_project",
        "content_project",
        "mixed",
    ]
    language_classes: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    workflow_classes: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    interaction_topics: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    safety_notes: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    contains_names_paths_code_or_secrets: Literal[False]

    @field_validator(
        "language_classes",
        "workflow_classes",
        "interaction_topics",
        "safety_notes",
    )
    @classmethod
    def categories_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("repository archetype categories must be unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RepositoryArchetypeReceipt(FrozenModel):
    """Raw-free binding to one externally retained repository archetype."""

    context_id: Identifier
    archetype_digest: Sha256Digest
    source_access: Literal["read_only"] = "read_only"
    source_write_permitted: Literal[False] = False
    raw_repository_content_retained: Literal[False] = False


class SemanticStimulationScenario(FrozenModel):
    """A label-first scenario whose wording is generated only after labels are frozen."""

    case_id: Identifier
    split: Literal["calibration", "holdout"]
    context_id: Identifier
    turn_index: Literal[1, 3, 5, 10, 15]
    polarity: StimulationPolarity
    semantic_class: StimulationSemanticClass
    style: StimulationStyle
    generation_brief: NonEmptyStr
    tags: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    expectation: SemanticFeedbackExpectation

    @field_validator("tags")
    @classmethod
    def tags_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("stimulation tags must be sorted and unique")
        return value

    @model_validator(mode="after")
    def polarity_matches_expectation(self) -> SemanticStimulationScenario:
        expected_positive = self.polarity is StimulationPolarity.POSITIVE
        if self.expectation.durable_signal is not expected_positive:
            raise ValueError("stimulation polarity disagrees with its frozen expectation")
        return self


class SemanticStimulationPlan(FrozenModel):
    """Frozen balanced design for repository-informed synthetic calibration."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    plan_id: Identifier
    created_at: UtcDateTime
    cases: Annotated[tuple[SemanticStimulationScenario, ...], Field(min_length=100, max_length=100)]

    @field_validator("cases")
    @classmethod
    def cases_are_sorted_unique(
        cls,
        value: tuple[SemanticStimulationScenario, ...],
    ) -> tuple[SemanticStimulationScenario, ...]:
        case_ids = tuple(case.case_id for case in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("stimulation cases must be sorted by unique case ID")
        return value

    @model_validator(mode="after")
    def design_is_balanced(self) -> SemanticStimulationPlan:
        contexts = {case.context_id for case in self.cases}
        if len(contexts) != 5:
            raise ValueError("stimulation plan requires exactly five anonymous contexts")
        for split in ("calibration", "holdout"):
            selected = tuple(case for case in self.cases if case.split == split)
            positives = tuple(
                case for case in selected if case.polarity is StimulationPolarity.POSITIVE
            )
            negatives = tuple(
                case for case in selected if case.polarity is StimulationPolarity.NEGATIVE
            )
            if len(selected) != 50 or len(positives) != 25 or len(negatives) != 25:
                raise ValueError("each stimulation split requires 25 positives and 25 negatives")
            for context_id in contexts:
                if sum(case.context_id == context_id for case in selected) != 10:
                    raise ValueError("each split requires ten cases per anonymous context")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticStimulationProtocol(FrozenModel):
    """Fail-closed declaration separating synthetic stimulation from user learning."""

    protocol_version: Literal["1.0.0"] = "1.0.0"
    protocol_id: Identifier
    created_at: UtcDateTime
    source_access_mode: Literal["read_only_privacy_minimized_archetypes"]
    archetypes: Annotated[tuple[RepositoryArchetypeReceipt, ...], Field(min_length=5, max_length=5)]
    plan_digest: Sha256Digest
    generation_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    generation_reasoning_effort: Literal["low"] = "low"
    audit_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    audit_reasoning_effort: Literal["low"] = "low"
    detector_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    detector_reasoning_effort: Literal["medium"] = "medium"
    authentication: Literal["saved_chatgpt_subscription"] = "saved_chatgpt_subscription"
    provider_billed_cost_usd: Literal[0] = 0
    synthetic_only: Literal[True] = True
    synthetic_is_user_authority: Literal[False] = False
    production_promotion_permitted: Literal[False] = False
    production_state_mutation_permitted: Literal[False] = False
    sealed_external_validation_access_permitted: Literal[False] = False
    raw_repository_content_retained: Literal[False] = False

    @field_validator("archetypes")
    @classmethod
    def archetypes_are_sorted_unique(
        cls,
        value: tuple[RepositoryArchetypeReceipt, ...],
    ) -> tuple[RepositoryArchetypeReceipt, ...]:
        context_ids = tuple(item.context_id for item in value)
        if not strings_are_sorted_unique(context_ids):
            raise ValueError("archetype receipts must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticStimulationGeneratedItem(FrozenModel):
    """Synthetic wording for one already-labeled scenario."""

    case_id: Identifier
    text: str = Field(min_length=1, max_length=500)


class SemanticStimulationGeneration(FrozenModel):
    """One isolated model batch containing wording but no authority."""

    generation_version: Literal["1.0.0", "1.1.0", "1.2.0", "1.3.0"] = "1.0.0"
    source_plan_digest: Sha256Digest
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["low"] = "low"
    synthetic_only: Literal[True] = True
    items: Annotated[
        tuple[SemanticStimulationGeneratedItem, ...],
        Field(min_length=100, max_length=100),
    ]

    @field_validator("items")
    @classmethod
    def items_are_sorted_unique(
        cls,
        value: tuple[SemanticStimulationGeneratedItem, ...],
    ) -> tuple[SemanticStimulationGeneratedItem, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("generated stimulation items must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticStimulationRemediation(FrozenModel):
    """Replacement wording for exactly the cases rejected by an independent audit."""

    remediation_version: Literal["1.0.0"] = "1.0.0"
    source_generation_digest: Sha256Digest
    source_audit_digest: Sha256Digest
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["low"] = "low"
    synthetic_only: Literal[True] = True
    items: Annotated[
        tuple[SemanticStimulationGeneratedItem, ...],
        Field(min_length=1, max_length=100),
    ]

    @field_validator("items")
    @classmethod
    def items_are_sorted_unique(
        cls,
        value: tuple[SemanticStimulationGeneratedItem, ...],
    ) -> tuple[SemanticStimulationGeneratedItem, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("stimulation remediation items must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class StimulationAuditVerdict(StrEnum):
    """Whether generated wording cleanly realizes its frozen label."""

    AMBIGUOUS = "ambiguous"
    FAIL = "fail"
    PASS = "pass"


class StimulationAuditReason(StrEnum):
    """Bounded audit findings that cannot carry repository content."""

    CLEAN = "clean"
    DURABILITY_MISMATCH = "durability_mismatch"
    IDENTIFYING_DETAIL = "identifying_detail"
    LABEL_MISMATCH = "label_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    UNEXPRESSED_ASSUMPTION = "unexpressed_assumption"


class SemanticStimulationAuditEntry(FrozenModel):
    """Raw-free audit verdict for one generated case."""

    case_id: Identifier
    verdict: StimulationAuditVerdict
    reason: StimulationAuditReason

    @model_validator(mode="after")
    def pass_has_clean_reason(self) -> SemanticStimulationAuditEntry:
        if (self.verdict is StimulationAuditVerdict.PASS) != (
            self.reason is StimulationAuditReason.CLEAN
        ):
            raise ValueError("only a passing audit entry may use the clean reason")
        return self


class SemanticStimulationAuditProposal(FrozenModel):
    """Schema-bound output from a separate isolated audit context."""

    audit_version: Literal["1.0.0"] = "1.0.0"
    source_generation_digest: Sha256Digest
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["low"] = "low"
    entries: Annotated[
        tuple[SemanticStimulationAuditEntry, ...],
        Field(min_length=100, max_length=100),
    ]

    @field_validator("entries")
    @classmethod
    def entries_are_sorted_unique(
        cls,
        value: tuple[SemanticStimulationAuditEntry, ...],
    ) -> tuple[SemanticStimulationAuditEntry, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("stimulation audit entries must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticStimulationIncrementalAudit(FrozenModel):
    """Audit proposal limited to wording changed after a complete prior audit."""

    audit_version: Literal["1.0.0"] = "1.0.0"
    source_generation_digest: Sha256Digest
    base_generation_digest: Sha256Digest
    base_audit_digest: Sha256Digest
    changed_case_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=100)]
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["low"] = "low"
    entries: Annotated[
        tuple[SemanticStimulationAuditEntry, ...],
        Field(min_length=1, max_length=100),
    ]

    @field_validator("changed_case_ids")
    @classmethod
    def changed_cases_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("incremental audit changed cases must be sorted and unique")
        return value

    @field_validator("entries")
    @classmethod
    def entries_are_sorted_unique(
        cls,
        value: tuple[SemanticStimulationAuditEntry, ...],
    ) -> tuple[SemanticStimulationAuditEntry, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("incremental audit entries must be sorted and unique")
        return value

    @model_validator(mode="after")
    def entries_match_changed_cases(self) -> SemanticStimulationIncrementalAudit:
        if tuple(item.case_id for item in self.entries) != self.changed_case_ids:
            raise ValueError("incremental audit entries must equal the changed cases")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticStimulationSliceMetrics(FrozenModel):
    """Detection, routing, and scope metrics for one controlled slice."""

    dimension: Literal["context", "semantic_class", "split", "style", "turn"]
    slice_id: Identifier
    case_count: int = Field(ge=1)
    expected_positive: int = Field(ge=0)
    expected_negative: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    detection_accuracy: float = Field(ge=0, le=1)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    negative_specificity: float = Field(ge=0, le=1)
    route_accuracy: float = Field(ge=0, le=1)
    scope_accuracy: float = Field(ge=0, le=1)


class SemanticStimulationSummary(FrozenModel):
    """Raw-free diagnostic result; never a production-promotion receipt."""

    summary_version: Literal["1.0.0"] = "1.0.0"
    created_at: UtcDateTime
    protocol_digest: Sha256Digest
    plan_digest: Sha256Digest
    generation_digest: Sha256Digest
    audit_digest: Sha256Digest
    corpus_digest: Sha256Digest
    calibration_report_digest: Sha256Digest
    holdout_report_digest: Sha256Digest
    case_count: Literal[100] = 100
    detector_gate_passed: bool
    synthetic_only: Literal[True] = True
    synthetic_is_user_authority: Literal[False] = False
    production_promotion_permitted: Literal[False] = False
    production_state_mutated: Literal[False] = False
    slices: tuple[SemanticStimulationSliceMetrics, ...]
    failed_case_ids: tuple[Identifier, ...]

    @field_validator("failed_case_ids")
    @classmethod
    def failures_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("stimulation failures must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


_STYLES = tuple(StimulationStyle)
_TURN_INDICES: tuple[Literal[1, 3, 5, 10, 15], ...] = (1, 3, 5, 10, 15)


def _sorted_kinds(*values: FeedbackSignalKind) -> tuple[FeedbackSignalKind, ...]:
    return tuple(sorted(values, key=lambda item: item.value))


def _sorted_routes(*values: ArtifactRoute) -> tuple[ArtifactRoute, ...]:
    return tuple(sorted(values, key=lambda item: item.value))


def _positive_spec(
    variant: int,
    *,
    topic: str,
    context_id: str,
) -> tuple[StimulationSemanticClass, str, SemanticFeedbackExpectation]:
    if variant == 0:
        return (
            StimulationSemanticClass.PREFERENCE,
            f"Express a stable cross-project preference concerning {topic} in future work.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=(FeedbackSignalKind.PREFERENCE,),
                accepted_routes=(ArtifactRoute.PREFERENCE,),
                scope_hint=SemanticScopeHint.PERMANENT_PROFILE,
            ),
        )
    if variant == 1:
        return (
            StimulationSemanticClass.PROCEDURE,
            f"State a repeatable workflow concerning {topic}, explicitly limited to this project.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=_sorted_kinds(
                    FeedbackSignalKind.PROCEDURE,
                    FeedbackSignalKind.PROMPT_RULE,
                ),
                accepted_routes=_sorted_routes(
                    ArtifactRoute.PROCEDURE,
                    ArtifactRoute.PROMPT_RULE,
                ),
                scope_hint=SemanticScopeHint.CURRENT_CONTEXT,
            ),
        )
    if variant == 2:
        return (
            StimulationSemanticClass.PROMPT_RULE,
            f"Give an explicit standing requirement or prohibition concerning {topic}.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=_sorted_kinds(
                    FeedbackSignalKind.PREFERENCE,
                    FeedbackSignalKind.PROMPT_RULE,
                ),
                accepted_routes=_sorted_routes(
                    ArtifactRoute.PREFERENCE,
                    ArtifactRoute.PROMPT_RULE,
                ),
                scope_hint=SemanticScopeHint.PERMANENT_PROFILE,
            ),
        )
    if variant == 3:
        return (
            StimulationSemanticClass.CORRECTION,
            "Correct a just-observed assistant behavior and explicitly make the correction the "
            f"future rule for this project, concerning {topic}.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=_sorted_kinds(
                    FeedbackSignalKind.CORRECTION,
                    FeedbackSignalKind.PROCEDURE,
                    FeedbackSignalKind.PROMPT_RULE,
                ),
                accepted_routes=_sorted_routes(
                    ArtifactRoute.PROCEDURE,
                    ArtifactRoute.PROMPT_RULE,
                ),
                scope_hint=SemanticScopeHint.CURRENT_CONTEXT,
            ),
        )
    specialty = int(context_id[-1], 36) % 5
    if specialty == 0:
        return (
            StimulationSemanticClass.MEMORY,
            "State a non-sensitive fact about the synthetic user that will matter in later tasks.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=(FeedbackSignalKind.MEMORY,),
                accepted_routes=(ArtifactRoute.MEMORY,),
                scope_hint=SemanticScopeHint.PERMANENT_PROFILE,
            ),
        )
    if specialty == 1:
        return (
            StimulationSemanticClass.POSITIVE_EXAMPLE,
            "Endorse a just-shown response pattern and explicitly request using that pattern "
            "later.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=(FeedbackSignalKind.POSITIVE_EXAMPLE,),
                accepted_routes=(ArtifactRoute.EXAMPLE,),
                scope_hint=SemanticScopeHint.PERMANENT_PROFILE,
            ),
        )
    if specialty == 2:
        artifact_id = f"artifact-{context_id}-behavior"
        return (
            StimulationSemanticClass.REVOCATION,
            f"Explicitly request removal of the exact active artifact ID {artifact_id}.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=(FeedbackSignalKind.REVOCATION,),
                accepted_routes=(),
                scope_hint=SemanticScopeHint.CURRENT_CONTEXT,
            ),
        )
    if specialty == 3:
        return (
            StimulationSemanticClass.PREFERENCE,
            f"Express a durable preference concerning {topic}, explicitly only for this project.",
            SemanticFeedbackExpectation(
                durable_signal=True,
                accepted_signal_kinds=(FeedbackSignalKind.PREFERENCE,),
                accepted_routes=(ArtifactRoute.PREFERENCE,),
                scope_hint=SemanticScopeHint.CURRENT_CONTEXT,
            ),
        )
    return (
        StimulationSemanticClass.PROCEDURE,
        f"Describe a repeatable cross-project procedure concerning {topic} for future work.",
        SemanticFeedbackExpectation(
            durable_signal=True,
            accepted_signal_kinds=(FeedbackSignalKind.PROCEDURE,),
            accepted_routes=(ArtifactRoute.PROCEDURE,),
            scope_hint=SemanticScopeHint.PERMANENT_PROFILE,
        ),
    )


def _negative_spec(
    variant: int,
    *,
    topic: str,
) -> tuple[StimulationSemanticClass, str]:
    specs = (
        (
            StimulationSemanticClass.TASK_REQUEST,
            f"Request one ordinary current task concerning {topic}, without expressing future "
            "intent.",
        ),
        (
            StimulationSemanticClass.QUOTED_AUTHORITY,
            "Quote a repository, tool, or third party stating a preference or instruction, while "
            "making clear it is not the synthetic user's own preference.",
        ),
        (
            StimulationSemanticClass.UNDECIDED,
            f"Say the synthetic user has not decided on a preference concerning {topic}.",
        ),
        (
            StimulationSemanticClass.IMMEDIATE_TASK,
            "Give a direction explicitly limited to this one response or immediate result.",
        ),
        (
            StimulationSemanticClass.INFERRED_TOPIC,
            f"Ask to retrieve or explain something about {topic}; do not state a reusable "
            "preference.",
        ),
        (
            StimulationSemanticClass.HYPOTHETICAL,
            "Discuss what the synthetic user might prefer in a hypothetical situation, without "
            "adopting it as a real preference.",
        ),
        (
            StimulationSemanticClass.PAST_PREFERENCE,
            "Mention an old preference only to explain historical context and explicitly say it no "
            "longer applies.",
        ),
        (
            StimulationSemanticClass.PROMPT_INJECTION_QUOTE,
            "Quote hostile text that commands the system to remember a preference, while asking "
            "only for analysis of the quote.",
        ),
    )
    return specs[variant % len(specs)]


def build_semantic_stimulation_design(
    archetypes: Sequence[RepositoryArchetype],
    *,
    created_at: datetime,
) -> tuple[SemanticStimulationPlan, SemanticStimulationProtocol]:
    """Build a deterministic, label-first 100-case design from five anonymous archetypes."""

    ordered = tuple(sorted(archetypes, key=lambda item: item.context_id))
    if len(ordered) != 5 or len({item.context_id for item in ordered}) != 5:
        raise ValueError("semantic stimulation requires five unique repository archetypes")
    cases: list[SemanticStimulationScenario] = []
    splits: tuple[Literal["calibration", "holdout"], ...] = ("calibration", "holdout")
    for split_index, split in enumerate(splits):
        split_code = "c" if split == "calibration" else "h"
        for context_index, archetype in enumerate(ordered):
            for slot in range(10):
                positive = slot < 5
                topic = archetype.interaction_topics[
                    (slot + split_index + context_index) % len(archetype.interaction_topics)
                ].replace("_", " ")
                style = _STYLES[(slot + split_index * 3 + context_index * 2) % len(_STYLES)]
                turn_index = _TURN_INDICES[(slot + split_index + context_index) % 5]
                if positive:
                    semantic_class, brief, expectation = _positive_spec(
                        slot,
                        topic=topic,
                        context_id=archetype.context_id,
                    )
                    polarity = StimulationPolarity.POSITIVE
                else:
                    semantic_class, brief = _negative_spec(
                        slot - 5 + split_index * 2 + context_index,
                        topic=topic,
                    )
                    expectation = SemanticFeedbackExpectation(durable_signal=False)
                    polarity = StimulationPolarity.NEGATIVE
                case_id = f"stim-{split_code}-{context_index + 1:02d}-{slot + 1:02d}"
                tags = tuple(
                    sorted(
                        {
                            "synthetic_stimulation",
                            archetype.context_id,
                            f"turn_{turn_index}",
                            style.value,
                            semantic_class.value,
                            polarity.value,
                        }
                    )
                )
                cases.append(
                    SemanticStimulationScenario(
                        case_id=case_id,
                        split=split,
                        context_id=archetype.context_id,
                        turn_index=turn_index,
                        polarity=polarity,
                        semantic_class=semantic_class,
                        style=style,
                        generation_brief=(
                            f"{brief} Render it as a natural user message in "
                            f"{style.value.replace('_', ' ')} style. Do not mention real people, "
                            "products, repositories, paths, URLs, credentials, source code, or "
                            "private facts."
                        ),
                        tags=tags,
                        expectation=expectation,
                    )
                )
    plan = SemanticStimulationPlan(
        plan_id="semantic-stimulation-repository-archetypes-v1",
        created_at=created_at,
        cases=tuple(sorted(cases, key=lambda item: item.case_id)),
    )
    protocol = SemanticStimulationProtocol(
        protocol_id="semantic-stimulation-protocol-v1",
        created_at=created_at,
        source_access_mode="read_only_privacy_minimized_archetypes",
        archetypes=tuple(
            RepositoryArchetypeReceipt(
                context_id=item.context_id,
                archetype_digest=item.content_digest,
            )
            for item in ordered
        ),
        plan_digest=plan.content_digest,
    )
    return plan, protocol


def semantic_stimulation_generation_prompt(plan: SemanticStimulationPlan) -> str:
    """Render the synthetic-only generation packet for one isolated blank context."""

    payload = [
        {
            "case_id": case.case_id,
            "brief": case.generation_brief,
        }
        for case in plan.cases
    ]
    return (
        "Generate synthetic user-message wording for this fixed calibration design. These messages "
        "are fictional and must never be described as Kevin's real feedback. Do not use tools, "
        "files, web access, memories, or prior conversations. Preserve every case_id and order. "
        "Produce one short natural message per brief. Do not reveal or invent real names, "
        "products, repositories, paths, URLs, credentials, code, or private facts. Return only "
        "the schema-bound JSON.\n\n"
        + str(
            {
                "source_plan_digest": plan.content_digest,
                "cases": payload,
            }
        )
    )


def attest_semantic_stimulation_generation(
    plan: SemanticStimulationPlan,
    proposal: SemanticStimulationGeneration,
) -> SemanticStimulationGeneration:
    """Bind untrusted generated wording to the plan using deterministic local code."""

    plan_ids = tuple(case.case_id for case in plan.cases)
    if tuple(item.case_id for item in proposal.items) != plan_ids:
        raise ValueError("stimulation generation omitted, reordered, or invented cases")
    return proposal.model_copy(update={"source_plan_digest": plan.content_digest})


def attest_semantic_stimulation_audit(
    plan: SemanticStimulationPlan,
    generation: SemanticStimulationGeneration,
    proposal: SemanticStimulationAuditProposal,
) -> SemanticStimulationAuditProposal:
    """Bind untrusted audit verdicts to their exact generation deterministically."""

    plan_ids = tuple(case.case_id for case in plan.cases)
    if tuple(item.case_id for item in proposal.entries) != plan_ids:
        raise ValueError("stimulation audit omitted, reordered, or invented cases")
    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("stimulation generation does not bind the exact plan")
    return proposal.model_copy(update={"source_generation_digest": generation.content_digest})


def _changed_generation_case_ids(
    base: SemanticStimulationGeneration,
    revised: SemanticStimulationGeneration,
) -> tuple[Identifier, ...]:
    base_items = {item.case_id: item.text for item in base.items}
    revised_items = {item.case_id: item.text for item in revised.items}
    if tuple(base_items) != tuple(revised_items):
        raise ValueError("revised stimulation generation changed the case inventory")
    changed = tuple(
        sorted(case_id for case_id in base_items if base_items[case_id] != revised_items[case_id])
    )
    if not changed:
        raise ValueError("incremental stimulation audit requires changed wording")
    return changed


def semantic_stimulation_incremental_audit_prompt(
    plan: SemanticStimulationPlan,
    base_generation: SemanticStimulationGeneration,
    base_audit: SemanticStimulationAuditProposal,
    revised_generation: SemanticStimulationGeneration,
) -> str:
    """Render an audit packet containing only wording changed after the prior audit."""

    if base_generation.source_plan_digest != plan.content_digest:
        raise ValueError("base stimulation generation does not bind the exact plan")
    if revised_generation.source_plan_digest != plan.content_digest:
        raise ValueError("revised stimulation generation does not bind the exact plan")
    if base_audit.source_generation_digest != base_generation.content_digest:
        raise ValueError("base stimulation audit does not bind the base generation")
    changed_ids = _changed_generation_case_ids(base_generation, revised_generation)
    base_by_id = {item.case_id: item for item in base_audit.entries}
    if any(
        item.verdict is not StimulationAuditVerdict.PASS
        for case_id, item in base_by_id.items()
        if case_id not in changed_ids
    ):
        raise ValueError("base audit did not pass every unchanged stimulation case")
    revised_text = {item.case_id: item.text for item in revised_generation.items}
    by_case = {case.case_id: case for case in plan.cases}
    scope_by_case = {
        case.case_id: (
            None if case.expectation.scope_hint is None else case.expectation.scope_hint.value
        )
        for case in plan.cases
    }
    payload = [
        {
            "case_id": case_id,
            "text": revised_text[case_id],
            "polarity": by_case[case_id].polarity.value,
            "accepted_signal_kinds": [
                item.value for item in by_case[case_id].expectation.accepted_signal_kinds
            ],
            "accepted_routes": [
                item.value for item in by_case[case_id].expectation.accepted_routes
            ],
            "scope_hint": scope_by_case[case_id],
        }
        for case_id in changed_ids
    ]
    return (
        "Audit only these changed synthetic messages in a fresh context. Do not reassess unchanged "
        "cases. Do not use tools, files, web access, memories, or prior conversations. Mark pass "
        "only when each text unambiguously realizes its frozen polarity, accepted semantic "
        "type/route, and scope without unstated assumptions. Exact synthetic IDs matching "
        "artifact-context-[letter]-behavior are fixtures, not identifying details. Preserve case "
        "order and return only schema-bound JSON.\n\n"
        + str(
            {
                "source_generation_digest": revised_generation.content_digest,
                "base_generation_digest": base_generation.content_digest,
                "base_audit_digest": base_audit.content_digest,
                "changed_case_ids": changed_ids,
                "cases": payload,
            }
        )
    )


def attest_semantic_stimulation_incremental_audit(
    base_generation: SemanticStimulationGeneration,
    base_audit: SemanticStimulationAuditProposal,
    revised_generation: SemanticStimulationGeneration,
    proposal: SemanticStimulationIncrementalAudit,
) -> SemanticStimulationIncrementalAudit:
    """Deterministically bind an incremental proposal to exact old and new artifacts."""

    if base_audit.source_generation_digest != base_generation.content_digest:
        raise ValueError("base stimulation audit does not bind the base generation")
    changed_ids = _changed_generation_case_ids(base_generation, revised_generation)
    if tuple(item.case_id for item in proposal.entries) != changed_ids:
        raise ValueError("incremental audit must cover exactly the changed cases")
    return proposal.model_copy(
        update={
            "source_generation_digest": revised_generation.content_digest,
            "base_generation_digest": base_generation.content_digest,
            "base_audit_digest": base_audit.content_digest,
            "changed_case_ids": changed_ids,
        }
    )


def compose_semantic_stimulation_audit(
    base_generation: SemanticStimulationGeneration,
    base_audit: SemanticStimulationAuditProposal,
    revised_generation: SemanticStimulationGeneration,
    incremental_audit: SemanticStimulationIncrementalAudit,
) -> SemanticStimulationAuditProposal:
    """Compose prior unchanged verdicts with changed-case verdicts, without re-judging either."""

    if base_audit.source_generation_digest != base_generation.content_digest:
        raise ValueError("base stimulation audit does not bind the base generation")
    changed_ids = _changed_generation_case_ids(base_generation, revised_generation)
    if (
        incremental_audit.source_generation_digest != revised_generation.content_digest
        or incremental_audit.base_generation_digest != base_generation.content_digest
        or incremental_audit.base_audit_digest != base_audit.content_digest
        or incremental_audit.changed_case_ids != changed_ids
    ):
        raise ValueError("incremental audit does not bind the exact audit transition")
    replacements = {item.case_id: item for item in incremental_audit.entries}
    entries = tuple(replacements.get(item.case_id, item) for item in base_audit.entries)
    if any(item.verdict is not StimulationAuditVerdict.PASS for item in entries):
        raise ValueError("composed stimulation audit still contains non-passing cases")
    return SemanticStimulationAuditProposal(
        source_generation_digest=revised_generation.content_digest,
        entries=entries,
    )


def semantic_stimulation_audit_prompt(
    plan: SemanticStimulationPlan,
    generation: SemanticStimulationGeneration,
) -> str:
    """Render an independent label-consistency audit packet without repository content."""

    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("stimulation generation does not bind the supplied plan")
    generated = {item.case_id: item.text for item in generation.items}
    payload = [
        {
            "case_id": case.case_id,
            "text": generated[case.case_id],
            "polarity": case.polarity.value,
            "accepted_signal_kinds": [
                item.value for item in case.expectation.accepted_signal_kinds
            ],
            "accepted_routes": [item.value for item in case.expectation.accepted_routes],
            "scope_hint": (
                None if case.expectation.scope_hint is None else case.expectation.scope_hint.value
            ),
        }
        for case in plan.cases
    ]
    return (
        "Audit this synthetic semantic-feedback corpus in a fresh context. Do not use tools, "
        "files, "
        "web access, memories, or prior conversations. For each case, mark pass only when the text "
        "unambiguously realizes its frozen polarity, accepted semantic type/route, and scope "
        "without unstated assumptions. Mark identifying_detail if it contains a real-seeming name, "
        "product, repository, path, URL, credential, code, or private fact. Preserve case order. "
        "Synthetic test IDs matching artifact-context-[letter]-behavior are required fixtures, not "
        "identifying details. "
        "Return only the schema-bound JSON.\n\n"
        + str(
            {
                "source_generation_digest": generation.content_digest,
                "cases": payload,
            }
        )
    )


def semantic_stimulation_remediation_prompt(
    plan: SemanticStimulationPlan,
    generation: SemanticStimulationGeneration,
    audit: SemanticStimulationAuditProposal,
) -> str:
    """Render a replacement-only packet for cases rejected by the independent audit."""

    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("stimulation generation does not bind the supplied plan")
    if audit.source_generation_digest != generation.content_digest:
        raise ValueError("stimulation audit does not bind the supplied generation")
    generated = {item.case_id: item.text for item in generation.items}
    rejected = {
        item.case_id: item
        for item in audit.entries
        if item.verdict is not StimulationAuditVerdict.PASS
    }
    payload = [
        {
            "case_id": case.case_id,
            "previous_text": generated[case.case_id],
            "audit_reason": rejected[case.case_id].reason.value,
            "brief": case.generation_brief,
            "polarity": case.polarity.value,
            "accepted_signal_kinds": [
                item.value for item in case.expectation.accepted_signal_kinds
            ],
            "accepted_routes": [item.value for item in case.expectation.accepted_routes],
            "scope_hint": (
                None if case.expectation.scope_hint is None else case.expectation.scope_hint.value
            ),
        }
        for case in plan.cases
        if case.case_id in rejected
    ]
    return (
        "Replace only these rejected synthetic messages in a fresh context. Do not use tools, "
        "files, web access, memories, or prior conversations. Make each replacement unambiguously "
        "realize the frozen polarity, semantic type/route, and scope. Keep it natural and short. "
        "When preference is the only accepted signal kind, use explicit first-person preference "
        "wording rather than an imperative rule. "
        "Exact synthetic IDs matching artifact-context-[letter]-behavior must remain verbatim and "
        "are not identifying details. Do not add real names, products, repositories, paths, URLs, "
        "credentials, code, or private facts. Preserve case order. Return only the schema-bound "
        "JSON.\n\n"
        + str(
            {
                "source_generation_digest": generation.content_digest,
                "source_audit_digest": audit.content_digest,
                "cases": payload,
            }
        )
    )


def apply_semantic_stimulation_remediation(
    plan: SemanticStimulationPlan,
    generation: SemanticStimulationGeneration,
    audit: SemanticStimulationAuditProposal,
    remediation: SemanticStimulationRemediation,
) -> SemanticStimulationGeneration:
    """Replace exactly the rejected cases while preserving immutable failed inputs."""

    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("stimulation generation does not bind the exact plan")
    if audit.source_generation_digest != generation.content_digest:
        raise ValueError("stimulation audit does not bind the exact generation")
    if (
        remediation.source_generation_digest != generation.content_digest
        or remediation.source_audit_digest != audit.content_digest
    ):
        raise ValueError("stimulation remediation does not bind the failed generation and audit")
    rejected_ids = tuple(
        item.case_id for item in audit.entries if item.verdict is not StimulationAuditVerdict.PASS
    )
    replacement_ids = tuple(item.case_id for item in remediation.items)
    if replacement_ids != rejected_ids:
        raise ValueError("stimulation remediation must replace exactly the rejected cases")
    replacements = {item.case_id: item for item in remediation.items}
    if generation.generation_version == "1.0.0":
        next_version: Literal["1.1.0", "1.2.0", "1.3.0"] = "1.1.0"
    elif generation.generation_version == "1.1.0":
        next_version = "1.2.0"
    elif generation.generation_version == "1.2.0":
        next_version = "1.3.0"
    else:
        raise ValueError("stimulation generation has exhausted the frozen remediation sequence")
    return SemanticStimulationGeneration(
        generation_version=next_version,
        source_plan_digest=plan.content_digest,
        items=tuple(replacements.get(item.case_id, item) for item in generation.items),
    )


def attest_semantic_stimulation_remediation(
    generation: SemanticStimulationGeneration,
    audit: SemanticStimulationAuditProposal,
    proposal: SemanticStimulationRemediation,
) -> SemanticStimulationRemediation:
    """Bind replacement wording to the failed generation and audit deterministically."""

    if audit.source_generation_digest != generation.content_digest:
        raise ValueError("stimulation audit does not bind the exact generation")
    rejected_ids = tuple(
        item.case_id for item in audit.entries if item.verdict is not StimulationAuditVerdict.PASS
    )
    if tuple(item.case_id for item in proposal.items) != rejected_ids:
        raise ValueError("stimulation remediation must replace exactly the rejected cases")
    return proposal.model_copy(
        update={
            "source_generation_digest": generation.content_digest,
            "source_audit_digest": audit.content_digest,
        }
    )


def freeze_semantic_stimulation_corpus(
    plan: SemanticStimulationPlan,
    generation: SemanticStimulationGeneration,
    audit: SemanticStimulationAuditProposal,
) -> SemanticFeedbackCorpus:
    """Freeze only a complete, independently audited synthetic corpus."""

    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("stimulation generation does not bind the exact plan")
    if audit.source_generation_digest != generation.content_digest:
        raise ValueError("stimulation audit does not bind the exact generation")
    plan_ids = tuple(case.case_id for case in plan.cases)
    if tuple(item.case_id for item in generation.items) != plan_ids:
        raise ValueError("stimulation generation omitted, reordered, or invented cases")
    if tuple(item.case_id for item in audit.entries) != plan_ids:
        raise ValueError("stimulation audit omitted, reordered, or invented cases")
    rejected = tuple(
        item.case_id for item in audit.entries if item.verdict is not StimulationAuditVerdict.PASS
    )
    if rejected:
        raise ValueError(
            "stimulation corpus contains non-passing audit cases: " + ", ".join(rejected)
        )
    generated = {item.case_id: item.text for item in generation.items}
    return SemanticFeedbackCorpus(
        corpus_version="3.0.0",
        corpus_id="semantic-feedback-repository-stimulation-v3",
        frozen_at=plan.created_at,
        cases=tuple(
            SemanticFeedbackCase(
                case_id=case.case_id,
                split=case.split,
                text=generated[case.case_id],
                tags=case.tags,
                expectation=case.expectation,
            )
            for case in plan.cases
        ),
    )


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def _slice_metrics(
    *,
    dimension: Literal["context", "semantic_class", "split", "style", "turn"],
    slice_id: str,
    evaluations: Iterable[SemanticCaseEvaluation],
) -> SemanticStimulationSliceMetrics:
    selected = tuple(evaluations)
    expected_positive = sum(item.expected_durable for item in selected)
    expected_negative = len(selected) - expected_positive
    true_positive = sum(item.expected_durable and item.predicted_durable for item in selected)
    false_positive = sum(not item.expected_durable and item.predicted_durable for item in selected)
    true_negative = sum(
        not item.expected_durable and not item.predicted_durable for item in selected
    )
    false_negative = sum(item.expected_durable and not item.predicted_durable for item in selected)
    predicted_positive = tuple(item for item in selected if item.predicted_durable)
    return SemanticStimulationSliceMetrics(
        dimension=dimension,
        slice_id=slice_id,
        case_count=len(selected),
        expected_positive=expected_positive,
        expected_negative=expected_negative,
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        detection_accuracy=_ratio(true_positive + true_negative, len(selected)),
        precision=_ratio(true_positive, true_positive + false_positive),
        recall=_ratio(true_positive, true_positive + false_negative),
        negative_specificity=_ratio(true_negative, true_negative + false_positive),
        route_accuracy=_ratio(
            sum(item.route_correct for item in predicted_positive),
            len(predicted_positive),
        ),
        scope_accuracy=_ratio(
            sum(item.scope_correct for item in predicted_positive),
            len(predicted_positive),
        ),
    )


def summarize_semantic_stimulation(
    *,
    created_at: datetime,
    protocol: SemanticStimulationProtocol,
    plan: SemanticStimulationPlan,
    generation: SemanticStimulationGeneration,
    audit: SemanticStimulationAuditProposal,
    corpus: SemanticFeedbackCorpus,
    calibration_report: SemanticEvaluationReport,
    holdout_report: SemanticEvaluationReport,
) -> SemanticStimulationSummary:
    """Aggregate raw-free results across controlled context, style, class, and turn slices."""

    if protocol.plan_digest != plan.content_digest:
        raise ValueError("stimulation protocol does not bind the exact plan")
    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("stimulation generation does not bind the exact plan")
    if audit.source_generation_digest != generation.content_digest:
        raise ValueError("stimulation audit does not bind the exact generation")
    for split, report in (("calibration", calibration_report), ("holdout", holdout_report)):
        if report.split != split or report.source_corpus_digest != corpus.content_digest:
            raise ValueError("stimulation report does not bind the exact corpus and split")
    evaluations = calibration_report.case_evaluations + holdout_report.case_evaluations
    by_case = {item.case_id: item for item in evaluations}
    if tuple(sorted(by_case)) != tuple(case.case_id for case in plan.cases):
        raise ValueError("stimulation reports omitted or invented cases")

    grouped: dict[
        tuple[Literal["context", "semantic_class", "split", "style", "turn"], str],
        list[SemanticCaseEvaluation],
    ] = defaultdict(list)
    for case in plan.cases:
        evaluation = by_case[case.case_id]
        grouped[("context", case.context_id)].append(evaluation)
        grouped[("semantic_class", case.semantic_class.value)].append(evaluation)
        grouped[("split", case.split)].append(evaluation)
        grouped[("style", case.style.value)].append(evaluation)
        grouped[("turn", f"turn_{case.turn_index}")].append(evaluation)
    slices = tuple(
        _slice_metrics(dimension=dimension, slice_id=slice_id, evaluations=selected)
        for (dimension, slice_id), selected in sorted(grouped.items())
    )
    return SemanticStimulationSummary(
        created_at=created_at,
        protocol_digest=protocol.content_digest,
        plan_digest=plan.content_digest,
        generation_digest=generation.content_digest,
        audit_digest=audit.content_digest,
        corpus_digest=corpus.content_digest,
        calibration_report_digest=calibration_report.content_digest,
        holdout_report_digest=holdout_report.content_digest,
        detector_gate_passed=(
            calibration_report.promotion_ready and holdout_report.promotion_ready
        ),
        slices=slices,
        failed_case_ids=tuple(
            sorted(set(calibration_report.failed_case_ids) | set(holdout_report.failed_case_ids))
        ),
    )
