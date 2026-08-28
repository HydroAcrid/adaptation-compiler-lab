"""Export checked-in native instruction interoperability JSON Schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.instruction_environment.schema_export import (
    export_instruction_environment_schemas,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    export_instruction_environment_schemas(arguments.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
