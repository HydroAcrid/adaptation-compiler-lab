"""Bind previously seen scenarios to a new analyzer as development regression only."""

from __future__ import annotations

import json
from pathlib import Path

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, analyzer_digest
from adaptation_compiler_lab.autonomy.defaults import frozen_defaults
from adaptation_compiler_lab.serialization import canonical_digest


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autonomy"
    source = root / "habit_eval_v3.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["evaluation_version"] = EVALUATION_VERSION
    data["purpose"] = "development_regression"
    data["provenance"] = (
        "Previously executed fictional v3 scenarios. Labels unchanged. "
        "Used for development regression, never fresh prospective release validation."
    )
    manifest = {
        "evaluation_version": EVALUATION_VERSION,
        "purpose": "development_regression",
        "source_dataset_digest": canonical_digest(json.loads(source.read_text(encoding="utf-8"))),
        "dataset_digest": canonical_digest(data),
        "analyzer_digest": analyzer_digest(),
        "precision_gate": 0.95,
        "recall_gate": 0.8,
        "disallowed_promotion_gate": 0,
        "wrong_scope_gate": 0,
        "executed": False,
        "defaults": frozen_defaults(),
        "reason": (
            "Classified evidence and complete known-habit assessment; preserve prior failures."
        ),
    }
    prefix = EVALUATION_VERSION.replace("-", "_")
    for name, value in ((prefix + ".json", data), (prefix + ".manifest.json", manifest)):
        path = root / name
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise ValueError("Existing regression binding changed; create a new version")
        else:
            path.write_text(encoded, encoding="utf-8")
    print(json.dumps({"version": EVALUATION_VERSION, "purpose": "development_regression"}))


if __name__ == "__main__":
    main()
