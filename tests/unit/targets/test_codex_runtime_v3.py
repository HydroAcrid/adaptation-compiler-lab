from datetime import timedelta
from typing import cast

import pytest

from adaptation_compiler_lab.dogfood import (
    PUBLIC_DOGFOOD_NOW,
    PUBLIC_DOGFOOD_SUBJECT,
    LongitudinalDogfoodCompiler,
    public_dogfood_transitions,
)
from adaptation_compiler_lab.runtime import (
    ArtifactDecisionTable,
    BehavioralDecisionCase,
    RuntimeProjectionContext,
    bind_decision_release,
    build_external_governed_releases,
)
from adaptation_compiler_lab.targets.codex_runtime_v3 import (
    build_codex_runtime_projection_v3,
    build_runtime_projection_manifest_v3,
    render_codex_runtime_projection_v3,
)
from adaptation_compiler_lab.targets.models import (
    ArtifactRenderProjection,
    ScopeDimension,
    TargetKind,
)
from adaptation_compiler_lab.targets.profiles import default_target_profile


def _decision_tables() -> tuple[ArtifactDecisionTable, ...]:
    transitions = public_dogfood_transitions()
    cases = (
        (
            BehavioralDecisionCase(
                case_id="retained-existing-any-request",
                situation=(
                    "an existing persistent user-managed target, whether recovery was "
                    "requested or not"
                ),
                required_actions=("create a recovery copy", "replace it"),
            ),
        ),
        (
            BehavioralDecisionCase(
                case_id="cache-existing-any-request",
                situation=(
                    "an existing disposable generated-cache target, whether recovery was "
                    "requested or not"
                ),
                required_actions=("write a temporary tree", "atomically replace it"),
                forbidden_actions=("create a recovery copy",),
            ),
        ),
        (
            BehavioralDecisionCase(
                case_id="retained-existing-requested",
                situation=("an existing persistent user-managed target has a recovery request"),
                required_actions=("create a recovery copy", "replace it"),
            ),
            BehavioralDecisionCase(
                case_id="retained-existing-unrequested",
                situation=("an existing persistent user-managed target has no recovery request"),
                required_actions=("refuse replacement",),
                forbidden_actions=("replace it",),
            ),
        ),
    )
    return tuple(
        ArtifactDecisionTable(
            artifact_ref=cast(ArtifactRenderProjection, transition.instruction).artifact_ref,
            cases=stage_cases,
        )
        for transition, stage_cases in zip(transitions, cases, strict=True)
    )


def _rendered_stages() -> tuple[str, str, str]:
    transitions = public_dogfood_transitions()
    dogfood = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )
    releases = build_external_governed_releases(transitions, dogfood)
    context = RuntimeProjectionContext(
        known_dimensions=(
            ScopeDimension.SUBJECT_IDS,
            ScopeDimension.TARGET_FAMILIES,
            ScopeDimension.VALIDITY_WINDOW,
        ),
        target_profile_id=default_target_profile(TargetKind.CODEX).capabilities.profile_id,
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
        target_family=TargetKind.CODEX.value,
        evaluated_at=PUBLIC_DOGFOOD_NOW + timedelta(days=1),
    )
    rendered: list[str] = []
    for release in releases:
        decision_release = bind_decision_release(release, _decision_tables())
        projection = build_codex_runtime_projection_v3(decision_release, context)
        output = render_codex_runtime_projection_v3(projection)
        manifest = build_runtime_projection_manifest_v3(
            release=decision_release,
            projection=projection,
            rendered=output,
        )
        assert len(manifest.clause_bindings) == len(projection.clauses)
        rendered.append(output.content)
    return tuple(rendered)  # type: ignore[return-value]


def test_decision_cases_reject_contradictory_actions() -> None:
    with pytest.raises(ValueError, match="require and forbid"):
        BehavioralDecisionCase(
            case_id="contradiction",
            situation="a branch applies",
            required_actions=("replace the target",),
            forbidden_actions=("replace the target",),
        )


def test_decision_tables_bind_exact_artifacts_without_changing_v1_release() -> None:
    transitions = public_dogfood_transitions()
    dogfood = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )
    release = build_external_governed_releases(transitions, dogfood)[-1]
    original_digest = release.content_digest

    decision_release = bind_decision_release(release, _decision_tables())

    assert decision_release.governed_release.content_digest == original_digest
    assert tuple(item.artifact_ref for item in decision_release.decision_tables) == tuple(
        item.artifact_ref for item in release.active_artifacts
    )


def test_v3_projection_makes_branches_actions_and_prohibitions_explicit() -> None:
    stage_1, stage_2, stage_3 = _rendered_stages()

    assert "whether recovery was requested or not" in stage_1
    assert "create a recovery copy; then replace it" in stage_1
    assert "Project generated-cache" in stage_2
    assert "do not create a recovery copy" in stage_2
    assert "has no recovery request: refuse replacement" in stage_3
    assert "do not replace it" in stage_3
    assert stage_3.count("Verify the selected publish action") == 1


def test_v3_projection_remains_smaller_than_frozen_strong_profile() -> None:
    stage_1, stage_2, stage_3 = _rendered_stages()

    assert tuple(len(item.encode("utf-8")) for item in (stage_1, stage_2, stage_3)) <= (
        221,
        460,
        504,
    )
