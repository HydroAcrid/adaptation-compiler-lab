"""Bind never-executed fresh utterances with opaque IDs that cannot reveal the test cohort."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from scripts.prepare_habit_prospective_v11 import build as unexecuted_materials


def build() -> dict[str, object]:
    data = unexecuted_materials()
    data["evaluation_version"] = "habit-eval-v12"
    data["provenance"] = (
        "Never-executed fresh v11 utterances, bound before v12 execution with opaque task IDs; "
        "no private evidence or cohort labels in model-visible identifiers."
    )
    for case in cast(list[dict[str, Any]], data["cases"]):
        for episode in case["episodes"]:
            digest = sha256(("v12-opaque:" + episode["task_id"]).encode()).hexdigest()[:24]
            episode["task_id"] = "episode-" + digest
    return data


def main() -> None:
    from adaptation_compiler_lab.serialization import canonical_digest

    data = build()
    path = (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/autonomy/habit_eval_v12_prospective.json"
    )
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError("existing prospective materials changed; preserve the freeze")
    path.write_text(encoded, encoding="utf-8")
    print(json.dumps({"dataset_digest": canonical_digest(data), "cases": 120, "executed": False}))


if __name__ == "__main__":
    main()
