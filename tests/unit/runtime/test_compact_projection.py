from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from adaptation_compiler_lab.dogfood import (
    PUBLIC_DOGFOOD_NOW,
    PUBLIC_DOGFOOD_SUBJECT,
    DogfoodTransition,
    DogfoodTransitionKind,
    LongitudinalDogfoodCompiler,
    public_dogfood_transitions,
)
from adaptation_compiler_lab.domain import (
    ArtifactRef,
    BehavioralContract,
    Scope,
)
from adaptation_compiler_lab.runtime import (
    ExternalGovernedRelease,
    RuntimeClauseRole,
    RuntimeProjectionContext,
    build_external_governed_releases,
    build_runtime_projection,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.codex_runtime import (
    SharedExecutionEnvelope,
    build_runtime_projection_manifest,
    render_codex_runtime_projection,
    render_shared_execution_envelope,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile

type TransitionTriple = tuple[DogfoodTransition, DogfoodTransition, DogfoodTransition]
type ReleaseTriple = tuple[
    ExternalGovernedRelease,
    ExternalGovernedRelease,
    ExternalGovernedRelease,
]


def _transitions() -> TransitionTriple:
    return public_dogfood_transitions()


def _releases(transitions: TransitionTriple | None = None) -> ReleaseTriple:
    selected = _transitions() if transitions is None else transitions
    result = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(selected)
    return cast(ReleaseTriple, build_external_governed_releases(selected, result))


def _context(
    *,
    project_known: bool = False,
    project_id: str | None = None,
) -> RuntimeProjectionContext:
    dimensions = [
        ScopeDimension.SUBJECT_IDS,
        ScopeDimension.TARGET_FAMILIES,
        ScopeDimension.VALIDITY_WINDOW,
    ]
    if project_known:
        dimensions.append(ScopeDimension.PROJECT_IDS)
    return RuntimeProjectionContext(
        known_dimensions=tuple(sorted(dimensions, key=lambda item: item.value)),
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
        project_id=project_id,
        target_family=TargetKind.CODEX.value,
        evaluated_at=PUBLIC_DOGFOOD_NOW + timedelta(days=1),
    )


def test_three_stage_projection_is_deterministic_and_within_profile_ceilings() -> None:
    first = _releases()
    second = _releases()
    ceilings = (227, 508, 462)

    assert first == second
    for release, repeated, ceiling in zip(first, second, ceilings, strict=True):
        projection = build_runtime_projection(release, _context())
        rendered = render_codex_runtime_projection(projection)
        repeated_render = render_codex_runtime_projection(
            build_runtime_projection(repeated, _context())
        )

        assert rendered == repeated_render
        assert rendered.utf8_bytes <= ceiling
        assert rendered.utf8_bytes == len(rendered.content.encode("utf-8"))
        assert "compiled adaptation" not in rendered.content.casefold()
        assert "dogfood-" not in rendered.content.casefold()
        assert "artifact" not in rendered.content.casefold()
        assert "evidence" not in rendered.content.casefold()


def test_partial_context_retains_narrow_rule_and_claim_specific_precedence() -> None:
    stage_two = _releases()[1]

    projection = build_runtime_projection(stage_two, _context())

    assert len(projection.clauses) == 4
    assert any(RuntimeClauseRole.NECESSARY_SCOPE in item.roles for item in projection.clauses)
    assert any(RuntimeClauseRole.NECESSARY_PRECEDENCE in item.roles for item in projection.clauses)
    assert "project is generated-cache" in projection.clauses[0].text


def test_fully_known_context_resolves_precedence_and_omits_inactive_rule() -> None:
    stage_two = _releases()[1]
    generated = build_runtime_projection(
        stage_two,
        _context(project_known=True, project_id="generated-cache"),
    )
    ordinary = build_runtime_projection(
        stage_two,
        _context(project_known=True, project_id="customer-project"),
    )

    assert "atomically replace" in render_codex_runtime_projection(generated).content
    assert (
        "recoverable backup before replacing"
        not in render_codex_runtime_projection(generated).content
    )
    assert (
        "recoverable backup before replacing" in render_codex_runtime_projection(ordinary).content
    )
    assert "atomically replace" not in render_codex_runtime_projection(ordinary).content
    assert all(
        RuntimeClauseRole.NECESSARY_PRECEDENCE not in item.roles
        for item in (*generated.clauses, *ordinary.clauses)
    )


def test_supersession_and_revocation_remove_inactive_behavior() -> None:
    superseded = build_runtime_projection(_releases()[2], _context())
    assert "create a recoverable backup before replacing existing content" not in (
        render_codex_runtime_projection(superseded).content
    )
    assert "refuse overwrite unless" in render_codex_runtime_projection(superseded).content

    first, second, third = _transitions()
    transitions = (
        first,
        second,
        third.model_copy(
            update={
                "kind": DogfoodTransitionKind.REVOCATION,
                "instruction": None,
                "supersedes_artifact_ids": (),
            }
        ),
    )
    revoked = build_runtime_projection(_releases(transitions)[2], _context())
    content = render_codex_runtime_projection(revoked).content

    assert "persistent user-managed" not in content
    assert "atomically replace" in content


def test_unrelated_subject_and_target_do_not_activate() -> None:
    release = _releases()[2]
    wrong_subject = _context().model_copy(update={"subject_id": "another-user"})
    wrong_target = _context().model_copy(update={"target_family": "claude-code"})

    assert not build_runtime_projection(release, wrong_subject).clauses
    assert not build_runtime_projection(release, wrong_target).clauses


def test_every_rendered_clause_binds_to_external_provenance() -> None:
    release = _releases()[2]
    projection = build_runtime_projection(release, _context())
    rendered = render_codex_runtime_projection(projection)
    manifest = build_runtime_projection_manifest(
        release=release,
        projection=projection,
        rendered=rendered,
    )

    assert manifest.external_release_digest == release.content_digest
    assert manifest.runtime_projection_digest == projection.content_digest
    assert tuple(item.clause_digest for item in manifest.clause_bindings) == (
        rendered.clause_digests
    )
    assert all(item.source_binding_digests for item in manifest.clause_bindings)
    assert len((canonical_json(release) + "\n").encode("utf-8")) > rendered.utf8_bytes


def test_shared_execution_envelope_is_separate_and_exactly_measured() -> None:
    envelope = render_shared_execution_envelope(
        SharedExecutionEnvelope(allowed_paths=("policy.py",))
    )
    adaptation = render_codex_runtime_projection(
        build_runtime_projection(_releases()[0], _context())
    )

    assert envelope.utf8_bytes == len(envelope.content.encode("utf-8"))
    assert "Allowed paths: policy.py." in envelope.content
    assert "parent or host paths" in envelope.content
    assert "Allowed paths" not in adaptation.content


def test_activation_conditions_and_exclusions_resolve_independently() -> None:
    release = _releases()[0]
    artifact = release.active_artifacts[0]
    scope = artifact.scope.model_copy(
        update={
            "activation_conditions": ("approved",),
            "exclusions": ("blocked",),
        }
    )
    scoped = release.model_copy(
        update={
            "active_artifacts": (artifact.model_copy(update={"scope": scope}),),
            "active_bindings": (release.active_bindings[0].model_copy(update={"scope": scope}),),
        }
    )
    exclusion_known = _context().model_copy(
        update={
            "known_dimensions": tuple(
                sorted(
                    (*_context().known_dimensions, ScopeDimension.EXCLUSIONS),
                    key=lambda item: item.value,
                )
            ),
            "condition_labels": ("blocked",),
        }
    )
    activation_known = _context().model_copy(
        update={
            "known_dimensions": tuple(
                sorted(
                    (*_context().known_dimensions, ScopeDimension.ACTIVATION_CONDITIONS),
                    key=lambda item: item.value,
                )
            ),
            "condition_labels": ("approved",),
        }
    )

    assert not build_runtime_projection(scoped, exclusion_known).clauses
    unresolved_exclusion = build_runtime_projection(scoped, activation_known)
    assert unresolved_exclusion.clauses
    assert "conditions exclude blocked" in unresolved_exclusion.clauses[0].text


def test_revoked_artifacts_are_rejected_and_defensively_omitted() -> None:
    release = _releases()[0]
    revoked = release.active_artifacts[0].model_copy(update={"revoked": True})
    raw = release.model_dump(mode="json", round_trip=True)
    raw["active_artifacts"][0]["revoked"] = True

    with pytest.raises(ValueError, match="revoked artifacts cannot be active"):
        ExternalGovernedRelease.model_validate_json(canonical_json(raw))

    bypassed = release.model_copy(update={"active_artifacts": (revoked,)})
    projection = build_runtime_projection(bypassed, _context())
    assert not projection.clauses
    assert projection.omitted_artifact_refs == (revoked.artifact_ref,)

    raw = release.model_dump(mode="json", round_trip=True)
    raw["revoked_artifact_ids"] = [release.active_artifacts[0].artifact_ref.record_id]
    with pytest.raises(ValueError, match="cannot also be active"):
        ExternalGovernedRelease.model_validate_json(canonical_json(raw))


@pytest.mark.parametrize("field", ("artifact_ref", "scope", "evidence_links"))
def test_governance_bindings_must_exactly_match_active_artifacts(field: str) -> None:
    release = _releases()[0]
    raw = release.model_dump(mode="json", round_trip=True)
    if field == "artifact_ref":
        raw["active_bindings"][0]["artifact_ref"]["record_version"] = "9.0.0"
    elif field == "scope":
        raw["active_bindings"][0]["scope"]["project_ids"] = ["wrong-project"]
    else:
        raw["active_bindings"][0]["evidence_links"]["supporting"][0]["record_version"] = "9.0.0"

    with pytest.raises(ValueError, match="governance binding"):
        ExternalGovernedRelease.model_validate_json(canonical_json(raw))


def test_manifest_rejects_arbitrary_content_with_borrowed_clause_digests() -> None:
    release = _releases()[2]
    projection = build_runtime_projection(release, _context())
    legitimate = render_codex_runtime_projection(projection)
    content = "- unrelated but internally self-consistent target instruction\n"
    forged = legitimate.model_copy(
        update={
            "content": content,
            "content_digest": sha256_text(content),
            "utf8_bytes": len(content.encode("utf-8")),
        }
    )

    with pytest.raises(ValueError, match="does not exactly match"):
        build_runtime_projection_manifest(
            release=release,
            projection=projection,
            rendered=forged,
        )


def test_manifest_rejects_tampered_projection_with_consistent_render() -> None:
    release = _releases()[2]
    projection = build_runtime_projection(release, _context())
    forged_clause = projection.clauses[0].model_copy(
        update={"text": "Perform an arbitrary unrelated action."}
    )
    forged_projection = projection.model_copy(
        update={"clauses": (forged_clause, *projection.clauses[1:])}
    )
    forged_render = render_codex_runtime_projection(forged_projection)

    with pytest.raises(ValueError, match="not the canonical projection"):
        build_runtime_projection_manifest(
            release=release,
            projection=forged_projection,
            rendered=forged_render,
        )


@given(
    project_id=st.from_regex(r"[a-z][a-z0-9]{2,10}", fullmatch=True),
)
def test_equivalent_scoped_semantics_across_generated_project_ids(
    project_id: str,
) -> None:
    first, second, third = _transitions()
    assert second.instruction is not None
    artifact_id = f"exception-{project_id}"
    instruction = second.instruction.model_copy(
        update={
            "artifact_ref": ArtifactRef(
                record_id=artifact_id,
                record_version="1.0.0",
                content_digest=canonical_digest({"project_id": project_id}),
            ),
            "behavioral_contract": BehavioralContract(
                intent="Apply the project-specific replacement rule.",
                required_behaviors=(
                    "Atomically replace disposable generated output without a backup.",
                ),
                verification_requirements=("Verify the chosen operation before completion.",),
            ),
            "scope": Scope(
                subject_ids=(PUBLIC_DOGFOOD_SUBJECT,),
                project_ids=(project_id,),
                target_families=(TargetKind.CODEX.value,),
            ),
        }
    )
    second = second.model_copy(update={"instruction": instruction})
    transitions = (first, second, third)
    release = _releases(transitions)[1]

    matching = build_runtime_projection(
        release,
        _context(project_known=True, project_id=project_id),
    )
    other = build_runtime_projection(
        release,
        _context(project_known=True, project_id=f"other-{project_id}"),
    )

    assert "Atomically replace" in render_codex_runtime_projection(matching).content
    assert "Atomically replace" not in render_codex_runtime_projection(other).content
