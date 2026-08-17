"""Export deterministic v3.1 replacement-smoke schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.benchmark.persona_v31 import persona_v31_schemas
from adaptation_compiler_lab.serialization import canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, schema in persona_v31_schemas().items():
        (output / name).write_text(canonical_json(schema) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
