"""Export versioned offline recovery schemas."""

from pathlib import Path

from adaptation_compiler_lab.recovery.schema_export import export_recovery_schemas

if __name__ == "__main__":
    export_recovery_schemas(Path("schemas/recovery/v1"))
