"""Temporary capability Mode schema drift tests."""

from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.modes.schema_export import mode_schema_bundle

ROOT = Path(__file__).resolve().parents[3]


def test_mode_v1_schema_snapshots_are_current() -> None:
    root = ROOT / "schemas" / "modes" / "v1"
    expected = mode_schema_bundle()

    assert {path.name for path in root.glob("*.schema.json")} == {
        f"{name}.schema.json" for name in expected
    }
    for name, schema in expected.items():
        assert json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8")) == schema
