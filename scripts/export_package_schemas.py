"""Export checked-in offline shareable-package JSON Schemas."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.portability.schema_export import export_package_schemas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    export_package_schemas(arguments.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
