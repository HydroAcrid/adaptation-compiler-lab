from datetime import timedelta

from adaptation_compiler_lab.benchmark.decision_fixture import (
    public_complete_decision_tables,
)
from adaptation_compiler_lab.dogfood import (
    PUBLIC_DOGFOOD_NOW,
    PUBLIC_DOGFOOD_SUBJECT,
    LongitudinalDogfoodCompiler,
    public_dogfood_transitions,
)
from adaptation_compiler_lab.runtime import (
    RuntimeProjectionContext,
    bind_decision_release,
    build_external_governed_releases,
)
from adaptation_compiler_lab.targets.codex_runtime_v4 import (
    build_codex_runtime_projection_v4,
    build_runtime_projection_manifest_v4,
    render_codex_runtime_projection_v4,
)
from adaptation_compiler_lab.targets.models import ScopeDimension, TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile


def _rendered_stages() -> tuple[str, str, str]:
    transitions = public_dogfood_transitions()
    dogfood = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )
    releases = build_external_governed_releases(transitions, dogfood)
    tables = public_complete_decision_tables(transitions)
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
        decision_release = bind_decision_release(release, tables)
        projection = build_codex_runtime_projection_v4(decision_release, context)
        rendered = render_codex_runtime_projection_v4(projection)
        manifest = build_runtime_projection_manifest_v4(
            release=decision_release,
            projection=projection,
            rendered=rendered,
        )
        assert len(manifest.clause_bindings) == len(projection.clauses)
        contents.append(rendered.content)
    return tuple(contents)  # type: ignore[return-value]


def test_v4_projection_enumerates_both_branches_and_preserves_unlisted_cases() -> None:
    stage_1, stage_2, stage_3 = _rendered_stages()

    assert "persistent existing; recovery=no" in stage_1
    assert "persistent existing; recovery=yes" in stage_1
    assert "unlisted: preserve behavior" in stage_1
    assert "disposable cache existing; recovery=no" in stage_2
    assert "disposable cache existing; recovery=yes" in stage_2
    assert "never backup" in stage_2
    assert "recovery=no: refuse; never replace" in stage_3
    assert stage_3.count("Verify action.") == 1


def test_v4_complete_table_remains_smaller_than_frozen_static_profile() -> None:
    sizes = tuple(len(item.encode("utf-8")) for item in _rendered_stages())

    assert sizes <= (221, 460, 504)
