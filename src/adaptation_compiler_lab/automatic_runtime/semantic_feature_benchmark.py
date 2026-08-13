"""Fresh blind holdout for structured semantic extraction and deterministic routing."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackSignalKind,
    SemanticRouteResolution,
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


class SemanticFeatureClass(StrEnum):
    MEMORY = "memory"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    PROMPT_RULE = "prompt_rule"
    POSITIVE_EXAMPLE = "positive_example"
    REVOCATION = "revocation"
    CORRECTION = "correction"
    AMBIGUOUS = "ambiguous"


class SemanticFeatureStyle(StrEnum):
    DIRECT = "direct"
    CONVERSATIONAL = "conversational"
    FRAGMENT = "fragment"
    TYPOS = "typos"
    CONTRASTIVE = "contrastive"
    INDIRECT = "indirect"
    EMPHATIC = "emphatic"
    NEGATED_ALTERNATIVE = "negated_alternative"


class SemanticFeatureScenario(FrozenModel):
    case_id: Identifier
    semantic_class: SemanticFeatureClass
    style: SemanticFeatureStyle
    scope_hint: SemanticScopeHint
    context_name: NonEmptyStr | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    topic: Identifier
    secondary_topic: Identifier | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    brief: NonEmptyStr
    expectation: SemanticFeedbackExpectation
    expected_route_candidates: tuple[ArtifactRoute, ...]
    expected_resolution: SemanticRouteResolution

    @field_validator("expected_route_candidates")
    @classmethod
    def candidates_are_sorted_unique(
        cls, value: tuple[ArtifactRoute, ...]
    ) -> tuple[ArtifactRoute, ...]:
        raw = tuple(item.value for item in value)
        if not strings_are_sorted_unique(raw):
            raise ValueError("feature benchmark candidates must be sorted and unique")
        return value


class SemanticFeaturePlan(FrozenModel):
    plan_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0"] = "1.0.0"
    plan_id: Literal["milestone-6a2i-feature-holdout"] = "milestone-6a2i-feature-holdout"
    created_at: UtcDateTime
    seed_digest: Sha256Digest
    calibration_corpus_digest: Sha256Digest
    supersedes_plan_digest: Sha256Digest | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    synthetic_only: Literal[True] = True
    synthetic_is_user_authority: Literal[False] = False
    production_promotion_permitted: Literal[False] = False
    production_state_mutation_permitted: Literal[False] = False
    scenarios: Annotated[tuple[SemanticFeatureScenario, ...], Field(min_length=64, max_length=64)]

    @field_validator("scenarios")
    @classmethod
    def scenarios_are_sorted_unique(
        cls, value: tuple[SemanticFeatureScenario, ...]
    ) -> tuple[SemanticFeatureScenario, ...]:
        ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(ids):
            raise ValueError("feature benchmark scenarios must be sorted by unique case ID")
        return value

    @model_validator(mode="after")
    def design_is_balanced(self) -> SemanticFeaturePlan:
        for semantic_class in SemanticFeatureClass:
            selected = tuple(
                item for item in self.scenarios if item.semantic_class is semantic_class
            )
            if len(selected) != 8:
                raise ValueError("feature benchmark requires eight cases per semantic class")
            if {item.style for item in selected} != set(SemanticFeatureStyle):
                raise ValueError("every feature class must cover all wording styles")
            if {item.scope_hint for item in selected} != set(SemanticScopeHint):
                raise ValueError("every feature class must cover both scope hints")
        if self.plan_version == "4.0.0":
            for scenario in self.scenarios:
                if scenario.scope_hint is SemanticScopeHint.CURRENT_CONTEXT:
                    if scenario.context_name is None:
                        raise ValueError("v4 current-context cases require an explicit context")
                elif scenario.context_name is not None:
                    raise ValueError("v4 permanent-profile cases cannot carry a context name")
        if self.plan_version == "5.0.0":
            for scenario in self.scenarios:
                if scenario.scope_hint is SemanticScopeHint.CURRENT_CONTEXT:
                    if scenario.context_name is None:
                        raise ValueError("v5 current-context cases require an explicit context")
                elif scenario.context_name is not None:
                    raise ValueError("v5 permanent-profile cases cannot carry a context name")
                if scenario.semantic_class is SemanticFeatureClass.AMBIGUOUS:
                    if (
                        scenario.secondary_topic is None
                        or scenario.secondary_topic == scenario.topic
                    ):
                        raise ValueError("v5 ambiguous cases require two distinct topics")
                elif scenario.secondary_topic is not None:
                    raise ValueError("v5 resolved cases cannot carry a secondary topic")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticArchitectureBinding(FrozenModel):
    component: Identifier
    digest: Sha256Digest


class SemanticFeatureProtocol(FrozenModel):
    protocol_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0", "5.1.0"] = "1.0.0"
    protocol_id: Literal["milestone-6a2i-structured-route-gate"] = (
        "milestone-6a2i-structured-route-gate"
    )
    created_at: UtcDateTime
    plan_digest: Sha256Digest
    calibration_corpus_digest: Sha256Digest
    supersedes_protocol_digest: Sha256Digest | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    architecture_bindings: Annotated[tuple[SemanticArchitectureBinding, ...], Field(min_length=4)]
    holdout_case_count: Literal[64] = 64
    one_sensor_execution: Literal[True] = True
    two_blind_auditors: Literal[True] = True
    minimum_detection_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_scope_accuracy: float = Field(default=1.0, ge=0, le=1)
    minimum_overall_class_accuracy: float = Field(default=0.9, ge=0, le=1)
    minimum_resolved_class_accuracy: float = Field(default=0.75, ge=0, le=1)
    safety_classes_require_perfect_accuracy: Literal[True] = True
    automatic_promotion_if_passed: Literal[False] = False
    sealed_external_study_access_permitted: Literal[False] = False
    provider_billed_calls_permitted: Literal[False] = False

    @field_validator("architecture_bindings")
    @classmethod
    def bindings_are_sorted_unique(
        cls, value: tuple[SemanticArchitectureBinding, ...]
    ) -> tuple[SemanticArchitectureBinding, ...]:
        names = tuple(item.component for item in value)
        if not strings_are_sorted_unique(names):
            raise ValueError("architecture bindings must be sorted and unique")
        return value

    @model_validator(mode="after")
    def thresholds_are_frozen(self) -> SemanticFeatureProtocol:
        if (
            self.minimum_detection_accuracy,
            self.minimum_scope_accuracy,
            self.minimum_overall_class_accuracy,
            self.minimum_resolved_class_accuracy,
        ) != (1.0, 1.0, 0.9, 0.75):
            raise ValueError("feature benchmark thresholds are frozen")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticFeatureGeneratedItem(FrozenModel):
    case_id: Identifier
    message: str = Field(min_length=12, max_length=600)


class SemanticFeatureGeneration(FrozenModel):
    generation_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0"] = "1.0.0"
    plan_digest: Sha256Digest
    synthetic_only: Literal[True] = True
    items: Annotated[tuple[SemanticFeatureGeneratedItem, ...], Field(min_length=64, max_length=64)]

    @field_validator("items")
    @classmethod
    def items_are_sorted_unique(
        cls, value: tuple[SemanticFeatureGeneratedItem, ...]
    ) -> tuple[SemanticFeatureGeneratedItem, ...]:
        ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(ids):
            raise ValueError("feature generation must be sorted by unique case ID")
        messages = tuple(item.message.casefold() for item in value)
        if len(messages) != len(set(messages)):
            raise ValueError("feature generation messages must be unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticFeatureRemediation(FrozenModel):
    remediation_version: Literal["1.0.0"] = "1.0.0"
    plan_digest: Sha256Digest
    source_generation_digest: Sha256Digest
    synthetic_only: Literal[True] = True
    items: Annotated[tuple[SemanticFeatureGeneratedItem, ...], Field(min_length=1, max_length=64)]

    @field_validator("items")
    @classmethod
    def items_are_sorted_unique(
        cls, value: tuple[SemanticFeatureGeneratedItem, ...]
    ) -> tuple[SemanticFeatureGeneratedItem, ...]:
        ids = tuple(item.case_id for item in value)
        if not strings_are_sorted_unique(ids):
            raise ValueError("feature remediation must be sorted by unique case ID")
        return value


class SemanticFeatureBlindEntry(FrozenModel):
    case_id: Identifier | None = Field(default=None, exclude_if=lambda value: value is None)
    case_index: int | None = Field(
        default=None,
        ge=0,
        le=63,
        exclude_if=lambda value: value is None,
    )
    classification: SemanticFeatureClass
    scope_hint: SemanticScopeHint

    @model_validator(mode="after")
    def exactly_one_case_reference(self) -> SemanticFeatureBlindEntry:
        if (self.case_id is None) == (self.case_index is None):
            raise ValueError("feature audit entry requires exactly one case reference")
        return self


class SemanticFeatureBlindAudit(FrozenModel):
    audit_version: Literal["1.0.0"] = "1.0.0"
    auditor_id: Identifier
    generation_digest: Sha256Digest
    entries: Annotated[tuple[SemanticFeatureBlindEntry, ...], Field(min_length=64, max_length=64)]

    @field_validator("entries")
    @classmethod
    def entries_are_sorted_unique(
        cls, value: tuple[SemanticFeatureBlindEntry, ...]
    ) -> tuple[SemanticFeatureBlindEntry, ...]:
        if all(item.case_id is not None for item in value):
            ids = tuple(str(item.case_id) for item in value)
            if not strings_are_sorted_unique(ids):
                raise ValueError("feature audit must be sorted by unique case ID")
        elif all(item.case_index is not None for item in value):
            indexes_list: list[int] = []
            for item in value:
                if item.case_index is None:
                    raise ValueError("feature audit cannot mix case IDs and indexes")
                indexes_list.append(item.case_index)
            indexes = tuple(indexes_list)
            if indexes != tuple(range(len(value))):
                raise ValueError("feature audit must use every sorted case index exactly once")
        else:
            raise ValueError("feature audit cannot mix case IDs and indexes")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class SemanticFeatureClassMetrics(FrozenModel):
    semantic_class: SemanticFeatureClass
    case_count: int = Field(ge=1)
    sensor_correct: int = Field(ge=0)
    sensor_accuracy: float = Field(ge=0, le=1)


class SemanticFeatureSummary(FrozenModel):
    summary_version: Literal["1.0.0"] = "1.0.0"
    created_at: UtcDateTime
    protocol_digest: Sha256Digest
    plan_digest: Sha256Digest
    generation_digest: Sha256Digest
    corpus_digest: Sha256Digest
    auditor_a_digest: Sha256Digest
    auditor_b_digest: Sha256Digest
    report_digest: Sha256Digest
    detection_accuracy: float = Field(ge=0, le=1)
    scope_accuracy: float = Field(ge=0, le=1)
    sensor_class_accuracy: float = Field(ge=0, le=1)
    feature_decision_accuracy: float = Field(ge=0, le=1)
    auditor_a_accuracy: float = Field(ge=0, le=1)
    auditor_b_accuracy: float = Field(ge=0, le=1)
    auditor_pair_agreement: float = Field(ge=0, le=1)
    class_metrics: tuple[SemanticFeatureClassMetrics, ...]
    failed_case_ids: tuple[Identifier, ...]
    development_gate_passed: bool
    production_mode: Literal["review"] = "review"
    synthetic_is_user_authority: Literal[False] = False
    automatic_promotion_authorized: Literal[False] = False

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


_TOPICS = (
    "accounting_periods",
    "archive_layout",
    "branch_naming",
    "build_logs",
    "calendar_boundaries",
    "change_summaries",
    "client_regions",
    "command_examples",
    "deployment_windows",
    "design_tokens",
    "diagnostic_notes",
    "document_headings",
    "error_reports",
    "fixture_names",
    "handoff_notes",
    "incident_owners",
    "invoice_formats",
    "issue_labels",
    "keyboard_navigation",
    "language_versions",
    "local_caches",
    "log_retention",
    "meeting_records",
    "migration_checks",
    "module_boundaries",
    "network_fallbacks",
    "notification_timing",
    "package_updates",
    "path_quoting",
    "permission_reviews",
    "preview_commands",
    "privacy_labels",
    "project_aliases",
    "release_notes",
    "request_scopes",
    "research_claims",
    "review_queues",
    "rollback_steps",
    "runtime_versions",
    "screen_reader_labels",
    "search_filters",
    "secret_scans",
    "shell_dialects",
    "source_citations",
    "status_updates",
    "storage_limits",
    "support_rotations",
    "sync_backups",
    "task_owners",
    "test_commands",
    "time_zones",
    "tool_permissions",
    "trace_fields",
    "usage_budgets",
    "user_prompts",
    "validation_order",
    "version_pins",
    "workspace_roots",
    "writing_tone",
    "approval_records",
    "dependency_updates",
    "failure_messages",
    "output_examples",
    "review_checklists",
)
_TOPICS_V3 = (
    "api_responses",
    "artifact_names",
    "backup_locations",
    "batch_sizes",
    "browser_support",
    "cache_keys",
    "change_approvals",
    "code_comments",
    "commit_messages",
    "configuration_files",
    "consent_notices",
    "data_exports",
    "database_migrations",
    "date_formats",
    "dependency_pins",
    "deployment_checks",
    "directory_names",
    "error_context",
    "evaluation_rubrics",
    "feature_flags",
    "file_encodings",
    "form_labels",
    "handoff_commands",
    "health_checks",
    "incident_summaries",
    "input_validation",
    "issue_templates",
    "job_timeouts",
    "keyboard_shortcuts",
    "license_headers",
    "local_services",
    "log_fields",
    "merge_checks",
    "metric_names",
    "model_versions",
    "network_retries",
    "notification_channels",
    "package_names",
    "pagination_limits",
    "permission_prompts",
    "preview_outputs",
    "privacy_reviews",
    "project_roots",
    "release_tags",
    "request_ids",
    "research_sources",
    "review_assignments",
    "rollback_commands",
    "runtime_flags",
    "screen_reader_text",
    "search_queries",
    "security_findings",
    "shell_commands",
    "source_links",
    "status_reports",
    "storage_paths",
    "support_handoffs",
    "sync_conflicts",
    "task_priorities",
    "test_fixtures",
    "time_limits",
    "tool_allowlists",
    "trace_events",
    "usage_reports",
)
_TOPICS_V4 = (
    "accessibility_audits",
    "api_timeouts",
    "approval_chains",
    "archive_formats",
    "audit_fields",
    "auth_scopes",
    "backup_checks",
    "batch_reports",
    "branch_protection",
    "browser_tests",
    "cache_expiry",
    "changelog_entries",
    "citation_formats",
    "cleanup_steps",
    "client_versions",
    "command_output",
    "config_precedence",
    "consent_expiry",
    "cost_limits",
    "data_redaction",
    "dependency_ranges",
    "deployment_regions",
    "diff_summaries",
    "disaster_recovery",
    "documentation_links",
    "error_codes",
    "evaluation_notes",
    "export_formats",
    "feature_rollouts",
    "file_permissions",
    "form_errors",
    "incident_channels",
    "input_formats",
    "issue_priorities",
    "job_retries",
    "keyboard_focus",
    "license_checks",
    "local_ports",
    "log_levels",
    "merge_owners",
    "metric_thresholds",
    "migration_order",
    "model_fallbacks",
    "network_ports",
    "notification_copy",
    "package_sources",
    "pagination_tokens",
    "permission_boundaries",
    "preview_limits",
    "privacy_exceptions",
    "project_templates",
    "release_approvals",
    "request_timeouts",
    "research_dates",
    "review_evidence",
    "rollback_points",
    "runtime_paths",
    "screen_sizes",
    "search_order",
    "secret_rotation",
    "shell_paths",
    "source_versions",
    "status_intervals",
    "storage_quotas",
)
_TOPICS_V5 = (
    "artifact_retention",
    "assistant_tone",
    "audit_exports",
    "authorization_boundaries",
    "background_jobs",
    "billing_cycles",
    "browser_permissions",
    "build_artifacts",
    "cancellation_handling",
    "case_normalization",
    "code_ownership",
    "command_retries",
    "compliance_labels",
    "configuration_defaults",
    "connection_pools",
    "content_warnings",
    "cookie_settings",
    "crash_reports",
    "credential_storage",
    "data_backfills",
    "deletion_notices",
    "delivery_formats",
    "dependency_sources",
    "design_reviews",
    "directory_cleanup",
    "documentation_examples",
    "editor_settings",
    "escalation_paths",
    "experiment_rollouts",
    "export_redaction",
    "feature_ownership",
    "filename_conventions",
    "firewall_rules",
    "form_validation",
    "incident_severity",
    "indexing_schedules",
    "integration_tests",
    "localization_fallbacks",
    "lockfile_updates",
    "maintenance_windows",
    "merge_strategies",
    "message_summaries",
    "monitoring_alerts",
    "naming_conventions",
    "offline_behavior",
    "package_mirrors",
    "password_rotation",
    "performance_budgets",
    "platform_support",
    "pull_request_templates",
    "query_limits",
    "recovery_codes",
    "release_channels",
    "repository_archives",
    "response_formats",
    "retry_backoff",
    "review_deadlines",
    "risk_acceptance",
    "sandbox_limits",
    "schema_migrations",
    "session_expiry",
    "telemetry_fields",
    "test_isolation",
    "warning_messages",
)
_CONTEXT_NAMES = (
    "Project Atlas",
    "Project Birch",
    "Project Comet",
    "Project Delta",
    "Project Ember",
    "Project Fjord",
    "Project Grove",
    "Project Harbor",
)
_CONTEXT_NAMES_V5 = (
    "Project Iris",
    "Project Juniper",
    "Project Kestrel",
    "Project Lumen",
    "Project Meridian",
    "Project Nimbus",
    "Project Onyx",
    "Project Prairie",
)
_ROUTE_BY_CLASS = {
    SemanticFeatureClass.MEMORY: ArtifactRoute.MEMORY,
    SemanticFeatureClass.PREFERENCE: ArtifactRoute.PREFERENCE,
    SemanticFeatureClass.PROCEDURE: ArtifactRoute.PROCEDURE,
    SemanticFeatureClass.PROMPT_RULE: ArtifactRoute.PROMPT_RULE,
    SemanticFeatureClass.POSITIVE_EXAMPLE: ArtifactRoute.EXAMPLE,
}
_KIND_BY_CLASS = {
    SemanticFeatureClass.MEMORY: FeedbackSignalKind.MEMORY,
    SemanticFeatureClass.PREFERENCE: FeedbackSignalKind.PREFERENCE,
    SemanticFeatureClass.PROCEDURE: FeedbackSignalKind.PROCEDURE,
    SemanticFeatureClass.PROMPT_RULE: FeedbackSignalKind.PROMPT_RULE,
    SemanticFeatureClass.POSITIVE_EXAMPLE: FeedbackSignalKind.POSITIVE_EXAMPLE,
}
_AMBIGUOUS_CANDIDATES = (
    (ArtifactRoute.MEMORY, ArtifactRoute.PREFERENCE),
    (ArtifactRoute.PROCEDURE, ArtifactRoute.PROMPT_RULE),
    (ArtifactRoute.EXAMPLE, ArtifactRoute.PROMPT_RULE),
    (ArtifactRoute.MEMORY, ArtifactRoute.PROCEDURE),
)
_FORBIDDEN_FRAMING = ("synthetic", "benchmark", "fictional", "hypothetical", "classification")


def _case_id(seed: str, semantic_class: SemanticFeatureClass, index: int, topic: str) -> str:
    source = f"{seed}\0{semantic_class.value}\0{index}\0{topic}".encode()
    digest = hashlib.sha256(source).hexdigest()
    return f"feature-{digest[:20]}"


def _brief(
    semantic_class: SemanticFeatureClass,
    *,
    scope: SemanticScopeHint,
    topic: str,
    index: int,
    affected_artifact_id: str | None,
    revision: Literal["v1", "v2", "v3", "v4", "v5"],
    context_name: str | None,
    secondary_topic: str | None,
) -> str:
    if revision in {"v4", "v5"}:
        if scope is SemanticScopeHint.CURRENT_CONTEXT:
            if context_name is None:
                raise ValueError("v4 current-context brief lacks a context name")
            scope_text = (
                f"future work only in {context_name}. Include the exact name '{context_name}' "
                "and make every durable clause apply only there"
            )
        else:
            scope_text = (
                "future work generally. Include the exact phrase 'across all future projects'"
            )
    else:
        scope_text = (
            (
                "future work in one named fictional project"
                if revision == "v1"
                else "future work in one named project"
            )
            if scope is SemanticScopeHint.CURRENT_CONTEXT
            else "future work generally without naming a project"
        )
    common = f"Write one natural user message about {topic.replace('_', ' ')} for {scope_text}."
    if semantic_class is SemanticFeatureClass.MEMORY:
        return common + (
            " State only a stable user circumstance or environment fact; express no choice or rule."
        )
    if semantic_class is SemanticFeatureClass.PREFERENCE:
        return common + (
            " Express one soft future choice; include no stable fact, example, trigger, "
            "sequence, or invariant."
        )
    if semantic_class is SemanticFeatureClass.PROCEDURE:
        return common + (
            " Express one recurring trigger and an ordered two-step workflow without "
            "always/never/must."
        )
    if semantic_class is SemanticFeatureClass.PROMPT_RULE:
        return common + (
            " Express one hard required or prohibited behavior without a sequence or "
            "reusable example."
        )
    if semantic_class is SemanticFeatureClass.POSITIVE_EXAMPLE:
        return common + (
            " Explicitly endorse one concrete prior output, pattern, model, or example for "
            "later imitation; do not refine it."
        )
    if semantic_class is SemanticFeatureClass.REVOCATION:
        return common + (
            f" Explicitly remove exact active adaptation artifact {affected_artifact_id}; "
            "include that ID verbatim."
        )
    if semantic_class is SemanticFeatureClass.CORRECTION:
        route = tuple(_ROUTE_BY_CLASS.values())[index % len(_ROUTE_BY_CLASS)]
        return common + (
            " Use two clauses: explicitly say the earlier behavior was wrong or unsuitable, "
            f"then say 'Instead' and give corrected content that naturally maps to {route.value}."
        )
    pair = _AMBIGUOUS_CANDIDATES[index % len(_AMBIGUOUS_CANDIDATES)]
    if revision == "v5":
        if secondary_topic is None:
            raise ValueError("v5 ambiguous brief lacks a secondary topic")
        return common + (
            " Write exactly two unrelated durable sentences. The first is about "
            f"{topic.replace('_', ' ')} "
            f"and clearly expresses {pair[0].value}. The second is about "
            f"{secondary_topic.replace('_', ' ')} and clearly expresses {pair[1].value}. "
            "Repeat the required scope wording in both sentences. Neither sentence may be a "
            "step, consequence, explanation, prerequisite, or refinement of the other."
        )
    return common + (
        " Write two separate sentences, each independently durable: one clearly expresses "
        f"{pair[0].value}, and the other clearly expresses {pair[1].value}. Do not blend them "
        "into one idea or make either sentence explain the other; both must remain applicable "
        "so review is necessary."
    )


def build_semantic_feature_design(
    *,
    created_at: UtcDateTime,
    calibration_corpus_digest: Sha256Digest,
    architecture_bindings: tuple[SemanticArchitectureBinding, ...],
    revision: Literal["v1", "v2", "v3", "v4", "v5"] = "v1",
    prior_plan_digest: Sha256Digest | None = None,
    prior_protocol_digest: Sha256Digest | None = None,
) -> tuple[SemanticFeaturePlan, SemanticFeatureProtocol]:
    if revision == "v1" and (prior_plan_digest is not None or prior_protocol_digest is not None):
        raise ValueError("feature benchmark v1 cannot supersede prior records")
    if revision in {"v2", "v3", "v4", "v5"} and (
        prior_plan_digest is None or prior_protocol_digest is None
    ):
        raise ValueError(
            "feature benchmark revision requires exact prior plan and protocol digests"
        )
    seed = f"adaptation-compiler-lab-6a2i-feature-holdout-{revision}"
    topics = {"v3": _TOPICS_V3, "v4": _TOPICS_V4, "v5": _TOPICS_V5}.get(revision, _TOPICS)
    scenarios: list[SemanticFeatureScenario] = []
    topic_index = 0
    for semantic_class in SemanticFeatureClass:
        for index, style in enumerate(SemanticFeatureStyle):
            topic = topics[topic_index]
            topic_index += 1
            scope = (
                SemanticScopeHint.PERMANENT_PROFILE
                if index % 2 == 0
                else SemanticScopeHint.CURRENT_CONTEXT
            )
            affected = (
                f"artifact-{hashlib.sha256(topic.encode()).hexdigest()[:16]}"
                if semantic_class is SemanticFeatureClass.REVOCATION
                else None
            )
            context_names = _CONTEXT_NAMES_V5 if revision == "v5" else _CONTEXT_NAMES
            context_name = (
                context_names[index]
                if revision in {"v4", "v5"} and scope is SemanticScopeHint.CURRENT_CONTEXT
                else None
            )
            secondary_topic = (
                topics[index]
                if revision == "v5" and semantic_class is SemanticFeatureClass.AMBIGUOUS
                else None
            )
            route: ArtifactRoute | None
            kind: FeedbackSignalKind
            candidates: tuple[ArtifactRoute, ...]
            resolution: SemanticRouteResolution
            if semantic_class in _ROUTE_BY_CLASS:
                route = _ROUTE_BY_CLASS[semantic_class]
                kind = _KIND_BY_CLASS[semantic_class]
                candidates = (route,)
                resolution = SemanticRouteResolution.RESOLVED
            elif semantic_class is SemanticFeatureClass.REVOCATION:
                route = None
                kind = FeedbackSignalKind.REVOCATION
                candidates = ()
                resolution = SemanticRouteResolution.RESOLVED
            elif semantic_class is SemanticFeatureClass.CORRECTION:
                route = tuple(_ROUTE_BY_CLASS.values())[index % len(_ROUTE_BY_CLASS)]
                kind = FeedbackSignalKind.CORRECTION
                candidates = (route,)
                resolution = SemanticRouteResolution.RESOLVED
            else:
                candidates = _AMBIGUOUS_CANDIDATES[index % len(_AMBIGUOUS_CANDIDATES)]
                route = candidates[0]
                kind = {
                    ArtifactRoute.MEMORY: FeedbackSignalKind.MEMORY,
                    ArtifactRoute.EXAMPLE: FeedbackSignalKind.POSITIVE_EXAMPLE,
                    ArtifactRoute.PROCEDURE: FeedbackSignalKind.PROCEDURE,
                }[route]
                resolution = SemanticRouteResolution.AMBIGUOUS
            scenario = SemanticFeatureScenario(
                case_id=_case_id(seed, semantic_class, index, topic),
                semantic_class=semantic_class,
                style=style,
                scope_hint=scope,
                context_name=context_name,
                topic=topic,
                secondary_topic=secondary_topic,
                brief=_brief(
                    semantic_class,
                    scope=scope,
                    topic=topic,
                    index=index,
                    affected_artifact_id=affected,
                    revision=revision,
                    context_name=context_name,
                    secondary_topic=secondary_topic,
                ),
                expectation=SemanticFeedbackExpectation(
                    durable_signal=True,
                    accepted_signal_kinds=(kind,),
                    accepted_routes=(() if route is None else (route,)),
                    scope_hint=scope,
                    affected_artifact_id=affected,
                ),
                expected_route_candidates=candidates,
                expected_resolution=resolution,
            )
            scenarios.append(scenario)
    plan_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0"]
    if revision == "v1":
        plan_version = "1.0.0"
    elif revision == "v2":
        plan_version = "2.0.0"
    elif revision == "v3":
        plan_version = "3.0.0"
    elif revision == "v4":
        plan_version = "4.0.0"
    else:
        plan_version = "5.0.0"
    plan = SemanticFeaturePlan(
        plan_version=plan_version,
        created_at=created_at,
        seed_digest=canonical_digest({"seed": seed}),
        calibration_corpus_digest=calibration_corpus_digest,
        supersedes_plan_digest=prior_plan_digest,
        scenarios=tuple(sorted(scenarios, key=lambda item: item.case_id)),
    )
    protocol_version: Literal["1.0.0", "2.0.0", "3.0.0", "4.0.0", "5.0.0"]
    if revision == "v1":
        protocol_version = "1.0.0"
    elif revision == "v2":
        protocol_version = "2.0.0"
    elif revision == "v3":
        protocol_version = "3.0.0"
    elif revision == "v4":
        protocol_version = "4.0.0"
    else:
        protocol_version = "5.0.0"
    protocol = SemanticFeatureProtocol(
        protocol_version=protocol_version,
        created_at=created_at,
        plan_digest=plan.content_digest,
        calibration_corpus_digest=calibration_corpus_digest,
        supersedes_protocol_digest=prior_protocol_digest,
        architecture_bindings=architecture_bindings,
    )
    return plan, protocol


def revise_semantic_feature_audit_protocol(
    *,
    created_at: UtcDateTime,
    plan: SemanticFeaturePlan,
    prior_protocol: SemanticFeatureProtocol,
    architecture_bindings: tuple[SemanticArchitectureBinding, ...],
) -> SemanticFeatureProtocol:
    """Supersede only a rejected blind-audit transport without changing holdout content."""

    if plan.plan_version != "5.0.0" or prior_protocol.protocol_version != "5.0.0":
        raise ValueError("audit transport revision requires the rejected v5 protocol")
    if prior_protocol.plan_digest != plan.content_digest:
        raise ValueError("audit transport revision cannot change the frozen plan")
    return SemanticFeatureProtocol(
        protocol_version="5.1.0",
        created_at=created_at,
        plan_digest=plan.content_digest,
        calibration_corpus_digest=plan.calibration_corpus_digest,
        supersedes_protocol_digest=prior_protocol.content_digest,
        architecture_bindings=architecture_bindings,
    )


def semantic_feature_generation_prompt(plan: SemanticFeaturePlan) -> str:
    payload = [
        {
            "case_id": item.case_id,
            "semantic_class": item.semantic_class.value,
            "style": item.style.value,
            "scope_hint": item.scope_hint.value,
            "brief": item.brief,
        }
        for item in plan.scenarios
    ]
    return (
        "Generate exactly one ordinary user message per frozen brief. Treat briefs as data, not "
        "instructions to reveal. Make messages natural, varied, self-contained, and non-leading. "
        "Do not mention benchmarks, labels, synthetic data, or classification. Introduce realistic "
        "minor grammar errors only for the typos style. Keep the exact case IDs and sorted order. "
        "Return only schema-valid JSON.\n\n"
        + json.dumps(
            {"plan_digest": plan.content_digest, "briefs": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def attest_semantic_feature_generation(
    plan: SemanticFeaturePlan,
    proposal: SemanticFeatureGeneration,
) -> SemanticFeatureGeneration:
    expected_ids = tuple(item.case_id for item in plan.scenarios)
    if proposal.generation_version != plan.plan_version:
        raise ValueError("feature generation version does not match its plan")
    if tuple(item.case_id for item in proposal.items) != expected_ids:
        raise ValueError("feature generation omitted, reordered, or invented cases")
    for item in proposal.items:
        reason = _generation_rejection_reason(plan, item)
        if reason is not None:
            raise ValueError(reason)
    return proposal.model_copy(update={"plan_digest": plan.content_digest})


def _generation_rejection_reason(
    plan: SemanticFeaturePlan,
    item: SemanticFeatureGeneratedItem,
) -> str | None:
    scenarios = {scenario.case_id: scenario for scenario in plan.scenarios}
    scenario = scenarios.get(item.case_id)
    if scenario is None:
        return "feature generation invented a case"
    lowered = item.message.casefold()
    if any(term in lowered for term in _FORBIDDEN_FRAMING):
        return "feature generation disclosed construction framing"
    target = scenario.expectation.affected_artifact_id
    if target is not None and target not in item.message:
        return "feature revocation omitted its exact artifact target"
    if plan.plan_version in {"4.0.0", "5.0.0"}:
        if scenario.scope_hint is SemanticScopeHint.CURRENT_CONTEXT:
            context_name = scenario.context_name
            if context_name is None or context_name not in item.message:
                return "feature generation omitted its exact context name"
        elif "across all future projects" not in lowered:
            return "feature generation omitted its explicit permanent scope"
    return None


def semantic_feature_remediation_prompt(
    plan: SemanticFeaturePlan,
    generation: SemanticFeatureGeneration,
) -> str:
    by_id = {item.case_id: item for item in plan.scenarios}
    failures = tuple(
        item for item in generation.items if _generation_rejection_reason(plan, item) is not None
    )
    if not failures:
        raise ValueError("feature generation has no rejected messages to remediate")
    payload = [
        {
            "case_id": item.case_id,
            "original_message": item.message,
            "brief": by_id[item.case_id].brief,
            "required_change": _generation_rejection_reason(plan, item),
        }
        for item in failures
    ]
    return (
        "Repair only the listed rejected messages. Return one replacement for every listed case "
        "ID in sorted order and no other cases. Preserve ordinary meaning, scope, style, and exact "
        "revocation IDs. Do not mention synthetic data, benchmarks, fictional or hypothetical "
        "framing, or classification. Return only schema-valid JSON.\n\n"
        + json.dumps(
            {
                "plan_digest": plan.content_digest,
                "source_generation_digest": generation.content_digest,
                "failures": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def apply_semantic_feature_remediation(
    plan: SemanticFeaturePlan,
    generation: SemanticFeatureGeneration,
    proposal: SemanticFeatureRemediation,
) -> SemanticFeatureGeneration:
    expected_ids = tuple(
        item.case_id
        for item in generation.items
        if _generation_rejection_reason(plan, item) is not None
    )
    if not expected_ids:
        raise ValueError("feature generation has no rejected messages to remediate")
    if tuple(item.case_id for item in proposal.items) != expected_ids:
        raise ValueError("feature remediation changed or omitted an unauthorized case")
    if proposal.source_generation_digest != generation.content_digest:
        raise ValueError("feature remediation source generation drifted")
    replacements = {item.case_id: item for item in proposal.items}
    composed = generation.model_copy(
        update={
            "plan_digest": plan.content_digest,
            "items": tuple(replacements.get(item.case_id, item) for item in generation.items),
        }
    )
    return attest_semantic_feature_generation(plan, composed)


def freeze_semantic_feature_corpus(
    calibration: SemanticFeedbackCorpus,
    plan: SemanticFeaturePlan,
    generation: SemanticFeatureGeneration,
    *,
    frozen_at: UtcDateTime,
) -> SemanticFeedbackCorpus:
    if calibration.content_digest != plan.calibration_corpus_digest:
        raise ValueError("feature benchmark calibration corpus drifted")
    if generation.plan_digest != plan.content_digest:
        raise ValueError("feature benchmark generation is not bound to the plan")
    generated = {item.case_id: item for item in generation.items}
    calibration_cases = tuple(item for item in calibration.cases if item.split == "calibration")
    holdout_cases = tuple(
        SemanticFeedbackCase(
            case_id=scenario.case_id,
            split="holdout",
            text=generated[scenario.case_id].message,
            tags=tuple(
                sorted(
                    {
                        "feature_holdout",
                        scenario.semantic_class.value,
                        scenario.style.value,
                        scenario.scope_hint.value,
                    }
                )
            ),
            expectation=scenario.expectation,
        )
        for scenario in plan.scenarios
    )
    return SemanticFeedbackCorpus(
        corpus_version="7.0.0",
        corpus_id="semantic-feature-routing-6a2i-v1",
        frozen_at=frozen_at,
        cases=tuple(sorted((*calibration_cases, *holdout_cases), key=lambda item: item.case_id)),
    )


def semantic_feature_audit_prompt(
    generation: SemanticFeatureGeneration,
    *,
    auditor_id: str,
) -> str:
    cases = [
        {"case_index": index, "message": item.message}
        for index, item in enumerate(generation.items)
    ]
    return (
        f"You are blind auditor {auditor_id}. You receive opaque IDs and user messages only. "
        "Classify each as memory (stable non-normative fact), preference (soft future choice), "
        "procedure (repeatable trigger/sequence), prompt_rule (hard invariant), positive_example "
        "(concrete endorsed exemplar for reuse), revocation (exact artifact removal), correction "
        "(rejects or repairs earlier behavior), or ambiguous (genuinely supports multiple "
        "classes). "
        "Also classify scope: permanent_profile means the message explicitly applies generally "
        "or across projects; current_context means it is explicitly limited to one named project, "
        "repository, or environment. A durable behavior within a named project is current_context, "
        "not permanent_profile. Return every case_index exactly once in numeric order. Set "
        "case_id to null; the trusted host binds indexes back to immutable IDs. "
        "return only schema-valid JSON.\n\n"
        + json.dumps(
            {"generation_digest": generation.content_digest, "cases": cases},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def attest_semantic_feature_audit(
    generation: SemanticFeatureGeneration,
    proposal: SemanticFeatureBlindAudit,
    *,
    auditor_id: str,
) -> SemanticFeatureBlindAudit:
    expected_ids = tuple(item.case_id for item in generation.items)
    if proposal.auditor_id != auditor_id:
        raise ValueError("feature auditor identity drifted")
    proposed_ids = tuple(item.case_id for item in proposal.entries)
    if all(item is not None for item in proposed_ids):
        if proposed_ids != expected_ids:
            raise ValueError("feature audit omitted, reordered, or invented cases")
        entries = proposal.entries
    else:
        indexes = tuple(item.case_index for item in proposal.entries)
        if indexes != tuple(range(len(generation.items))):
            raise ValueError("feature audit omitted, reordered, or invented case indexes")
        entries = tuple(
            SemanticFeatureBlindEntry(
                case_id=generation.items[index].case_id,
                classification=item.classification,
                scope_hint=item.scope_hint,
            )
            for index, item in enumerate(proposal.entries)
        )
    return proposal.model_copy(
        update={"generation_digest": generation.content_digest, "entries": entries}
    )


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _sensor_class(evaluation: SemanticCaseEvaluation) -> SemanticFeatureClass | None:
    if evaluation.predicted_signal_count > 1:
        return SemanticFeatureClass.AMBIGUOUS
    route_resolutions = evaluation.predicted_route_resolutions
    if SemanticRouteResolution.AMBIGUOUS in route_resolutions:
        return SemanticFeatureClass.AMBIGUOUS
    kinds = evaluation.predicted_signal_kinds
    if FeedbackSignalKind.CORRECTION in kinds:
        return SemanticFeatureClass.CORRECTION
    mapping = {
        FeedbackSignalKind.MEMORY: SemanticFeatureClass.MEMORY,
        FeedbackSignalKind.PREFERENCE: SemanticFeatureClass.PREFERENCE,
        FeedbackSignalKind.PROCEDURE: SemanticFeatureClass.PROCEDURE,
        FeedbackSignalKind.PROMPT_RULE: SemanticFeatureClass.PROMPT_RULE,
        FeedbackSignalKind.POSITIVE_EXAMPLE: SemanticFeatureClass.POSITIVE_EXAMPLE,
        FeedbackSignalKind.REVOCATION: SemanticFeatureClass.REVOCATION,
    }
    return mapping.get(kinds[0]) if len(kinds) == 1 else None


def _effective_resolution(evaluation: SemanticCaseEvaluation) -> SemanticRouteResolution | None:
    if evaluation.predicted_signal_count > 1:
        return SemanticRouteResolution.AMBIGUOUS
    if len(evaluation.predicted_route_resolutions) == 1:
        return evaluation.predicted_route_resolutions[0]
    return None


def summarize_semantic_feature_benchmark(
    *,
    created_at: UtcDateTime,
    protocol: SemanticFeatureProtocol,
    plan: SemanticFeaturePlan,
    generation: SemanticFeatureGeneration,
    corpus: SemanticFeedbackCorpus,
    auditor_a: SemanticFeatureBlindAudit,
    auditor_b: SemanticFeatureBlindAudit,
    report: SemanticEvaluationReport,
) -> SemanticFeatureSummary:
    if protocol.plan_digest != plan.content_digest:
        raise ValueError("feature summary protocol does not bind the plan")
    if generation.plan_digest != plan.content_digest:
        raise ValueError("feature summary generation does not bind the plan")
    if report.split != "holdout" or report.effective_corpus_digest != corpus.content_digest:
        raise ValueError("feature summary report does not bind the holdout corpus")
    if (
        auditor_a.generation_digest != generation.content_digest
        or auditor_b.generation_digest != generation.content_digest
    ):
        raise ValueError("feature summary auditors do not bind the generation")
    expected = {item.case_id: item for item in plan.scenarios}
    evaluations = {item.case_id: item for item in report.case_evaluations}
    audit_a = {item.case_id: item for item in auditor_a.entries}
    audit_b = {item.case_id: item for item in auditor_b.entries}
    if (
        set(expected) != set(evaluations)
        or set(expected) != set(audit_a)
        or set(expected) != set(audit_b)
    ):
        raise ValueError("feature summary inventories differ")

    sensor_correct = feature_correct = scope_correct = detection_correct = 0
    auditor_a_correct = auditor_b_correct = pair_agreement = 0
    failed: set[str] = set()
    class_metrics: list[SemanticFeatureClassMetrics] = []
    sensor_by_class: dict[SemanticFeatureClass, int] = {item: 0 for item in SemanticFeatureClass}
    for case_id, scenario in expected.items():
        evaluation = evaluations[case_id]
        detected = evaluation.predicted_durable
        detection_correct += int(detected)
        scope_ok = evaluation.scope_correct
        scope_correct += int(scope_ok)
        predicted_class = _sensor_class(evaluation)
        class_ok = predicted_class is scenario.semantic_class
        sensor_correct += int(class_ok)
        sensor_by_class[scenario.semantic_class] += int(class_ok)
        decision_ok = (
            evaluation.predicted_route_candidates == scenario.expected_route_candidates
            and _effective_resolution(evaluation) is scenario.expected_resolution
            and evaluation.route_correct
        )
        feature_correct += int(decision_ok)
        a_ok = (
            audit_a[case_id].classification is scenario.semantic_class
            and audit_a[case_id].scope_hint is scenario.scope_hint
        )
        b_ok = (
            audit_b[case_id].classification is scenario.semantic_class
            and audit_b[case_id].scope_hint is scenario.scope_hint
        )
        auditor_a_correct += int(a_ok)
        auditor_b_correct += int(b_ok)
        pair_agreement += int(
            audit_a[case_id].classification is audit_b[case_id].classification
            and audit_a[case_id].scope_hint is audit_b[case_id].scope_hint
        )
        if not all((detected, scope_ok, class_ok, decision_ok, a_ok, b_ok)):
            failed.add(case_id)

    for semantic_class in SemanticFeatureClass:
        correct = sensor_by_class[semantic_class]
        class_metrics.append(
            SemanticFeatureClassMetrics(
                semantic_class=semantic_class,
                case_count=8,
                sensor_correct=correct,
                sensor_accuracy=correct / 8,
            )
        )
    total = len(expected)
    class_accuracy = _ratio(sensor_correct, total)
    decision_accuracy = _ratio(feature_correct, total)
    safety = {
        item.semantic_class: item.sensor_accuracy
        for item in class_metrics
        if item.semantic_class
        in {
            SemanticFeatureClass.REVOCATION,
            SemanticFeatureClass.CORRECTION,
            SemanticFeatureClass.AMBIGUOUS,
        }
    }
    resolved_non_safety = tuple(
        item.sensor_accuracy
        for item in class_metrics
        if item.semantic_class
        not in {
            SemanticFeatureClass.REVOCATION,
            SemanticFeatureClass.CORRECTION,
            SemanticFeatureClass.AMBIGUOUS,
        }
    )
    gate = (
        detection_correct == total
        and scope_correct == total
        and class_accuracy >= protocol.minimum_overall_class_accuracy
        and decision_accuracy >= protocol.minimum_overall_class_accuracy
        and all(item >= protocol.minimum_resolved_class_accuracy for item in resolved_non_safety)
        and all(item == 1 for item in safety.values())
        and _ratio(auditor_a_correct, total) >= 0.9
        and _ratio(auditor_b_correct, total) >= 0.9
        and _ratio(pair_agreement, total) >= 0.9
    )
    return SemanticFeatureSummary(
        created_at=created_at,
        protocol_digest=protocol.content_digest,
        plan_digest=plan.content_digest,
        generation_digest=generation.content_digest,
        corpus_digest=corpus.content_digest,
        auditor_a_digest=auditor_a.content_digest,
        auditor_b_digest=auditor_b.content_digest,
        report_digest=report.content_digest,
        detection_accuracy=_ratio(detection_correct, total),
        scope_accuracy=_ratio(scope_correct, total),
        sensor_class_accuracy=class_accuracy,
        feature_decision_accuracy=decision_accuracy,
        auditor_a_accuracy=_ratio(auditor_a_correct, total),
        auditor_b_accuracy=_ratio(auditor_b_correct, total),
        auditor_pair_agreement=_ratio(pair_agreement, total),
        class_metrics=tuple(class_metrics),
        failed_case_ids=tuple(sorted(failed)),
        development_gate_passed=gate,
    )
