from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    semantic_feedback_output_schema,
)
from adaptation_compiler_lab.benchmark.persona_v31_remediation import (
    PersonaV31RemediationProtocol,
    PersonaV31RemediationReport,
    persona_v31_remediation_schemas,
)

ROOT = Path(__file__).resolve().parents[3]


def test_remediated_schema_has_one_neutral_learning_shape() -> None:
    schema = json.dumps(semantic_feedback_output_schema(), sort_keys=True)

    assert schema.count('"anyOf"') == 1
    assert '"const": "endorsed_for_reuse"' not in schema
    assert '"enum": ["none", "endorsed_for_reuse"]' in schema


def test_remediation_is_one_session_and_non_evidentiary() -> None:
    protocol = PersonaV31RemediationProtocol()

    assert protocol.isolated_luna_sessions == 1
    assert protocol.profile_sessions == 0
    assert protocol.output_schema_only_change is True
    assert protocol.counts_toward_effectiveness_evidence is False
    assert protocol.full_grid_execution_authorized is False


def test_remediation_schemas_match_snapshots() -> None:
    schemas = persona_v31_remediation_schemas()

    assert len(schemas) == 5
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    for name, schema in schemas.items():
        snapshot = ROOT / "schemas" / "persona_evaluation" / "v3.1-remediation" / name
        assert json.loads(snapshot.read_text(encoding="utf-8")) == schema


def test_frozen_remediation_passes_exactly_without_rewriting_prior_smoke() -> None:
    report = PersonaV31RemediationReport.model_validate_json(
        (
            ROOT
            / "development_benchmark_persona_v31"
            / "remediation"
            / "results"
            / "REPORT-v1.json"
        ).read_bytes()
    )

    assert report.instrument_remediation_passed is True
    assert report.schema_hypothesis_supported is True
    assert report.remediated_compiled_score.exact is True
    assert report.remediated_compiled_score.correct_count == 2
    assert report.task_only_false_activations == 0
    assert report.prior_smoke_result_changed is False
    assert report.total_luna_launches == 2
    assert report.successful_luna_sessions == 1
    assert report.provider_billed_calls == 0
    assert report.counts_toward_effectiveness_evidence is False
