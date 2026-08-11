"""Blind, route-specific evaluation for the semantic feedback sensor.

The route benchmark isolates one question left open by repository-informed stimulation: once a
message is known to contain durable learning, can the sensor distinguish facts, preferences,
procedures, hard rules, endorsed examples, and exact revocations? Labels are fixed before wording
generation. Blind auditors receive only case identifiers and generated text.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal, cast

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticScopeHint,
)
from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
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


class SemanticRouteClass(StrEnum):
    """Mutually exclusive semantic forms under test."""

    MEMORY = "memory"
    POSITIVE_EXAMPLE = "positive_example"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    PROMPT_RULE = "prompt_rule"
    REVOCATION = "revocation"


class SemanticRouteStyle(StrEnum):
    """Natural surface-form variations balanced within every split."""

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


class BlindRouteClass(StrEnum):
    """Class labels available to a blind auditor."""

    AMBIGUOUS = "ambiguous"
    MEMORY = "memory"
    NO_DURABLE_SIGNAL = "no_durable_signal"
    POSITIVE_EXAMPLE = "positive_example"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    PROMPT_RULE = "prompt_rule"
    REVOCATION = "revocation"


class BlindRouteScope(StrEnum):
    """Scope labels available to a blind auditor without nullable fields."""

    AMBIGUOUS = "ambiguous"
    CURRENT_CONTEXT = "current_context"
    NO_DURABLE_SIGNAL = "no_durable_signal"
    PERMANENT_PROFILE = "permanent_profile"


class BlindRouteReason(StrEnum):
    """Closed reasons that prevent auditors from returning private or generated prose."""

    AMBIGUOUS = "ambiguous"
    ENDORSED_REUSE = "endorsed_reuse"
    EXACT_ARTIFACT_REMOVAL = "exact_artifact_removal"
    HARD_INVARIANT = "hard_invariant"
    NON_NORMATIVE_FACT = "non_normative_fact"
    NO_DURABLE_SIGNAL = "no_durable_signal"
    ORDERED_TRIGGER_WORKFLOW = "ordered_trigger_workflow"
    STABLE_CHOICE = "stable_choice"


_CLASS_EXPECTATIONS: Mapping[
    SemanticRouteClass,
    tuple[FeedbackSignalKind, ArtifactRoute | None],
] = {
    SemanticRouteClass.MEMORY: (FeedbackSignalKind.MEMORY, ArtifactRoute.MEMORY),
    SemanticRouteClass.POSITIVE_EXAMPLE: (
        FeedbackSignalKind.POSITIVE_EXAMPLE,
        ArtifactRoute.EXAMPLE,
    ),
    SemanticRouteClass.PREFERENCE: (
        FeedbackSignalKind.PREFERENCE,
        ArtifactRoute.PREFERENCE,
    ),
    SemanticRouteClass.PROCEDURE: (
        FeedbackSignalKind.PROCEDURE,
        ArtifactRoute.PROCEDURE,
    ),
    SemanticRouteClass.PROMPT_RULE: (
        FeedbackSignalKind.PROMPT_RULE,
        ArtifactRoute.PROMPT_RULE,
    ),
    SemanticRouteClass.REVOCATION: (FeedbackSignalKind.REVOCATION, None),
}

_BLIND_REASONS: Mapping[BlindRouteClass, BlindRouteReason] = {
    BlindRouteClass.AMBIGUOUS: BlindRouteReason.AMBIGUOUS,
    BlindRouteClass.MEMORY: BlindRouteReason.NON_NORMATIVE_FACT,
    BlindRouteClass.NO_DURABLE_SIGNAL: BlindRouteReason.NO_DURABLE_SIGNAL,
    BlindRouteClass.POSITIVE_EXAMPLE: BlindRouteReason.ENDORSED_REUSE,
    BlindRouteClass.PREFERENCE: BlindRouteReason.STABLE_CHOICE,
    BlindRouteClass.PROCEDURE: BlindRouteReason.ORDERED_TRIGGER_WORKFLOW,
    BlindRouteClass.PROMPT_RULE: BlindRouteReason.HARD_INVARIANT,
    BlindRouteClass.REVOCATION: BlindRouteReason.EXACT_ARTIFACT_REMOVAL,
}

_BLIND_CLASS_FOR_EXPECTED: Mapping[SemanticRouteClass, BlindRouteClass] = {
    item: BlindRouteClass(item.value) for item in SemanticRouteClass
}


class SemanticRouteScenario(FrozenModel):
    """One label-first matched-contrast scenario."""

    case_id: Identifier
    split: Literal["calibration", "holdout"]
    contrast_id: Identifier
    semantic_class: SemanticRouteClass
    style: SemanticRouteStyle
    scope_hint: SemanticScopeHint
    affected_artifact_id: Identifier | None = None
    generation_brief: NonEmptyStr
    tags: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    expectation: SemanticFeedbackExpectation

    @field_validator("tags")
    @classmethod
    def tags_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("semantic route tags must be sorted and unique")
        return value

    @model_validator(mode="after")
    def expectation_is_exact(self) -> SemanticRouteScenario:
        signal_kind, route = _CLASS_EXPECTATIONS[self.semantic_class]
        expected_routes = () if route is None else (route,)
        if (
            not self.expectation.durable_signal
            or self.expectation.accepted_signal_kinds != (signal_kind,)
            or self.expectation.accepted_routes != expected_routes
            or self.expectation.scope_hint is not self.scope_hint
        ):
            raise ValueError("semantic route scenario expectation is not exact")
        if (self.semantic_class is SemanticRouteClass.REVOCATION) != (
            self.affected_artifact_id is not None
        ):
            raise ValueError("only semantic route revocations may name an artifact")
        if self.expectation.affected_artifact_id not in {
            None,
            self.affected_artifact_id,
        }:
            raise ValueError("semantic route expectation names the wrong affected artifact")
        return self


class SemanticRoutePlan(FrozenModel):
    """Frozen 120-case route-discrimination design."""

    plan_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0"] = "1.0.0"
    plan_id: Literal[
        "semantic-route-discrimination-v1",
        "semantic-route-discrimination-v2",
        "semantic-route-discrimination-v3",
        "semantic-route-discrimination-v4",
    ] = "semantic-route-discrimination-v1"
    created_at: UtcDateTime
    cases: Annotated[tuple[SemanticRouteScenario, ...], Field(min_length=120, max_length=120)]

    @field_validator("cases")
    @classmethod
    def cases_are_sorted_unique(
        cls,
        value: tuple[SemanticRouteScenario, ...],
    ) -> tuple[SemanticRouteScenario, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("semantic route cases must be sorted by unique case ID")
        return value

    @model_validator(mode="after")
    def design_is_balanced(self) -> SemanticRoutePlan:
        for split in ("calibration", "holdout"):
            selected = tuple(item for item in self.cases if item.split == split)
            if len(selected) != 60:
                raise ValueError("each semantic route split requires exactly 60 cases")
            for semantic_class in SemanticRouteClass:
                class_cases = tuple(
                    item for item in selected if item.semantic_class is semantic_class
                )
                if len(class_cases) != 10:
                    raise ValueError("each split requires ten cases per semantic route class")
                for scope in SemanticScopeHint:
                    if sum(item.scope_hint is scope for item in class_cases) != 5:
                        raise ValueError("each route class requires five cases per scope")
            for style in SemanticRouteStyle:
                if sum(item.style is style for item in selected) != 6:
                    raise ValueError("each split requires six cases per wording style")
            contrasts = {item.contrast_id for item in selected}
            if len(contrasts) != 10:
                raise ValueError("each split requires ten matched contrast sets")
            if any(
                sum(item.contrast_id == contrast for item in selected) != 6
                for contrast in contrasts
            ):
                raise ValueError("each matched contrast set requires all six semantic classes")
        if self.plan_version in {"3.0.0", "4.0.0"} and any(
            item.semantic_class is SemanticRouteClass.REVOCATION
            and item.expectation.affected_artifact_id != item.affected_artifact_id
            for item in self.cases
        ):
            raise ValueError("route plan v3 requires an exact revocation target")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticRouteProtocol(FrozenModel):
    """Fail-closed protocol for subscription-only synthetic route testing."""

    protocol_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0"] = "1.0.0"
    protocol_id: Literal[
        "semantic-route-protocol-v1",
        "semantic-route-protocol-v2",
        "semantic-route-protocol-v3",
        "semantic-route-protocol-v4",
    ] = "semantic-route-protocol-v1"
    created_at: UtcDateTime
    plan_digest: Sha256Digest
    generation_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    generation_reasoning_effort: Literal["low"] = "low"
    blind_audit_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    blind_audit_reasoning_effort: Literal["low"] = "low"
    detector_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    detector_reasoning_effort: Literal["medium"] = "medium"
    authentication: Literal["saved_chatgpt_subscription"] = "saved_chatgpt_subscription"
    provider_billed_cost_usd: Literal[0] = 0
    labels_frozen_before_generation: Literal[True] = True
    blind_auditors_receive_labels: Literal[False] = False
    holdout_used_for_prompt_revision: Literal[False] = False
    synthetic_only: Literal[True] = True
    synthetic_is_user_authority: Literal[False] = False
    production_promotion_permitted: Literal[False] = False
    production_state_mutation_permitted: Literal[False] = False
    sealed_external_validation_access_permitted: Literal[False] = False

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticRouteGeneratedItem(FrozenModel):
    """Natural synthetic wording for one fixed route scenario."""

    case_id: Identifier
    text: str = Field(min_length=1, max_length=600)


class SemanticRouteGeneration(FrozenModel):
    """One schema-bound synthetic generation batch."""

    generation_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0"] = "1.0.0"
    source_plan_digest: Sha256Digest
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["low"] = "low"
    synthetic_only: Literal[True] = True
    items: Annotated[tuple[SemanticRouteGeneratedItem, ...], Field(min_length=120, max_length=120)]

    @field_validator("items")
    @classmethod
    def items_are_sorted_unique(
        cls,
        value: tuple[SemanticRouteGeneratedItem, ...],
    ) -> tuple[SemanticRouteGeneratedItem, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("semantic route generation must be sorted and complete")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticRouteBlindEntry(FrozenModel):
    """One classification made without access to intended labels."""

    case_id: Identifier
    classification: BlindRouteClass
    scope: BlindRouteScope
    reason: BlindRouteReason

    @model_validator(mode="after")
    def classification_shape_is_coherent(self) -> SemanticRouteBlindEntry:
        if self.reason is not _BLIND_REASONS[self.classification]:
            raise ValueError("blind route reason must match the classification")
        if self.classification is BlindRouteClass.AMBIGUOUS:
            if self.scope is not BlindRouteScope.AMBIGUOUS:
                raise ValueError("ambiguous route requires ambiguous scope")
        elif self.classification is BlindRouteClass.NO_DURABLE_SIGNAL:
            if self.scope is not BlindRouteScope.NO_DURABLE_SIGNAL:
                raise ValueError("no-signal route requires no-signal scope")
        elif self.scope not in {
            BlindRouteScope.CURRENT_CONTEXT,
            BlindRouteScope.PERMANENT_PROFILE,
        }:
            raise ValueError("resolved route requires a resolved scope")
        return self


class SemanticRouteBlindAudit(FrozenModel):
    """Schema-bound output from one fresh label-blind context."""

    audit_version: Literal["1.0.0"] = "1.0.0"
    auditor_id: Identifier
    source_generation_digest: Sha256Digest
    model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    reasoning_effort: Literal["low"] = "low"
    labels_visible: Literal[False] = False
    entries: Annotated[tuple[SemanticRouteBlindEntry, ...], Field(min_length=120, max_length=120)]

    @field_validator("entries")
    @classmethod
    def entries_are_sorted_unique(
        cls,
        value: tuple[SemanticRouteBlindEntry, ...],
    ) -> tuple[SemanticRouteBlindEntry, ...]:
        case_ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(case_ids):
            raise ValueError("blind route audit must be sorted and complete")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticRouteClassMetrics(FrozenModel):
    """Exact route and scope measurements for one semantic class."""

    split: Literal["calibration", "holdout", "combined"]
    semantic_class: SemanticRouteClass
    case_count: int = Field(ge=1)
    detected_count: int = Field(ge=0)
    exact_route_count: int = Field(ge=0)
    exact_scope_count: int = Field(ge=0)
    detection_accuracy: float = Field(ge=0, le=1)
    route_accuracy: float = Field(ge=0, le=1)
    scope_accuracy: float = Field(ge=0, le=1)


class SemanticRouteBlindMetrics(FrozenModel):
    """Agreement of two label-blind auditors with the frozen answer key."""

    case_count: Literal[120] = 120
    auditor_a_label_accuracy: float = Field(ge=0, le=1)
    auditor_b_label_accuracy: float = Field(ge=0, le=1)
    auditor_a_scope_accuracy: float = Field(ge=0, le=1)
    auditor_b_scope_accuracy: float = Field(ge=0, le=1)
    pair_label_agreement: float = Field(ge=0, le=1)
    pair_scope_agreement: float = Field(ge=0, le=1)
    both_match_answer_key_count: int = Field(ge=0, le=120)
    ambiguous_case_ids: tuple[Identifier, ...]

    @field_validator("ambiguous_case_ids")
    @classmethod
    def ambiguous_cases_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("ambiguous route cases must be sorted and unique")
        return value


class SemanticRouteSummary(FrozenModel):
    """Raw-free result that cannot authorize production promotion."""

    summary_version: Literal["1.0.0"] = "1.0.0"
    created_at: UtcDateTime
    protocol_digest: Sha256Digest
    plan_digest: Sha256Digest
    generation_digest: Sha256Digest
    corpus_digest: Sha256Digest
    auditor_a_digest: Sha256Digest
    auditor_b_digest: Sha256Digest
    calibration_report_digest: Sha256Digest
    holdout_report_digest: Sha256Digest
    blind_metrics: SemanticRouteBlindMetrics
    class_metrics: tuple[SemanticRouteClassMetrics, ...]
    route_gate_passed: bool
    production_promotion_authorized: Literal[False] = False
    synthetic_only: Literal[True] = True
    synthetic_is_user_authority: Literal[False] = False
    production_state_mutated: Literal[False] = False
    failed_case_ids: tuple[Identifier, ...]

    @field_validator("failed_case_ids")
    @classmethod
    def failures_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("semantic route failures must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


_STYLES = tuple(SemanticRouteStyle)
_CLASSES = tuple(SemanticRouteClass)

_CALIBRATION_TOPICS = (
    "communication handoffs",
    "naming choices",
    "test verification",
    "backup safety",
    "research reporting",
    "dependency changes",
    "error handling",
    "code comments",
    "review summaries",
    "file organization",
)

_HOLDOUT_TOPICS = (
    "release notes",
    "shell commands",
    "data migrations",
    "configuration defaults",
    "service responses",
    "debug traces",
    "documentation updates",
    "workspace synchronization",
    "security checks",
    "performance changes",
)

_CALIBRATION_TOPICS_V2 = (
    "accessibility settings",
    "patch summaries",
    "branch cleanup",
    "dependency review",
    "incident notes",
    "command previews",
    "test failures",
    "user-facing errors",
    "fixture updates",
    "release approval",
)

_HOLDOUT_TOPICS_V2 = (
    "code review comments",
    "log retention",
    "local backups",
    "database queries",
    "issue triage",
    "interface copy",
    "deployment checks",
    "data exports",
    "performance reports",
    "security warnings",
)

_CALIBRATION_TOPICS_V3 = (
    "pull request descriptions",
    "local environment notes",
    "dependency upgrades",
    "failure summaries",
    "command explanations",
    "temporary file cleanup",
    "test selection",
    "configuration reviews",
    "data validation",
    "release checklists",
)

_HOLDOUT_TOPICS_V3 = (
    "code ownership notes",
    "backup restoration",
    "migration summaries",
    "error reproduction",
    "documentation examples",
    "workspace setup",
    "security review notes",
    "performance measurements",
    "issue updates",
    "deployment summaries",
)

_CALIBRATION_TOPICS_V4 = (
    "operating systems",
    "accessibility needs",
    "team schedules",
    "language fluency",
    "device constraints",
    "review responsibilities",
    "workspace layout",
    "network availability",
    "release permissions",
    "collaboration roles",
)

_HOLDOUT_TOPICS_V4 = (
    "time zones",
    "hardware limits",
    "account access",
    "support rotations",
    "data residency",
    "approval responsibilities",
    "local tooling",
    "deployment ownership",
    "documentation audiences",
    "testing environments",
)


def _expectation(
    semantic_class: SemanticRouteClass,
    scope: SemanticScopeHint,
    *,
    affected_artifact_id: str | None = None,
) -> SemanticFeedbackExpectation:
    signal_kind, route = _CLASS_EXPECTATIONS[semantic_class]
    return SemanticFeedbackExpectation(
        durable_signal=True,
        accepted_signal_kinds=(signal_kind,),
        accepted_routes=() if route is None else (route,),
        scope_hint=scope,
        affected_artifact_id=affected_artifact_id,
    )


def _generation_brief_v1(
    semantic_class: SemanticRouteClass,
    *,
    topic: str,
    scope: SemanticScopeHint,
    style: SemanticRouteStyle,
    artifact_id: str | None,
) -> str:
    scope_text = (
        "Explicitly say this applies generally across future projects."
        if scope is SemanticScopeHint.PERMANENT_PROFILE
        else "Explicitly limit this to the fictional current project named Project Cedar."
    )
    class_text = {
        SemanticRouteClass.MEMORY: (
            "State a first-person, non-sensitive fact about the synthetic user's situation that "
            f"affects {topic}. Do not request or imply any assistant behavior."
        ),
        SemanticRouteClass.PREFERENCE: (
            f"Express a stable desired choice about {topic}. Use preference language, not an "
            "absolute requirement and not a trigger or ordered workflow."
        ),
        SemanticRouteClass.PROCEDURE: (
            f"Specify a repeatable trigger and at least two ordered steps for handling {topic}. "
            "Do not express an absolute always/never invariant."
        ),
        SemanticRouteClass.PROMPT_RULE: (
            f"State one hard always/never requirement or prohibition about {topic}. Do not turn "
            "it into an ordered multi-step workflow."
        ),
        SemanticRouteClass.POSITIVE_EXAMPLE: (
            f"Explicitly endorse a just-shown {topic} pattern as a good example and request that "
            "the same pattern be imitated in future. Do not merely state a preference."
        ),
        SemanticRouteClass.REVOCATION: (
            f"Explicitly request removal of the exact active artifact ID {artifact_id}. Do not "
            "describe a replacement behavior."
        ),
    }[semantic_class]
    return (
        f"{class_text} {scope_text} Render one natural user message in "
        f"{style.value.replace('_', ' ')} style. Keep the intended semantic form explicit despite "
        "the style. Do not mention real people, products, repositories, paths, URLs, credentials, "
        "source code, or private facts."
    )


def _generation_brief_v2(
    semantic_class: SemanticRouteClass,
    *,
    topic: str,
    scope: SemanticScopeHint,
    style: SemanticRouteStyle,
    artifact_id: str | None,
) -> str:
    scope_text = (
        "Express the scope as a direct fact or intention across all future projects, without "
        "saying that a behavior merely 'applies'."
        if scope is SemanticScopeHint.PERMANENT_PROFILE
        else "Explicitly limit the fact or intention to the current project named Project Harbor."
    )
    class_text = {
        SemanticRouteClass.MEMORY: (
            "State a harmless, direct first-person fact about the user's real-seeming situation "
            f"that affects {topic}. Do not request, recommend, or imply assistant behavior. The "
            "fact may describe an environment, schedule, access need, or collaboration structure."
        ),
        SemanticRouteClass.PREFERENCE: (
            f"Express a stable desired choice about {topic} using 'prefer', 'like', or equivalent "
            "choice language. Do not use must, always, never, required, or ordered steps."
        ),
        SemanticRouteClass.PROCEDURE: (
            "Specify a repeatable when/whenever trigger and at least two ordered steps for "
            f"{topic}. "
            "Do not use must, always, never, or turn it into one absolute invariant."
        ),
        SemanticRouteClass.PROMPT_RULE: (
            f"State exactly one hard always/never/must requirement or prohibition about {topic}. "
            "Do not include an ordered multi-step workflow."
        ),
        SemanticRouteClass.POSITIVE_EXAMPLE: (
            f"Refer to a just-shown {topic} pattern, explicitly endorse it as a good model, and "
            "request imitating that same pattern later. Make endorsement and reuse explicit."
        ),
        SemanticRouteClass.REVOCATION: (
            f"Explicitly request removal of the exact active artifact ID {artifact_id}. Do not "
            "describe any replacement behavior."
        ),
    }[semantic_class]
    if (
        style is SemanticRouteStyle.EMPHATIC
        and semantic_class is not SemanticRouteClass.PROMPT_RULE
    ):
        style_boundary = (
            "Make it emphatic with tone or punctuation only; do not introduce must, always, never, "
            "required, or another hard-rule marker."
        )
    else:
        style_boundary = "Do not let the wording style change the requested semantic class."
    return (
        f"{class_text} {scope_text} Render one natural user message in "
        f"{style.value.replace('_', ' ')} style. {style_boundary} The message itself must never "
        "say or imply that the user, project, fact, artifact, or message is fictional, synthetic, "
        "hypothetical, imaginary, a benchmark, or a test fixture. Do not mention real people, "
        "products, repositories, paths, URLs, credentials, source code, or private facts."
    )


def _generation_brief_v3(
    semantic_class: SemanticRouteClass,
    *,
    topic: str,
    scope: SemanticScopeHint,
    style: SemanticRouteStyle,
    artifact_id: str | None,
) -> str:
    scope_text = (
        "Express the scope directly across all future projects without saying a behavior merely "
        "'applies'."
        if scope is SemanticScopeHint.PERMANENT_PROFILE
        else "Explicitly limit the fact or intention to the current project named Project Summit."
    )
    class_text = {
        SemanticRouteClass.MEMORY: (
            "State a harmless direct first-person fact about the user's situation that affects "
            f"{topic}, without requesting or implying assistant behavior."
        ),
        SemanticRouteClass.PREFERENCE: (
            f"Express a stable desired choice about {topic} using preference language. Do not use "
            "must, always, never, required, or ordered steps."
        ),
        SemanticRouteClass.PROCEDURE: (
            "Specify a repeatable when/whenever trigger and at least two ordered steps for "
            f"{topic}. Do not turn it into one absolute invariant."
        ),
        SemanticRouteClass.PROMPT_RULE: (
            f"State exactly one hard always/never/must requirement about {topic}, without ordered "
            "steps."
        ),
        SemanticRouteClass.POSITIVE_EXAMPLE: (
            f"Explicitly endorse a just-shown {topic} pattern and request imitating that same "
            "pattern later."
        ),
        SemanticRouteClass.REVOCATION: (
            "Explicitly say to remove the active adaptation artifact with exact ID "
            f"{artifact_id}. Copy the ID exactly and describe no replacement."
        ),
    }[semantic_class]
    if (
        style is SemanticRouteStyle.EMPHATIC
        and semantic_class is not SemanticRouteClass.PROMPT_RULE
    ):
        style_boundary = (
            "Use emphatic tone or punctuation only; do not introduce must, always, never, "
            "required, "
            "or another hard-rule marker."
        )
    else:
        style_boundary = "Do not let the wording style change the requested semantic class."
    return (
        f"{class_text} {scope_text} Render one natural user message in "
        f"{style.value.replace('_', ' ')} style. {style_boundary} Never disclose that the message "
        "or its content is fictional, synthetic, hypothetical, imaginary, a benchmark, or a test "
        "fixture. Do not mention real people, products, repositories, paths, URLs, credentials, "
        "source code, or private facts."
    )


def _generation_brief_v4(
    semantic_class: SemanticRouteClass,
    *,
    topic: str,
    scope: SemanticScopeHint,
    style: SemanticRouteStyle,
    artifact_id: str | None,
) -> str:
    scope_text = (
        "Express the scope directly across all future projects."
        if scope is SemanticScopeHint.PERMANENT_PROFILE
        else "Explicitly limit the fact or intention to the current project named Project Aurora."
    )
    class_text = {
        SemanticRouteClass.MEMORY: (
            "State a stable, reusable, long-term first-person fact about the user's structural "
            f"circumstances relevant to {topic}. It must remain useful in later work. Do not "
            "request or imply assistant behavior. Do not describe something temporary, unsettled, "
            "or happening only at the moment. Never use current, currently, right now, today, "
            "lately, temporary, dealing with, piling up, or not yet."
        ),
        SemanticRouteClass.PREFERENCE: (
            f"Express a stable desired choice about {topic} using preference language. Do not use "
            "must, always, never, required, or ordered steps."
        ),
        SemanticRouteClass.PROCEDURE: (
            "Specify a repeatable when/whenever trigger and at least two ordered steps for "
            f"{topic}, without turning it into one absolute invariant."
        ),
        SemanticRouteClass.PROMPT_RULE: (
            f"State exactly one hard always/never/must requirement about {topic}, without ordered "
            "steps."
        ),
        SemanticRouteClass.POSITIVE_EXAMPLE: (
            f"Explicitly endorse a just-shown {topic} pattern and request imitating that same "
            "pattern later."
        ),
        SemanticRouteClass.REVOCATION: (
            "The final message must include the exact phrase 'active adaptation artifact' "
            f"immediately followed by the exact ID {artifact_id}, and explicitly request removing "
            "it. Copy the ID exactly and describe no replacement."
        ),
    }[semantic_class]
    if (
        style is SemanticRouteStyle.EMPHATIC
        and semantic_class is not SemanticRouteClass.PROMPT_RULE
    ):
        style_boundary = (
            "Use emphatic tone or punctuation only; do not introduce must, always, never, "
            "required, or another hard-rule marker."
        )
    else:
        style_boundary = "Do not let the wording style change the requested semantic class."
    return (
        f"{class_text} {scope_text} Render one natural user message in "
        f"{style.value.replace('_', ' ')} style. {style_boundary} Never disclose that the message "
        "or its content is fictional, synthetic, hypothetical, imaginary, a benchmark, or a test "
        "fixture. Do not mention real people, products, repositories, paths, URLs, credentials, "
        "source code, or private facts."
    )


def build_semantic_route_design(
    *,
    created_at: datetime,
    revision: Literal["v1", "v2", "v3", "v4"] = "v1",
) -> tuple[SemanticRoutePlan, SemanticRouteProtocol]:
    """Build the deterministic label-first matched-contrast design."""

    cases: list[SemanticRouteScenario] = []
    split_specs: tuple[tuple[Literal["calibration", "holdout"], str, tuple[str, ...]], ...]
    if revision == "v1":
        split_specs = (
            ("calibration", "c", _CALIBRATION_TOPICS),
            ("holdout", "h", _HOLDOUT_TOPICS),
        )
    elif revision == "v2":
        split_specs = (
            ("calibration", "c", _CALIBRATION_TOPICS_V2),
            ("holdout", "h", _HOLDOUT_TOPICS_V2),
        )
    elif revision == "v3":
        split_specs = (
            ("calibration", "c", _CALIBRATION_TOPICS_V3),
            ("holdout", "h", _HOLDOUT_TOPICS_V3),
        )
    else:
        split_specs = (
            ("calibration", "c", _CALIBRATION_TOPICS_V4),
            ("holdout", "h", _HOLDOUT_TOPICS_V4),
        )
    for split, split_code, topics in split_specs:
        for contrast_index, topic in enumerate(topics):
            scope = (
                SemanticScopeHint.PERMANENT_PROFILE
                if contrast_index < 5
                else SemanticScopeHint.CURRENT_CONTEXT
            )
            style = _STYLES[contrast_index]
            if revision == "v1":
                contrast_id = f"route-{split_code}-contrast-{contrast_index + 1:02d}"
            elif revision == "v2":
                contrast_id = f"route-v2-{split_code}-contrast-{contrast_index + 1:02d}"
            elif revision == "v3":
                contrast_id = f"route-v3-{split_code}-contrast-{contrast_index + 1:02d}"
            else:
                contrast_id = f"route-v4-{split_code}-contrast-{contrast_index + 1:02d}"
            for semantic_class in _CLASSES:
                case_seed = (
                    f"semantic-route-{revision}|{split}|{contrast_index}|{semantic_class.value}"
                )
                artifact_id = (
                    (
                        f"artifact-route-{split_code}-{contrast_index + 1:02d}"
                        if revision == "v1"
                        else (
                            f"artifact-route-v2-{split_code}-{contrast_index + 1:02d}"
                            if revision == "v2"
                            else "artifact-"
                            + sha256(f"artifact|{case_seed}".encode()).hexdigest()[:16]
                        )
                    )
                    if semantic_class is SemanticRouteClass.REVOCATION
                    else None
                )
                case_id = f"route-{sha256(case_seed.encode('utf-8')).hexdigest()[:16]}"
                tags = tuple(
                    sorted(
                        {
                            "semantic_route",
                            contrast_id,
                            semantic_class.value,
                            scope.value,
                            style.value,
                        }
                    )
                )
                cases.append(
                    SemanticRouteScenario(
                        case_id=case_id,
                        split=split,
                        contrast_id=contrast_id,
                        semantic_class=semantic_class,
                        style=style,
                        scope_hint=scope,
                        affected_artifact_id=artifact_id,
                        generation_brief=(
                            _generation_brief_v1(
                                semantic_class,
                                topic=topic,
                                scope=scope,
                                style=style,
                                artifact_id=artifact_id,
                            )
                            if revision == "v1"
                            else (
                                _generation_brief_v2(
                                    semantic_class,
                                    topic=topic,
                                    scope=scope,
                                    style=style,
                                    artifact_id=artifact_id,
                                )
                                if revision == "v2"
                                else (
                                    _generation_brief_v3(
                                        semantic_class,
                                        topic=topic,
                                        scope=scope,
                                        style=style,
                                        artifact_id=artifact_id,
                                    )
                                    if revision == "v3"
                                    else _generation_brief_v4(
                                        semantic_class,
                                        topic=topic,
                                        scope=scope,
                                        style=style,
                                        artifact_id=artifact_id,
                                    )
                                )
                            )
                        ),
                        tags=tags,
                        expectation=_expectation(
                            semantic_class,
                            scope,
                            affected_artifact_id=(
                                artifact_id
                                if revision in {"v3", "v4"}
                                and semantic_class is SemanticRouteClass.REVOCATION
                                else None
                            ),
                        ),
                    )
                )
    plan_version = cast(
        Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0"],
        {"v1": "1.0.0", "v2": "2.0.0", "v3": "3.0.0", "v4": "4.0.0"}[revision],
    )
    plan_id = cast(
        Literal[
            "semantic-route-discrimination-v1",
            "semantic-route-discrimination-v2",
            "semantic-route-discrimination-v3",
            "semantic-route-discrimination-v4",
        ],
        {
            "v1": "semantic-route-discrimination-v1",
            "v2": "semantic-route-discrimination-v2",
            "v3": "semantic-route-discrimination-v3",
            "v4": "semantic-route-discrimination-v4",
        }[revision],
    )
    protocol_id = cast(
        Literal[
            "semantic-route-protocol-v1",
            "semantic-route-protocol-v2",
            "semantic-route-protocol-v3",
            "semantic-route-protocol-v4",
        ],
        {
            "v1": "semantic-route-protocol-v1",
            "v2": "semantic-route-protocol-v2",
            "v3": "semantic-route-protocol-v3",
            "v4": "semantic-route-protocol-v4",
        }[revision],
    )
    plan = SemanticRoutePlan(
        plan_version=plan_version,
        plan_id=plan_id,
        created_at=created_at,
        cases=tuple(sorted(cases, key=lambda item: item.case_id)),
    )
    protocol = SemanticRouteProtocol(
        protocol_version=plan_version,
        protocol_id=protocol_id,
        created_at=created_at,
        plan_digest=plan.content_digest,
    )
    return plan, protocol


def semantic_route_generation_prompt(plan: SemanticRoutePlan) -> str:
    """Render a label-visible packet for a synthetic wording generator."""

    cases = [{"case_id": case.case_id, "brief": case.generation_brief} for case in plan.cases]
    disclosure_boundary = (
        " The generated message text itself must not mention or imply that it is synthetic, "
        "fictional, hypothetical, imaginary, a benchmark, or a test fixture."
        if plan.plan_version in {"2.0.0", "3.0.0", "4.0.0"}
        else ""
    )
    return (
        "Generate fictional user-message wording for a fixed semantic-route benchmark. The "
        "messages are synthetic and are not real user feedback. Do not use tools, files, web "
        "access, memories, or prior conversations. Preserve every case_id and order. Return one "
        "short natural message for every brief. Do not reveal or invent real names, products, "
        "repositories, paths, URLs, credentials, code, or private facts."
        + disclosure_boundary
        + " Return only the "
        "schema-bound JSON.\n\n" + str({"source_plan_digest": plan.content_digest, "cases": cases})
    )


def attest_semantic_route_generation(
    plan: SemanticRoutePlan,
    proposal: SemanticRouteGeneration,
) -> SemanticRouteGeneration:
    """Replace model-echoed bindings and require the exact case inventory."""

    expected_ids = tuple(item.case_id for item in plan.cases)
    if tuple(item.case_id for item in proposal.items) != expected_ids:
        raise ValueError("semantic route generation omitted, reordered, or invented cases")
    return proposal.model_copy(
        update={
            "generation_version": plan.plan_version,
            "source_plan_digest": plan.content_digest,
        }
    )


def semantic_route_blind_audit_prompt(
    generation: SemanticRouteGeneration,
    *,
    auditor_id: Identifier,
) -> str:
    """Render a classification packet containing no intended labels or plan content."""

    cases = [{"case_id": item.case_id, "text": item.text} for item in generation.items]
    return (
        "Classify fictional user messages for a semantic-routing benchmark. You are intentionally "
        "blind to the answer key and generation briefs. Do not infer labels from case IDs; treat "
        "them as opaque. Do not use tools, files, web access, memories, or prior conversations.\n\n"
        "Choose exactly one class per message:\n"
        "- memory: a stable reusable first-person non-normative fact, without asking the "
        "assistant to behave a way; transient state limited to today, right now, lately, or an "
        "unsettled situation is no_durable_signal;\n"
        "- preference: a stable desired choice or tendency, without a hard invariant or workflow;\n"
        "- procedure: a repeatable trigger plus ordered workflow;\n"
        "- prompt_rule: a hard always/never invariant or prohibition, not an ordered workflow;\n"
        "- positive_example: an explicitly endorsed prior pattern requested for later imitation;\n"
        "- revocation: explicit removal of an exact active adaptation artifact ID;\n"
        "- ambiguous: durable intent exists but the exact class cannot be determined;\n"
        "- no_durable_signal: no reusable user learning is expressed.\n\n"
        "Classify scope as permanent_profile only when it is explicitly general across future "
        "projects, current_context only when explicitly limited to one named current project, "
        "ambiguous when "
        "a durable scope is unclear, and no_durable_signal when no learning exists. Use the closed "
        "reason matching your class. Preserve case order and return only schema-bound JSON.\n\n"
        + str(
            {
                "auditor_id": auditor_id,
                "source_generation_digest": generation.content_digest,
                "labels_visible": False,
                "cases": cases,
            }
        )
    )


def _single_character_edit(left: str, right: str) -> bool:
    """Return whether two opaque identifiers differ by exactly one character edit."""

    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) == 1
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    short_index = long_index = differences = 0
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        differences += 1
        long_index += 1
        if differences > 1:
            return False
    return True


def attest_semantic_route_blind_audit(
    generation: SemanticRouteGeneration,
    proposal: SemanticRouteBlindAudit,
    *,
    auditor_id: Identifier,
) -> SemanticRouteBlindAudit:
    """Bind blind predictions to exact generated bytes using local deterministic code."""

    expected_ids = tuple(item.case_id for item in generation.items)
    if len(proposal.entries) != len(expected_ids):
        raise ValueError("blind route audit omitted or invented cases")
    repaired_entries = []
    for expected_id, entry in zip(expected_ids, proposal.entries, strict=True):
        if entry.case_id != expected_id and not _single_character_edit(
            entry.case_id,
            expected_id,
        ):
            raise ValueError("blind route audit reordered or invented a case")
        repaired_entries.append(entry.model_copy(update={"case_id": expected_id}))
    return proposal.model_copy(
        update={
            "auditor_id": auditor_id,
            "source_generation_digest": generation.content_digest,
            "labels_visible": False,
            "entries": tuple(repaired_entries),
        }
    )


def freeze_semantic_route_corpus(
    plan: SemanticRoutePlan,
    generation: SemanticRouteGeneration,
) -> SemanticFeedbackCorpus:
    """Freeze exact generated text with the pre-existing answer key."""

    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("semantic route generation does not bind the exact plan")
    generated = {item.case_id: item.text for item in generation.items}
    if tuple(generated) != tuple(item.case_id for item in plan.cases):
        raise ValueError("semantic route generation inventory does not match the plan")
    exact_revocations = plan.plan_version in {"3.0.0", "4.0.0"}
    durable_memory_contract = plan.plan_version == "4.0.0"
    return SemanticFeedbackCorpus(
        corpus_version=(
            "6.0.0" if durable_memory_contract else ("5.0.0" if exact_revocations else "4.0.0")
        ),
        corpus_id=(
            "semantic-route-discrimination-v4"
            if durable_memory_contract
            else (
                "semantic-route-discrimination-v3"
                if exact_revocations
                else "semantic-route-discrimination-v1"
            )
        ),
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


def _blind_metrics(
    plan: SemanticRoutePlan,
    auditor_a: SemanticRouteBlindAudit,
    auditor_b: SemanticRouteBlindAudit,
) -> SemanticRouteBlindMetrics:
    expected = {item.case_id: item for item in plan.cases}
    by_a = {item.case_id: item for item in auditor_a.entries}
    by_b = {item.case_id: item for item in auditor_b.entries}
    expected_ids = tuple(expected)
    if tuple(by_a) != expected_ids or tuple(by_b) != expected_ids:
        raise ValueError("blind route audits do not match the route plan")
    label_a = label_b = scope_a = scope_b = pair_label = pair_scope = both = 0
    ambiguous: set[str] = set()
    for case_id, case in expected.items():
        entry_a = by_a[case_id]
        entry_b = by_b[case_id]
        expected_class = _BLIND_CLASS_FOR_EXPECTED[case.semantic_class]
        expected_scope = BlindRouteScope(case.scope_hint.value)
        match_label_a = entry_a.classification is expected_class
        match_label_b = entry_b.classification is expected_class
        match_scope_a = entry_a.scope is expected_scope
        match_scope_b = entry_b.scope is expected_scope
        label_a += int(match_label_a)
        label_b += int(match_label_b)
        scope_a += int(match_scope_a)
        scope_b += int(match_scope_b)
        pair_label += int(entry_a.classification is entry_b.classification)
        pair_scope += int(entry_a.scope is entry_b.scope)
        both += int(match_label_a and match_label_b and match_scope_a and match_scope_b)
        if (
            entry_a.classification is BlindRouteClass.AMBIGUOUS
            or entry_b.classification is BlindRouteClass.AMBIGUOUS
            or entry_a.scope is BlindRouteScope.AMBIGUOUS
            or entry_b.scope is BlindRouteScope.AMBIGUOUS
        ):
            ambiguous.add(case_id)
    count = len(expected)
    return SemanticRouteBlindMetrics(
        auditor_a_label_accuracy=_ratio(label_a, count),
        auditor_b_label_accuracy=_ratio(label_b, count),
        auditor_a_scope_accuracy=_ratio(scope_a, count),
        auditor_b_scope_accuracy=_ratio(scope_b, count),
        pair_label_agreement=_ratio(pair_label, count),
        pair_scope_agreement=_ratio(pair_scope, count),
        both_match_answer_key_count=both,
        ambiguous_case_ids=tuple(sorted(ambiguous)),
    )


def _class_metrics(
    plan: SemanticRoutePlan,
    calibration_report: SemanticEvaluationReport,
    holdout_report: SemanticEvaluationReport,
) -> tuple[SemanticRouteClassMetrics, ...]:
    plan_by_id = {item.case_id: item for item in plan.cases}
    reports = {
        "calibration": calibration_report,
        "holdout": holdout_report,
    }
    output: list[SemanticRouteClassMetrics] = []
    for split in ("calibration", "holdout", "combined"):
        evaluations = tuple(
            item
            for report_split, report in reports.items()
            if split == "combined" or split == report_split
            for item in report.case_evaluations
        )
        for semantic_class in SemanticRouteClass:
            selected = tuple(
                item
                for item in evaluations
                if plan_by_id[item.case_id].semantic_class is semantic_class
            )
            detected = sum(item.predicted_durable for item in selected)
            route_correct = sum(item.route_correct for item in selected)
            scope_correct = sum(item.scope_correct for item in selected)
            output.append(
                SemanticRouteClassMetrics(
                    split=split,
                    semantic_class=semantic_class,
                    case_count=len(selected),
                    detected_count=detected,
                    exact_route_count=route_correct,
                    exact_scope_count=scope_correct,
                    detection_accuracy=_ratio(detected, len(selected)),
                    route_accuracy=_ratio(route_correct, detected),
                    scope_accuracy=_ratio(scope_correct, detected),
                )
            )
    return tuple(output)


def summarize_semantic_route_benchmark(
    *,
    created_at: datetime,
    protocol: SemanticRouteProtocol,
    plan: SemanticRoutePlan,
    generation: SemanticRouteGeneration,
    corpus: SemanticFeedbackCorpus,
    auditor_a: SemanticRouteBlindAudit,
    auditor_b: SemanticRouteBlindAudit,
    calibration_report: SemanticEvaluationReport,
    holdout_report: SemanticEvaluationReport,
) -> SemanticRouteSummary:
    """Combine blind-oracle and detector results under a preregistered conservative gate."""

    if protocol.plan_digest != plan.content_digest:
        raise ValueError("semantic route protocol does not bind the exact plan")
    if generation.source_plan_digest != plan.content_digest:
        raise ValueError("semantic route generation does not bind the exact plan")
    if auditor_a.source_generation_digest != generation.content_digest:
        raise ValueError("semantic route auditor A does not bind the generation")
    if auditor_b.source_generation_digest != generation.content_digest:
        raise ValueError("semantic route auditor B does not bind the generation")
    if calibration_report.effective_corpus_digest != corpus.content_digest:
        raise ValueError("calibration report does not bind the exact route corpus")
    if holdout_report.effective_corpus_digest != corpus.content_digest:
        raise ValueError("holdout report does not bind the exact route corpus")
    blind = _blind_metrics(plan, auditor_a, auditor_b)
    classes = _class_metrics(plan, calibration_report, holdout_report)
    holdout_classes = tuple(item for item in classes if item.split == "holdout")
    gate = (
        calibration_report.metrics.recall == 1.0
        and holdout_report.metrics.recall == 1.0
        and calibration_report.metrics.route_accuracy >= 0.90
        and holdout_report.metrics.route_accuracy >= 0.90
        and calibration_report.metrics.scope_accuracy >= 0.90
        and holdout_report.metrics.scope_accuracy >= 0.90
        and all(item.route_accuracy >= 0.80 for item in holdout_classes)
        and blind.auditor_a_label_accuracy >= 0.90
        and blind.auditor_b_label_accuracy >= 0.90
        and blind.pair_label_agreement >= 0.90
    )
    failures = tuple(
        sorted(
            set(calibration_report.failed_case_ids)
            | set(holdout_report.failed_case_ids)
            | set(blind.ambiguous_case_ids)
        )
    )
    return SemanticRouteSummary(
        created_at=created_at,
        protocol_digest=protocol.content_digest,
        plan_digest=plan.content_digest,
        generation_digest=generation.content_digest,
        corpus_digest=corpus.content_digest,
        auditor_a_digest=auditor_a.content_digest,
        auditor_b_digest=auditor_b.content_digest,
        calibration_report_digest=calibration_report.content_digest,
        holdout_report_digest=holdout_report.content_digest,
        blind_metrics=blind,
        class_metrics=classes,
        route_gate_passed=gate,
        failed_case_ids=failures,
    )
