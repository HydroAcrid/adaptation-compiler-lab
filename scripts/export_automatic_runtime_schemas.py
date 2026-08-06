"""Export checked-in automatic-runtime JSON Schema snapshots."""

from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.schema_export import (
    export_automatic_runtime_schemas,
)

if __name__ == "__main__":
    export_automatic_runtime_schemas(Path("schemas/automatic_runtime/v1"))
