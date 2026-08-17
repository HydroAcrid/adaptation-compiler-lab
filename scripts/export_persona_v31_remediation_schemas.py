"""Export schemas for the one-session v3.1 instrument remediation."""

from pathlib import Path

from adaptation_compiler_lab.benchmark.persona_v31_remediation import (
    persona_v31_remediation_schemas,
)
from adaptation_compiler_lab.serialization import canonical_json

if __name__ == "__main__":
    output = Path("schemas/persona_evaluation/v3.1-remediation")
    output.mkdir(parents=True, exist_ok=True)
    for name, schema in persona_v31_remediation_schemas().items():
        (output / name).write_text(canonical_json(schema) + "\n", encoding="utf-8")
