"""Automatic-runtime schema snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.schema_export import (
    automatic_runtime_schema_bundle,
)
from adaptation_compiler_lab.governance.schema_export import governance_schema_bundle

ROOT = Path(__file__).resolve().parents[3]


def test_automatic_runtime_schema_snapshots_are_current() -> None:
    root = ROOT / "schemas" / "automatic_runtime" / "v1"
    expected = automatic_runtime_schema_bundle()

    assert {path.name for path in root.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in expected
    }
    for name, schema in expected.items():
        assert json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8")) == schema


def test_governance_snapshots_include_local_runtime_source() -> None:
    root = ROOT / "schemas" / "governance" / "v1"
    expected = governance_schema_bundle()

    for name, schema in expected.items():
        assert json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8")) == schema
    rendered = json.dumps(expected["consent_receipt"], sort_keys=True)
    assert "local_interaction_runtime" in rendered
