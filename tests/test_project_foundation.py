"""Smoke tests for the installable project and published contracts."""

import json
from pathlib import Path

from adaptation_compiler_lab.domain import RecordKind
from adaptation_compiler_lab.governance.schema_export import governance_schema_bundle
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
