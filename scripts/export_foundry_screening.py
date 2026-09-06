"""Export the deterministic bounded Foundry screening preregistration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptation_compiler_lab.modes import FOUNDRY_SCREENING_DESIGN


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(FOUNDRY_SCREENING_DESIGN.model_dump(mode="json"), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
