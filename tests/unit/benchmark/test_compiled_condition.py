"""Concise compiled-condition projection tests."""

from adaptation_compiler_lab.benchmark.compiled_condition import (
    render_compiled_adaptation_material,
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
