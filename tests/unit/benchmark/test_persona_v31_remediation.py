from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    semantic_feedback_output_schema,
)
from adaptation_compiler_lab.benchmark.persona_v31_remediation import (
    PersonaV31RemediationProtocol,
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

    assert len(schemas) == 3
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    for name, schema in schemas.items():
        snapshot = ROOT / "schemas" / "persona_evaluation" / "v3.1-remediation" / name
        assert json.loads(snapshot.read_text(encoding="utf-8")) == schema
