"""Concise compiled-condition projection tests."""

from adaptation_compiler_lab.benchmark.compiled_condition import (
    render_compiled_adaptation_material,
    render_compiled_adaptation_material_v2,
)
from adaptation_compiler_lab.domain import ArtifactState
from tests.unit.test_domain_policy import synthetic_graph


def test_compiled_condition_preserves_contract_and_exact_artifact_lineage() -> None:
    graph = synthetic_graph()

    material = render_compiled_adaptation_material((graph.artifact,))

    assert graph.artifact.behavioral_contract.intent in material.text
    assert len(material.entries) == 1
    assert material.entries[0].artifact_ref.record_id == graph.artifact.record_id
    assert "@1.0.0" not in material.text


def test_compiled_condition_rejects_non_approved_artifact() -> None:
    graph = synthetic_graph()
    draft = graph.artifact.model_copy(update={"state": ArtifactState.DRAFT})

    try:
        render_compiled_adaptation_material((draft,))
    except ValueError as error:
        assert "approved" in str(error)
    else:
        raise AssertionError("draft artifact unexpectedly entered compiled material")


def test_compiled_condition_v2_renders_evaluation_backed_operational_guidance() -> None:
    graph = synthetic_graph()

    material = render_compiled_adaptation_material_v2(
        (graph.artifact,),
        (graph.evaluation_case,),
    )

    assert material.renderer_version == "2.0.0"
    assert "Use this reviewed material as an execution checklist." in material.text
    assert "Check before completion:" in material.text
    assert "Failure signs:" in material.text
    assert graph.evaluation_case.expected_behaviors[0] in material.text
    assert graph.evaluation_case.failure_criteria[0] in material.text
    assert len(material.entries) == 1
    assert material.entries[0].evaluation_case_refs[0].record_id == (
        graph.evaluation_case.record_id
    )


def test_compiled_condition_v2_rejects_substituted_evaluation_version() -> None:
    graph = synthetic_graph()
    substituted = graph.evaluation_case.model_copy(update={"record_version": "1.0.1"})

    try:
        render_compiled_adaptation_material_v2(
            (graph.artifact,),
            (substituted,),
        )
    except ValueError as error:
        assert "resolve an exact evaluation case" in str(error)
    else:
        raise AssertionError("substituted evaluation unexpectedly entered compiled material")
