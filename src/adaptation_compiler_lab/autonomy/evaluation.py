"""Frozen benchmark admission and bounded scoring; never a real-work efficacy claim."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, analyzer_digest
from adaptation_compiler_lab.autonomy.defaults import frozen_defaults
from adaptation_compiler_lab.serialization import canonical_digest

COUNTS = {
    "stable": 30,
    "context_constraint": 20,
    "untrusted": 20,
    "changing": 20,
    "sparse": 15,
    "scope_override": 15,
}


def load_frozen_scenarios(path: Path, manifest: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    frozen = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        value.get("evaluation_version") != EVALUATION_VERSION
        or value.get("synthetic") is not True
        or canonical_digest(value) != frozen["dataset_digest"]
        or analyzer_digest() != frozen["analyzer_digest"]
        or frozen_defaults() != frozen["defaults"]
        or Counter(case["group"] for case in value["cases"]) != Counter(COUNTS)
        or len({case["id"] for case in value["cases"]}) != 120
    ):
        raise ValueError("frozen habit evaluation changed; create a new evaluation version")
    return value


def score_hypotheses(
    expected: set[tuple[str, str]], observed: set[tuple[str, str]]
) -> dict[str, float | int]:
    true_positive = len(expected & observed)
    false_positive = len(observed - expected)
    false_negative = len(expected - observed)
    # Absence of eligible labels/predictions cannot manufacture a successful serving gate.
    precision = true_positive / len(observed) if observed else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
    }
