"""Freeze the binder-only amendment after the first diagnostic launch."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    semantic_feedback_output_schema,
)
from adaptation_compiler_lab.benchmark.persona_v31_remediation import (
    PersonaV31RemediationAmendment,
    PersonaV31RemediationFreeze,
    PersonaV31RemediationIncident,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.runners.persona_smoke_support import json_bytes, write_or_verify
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    input_root = args.input.resolve()
    remediation = input_root / "remediation"
    if not input_root.is_relative_to(repo):
        raise RuntimeError("v3.1 remediation amendment must remain in the repository")
    freeze = PersonaV31RemediationFreeze.model_validate_json(
        (remediation / "FREEZE-v1.json").read_bytes()
    )
    incident = PersonaV31RemediationIncident(
        encrypted_raw_result_ref=(
            "sha256:861db6ab21db0f039e46d207e7625c901199386372e76885731b734d9e8c366d"
        )
    )
    amendment = PersonaV31RemediationAmendment(
        prior_freeze_digest=canonical_digest(freeze),
        incident_digest=canonical_digest(incident),
        output_schema_digest=canonical_digest(semantic_feedback_output_schema()),
        interpreter_module_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/automatic_runtime/semantic_interpreter.py"
        ),
        amended_benchmark_module_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v31_remediation.py"
        ),
        amended_runner_module_digest=sha256_file(repo / "scripts/run_persona_v31_remediation.py"),
    )
    write_or_verify(remediation / "INSTRUMENT-INCIDENT-001.json", json_bytes(incident))
    write_or_verify(remediation / "AMENDMENT-v1.1.json", json_bytes(amendment))
    print(
        canonical_json(
            {"incident": canonical_digest(incident), "amendment": canonical_digest(amendment)}
        )
    )


if __name__ == "__main__":
    main()
