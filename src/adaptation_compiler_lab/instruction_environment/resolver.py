"""Deterministic native-context comparison and least-delta projection policy."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from adaptation_compiler_lab.instruction_environment.models import (
    InstructionConflictV1,
    InstructionDeltaPlanV1,
    InstructionEnvironmentSnapshotV1,
    InstructionReconciliationPlanV1,
    InstructionRelationKind,
    InstructionRelationV1,
    InstructionResolution,
    NativeAuthorityClass,
    NativeInstructionClauseV1,
    NativeMemoryCapabilityV1,
    NativeSourceKind,
    ReconciliationDispositionKind,
    ReconciliationDispositionV1,
)
from adaptation_compiler_lab.runtime.models import (
    CanonicalRuntimeProjection,
    RuntimeClause,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.serialization import canonical_digest

_PUNCTUATION = re.compile(r"[^a-z0-9\s]")
_SPACE = re.compile(r"\s+")


def _normalized(value: str) -> str:
    return _SPACE.sub(" ", _PUNCTUATION.sub(" ", value.casefold())).strip()


def compare_instruction_clauses(
    temper_clause: RuntimeClause,
    native_clause: NativeInstructionClauseV1,
    *,
    semantic_relation: InstructionRelationV1 | None = None,
) -> InstructionRelationV1:
    """Return an exact deterministic relation or a validated semantic result."""

    if semantic_relation is not None:
        if (
            semantic_relation.temper_clause_digest != temper_clause.content_digest
            or semantic_relation.native_clause_id != native_clause.clause_id
            or semantic_relation.native_clause_digest != native_clause.text_digest
        ):
            raise ValueError("semantic relation does not bind the supplied clauses")
        return semantic_relation
    if _normalized(temper_clause.text) == _normalized(native_clause.text):
        return InstructionRelationV1(
            temper_clause_digest=temper_clause.content_digest,
            native_clause_id=native_clause.clause_id,
            native_clause_digest=native_clause.text_digest,
            relation=InstructionRelationKind.EXACT_DUPLICATE,
            confidence=1.0,
            deterministic=True,
            resolution=InstructionResolution.OMIT_TEMPER,
            rationale="The native source already contains the same normalized instruction.",
        )
    return InstructionRelationV1(
        temper_clause_digest=temper_clause.content_digest,
        native_clause_id=native_clause.clause_id,
        native_clause_digest=native_clause.text_digest,
        relation=InstructionRelationKind.UNKNOWN,
        confidence=0.0,
        deterministic=True,
        resolution=InstructionResolution.INCLUDE_TEMPER,
        rationale="Deterministic comparison found no exact equivalence or contradiction.",
    )


def build_instruction_delta_plan(
    projection: CanonicalRuntimeProjection,
    environment: InstructionEnvironmentSnapshotV1,
    *,
    semantic_relations: Sequence[InstructionRelationV1] = (),
) -> InstructionDeltaPlanV1:
    """Resolve one governed projection against one exact native environment."""

    project_id = projection.context.project_id
    target = projection.context.target_family
    if project_id is None or project_id != environment.project_id:
        raise ValueError("native environment does not match the projection project")
    expected_targets = {
        environment.target.value,
        f"{environment.target.value}-code",
        f"{environment.target.value}-cli",
    }
    if target is None or target not in expected_targets:
        raise ValueError("native environment does not match the projection target")
    supplied = {
        (item.temper_clause_digest, item.native_clause_id): item for item in semantic_relations
    }
    if len(supplied) != len(tuple(semantic_relations)):
        raise ValueError("semantic relation input contains duplicate clause pairs")
    source_by_id = {item.source_id: item for item in environment.source_manifests}
    active_native_clauses = tuple(
        item
        for item in environment.clauses
        if source_by_id[item.source_id].source_kind
        not in {NativeSourceKind.PERSONAL_SKILL, NativeSourceKind.PROJECT_SKILL}
    )
    relations: list[InstructionRelationV1] = []
    conflicts: list[InstructionConflictV1] = []
    included: set[str] = set()
    omitted: set[str] = set()
    blocked: set[str] = set()
    fully_optimized = environment.complete and all(
        item.source_kind not in {NativeSourceKind.PERSONAL_SKILL, NativeSourceKind.PROJECT_SKILL}
        for item in environment.source_manifests
    )
    for temper_clause in projection.clauses:
        clause_relations = [
            compare_instruction_clauses(
                temper_clause,
                native_clause,
                semantic_relation=supplied.get(
                    (temper_clause.content_digest, native_clause.clause_id)
                ),
            )
            for native_clause in active_native_clauses
        ]
        material = [
            item
            for item in clause_relations
            if item.relation is not InstructionRelationKind.UNKNOWN
        ]
        relations.extend(material)
        contradictions = [
            item for item in material if item.relation is InstructionRelationKind.CONTRADICTION
        ]
        equivalents = [
            item
            for item in material
            if item.relation
            in {
                InstructionRelationKind.EXACT_DUPLICATE,
                InstructionRelationKind.SEMANTIC_EQUIVALENT,
            }
        ]
        policy_contradictions: list[InstructionRelationV1] = []
        memory_contradictions: list[InstructionRelationV1] = []
        for relation in contradictions:
            native = next(
                item
                for item in active_native_clauses
                if item.clause_id == relation.native_clause_id
            )
            source = source_by_id[native.source_id]
            if source.authority_class is NativeAuthorityClass.AGENT_GENERATED:
                memory_contradictions.append(relation)
            else:
                policy_contradictions.append(relation)
        if policy_contradictions:
            blocked.add(temper_clause.content_digest)
            for relation in policy_contradictions:
                native = next(
                    item
                    for item in active_native_clauses
                    if item.clause_id == relation.native_clause_id
                )
                source = source_by_id[native.source_id]
                conflicts.append(
                    InstructionConflictV1(
                        conflict_id=_conflict_id(
                            project_id,
                            temper_clause.content_digest,
                            native.clause_id,
                        ),
                        project_id=project_id,
                        target=environment.target,
                        temper_clause_digest=temper_clause.content_digest,
                        native_clause_id=native.clause_id,
                        native_source_id=native.source_id,
                        relation=relation.relation,
                        native_precedence=source.native_precedence,
                        severity="blocking",
                        resolution_state="unresolved",
                        rationale=(
                            "An applicable higher-authority native instruction conflicts with this "
                            "approved Temper behavior, so the Temper clause is withheld."
                        ),
                    )
                )
        elif memory_contradictions:
            included.add(temper_clause.content_digest)
            for relation in memory_contradictions:
                native = next(
                    item
                    for item in active_native_clauses
                    if item.clause_id == relation.native_clause_id
                )
                source = source_by_id[native.source_id]
                conflicts.append(
                    InstructionConflictV1(
                        conflict_id=_conflict_id(
                            project_id,
                            temper_clause.content_digest,
                            native.clause_id,
                        ),
                        project_id=project_id,
                        target=environment.target,
                        temper_clause_digest=temper_clause.content_digest,
                        native_clause_id=native.clause_id,
                        native_source_id=native.source_id,
                        relation=relation.relation,
                        native_precedence=source.native_precedence,
                        severity="notice",
                        resolution_state="unresolved",
                        rationale=(
                            "Lower-authority agent-generated memory conflicts with approved Temper "
                            "learning. Temper remains included; the native memory requires review "
                            "or isolation in a managed session."
                        ),
                    )
                )
        elif equivalents:
            omitted.add(temper_clause.content_digest)
        else:
            included.add(temper_clause.content_digest)
        if any(item.relation is InstructionRelationKind.UNKNOWN for item in clause_relations):
            fully_optimized = False
    known_pairs = {
        (clause.content_digest, native.clause_id)
        for clause in projection.clauses
        for native in active_native_clauses
    }
    if not set(supplied) <= known_pairs:
        raise ValueError("semantic relation names a clause outside this projection")
    input_bytes = sum(len(item.text.encode("utf-8")) for item in projection.clauses)
    output_bytes = sum(
        len(item.text.encode("utf-8"))
        for item in projection.clauses
        if item.content_digest in included
    )
    return InstructionDeltaPlanV1(
        project_id=project_id,
        target=environment.target,
        surface=environment.surface,
        surface_contract_version=environment.surface_contract_version,
        environment_digest=environment.content_digest,
        source_chain_digest=environment.source_chain_digest,
        included_temper_clause_digests=tuple(sorted(included)),
        omitted_temper_clause_digests=tuple(sorted(omitted)),
        blocked_temper_clause_digests=tuple(sorted(blocked)),
        relations=tuple(relations),
        conflicts=tuple(sorted(conflicts, key=lambda item: item.conflict_id)),
        input_utf8_bytes=input_bytes,
        output_utf8_bytes=output_bytes,
        fully_optimized=fully_optimized,
    )


def build_instruction_reconciliation_plan(
    projection: CanonicalRuntimeProjection,
    environment: InstructionEnvironmentSnapshotV1,
    *,
    semantic_relations: Sequence[InstructionRelationV1] = (),
    native_memory_capabilities: Sequence[NativeMemoryCapabilityV1] = (),
) -> InstructionReconciliationPlanV1:
    """Build an authority-aware plan without granting mutation authority."""

    delta = build_instruction_delta_plan(
        projection,
        environment,
        semantic_relations=semantic_relations,
    )
    source_by_id = {item.source_id: item for item in environment.source_manifests}
    relations_by_temper: dict[str, list[InstructionRelationV1]] = {}
    for relation in delta.relations:
        relations_by_temper.setdefault(relation.temper_clause_digest, []).append(relation)
    conflicts_by_temper: dict[str, list[InstructionConflictV1]] = {}
    for conflict in delta.conflicts:
        conflicts_by_temper.setdefault(conflict.temper_clause_digest, []).append(conflict)

    dispositions: list[ReconciliationDispositionV1] = []
    for clause in projection.clauses:
        conflicts = conflicts_by_temper.get(clause.content_digest, [])
        relations = relations_by_temper.get(clause.content_digest, [])
        native_clause_ids = tuple(sorted({item.native_clause_id for item in relations}))
        related_clause_ids = set(native_clause_ids)
        native_source_ids = tuple(
            sorted(
                {conflict.native_source_id for conflict in conflicts}
                | {
                    native.source_id
                    for native in environment.clauses
                    if native.clause_id in related_clause_ids
                }
            )
        )
        if clause.content_digest in set(delta.blocked_temper_clause_digests):
            kind = ReconciliationDispositionKind.BLOCKED_BY_POLICY
            rationale = "A higher-authority applicable native policy blocks this Temper clause."
            blocked = True
            review = True
        elif any(
            source_by_id[item.native_source_id].authority_class
            is NativeAuthorityClass.AGENT_GENERATED
            for item in conflicts
        ):
            kind = ReconciliationDispositionKind.INCLUDED_WITH_NATIVE_MEMORY_CONFLICT
            rationale = (
                "Approved Temper learning remains active; contradictory lower-authority native "
                "memory requires review or managed-session isolation."
            )
            blocked = False
            review = True
        elif clause.content_digest in set(delta.omitted_temper_clause_digests):
            kind = ReconciliationDispositionKind.OMITTED_AS_COVERED
            rationale = "An applicable native instruction already covers this behavior."
            blocked = False
            review = False
        else:
            kind = ReconciliationDispositionKind.INCLUDED
            rationale = "No applicable higher-authority native instruction covers this behavior."
            blocked = False
            review = any(
                item.resolution is InstructionResolution.NEEDS_REVIEW for item in relations
            )
        dispositions.append(
            ReconciliationDispositionV1(
                temper_clause_digest=clause.content_digest,
                disposition=kind,
                native_clause_ids=native_clause_ids,
                native_source_ids=native_source_ids,
                rationale=rationale,
                delivery_blocked=blocked,
                review_required=review,
            )
        )

    capabilities = tuple(
        sorted(
            native_memory_capabilities,
            key=lambda item: (item.target.value, item.surface, item.source_kind.value),
        )
    )
    memory_conflicts = tuple(
        item
        for item in delta.conflicts
        if source_by_id[item.native_source_id].authority_class
        is NativeAuthorityClass.AGENT_GENERATED
    )
    can_isolate = any(
        "isolate_managed_session" in {action.value for action in item.supported_actions}
        for item in capabilities
    )
    unresolved = tuple(sorted(item.conflict_id for item in delta.conflicts))
    return InstructionReconciliationPlanV1(
        project_id=delta.project_id,
        target=delta.target,
        surface=delta.surface,
        surface_contract_version=delta.surface_contract_version,
        environment_digest=delta.environment_digest,
        source_chain_digest=delta.source_chain_digest,
        delta_plan_digest=canonical_digest(delta),
        dispositions=tuple(sorted(dispositions, key=lambda item: item.temper_clause_digest)),
        native_memory_capabilities=capabilities,
        unresolved_conflict_ids=unresolved,
        managed_session_isolation_required=bool(memory_conflicts and can_isolate),
        fully_reconciled=delta.fully_optimized and not unresolved,
    )


def apply_instruction_environment(
    projection: CanonicalRuntimeProjection,
    plan: InstructionDeltaPlanV1,
) -> CanonicalRuntimeProjection:
    """Return the target-visible Temper delta while retaining governed source refs."""

    if projection.context.project_id != plan.project_id:
        raise ValueError("instruction delta plan crossed its project boundary")
    dispositions = (
        set(plan.included_temper_clause_digests)
        | set(plan.omitted_temper_clause_digests)
        | set(plan.blocked_temper_clause_digests)
    )
    projection_digests = {item.content_digest for item in projection.clauses}
    if dispositions != projection_digests:
        raise ValueError("instruction delta plan does not cover the exact projection")
    included = tuple(
        item
        for item in projection.clauses
        if item.content_digest in set(plan.included_temper_clause_digests)
    )
    return projection.model_copy(update={"clauses": included})


def bind_instruction_delta_manifest(
    manifest: RuntimeProjectionManifest,
    plan: InstructionDeltaPlanV1,
    *,
    reconciliation: InstructionReconciliationPlanV1 | None = None,
) -> RuntimeProjectionManifest:
    """Bind a rendered Temper delta to the exact native context that shaped it."""

    rendered_clauses = {item.clause_digest for item in manifest.clause_bindings}
    if rendered_clauses != set(plan.included_temper_clause_digests):
        raise ValueError("rendered manifest does not match the native-aware included clauses")
    if reconciliation is not None and (
        reconciliation.delta_plan_digest != canonical_digest(plan)
        or reconciliation.environment_digest != plan.environment_digest
    ):
        raise ValueError("reconciliation plan does not bind this instruction delta")
    return manifest.model_copy(
        update={
            "instruction_environment_digest": plan.environment_digest,
            "native_target_id": plan.target.value,
            "native_target_surface": plan.surface,
            "native_target_surface_version": plan.surface_contract_version,
            "native_source_chain_digest": plan.source_chain_digest,
            "native_included_clause_digests": plan.included_temper_clause_digests,
            "native_omitted_clause_digests": plan.omitted_temper_clause_digests,
            "native_blocked_clause_digests": plan.blocked_temper_clause_digests,
            "native_relation_digests": tuple(
                sorted(canonical_digest(item) for item in plan.relations)
            ),
            "native_reconciliation_plan_digest": (
                None if reconciliation is None else canonical_digest(reconciliation)
            ),
            "native_unresolved_conflict_ids": (
                () if reconciliation is None else reconciliation.unresolved_conflict_ids
            ),
            "native_managed_session_isolation_required": (
                False
                if reconciliation is None
                else reconciliation.managed_session_isolation_required
            ),
            "native_delta_fully_optimized": plan.fully_optimized,
        }
    )


def semantic_relation_index(
    relations: Sequence[InstructionRelationV1],
) -> Mapping[tuple[str, str], InstructionRelationV1]:
    """Validate and index model-produced relations for a deterministic resolver call."""

    result = {(item.temper_clause_digest, item.native_clause_id): item for item in relations}
    if len(result) != len(tuple(relations)):
        raise ValueError("semantic relation set contains duplicate bindings")
    return result


def _conflict_id(project_id: str, temper_digest: str, native_clause_id: str) -> str:
    digest = canonical_digest(
        {
            "native_clause_id": native_clause_id,
            "project_id": project_id,
            "temper_clause_digest": temper_digest,
        }
    ).removeprefix("sha256:")
    return f"native-conflict-{digest[:24]}"
