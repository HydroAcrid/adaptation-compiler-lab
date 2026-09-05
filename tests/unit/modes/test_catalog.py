"""Three-Mode catalog and frozen evaluation-design tests."""

from adaptation_compiler_lab.modes import (
    MODE_CATALOG,
    MODE_EVALUATION_DESIGNS,
    ModeEvaluationStatus,
    evaluate_mode_conformance,
    evaluation_design_by_mode_id,
    mode_by_id,
)


def test_catalog_contains_three_distinct_experimental_modes() -> None:
    assert tuple(mode.mode_id for mode in MODE_CATALOG) == (
        "frontend-studio",
        "research-analyst",
        "secure-backend",
    )
    assert all(mode.evaluation_status is ModeEvaluationStatus.EXPERIMENTAL for mode in MODE_CATALOG)
    assert all(mode.evaluation_digest is None for mode in MODE_CATALOG)
    assert all(not mode.auto_activates for mode in MODE_CATALOG)


def test_every_mode_passes_static_conformance_without_claiming_effectiveness() -> None:
    for mode in MODE_CATALOG:
        report = evaluate_mode_conformance(mode)
        assert report.valid is True
        assert report.projection_utf8_bytes <= mode.maximum_projection_utf8_bytes
        assert not mode.requested_tools
        assert not mode.required_capabilities


def test_each_evaluation_design_has_three_diagnostics_and_two_controls() -> None:
    assert tuple(item.mode_id for item in MODE_EVALUATION_DESIGNS) == tuple(
        item.mode_id for item in MODE_CATALOG
    )
    for mode, design in zip(MODE_CATALOG, MODE_EVALUATION_DESIGNS, strict=True):
        assert design.mode_digest == mode.content_digest
        assert sum(task.kind == "diagnostic" for task in design.tasks) == 3
        assert sum(task.kind == "neutral_control" for task in design.tasks) == 2
        assert design.maximum_target_runs == 10
        assert design.provider_billed_calls is False


def test_catalog_lookup_is_exact_and_has_no_fuzzy_aliases() -> None:
    assert mode_by_id("research-analyst") is MODE_CATALOG[1]
    assert evaluation_design_by_mode_id("secure-backend") is MODE_EVALUATION_DESIGNS[2]
    assert mode_by_id("Research Analyst") is None
    assert evaluation_design_by_mode_id("secure") is None
