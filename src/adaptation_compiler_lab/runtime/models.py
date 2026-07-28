"""Typed portable/runtime representation boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    ArtifactRef,
    CaptureReceiptRef,
    ConsentReceiptRef,
    EvaluationCaseRef,
    EvidenceLinks,
    EvidenceRef,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    ReleaseRef,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.domain.values import Scope
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    ScopeDimension,
)


class RuntimeClauseRole(StrEnum):
    """Semantic role retained externally for each target-visible clause."""

    ACTIONABLE_BEHAVIOR = "actionable_behavior"
    NECESSARY_SCOPE = "necessary_scope"
    NECESSARY_PRECEDENCE = "necessary_precedence"
    NECESSARY_VERIFICATION = "necessary_verification"


class GovernedLifecycleEvent(FrozenModel):
    """Content-addressed lifecycle history retained outside the target prompt."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"transition_kind": {"const": "addition"}},
                        "required": ["transition_kind"],
                    },
                    "then": {
                        "properties": {
                            "introduced_artifact_ref": {"not": {"type": "null"}},
                            "affected_artifact_id": {"type": "null"},
                            "supersedes_artifact_ids": {"maxItems": 0},
                        },
                        "required": ["introduced_artifact_ref"],
                    },
                },
                {
                    "if": {
                        "properties": {
                            "transition_kind": {"enum": ["scoped_correction", "supersession"]}
                        },
                        "required": ["transition_kind"],
                    },
                    "then": {
                        "properties": {
                            "introduced_artifact_ref": {"not": {"type": "null"}},
                            "affected_artifact_id": {"type": "string"},
                            "supersedes_artifact_ids": {
                                "minItems": 1,
                                "maxItems": 1,
                            },
                        },
                        "required": [
                            "introduced_artifact_ref",
                            "affected_artifact_id",
                            "supersedes_artifact_ids",
                        ],
                    },
                },
                {
                    "if": {
                        "properties": {"transition_kind": {"const": "revocation"}},
                        "required": ["transition_kind"],
                    },
                    "then": {
                        "properties": {
                            "introduced_artifact_ref": {"type": "null"},
                            "affected_artifact_id": {"type": "string"},
                            "supersedes_artifact_ids": {"maxItems": 0},
                        },
                        "required": ["affected_artifact_id"],
                    },
                },
            ]
        }
    )

    event_id: Identifier
    stage: int = Field(ge=1)
    transition_kind: Literal[
        "addition",
        "scoped_correction",
        "supersession",
        "revocation",
    ]
    evidence_ref: EvidenceRef
    consent_ref: ConsentReceiptRef
    capture_ref: CaptureReceiptRef
    evaluation_case_ref: EvaluationCaseRef
    review_digest: Sha256Digest
    review_approver_id: Identifier
    review_policy_version: NonEmptyStr
    introduced_artifact_ref: ArtifactRef | None = None
    affected_artifact_id: Identifier | None = None
    supersedes_artifact_ids: tuple[Identifier, ...] = ()
    released_at: UtcDateTime
    activated_at: UtcDateTime

    @field_validator("supersedes_artifact_ids")
    @classmethod
    def supersessions_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("governed lifecycle supersessions must be sorted and unique")
        return value

    @model_validator(mode="after")
    def transition_shape_is_valid(self) -> Self:
        if self.released_at > self.activated_at:
            raise ValueError("lifecycle release must precede activation")
        if self.transition_kind == "addition":
            if (
                self.introduced_artifact_ref is None
                or self.affected_artifact_id is not None
                or self.supersedes_artifact_ids
            ):
                raise ValueError("addition lifecycle event must introduce exactly one artifact")
        elif self.transition_kind in {"scoped_correction", "supersession"}:
            if (
                self.introduced_artifact_ref is None
                or self.affected_artifact_id is None
                or self.supersedes_artifact_ids != (self.affected_artifact_id,)
            ):
                raise ValueError(
                    f"{self.transition_kind} lifecycle event must replace exactly one artifact"
                )
        elif (
            self.introduced_artifact_ref is not None
            or self.affected_artifact_id is None
            or self.supersedes_artifact_ids
        ):
            raise ValueError("revocation lifecycle event must remove exactly one artifact")
        return self


