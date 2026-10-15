"""Bind previously seen scenarios to a new analyzer as development regression only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, analyzer_digest
from adaptation_compiler_lab.autonomy.defaults import frozen_defaults
from adaptation_compiler_lab.serialization import canonical_digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prospective", action="store_true")
    parser.add_argument("--prospective-source", type=Path)
    parser.add_argument("--trusted-conversations", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autonomy"
    source = root / "habit_eval_v3.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    data["evaluation_version"] = EVALUATION_VERSION
    data["purpose"] = "development_regression"
    data["provenance"] = (
        "Previously executed fictional v3 scenarios. Labels unchanged. "
        "Used for development regression, never fresh prospective release validation."
    )
    prefix = EVALUATION_VERSION.replace("-", "_")
    if args.trusted_conversations:
        if args.prospective:
            raise ValueError("trusted conversation controls are development regression")
        prefix += "_trusted"
        for case in data["cases"]:
            for episode in case["episodes"]:
                if episode["origin"] == "human":
                    episode["origin"] = "owner_authorized_chat"
        data["provenance"] = (
            "Development policy regression: previously seen fictional cases/labels; "
            "human-origin inputs replaced with explicitly owner-authorized conversation inputs. "
            "Untrusted origins remain disallowed. Not prospective release validation."
        )
    if args.prospective:
        prefix += "_prospective"
        source = args.prospective_source or root / (prefix + ".json")
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("purpose") != "prospective_shadow_detection":
            raise ValueError("prospective binding requires previously authored fresh materials")
        data["evaluation_version"] = EVALUATION_VERSION
    manifest = {
        "evaluation_version": EVALUATION_VERSION,
        "purpose": data["purpose"],
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
    for name, value in ((prefix + ".json", data), (prefix + ".manifest.json", manifest)):
        path = root / name
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise ValueError("Existing regression binding changed; create a new version")
        else:
            path.write_text(encoded, encoding="utf-8")
    print(json.dumps({"version": EVALUATION_VERSION, "purpose": data["purpose"]}))


if __name__ == "__main__":
    main()
