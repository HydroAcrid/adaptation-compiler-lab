from pathlib import Path

from adaptation_compiler_lab.copilot_delivery.schema_export import export_copilot_schemas

export_copilot_schemas(Path("schemas/copilot-delivery/v1"))
