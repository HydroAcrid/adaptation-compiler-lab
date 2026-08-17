"""Freeze the one-session neutral-schema remediation before execution."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    semantic_feedback_batch_input_digest,
    semantic_feedback_batch_prompt,
    semantic_feedback_output_schema,
    semantic_feedback_prompt_digest,
    semantic_feedback_role_contract,
)
from adaptation_compiler_lab.benchmark.persona_instrument import PersonaHiddenOracle
from adaptation_compiler_lab.benchmark.persona_v31 import (
    PersonaV31Fixture,
    PersonaV31Freeze,
    PersonaV31Report,
    build_v31_observations,
)
from adaptation_compiler_lab.benchmark.persona_v31_remediation import (
    PersonaV31RemediationFreeze,
    PersonaV31RemediationProtocol,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.runners.persona_smoke_support import json_bytes, write_or_verify
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    input_root = args.input.resolve()
    output = args.output.resolve()
    if not input_root.is_relative_to(repo) or output != input_root / "remediation":
        raise RuntimeError("v3.1 remediation must use its exact repository directory")
    output.mkdir(parents=True, exist_ok=True)

    fixture = PersonaV31Fixture.model_validate_json(
        (input_root / "SMOKE-FIXTURE-v1.json").read_bytes()
    )
    oracle = PersonaHiddenOracle.model_validate_json(
        (input_root / "SMOKE-ORACLE-v1.json").read_bytes()
    )
    prior_freeze = PersonaV31Freeze.model_validate_json(
        (input_root / "SMOKE-FREEZE-v1.json").read_bytes()
    )
    prior_report = PersonaV31Report.model_validate_json(
        (input_root / "results" / "SMOKE-REPORT-v1.json").read_bytes()
    )
    observations = build_v31_observations(fixture)
    unchanged = {
        "role": sha256_text(semantic_feedback_role_contract()),
        "prompt": semantic_feedback_prompt_digest(),
        "input": semantic_feedback_batch_input_digest(observations),
        "batch": sha256_text(semantic_feedback_batch_prompt(observations)),
    }
    if (
        unchanged["role"] != prior_freeze.semantic_role_contract_digest
        or unchanged["prompt"] != prior_freeze.semantic_prompt_template_digest
        or unchanged["input"] != prior_freeze.semantic_batch_input_digest
        or unchanged["batch"] != prior_freeze.semantic_batch_prompt_digest
    ):
        raise RuntimeError("v3.1 remediation changed more than the output schema")
    remediated_schema_digest = canonical_digest(semantic_feedback_output_schema())
    if remediated_schema_digest == prior_freeze.semantic_output_schema_digest:
        raise RuntimeError("v3.1 remediation did not change the biased output schema")

    protocol = PersonaV31RemediationProtocol()
    freeze = PersonaV31RemediationFreeze(
        protocol_digest=canonical_digest(protocol),
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        prior_smoke_freeze_digest=canonical_digest(prior_freeze),
        prior_smoke_report_digest=canonical_digest(prior_report),
        unchanged_role_contract_digest=unchanged["role"],
        unchanged_prompt_template_digest=unchanged["prompt"],
        unchanged_batch_input_digest=unchanged["input"],
        unchanged_batch_prompt_digest=unchanged["batch"],
        previous_output_schema_digest=prior_freeze.semantic_output_schema_digest,
        remediated_output_schema_digest=remediated_schema_digest,
        benchmark_module_digest=sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v31_remediation.py"
        ),
        runner_module_digest=sha256_file(repo / "scripts/run_persona_v31_remediation.py"),
    )
    write_or_verify(output / "PROTOCOL-v1.json", json_bytes(protocol))
    write_or_verify(output / "FREEZE-v1.json", json_bytes(freeze))
    print(
        canonical_json({"protocol": canonical_digest(protocol), "freeze": canonical_digest(freeze)})
    )


if __name__ == "__main__":
    main()
