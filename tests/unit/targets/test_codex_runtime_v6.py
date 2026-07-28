from datetime import timedelta

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
    RuntimeProjectionContext,
    bind_semantic_decision_release,
    build_external_governed_releases,
)
from adaptation_compiler_lab.targets.codex_runtime_v6 import (
    build_codex_runtime_projection_v6,
    build_runtime_projection_manifest_v6,
    render_codex_runtime_projection_v6,
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
        projection = build_codex_runtime_projection_v6(semantic_release, context)
        rendered = render_codex_runtime_projection_v6(projection)
        manifest = build_runtime_projection_manifest_v6(
            release=semantic_release,
            projection=projection,
            rendered=rendered,
        )
        assert len(manifest.clause_bindings) == len(projection.clauses)
        contents.append(rendered.content)
    return tuple(contents)  # type: ignore[return-value]


def test_v6_projection_makes_closed_world_and_temporal_rules_explicit() -> None:
    stage_1, stage_2, stage_3 = _rendered_stages()

    assert stage_1.startswith("Apply only these rules; infer no others")
    assert "always back up" in stage_1
    assert "even without a recovery request" in stage_1
    assert "Preserve every other case" in stage_1
    assert "generated-cache" not in stage_1
    assert "even when one was requested" in stage_2
    assert "Otherwise refuse" in stage_3


def test_v6_projection_remains_smaller_than_static_profile() -> None:
    sizes = tuple(len(item.encode("utf-8")) for item in _rendered_stages())

    assert sizes <= (221, 460, 504)
