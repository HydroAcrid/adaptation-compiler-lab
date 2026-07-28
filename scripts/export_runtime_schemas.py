"""Export checked-in Milestone 6A.1 runtime JSON Schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.runtime.schema_export import export_runtime_schemas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    export_runtime_schemas(arguments.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
