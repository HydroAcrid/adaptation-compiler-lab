"""Export checked-in temporary capability Mode JSON Schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.modes.schema_export import export_mode_schemas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    export_mode_schemas(arguments.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
