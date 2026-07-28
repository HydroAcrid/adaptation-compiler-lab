"""Smoke tests for the installable project and published contracts."""

import json
from hashlib import sha256
from pathlib import Path

from adaptation_compiler_lab.benchmark.models import (
    FeasibilityDesign,
    InternalFeasibilityDesign,
)
from adaptation_compiler_lab.domain import RecordKind
from adaptation_compiler_lab.governance.schema_export import governance_schema_bundle
from adaptation_compiler_lab.runtime.decision_schema_export import decision_schema_bundle
from adaptation_compiler_lab.runtime.schema_export import runtime_schema_bundle
from adaptation_compiler_lab.serialization import schema_bundle


def test_package_is_importable() -> None:
    """The package should be importable from the uv-managed environment."""
    import adaptation_compiler_lab

    assert adaptation_compiler_lab.__doc__


def test_checked_in_json_schemas_match_the_pydantic_contracts() -> None:
    """Schema drift is detected before an incompatible artifact can be published."""

    directory = Path(__file__).parents[1] / "schemas" / "v1"
    expected = {f"{kind.value}.schema.json" for kind in RecordKind}

    assert {path.name for path in directory.glob("*.schema.json")} == expected
    for name, schema in schema_bundle().items():
        assert json.loads((directory / f"{name}.schema.json").read_text(encoding="utf-8")) == schema


def test_evidence_v11_schema_snapshot_matches_the_additive_contract() -> None:
    directory = Path(__file__).parents[1] / "schemas" / "v1_1"
    schemas = schema_bundle("1.1")

    assert set(schemas) == {"evidence"}
    assert {path.name for path in directory.glob("*.schema.json")} == {"evidence.schema.json"}
    assert (
        json.loads((directory / "evidence.schema.json").read_text(encoding="utf-8"))
        == schemas["evidence"]
    )


def test_governance_v1_schema_snapshots_match_signed_contracts() -> None:
    directory = Path(__file__).parents[1] / "schemas" / "governance" / "v1"
    schemas = governance_schema_bundle()

    assert {path.name for path in directory.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in schemas
    }
    for name, schema in schemas.items():
        assert json.loads((directory / f"{name}.schema.json").read_text(encoding="utf-8")) == schema


def test_runtime_v1_schema_snapshots_match_projection_contracts() -> None:
    directory = Path(__file__).parents[1] / "schemas" / "runtime" / "v1"
    schemas = runtime_schema_bundle()

    assert {path.name for path in directory.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in schemas
    }
    for name, schema in schemas.items():
        assert json.loads((directory / f"{name}.schema.json").read_text(encoding="utf-8")) == schema


def test_runtime_v2_schema_snapshots_match_decision_contracts() -> None:
    directory = Path(__file__).parents[1] / "schemas" / "runtime" / "v2"
    schemas = decision_schema_bundle()

    assert {path.name for path in directory.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in schemas
    }
    for name, schema in schemas.items():
        assert json.loads((directory / f"{name}.schema.json").read_text(encoding="utf-8")) == schema


def test_feasibility_preregistration_is_typed_and_digest_frozen() -> None:
    root = Path(__file__).parents[1] / "preregistration"
    path = root / "feasibility-pilot-v1.json"
    encoded = path.read_bytes()
    design = FeasibilityDesign.model_validate_json(encoded)
    expected = (root / "feasibility-pilot-v1.sha256").read_text(encoding="ascii").strip()

    assert design == FeasibilityDesign()
    assert expected == f"{sha256(encoded).hexdigest()}  {path.name}"


def test_internal_feasibility_preregistration_is_typed_and_digest_frozen() -> None:
    root = Path(__file__).parents[1] / "preregistration"
    path = root / "internal-feasibility-pilot-v1.1.json"
    encoded = path.read_bytes()
    design = InternalFeasibilityDesign.model_validate_json(encoded)
    expected = (root / "internal-feasibility-pilot-v1.1.sha256").read_text(encoding="ascii").strip()

    assert design == InternalFeasibilityDesign()
    assert expected == f"{sha256(encoded).hexdigest()}  {path.name}"
