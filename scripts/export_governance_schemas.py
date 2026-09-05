from pathlib import Path

from adaptation_compiler_lab.governance.schema_export import export_governance_schemas

export_governance_schemas(Path("schemas/governance/v1"))