class ArtifactGovernanceBinding(FrozenModel):
    """Complete active artifact lineage retained in the external release."""

    artifact_ref: ArtifactRef
    scope: Scope
    evidence_links: EvidenceLinks
    evaluation_case_refs: tuple[EvaluationCaseRef, ...] = Field(min_length=1)
    consent_refs: tuple[ConsentReceiptRef, ...] = Field(min_length=1)
    capture_refs: tuple[CaptureReceiptRef, ...] = Field(min_length=1)
    review_approver_ids: tuple[Identifier, ...] = Field(min_length=1)
    review_policy_versions: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def binding_is_sorted_and_exact(self) -> Self:
        for name in (
            "evaluation_case_refs",
            "consent_refs",
            "capture_refs",
            "review_approver_ids",
            "review_policy_versions",
        ):
            values = getattr(self, name)
            keys = tuple(str(item) for item in values)
            if keys != tuple(sorted(set(keys))):
                raise ValueError(f"{name} must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ExternalGovernedRelease(FrozenModel):
    """Portable user-owned release; complete for audit and rollback, not target-visible."""

    external_release_version: Literal["1.0.0"] = "1.0.0"
    release_ref: ReleaseRef
    renderer_id: Literal["compact-runtime-projection"] = "compact-runtime-projection"
    renderer_version: Literal["1.0.0"] = "1.0.0"
    parent_release_digest: Sha256Digest | None = None
    source_snapshot_digest: Sha256Digest
    active_artifacts: tuple[ArtifactRenderProjection, ...]
    active_bindings: tuple[ArtifactGovernanceBinding, ...]
    lifecycle_history: tuple[GovernedLifecycleEvent, ...] = Field(min_length=1)
    scoped_supersessions: tuple[tuple[Identifier, Identifier], ...] = ()
    revoked_artifact_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def release_is_coherent(self) -> Self:
        artifact_ids = tuple(item.artifact_ref.record_id for item in self.active_artifacts)
        binding_ids = tuple(item.artifact_ref.record_id for item in self.active_bindings)
        if artifact_ids != tuple(sorted(set(artifact_ids))):
            raise ValueError("external release artifacts must be sorted and unique")
        if binding_ids != artifact_ids:
            raise ValueError("every external release artifact requires exact governance binding")
        for artifact, binding in zip(
            self.active_artifacts,
            self.active_bindings,
            strict=True,
        ):
            if binding.artifact_ref != artifact.artifact_ref:
                raise ValueError("governance binding must reference the exact artifact version")
            if binding.scope != artifact.scope:
                raise ValueError("governance binding scope must exactly match its artifact")
            if binding.evidence_links != artifact.evidence_links:
                raise ValueError(
                    "governance binding evidence links must exactly match its artifact"
                )
        if self.revoked_artifact_ids != tuple(sorted(set(self.revoked_artifact_ids))):
            raise ValueError("revoked artifact IDs must be sorted and unique")
        if any(item.revoked for item in self.active_artifacts):
            raise ValueError("revoked artifacts cannot be active in an external release")
        if set(artifact_ids) & set(self.revoked_artifact_ids):
            raise ValueError("revoked artifact IDs cannot also be active")
        if self.scoped_supersessions != tuple(sorted(set(self.scoped_supersessions))):
            raise ValueError("scoped supersessions must be sorted and unique")
        event_ids = tuple(item.event_id for item in self.lifecycle_history)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("governed lifecycle event IDs must be unique")
        stages = tuple(item.stage for item in self.lifecycle_history)
        if stages != tuple(sorted(stages)):
            raise ValueError("governed lifecycle events must be stage ordered")
        lifecycle_active: set[Identifier] = set()
        expected_revoked: set[Identifier] = set()
        expected_supersessions: list[tuple[Identifier, Identifier]] = []
        for event in self.lifecycle_history:
            introduced_id = (
                event.introduced_artifact_ref.record_id
                if event.introduced_artifact_ref is not None
                else None
            )
            affected_id = event.affected_artifact_id
            if event.transition_kind == "addition":
                assert introduced_id is not None
                if introduced_id in lifecycle_active or introduced_id in expected_revoked:
                    raise ValueError("lifecycle addition reused an artifact ID")
                lifecycle_active.add(introduced_id)
            elif event.transition_kind == "scoped_correction":
                assert introduced_id is not None
                assert affected_id is not None
                if affected_id not in lifecycle_active:
                    raise ValueError("lifecycle correction targets no active artifact")
                if introduced_id in lifecycle_active or introduced_id in expected_revoked:
                    raise ValueError("lifecycle correction reused an artifact ID")
                lifecycle_active.add(introduced_id)
                expected_supersessions.append((introduced_id, affected_id))
            else:
                assert affected_id is not None
                if affected_id not in lifecycle_active:
                    raise ValueError("lifecycle removal targets no active artifact")
                prior_replacements = tuple(
                    replacing_id
                    for replacing_id, replaced_id in expected_supersessions
                    if replaced_id == affected_id
                )
                lifecycle_active.remove(affected_id)
                expected_revoked.add(affected_id)
                expected_supersessions = [
                    pair for pair in expected_supersessions if affected_id not in pair
                ]
                if event.transition_kind == "supersession":
                    assert introduced_id is not None
                    if introduced_id in lifecycle_active or introduced_id in expected_revoked:
                        raise ValueError("lifecycle supersession reused an artifact ID")
                    lifecycle_active.add(introduced_id)
                    expected_supersessions.extend(
                        (replacing_id, introduced_id)
                        for replacing_id in prior_replacements
                        if replacing_id in lifecycle_active
                    )
        if artifact_ids != tuple(sorted(lifecycle_active)):
            raise ValueError("active artifacts do not match lifecycle state")
        if self.revoked_artifact_ids != tuple(sorted(expected_revoked)):
            raise ValueError("revoked artifact IDs do not match lifecycle state")
        if self.scoped_supersessions != tuple(sorted(expected_supersessions)):
            raise ValueError("scoped supersessions do not match lifecycle state")
        for binding in self.active_bindings:
            introductions = tuple(
                event
                for event in self.lifecycle_history
                if event.transition_kind in {"addition", "scoped_correction", "supersession"}
                and event.introduced_artifact_ref == binding.artifact_ref
            )
            if not introductions:
                raise ValueError("governance binding requires an exact lifecycle introduction")
            evidence_refs = tuple(sorted({event.evidence_ref for event in introductions}, key=str))
            evaluation_refs = tuple(
                sorted({event.evaluation_case_ref for event in introductions}, key=str)
            )
            consent_refs = tuple(sorted({event.consent_ref for event in introductions}, key=str))
            capture_refs = tuple(sorted({event.capture_ref for event in introductions}, key=str))
            reviewer_ids = tuple(
                sorted({event.review_approver_id for event in introductions}, key=str)
            )
            policy_versions = tuple(
                sorted({event.review_policy_version for event in introductions}, key=str)
            )
            bound_evidence_refs = tuple(
                sorted(
                    {
                        *binding.evidence_links.supporting,
                        *binding.evidence_links.contradicting,
                        *binding.evidence_links.scope_limiting,
                    },
                    key=str,
                )
            )
            if evidence_refs != bound_evidence_refs:
                raise ValueError("governance binding evidence must match lifecycle introductions")
            if evaluation_refs != binding.evaluation_case_refs:
                raise ValueError(
                    "governance binding evaluations must match lifecycle introductions"
                )
            if consent_refs != binding.consent_refs:
                raise ValueError("governance binding consent must match lifecycle introductions")
            if capture_refs != binding.capture_refs:
                raise ValueError("governance binding capture must match lifecycle introductions")
            if reviewer_ids != binding.review_approver_ids:
                raise ValueError("governance binding reviewers must match lifecycle introductions")
            if policy_versions != binding.review_policy_versions:
                raise ValueError(
                    "governance binding review policies must match lifecycle introductions"
                )
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class BehavioralDecisionCase(FrozenModel):
    """One explicit branch of a promoted behavioral decision."""

    case_id: Identifier
    situation: NonEmptyStr
    required_actions: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    forbidden_actions: tuple[NonEmptyStr, ...] = ()

    @field_validator("required_actions", "forbidden_actions")
    @classmethod
    def actions_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("behavioral decision actions must be unique")
        return value

    @model_validator(mode="after")
    def required_and_forbidden_are_disjoint(self) -> Self:
        if set(self.required_actions) & set(self.forbidden_actions):
            raise ValueError("a behavioral decision cannot require and forbid the same action")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ArtifactDecisionTable(FrozenModel):
    """Typed decision branches bound to one exact governed artifact."""

    decision_table_version: Literal["1.0.0"] = "1.0.0"
    artifact_ref: ArtifactRef
    cases: Annotated[tuple[BehavioralDecisionCase, ...], Field(min_length=1)]

    @field_validator("cases")
    @classmethod
    def cases_are_sorted_unique(
        cls,
        value: tuple[BehavioralDecisionCase, ...],
    ) -> tuple[BehavioralDecisionCase, ...]:
        case_ids = tuple(item.case_id for item in value)
        if case_ids != tuple(sorted(set(case_ids))):
            raise ValueError("behavioral decision cases must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ExternalDecisionRelease(FrozenModel):
    """Versioned decision-table projection over an immutable v1 governed release."""

    external_decision_release_version: Literal["1.0.0"] = "1.0.0"
    governed_release: ExternalGovernedRelease
    decision_tables: Annotated[tuple[ArtifactDecisionTable, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def every_active_artifact_has_one_exact_table(self) -> Self:
        artifact_refs = tuple(item.artifact_ref for item in self.governed_release.active_artifacts)
        table_refs = tuple(item.artifact_ref for item in self.decision_tables)
        if table_refs != artifact_refs:
            raise ValueError(
                "decision tables must match the sorted exact active artifact references"
            )
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class DecisionResourceClass(StrEnum):
    """Portable resource class used by a behavioral decision."""

    PERSISTENT_USER_MANAGED = "persistent_user_managed"
    DISPOSABLE_GENERATED_CACHE = "disposable_generated_cache"
    UNLISTED = "unlisted"


class RecoveryRequestState(StrEnum):
    """Whether an explicit recovery request is part of a decision branch."""

    REQUESTED = "requested"
    NOT_REQUESTED = "not_requested"
    EITHER = "either"
    NOT_APPLICABLE = "not_applicable"


class DecisionOperation(StrEnum):
    """Portable behavioral operation rendered into target-natural language."""

    CREATE_RECOVERABLE_BACKUP = "create_recoverable_backup"
    REPLACE_CONTENTS = "replace_contents"
    PREPARE_TEMPORARY_REPLACEMENT = "prepare_temporary_replacement"
    ACTIVATE_ATOMICALLY = "activate_atomically"
    REFUSE_REPLACEMENT = "refuse_replacement"
    PRESERVE_BEHAVIOR = "preserve_behavior"


class SemanticDecisionCase(FrozenModel):
    """One machine-checkable portable branch without target-specific wording."""

    case_id: Identifier
    resource_class: DecisionResourceClass
    recovery_request: RecoveryRequestState
    required_operations: Annotated[tuple[DecisionOperation, ...], Field(min_length=1)]
    forbidden_operations: tuple[DecisionOperation, ...] = ()

    @model_validator(mode="after")
    def branch_is_semantically_coherent(self) -> Self:
        if len(self.required_operations) != len(set(self.required_operations)):
            raise ValueError("semantic decision operations must be unique")
        if len(self.forbidden_operations) != len(set(self.forbidden_operations)):
            raise ValueError("semantic forbidden operations must be unique")
        if set(self.required_operations) & set(self.forbidden_operations):
            raise ValueError("semantic decision cannot require and forbid one operation")
        if self.resource_class is DecisionResourceClass.UNLISTED:
            if (
                self.recovery_request is not RecoveryRequestState.NOT_APPLICABLE
                or self.required_operations != (DecisionOperation.PRESERVE_BEHAVIOR,)
                or self.forbidden_operations
            ):
                raise ValueError("unlisted semantic branch must only preserve behavior")
        elif self.recovery_request is RecoveryRequestState.NOT_APPLICABLE:
            raise ValueError("listed semantic branches require a recovery-request state")
        return self


class SemanticDecisionTable(FrozenModel):
    """Portable semantic cases bound to one exact governed artifact."""

    semantic_decision_table_version: Literal["1.0.0"] = "1.0.0"
    artifact_ref: ArtifactRef
    cases: Annotated[tuple[SemanticDecisionCase, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def cases_are_sorted_unique_and_nonoverlapping(self) -> Self:
        case_ids = tuple(item.case_id for item in self.cases)
        if case_ids != tuple(sorted(set(case_ids))):
            raise ValueError("semantic decision cases must be sorted and unique")
        selectors = tuple((item.resource_class, item.recovery_request) for item in self.cases)
        if len(selectors) != len(set(selectors)):
            raise ValueError("semantic decision selectors cannot overlap")
        for resource in DecisionResourceClass:
            states = {
                item.recovery_request for item in self.cases if item.resource_class is resource
            }
            if RecoveryRequestState.EITHER in states and len(states) > 1:
                raise ValueError("an either branch cannot overlap explicit recovery branches")
        return self


class ExternalSemanticDecisionRelease(FrozenModel):
    """Semantic decision projection over an immutable governed release."""

    external_semantic_release_version: Literal["1.0.0"] = "1.0.0"
    governed_release: ExternalGovernedRelease
    decision_tables: Annotated[tuple[SemanticDecisionTable, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def every_active_artifact_has_one_exact_table(self) -> Self:
        artifact_refs = tuple(item.artifact_ref for item in self.governed_release.active_artifacts)
        table_refs = tuple(item.artifact_ref for item in self.decision_tables)
        if table_refs != artifact_refs:
            raise ValueError(
                "semantic tables must match the sorted exact active artifact references"
            )
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeProjectionContext(FrozenModel):
    """Known and unknown scope dimensions at projection time."""

    known_dimensions: tuple[ScopeDimension, ...]
    target_profile_id: Identifier | None = None
    subject_id: Identifier | None = None
    workspace_id: Identifier | None = None
    project_id: Identifier | None = None
    repository_id: Identifier | None = None
    task_class: Identifier | None = None
    target_family: Identifier | None = None
    environment_id: Identifier | None = None
    condition_labels: tuple[NonEmptyStr, ...] = ()
    evaluated_at: UtcDateTime | None = None

    @field_validator("known_dimensions")
    @classmethod
    def dimensions_are_sorted_unique(
        cls, value: tuple[ScopeDimension, ...]
    ) -> tuple[ScopeDimension, ...]:
        raw = tuple(item.value for item in value)
        if raw != tuple(sorted(set(raw))):
            raise ValueError("known scope dimensions must be sorted and unique")
        return value

    @field_validator("condition_labels")
    @classmethod
    def labels_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("runtime context labels must be sorted and unique")
        return value


class RuntimeClause(FrozenModel):
    """One target-independent effective runtime clause."""

    text: NonEmptyStr
    roles: Annotated[tuple[RuntimeClauseRole, ...], Field(min_length=1)]
    source_artifact_refs: Annotated[tuple[ArtifactRef, ...], Field(min_length=1)]

    @field_validator("roles")
    @classmethod
    def roles_are_sorted_unique(
        cls, value: tuple[RuntimeClauseRole, ...]
    ) -> tuple[RuntimeClauseRole, ...]:
        raw = tuple(item.value for item in value)
        if raw != tuple(sorted(set(raw))):
            raise ValueError("runtime clause roles must be sorted and unique")
        return value

    @field_validator("source_artifact_refs")
    @classmethod
    def sources_are_sorted_unique(cls, value: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
        keys = tuple((item.record_id, item.record_version, item.content_digest) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("runtime clause sources must be sorted and unique")
        return value

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class CanonicalRuntimeProjection(FrozenModel):
    """Target-independent active clauses derived from one governed release."""

    projection_version: Literal["1.0.0"] = "1.0.0"
    external_release_digest: Sha256Digest
    release_ref: ReleaseRef
    context: RuntimeProjectionContext
    clauses: tuple[RuntimeClause, ...]
    omitted_artifact_refs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def clauses_and_omissions_are_unique(self) -> Self:
        clause_digests = tuple(item.content_digest for item in self.clauses)
        if clause_digests != tuple(dict.fromkeys(clause_digests)):
            raise ValueError("runtime projection contains duplicate clauses")
        omitted = tuple(item.record_id for item in self.omitted_artifact_refs)
        if omitted != tuple(sorted(set(omitted))):
            raise ValueError("runtime omissions must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ClauseProvenanceBinding(FrozenModel):
    """Hidden exact binding from one rendered clause to governed lineage."""

    clause_digest: Sha256Digest
    rendered_fragment_digest: Sha256Digest
    source_binding_digests: tuple[Sha256Digest, ...] = Field(min_length=1)

    @field_validator("source_binding_digests")
    @classmethod
    def binding_digests_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("source binding digests must be sorted and unique")
        return value


class RuntimeProjectionManifest(FrozenModel):
    """External manifest; never delivered with the target-visible projection."""

    manifest_version: Literal["1.0.0"] = "1.0.0"
    external_release_digest: Sha256Digest
    runtime_projection_digest: Sha256Digest
    target_renderer_id: Identifier
    target_renderer_version: NonEmptyStr
    rendered_content_digest: Sha256Digest
    rendered_utf8_bytes: int = Field(ge=0)
    clause_bindings: tuple[ClauseProvenanceBinding, ...]

    @model_validator(mode="after")
    def clauses_are_unique(self) -> Self:
        digests = tuple(item.clause_digest for item in self.clause_bindings)
        if digests != tuple(dict.fromkeys(digests)):
            raise ValueError("runtime manifest contains duplicate clause bindings")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
