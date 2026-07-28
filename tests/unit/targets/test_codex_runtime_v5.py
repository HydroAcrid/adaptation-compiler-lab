from datetime import timedelta

import pytest

from adaptation_compiler_lab.benchmark.decision_fixture import (
    public_semantic_decision_tables,
)
from adaptation_compiler_lab.dogfood import (
    PUBLIC_DOGFOOD_NOW,
    PUBLIC_DOGFOOD_SUBJECT,
    LongitudinalDogfoodCompiler,
    public_dogfood_transitions,
)
from adaptation_compiler_lab.runtime import (
    DecisionOperation,
    DecisionResourceClass,
    RecoveryRequestState,
    RuntimeProjectionContext,
    SemanticDecisionCase,
    SemanticDecisionTable,
    bind_semantic_decision_release,
    build_external_governed_releases,
)
from adaptation_compiler_lab.targets.codex_runtime_v5 import (
    build_codex_runtime_projection_v5,
    build_runtime_projection_manifest_v5,
    render_codex_runtime_projection_v5,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile


def _rendered_stages() -> tuple[str, str, str]:
    transitions = public_dogfood_transitions()
    dogfood = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )
    releases = build_external_governed_releases(transitions, dogfood)
    tables = public_semantic_decision_tables(transitions)
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
    contents: list[str] = []
    for release in releases:
        semantic_release = bind_semantic_decision_release(release, tables)
        projection = build_codex_runtime_projection_v5(semantic_release, context)
        rendered = render_codex_runtime_projection_v5(projection)
        manifest = build_runtime_projection_manifest_v5(
            release=semantic_release,
            projection=projection,
            rendered=rendered,
        )
        assert len(manifest.clause_bindings) == len(projection.clauses)
        contents.append(rendered.content)
    return tuple(contents)  # type: ignore[return-value]


def test_v5_projection_is_explicit_target_natural_and_cumulative() -> None:
    stage_1, stage_2, stage_3 = _rendered_stages()

    assert stage_1.startswith("Apply user rules over defaults.")
    assert "whether recovery was requested or not" in stage_1
    assert "disposable generated-cache" not in stage_1
    assert "disposable generated-cache" in stage_2
    assert "without a recovery copy" in stage_2
    assert "Otherwise refuse" in stage_3
    assert "disposable generated-cache" in stage_3


def test_v5_semantic_projection_remains_smaller_than_static_profile() -> None:
    sizes = tuple(len(item.encode("utf-8")) for item in _rendered_stages())

    assert sizes <= (221, 460, 504)


def test_semantic_case_rejects_conflicting_operations() -> None:
    with pytest.raises(ValueError, match="require and forbid"):
        SemanticDecisionCase(
            case_id="conflict",
            resource_class=DecisionResourceClass.PERSISTENT_USER_MANAGED,
            recovery_request=RecoveryRequestState.REQUESTED,
            required_operations=(DecisionOperation.REPLACE_CONTENTS,),
            forbidden_operations=(DecisionOperation.REPLACE_CONTENTS,),
        )


def test_semantic_table_rejects_overlapping_either_and_explicit_branches() -> None:
    transitions = public_dogfood_transitions()
    artifact_ref = public_semantic_decision_tables(transitions)[0].artifact_ref

    with pytest.raises(ValueError, match="either branch cannot overlap"):
        SemanticDecisionTable(
            artifact_ref=artifact_ref,
            cases=(
                SemanticDecisionCase(
                    case_id="persistent-any",
                    resource_class=DecisionResourceClass.PERSISTENT_USER_MANAGED,
                    recovery_request=RecoveryRequestState.EITHER,
                    required_operations=(DecisionOperation.REPLACE_CONTENTS,),
                ),
                SemanticDecisionCase(
                    case_id="persistent-requested",
                    resource_class=DecisionResourceClass.PERSISTENT_USER_MANAGED,
                    recovery_request=RecoveryRequestState.REQUESTED,
                    required_operations=(DecisionOperation.REPLACE_CONTENTS,),
                ),
            ),
        )
