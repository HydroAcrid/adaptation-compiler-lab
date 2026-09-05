from pathlib import Path

from adaptation_compiler_lab.claude_delivery.schema_export import (
    export_claude_delivery_schemas,
)

export_claude_delivery_schemas(Path("schemas/claude_delivery/v1"))
