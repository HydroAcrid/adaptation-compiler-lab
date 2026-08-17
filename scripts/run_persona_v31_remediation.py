"""Run one isolated Luna session to diagnose the neutralized semantic schema."""

from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.detector import detect_feedback
from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackDetectorMode,
    StandingAutomationPolicy,
)
from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    bind_semantic_feedback_output,
    semantic_feedback_batch_input_digest,
    semantic_feedback_batch_prompt,
    semantic_feedback_output_schema,
    semantic_feedback_prompt_digest,
    semantic_feedback_role_contract,
)
from adaptation_compiler_lab.automatic_runtime.service import initial_runtime_state
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaHiddenOracle,
    bind_sensor_record,
)
from adaptation_compiler_lab.benchmark.persona_v31 import (
    PersonaV31Fixture,
    PersonaV31Freeze,
    PersonaV31Report,
    PersonaV31RoleReceipt,
    PersonaV31SensorResult,
    bind_v31_compiled_material,
    build_v31_observations,
    score_v31_material,
)
from adaptation_compiler_lab.benchmark.persona_v31_remediation import (
    PersonaV31RemediationFreeze,
    PersonaV31RemediationProtocol,
    PersonaV31RemediationReport,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.domain import ArtifactRoute, PermittedUse
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, require_external_raw_root
from adaptation_compiler_lab.runners.codex_persona import PersonaRoleRequest
from adaptation_compiler_lab.runners.codex_persona_v3 import CodexPersonaV3RoleRunner
from adaptation_compiler_lab.runners.persona_smoke_support import (
    approve_addition,
    capture_role_result,
    exclusive_write,
    json_bytes,
    load_or_create_key,
    semantic_receipt,
    write_or_verify,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_RUNTIME_DIGEST = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"


def _policy(fixture: PersonaV31Fixture) -> StandingAutomationPolicy:
    observations = build_v31_observations(fixture)
    return StandingAutomationPolicy(
        policy_id="persona-nola-v31-schema-remediation",
        subject_id=fixture.case.persona_id,
        scope=fixture.scope_registry.binding_for_turn(1).scope,
        permitted_uses=tuple(
            sorted(
                (
                    PermittedUse.AUDIT,
                    PermittedUse.CONSTRUCTION,
                    PermittedUse.PROMOTION,
                    PermittedUse.TARGET_DELIVERY,
                ),
                key=lambda item: item.value,
            )
        ),
        allowed_routes=tuple(
            sorted(
                (
                    ArtifactRoute.EXAMPLE,
                    ArtifactRoute.MEMORY,
                    ArtifactRoute.PREFERENCE,
                    ArtifactRoute.PROCEDURE,
                    ArtifactRoute.PROMPT_RULE,
                ),
                key=lambda item: item.value,
            )
        ),
        allowed_target_families=("codex",),
        effective_at=observations[0].observed_at - timedelta(minutes=2),
        expires_at=observations[-1].observed_at + timedelta(days=30),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--create-key-if-missing", action="store_true")
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for v3.1 schema remediation")
    repo = args.repo.resolve()
    input_root = args.input.resolve()
    output = args.output.resolve()
    if output != input_root / "remediation" / "results" or not input_root.is_relative_to(repo):
        raise RuntimeError("v3.1 remediation paths drifted")

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
    protocol = PersonaV31RemediationProtocol.model_validate_json(
        (input_root / "remediation" / "PROTOCOL-v1.json").read_bytes()
    )
    freeze = PersonaV31RemediationFreeze.model_validate_json(
        (input_root / "remediation" / "FREEZE-v1.json").read_bytes()
    )
    observations = build_v31_observations(fixture)
    expected = {
        "protocol_digest": canonical_digest(protocol),
        "fixture_digest": canonical_digest(fixture),
        "oracle_digest": canonical_digest(oracle),
        "prior_smoke_freeze_digest": canonical_digest(prior_freeze),
        "prior_smoke_report_digest": canonical_digest(prior_report),
        "unchanged_role_contract_digest": sha256_text(semantic_feedback_role_contract()),
        "unchanged_prompt_template_digest": semantic_feedback_prompt_digest(),
        "unchanged_batch_input_digest": semantic_feedback_batch_input_digest(observations),
        "unchanged_batch_prompt_digest": sha256_text(semantic_feedback_batch_prompt(observations)),
        "remediated_output_schema_digest": canonical_digest(semantic_feedback_output_schema()),
        "benchmark_module_digest": sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v31_remediation.py"
        ),
        "runner_module_digest": sha256_file(repo / "scripts/run_persona_v31_remediation.py"),
    }
    for field, value in expected.items():
        if getattr(freeze, field) != value:
            raise RuntimeError(f"v3.1 remediation freeze drifted: {field}")

    luna = CodexPersonaV3RoleRunner(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        bubblewrap=args.bubblewrap,
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        max_seconds=180,
    )
    preflight = luna.verify_preconditions()
    if args.preflight_only:
        print(canonical_json(preflight))
        return

    output.mkdir(parents=True, exist_ok=True)
    raw_root = require_external_raw_root(args.raw_root, workspace_root=repo)
    raw_store = LocalRawPayloadStore(
        raw_root,
        encryption_key=load_or_create_key(
            args.key_file,
            repo=repo,
            create_if_missing=args.create_key_if_missing,
        ),
    )
    packet = json_bytes(
        {
            "fixture_digest": canonical_digest(fixture),
            "observation_digests": [item.content_digest for item in observations],
            "schema_digest": freeze.remediated_output_schema_digest,
        }
    )
    role = luna.run(
        PersonaRoleRequest(
            role_id="persona-nola-v31-neutral-schema-remediation",
            persona_ids=(fixture.case.persona_id,),
            developer_contract=semantic_feedback_role_contract(),
            prompt=semantic_feedback_batch_prompt(observations),
            output_schema=semantic_feedback_output_schema(),
        )
    )
    raw_ref = capture_role_result(
        raw_store,
        role,
        media_type="application/vnd.temper.persona-v31-schema-remediation+json",
    )
    role_receipt = PersonaV31RoleReceipt(
        execution_id="v31-schema-remediation-nola",
        role="semantic_sensor",
        packet_digest=sha256_bytes(packet),
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        input_tokens=role.input_tokens,
        cached_input_tokens=role.cached_input_tokens,
        output_tokens=role.output_tokens,
        reasoning_output_tokens=role.reasoning_output_tokens,
        trace_digest=sha256_bytes(role.trace_bytes),
        encrypted_trace_ref=f"sha256:{raw_ref.sha256}",
        command_digest=role.command_digest,
        environment_digest=role.environment_digest,
    )
    receipt = semantic_receipt(
        observations,
        role,
        runtime_version="codex-cli 0.146.0",
        runtime_digest=_RUNTIME_DIGEST,
    )
    interpretations = bind_semantic_feedback_output(observations, role.response, receipt)
    policy = _policy(fixture)
    state = initial_runtime_state(policy)
    records = []
    for message, observation in zip(fixture.evidence.messages, observations, strict=True):
        interpretation = interpretations[observation.observation_id]
        detection = detect_feedback(
            observation,
            policy,
            state,
            mode=FeedbackDetectorMode.REVIEW,
            semantic_interpretation=interpretation,
        )
        approved, reasons = approve_addition(interpretation, detection)
        review_digest = canonical_digest(
            {
                "approved": approved,
                "detection_digest": detection.content_digest,
                "observation_digest": observation.content_digest,
                "reasons": reasons,
            }
        )
        records.append(
            bind_sensor_record(
                persona_id=fixture.case.persona_id,
                turn=message.turn,
                evidence=message,
                observation=observation,
                interpretation=interpretation,
                detection=detection,
                approved=approved,
                review_receipt_digest=(review_digest if approved else None),
            )
        )
    sensor = PersonaV31SensorResult(
        fixture_digest=canonical_digest(fixture),
        records=tuple(records),
        execution_receipt=role_receipt,
    )
    material = bind_v31_compiled_material(fixture=fixture, records=sensor.records)
    score = score_v31_material(fixture, oracle, material)
    forbidden = {1, 3, 4, 5, 7}
    false_activations = sum(item.approved and item.turn in forbidden for item in sensor.records)
    passed = score.exact and false_activations == 0
    report = PersonaV31RemediationReport(
        protocol_digest=canonical_digest(protocol),
        freeze_digest=canonical_digest(freeze),
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        prior_smoke_report_digest=canonical_digest(prior_report),
        remediated_sensor_result=sensor,
        remediated_compiled_material=material,
        remediated_compiled_score=score,
        task_only_false_activations=false_activations,
        schema_hypothesis_supported=passed,
        instrument_remediation_passed=passed,
    )
    exclusive_write(output / "SENSOR-RESULT-v1.json", json_bytes(sensor))
    write_or_verify(output / "REPORT-v1.json", json_bytes(report))
    print(canonical_json(report.model_dump(mode="json", round_trip=True)))


if __name__ == "__main__":
    main()
