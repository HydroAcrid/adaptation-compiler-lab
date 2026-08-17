"""Execute the three frozen roles for the fresh persona v3.1 replacement smoke."""

from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path
from typing import Literal, cast

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
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3ProfileAuthorPacket,
    bind_v3_profile_output,
    build_v3_profile_review_packet,
    persona_v3_profile_output_schema,
)
from adaptation_compiler_lab.benchmark.persona_v31 import (
    PersonaV31Fixture,
    PersonaV31Freeze,
    PersonaV31Protocol,
    PersonaV31Report,
    PersonaV31RoleReceipt,
    PersonaV31SensorResult,
    bind_v31_compiled_material,
    bind_v31_profile_material,
    build_v31_observations,
    score_v31_material,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.domain import ArtifactRoute, PermittedUse
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, require_external_raw_root
from adaptation_compiler_lab.runners.codex_persona import PersonaRoleRequest
from adaptation_compiler_lab.runners.codex_persona_v3 import CodexPersonaV3RoleRunner
from adaptation_compiler_lab.runners.codex_structured_role import StructuredRoleRawResult
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


def _receipt(
    *,
    role: str,
    packet: bytes,
    result: StructuredRoleRawResult,
    raw_digest: str,
) -> PersonaV31RoleReceipt:
    return PersonaV31RoleReceipt(
        execution_id=f"v31-smoke-{role}-nola",
        role=cast(Literal["semantic_sensor", "profile_author", "profile_reviewer"], role),
        packet_digest=sha256_bytes(packet),
        model=cast(Literal["gpt-5.6-luna", "gpt-5.6-sol"], result.model),
        reasoning_effort=cast(Literal["medium", "xhigh"], result.reasoning_effort),
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
        reasoning_output_tokens=result.reasoning_output_tokens,
        trace_digest=sha256_bytes(result.trace_bytes),
        encrypted_trace_ref=f"sha256:{raw_digest}",
        command_digest=result.command_digest,
        environment_digest=result.environment_digest,
    )


def _policy(fixture: PersonaV31Fixture) -> StandingAutomationPolicy:
    observations = build_v31_observations(fixture)
    uses = tuple(
        sorted(
            (
                PermittedUse.AUDIT,
                PermittedUse.CONSTRUCTION,
                PermittedUse.PROMOTION,
                PermittedUse.TARGET_DELIVERY,
            ),
            key=lambda item: item.value,
        )
    )
    routes = tuple(
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
    )
    return StandingAutomationPolicy(
        policy_id="persona-nola-v31-smoke-review",
        subject_id=fixture.case.persona_id,
        scope=fixture.scope_registry.binding_for_turn(1).scope,
        permitted_uses=uses,
        allowed_routes=routes,
        allowed_target_families=("codex",),
        effective_at=observations[0].observed_at - timedelta(minutes=2),
        expires_at=observations[-1].observed_at + timedelta(days=30),
    )


def _load_and_verify(
    *, repo: Path, input_root: Path
) -> tuple[
    PersonaV31Protocol,
    PersonaV31Fixture,
    PersonaV3ProfileAuthorPacket,
    PersonaV31Freeze,
]:
    protocol = PersonaV31Protocol.model_validate_json(
        (input_root / "PROTOCOL-v3.1.json").read_bytes()
    )
    fixture = PersonaV31Fixture.model_validate_json(
        (input_root / "SMOKE-FIXTURE-v1.json").read_bytes()
    )
    author = PersonaV3ProfileAuthorPacket.model_validate_json(
        (input_root / "SMOKE-AUTHOR-PACKET-v1.json").read_bytes()
    )
    freeze = PersonaV31Freeze.model_validate_json(
        (input_root / "SMOKE-FREEZE-v1.json").read_bytes()
    )
    observations = build_v31_observations(fixture)
    expected = {
        "protocol_digest": canonical_digest(protocol),
        "fixture_digest": canonical_digest(fixture),
        "author_packet_digest": sha256_bytes(json_bytes(author)),
        "semantic_role_contract_digest": sha256_text(semantic_feedback_role_contract()),
        "semantic_prompt_template_digest": semantic_feedback_prompt_digest(),
        "semantic_batch_input_digest": semantic_feedback_batch_input_digest(observations),
        "semantic_batch_prompt_digest": sha256_text(semantic_feedback_batch_prompt(observations)),
        "semantic_output_schema_digest": canonical_digest(semantic_feedback_output_schema()),
        "profile_output_schema_digest": canonical_digest(persona_v3_profile_output_schema()),
        "benchmark_module_digest": sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v31.py"
        ),
        "runner_module_digest": sha256_file(repo / "scripts/run_persona_v31_smoke.py"),
    }
    for field, value in expected.items():
        if getattr(freeze, field) != value:
            raise RuntimeError(f"frozen v3.1 smoke input drifted: {field}")
    if author.protocol_digest != freeze.protocol_digest:
        raise RuntimeError("v3.1 author packet protocol binding drifted")
    if author.scope_registry_digest != canonical_digest(fixture.scope_registry):
        raise RuntimeError("v3.1 author packet scope binding drifted")
    return protocol, fixture, author, freeze


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
        raise RuntimeError("OpenAI API keys are forbidden for the v3.1 subscription smoke")

    repo = args.repo.resolve()
    input_root = args.input.resolve()
    output = args.output.resolve()
    if not input_root.is_relative_to(repo) or output != input_root / "results":
        raise RuntimeError("v3.1 inputs and exact results directory must remain in the repository")
    protocol, fixture, author_packet, freeze = _load_and_verify(
        repo=repo,
        input_root=input_root,
    )
    luna = CodexPersonaV3RoleRunner(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        bubblewrap=args.bubblewrap,
        model=protocol.semantic_sensor_model,
        reasoning_effort=protocol.semantic_sensor_reasoning_effort,
        max_seconds=180,
    )
    sol = CodexPersonaV3RoleRunner(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        bubblewrap=args.bubblewrap,
        model=protocol.profile_model,
        reasoning_effort=protocol.profile_reasoning_effort,
        max_seconds=600,
    )
    preflight = {
        "semantic_sensor": luna.verify_preconditions(),
        "profile": sol.verify_preconditions(),
    }
    if args.preflight_only:
        print(canonical_json(preflight))
        return

    output.mkdir(parents=True, exist_ok=True)
    raw_root = require_external_raw_root(args.raw_root, workspace_root=repo)
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_store = LocalRawPayloadStore(
        raw_root,
        encryption_key=load_or_create_key(
            args.key_file,
            repo=repo,
            create_if_missing=args.create_key_if_missing,
        ),
    )
    observations = build_v31_observations(fixture)
    sensor_packet = json_bytes(
        {
            "fixture_digest": canonical_digest(fixture),
            "observation_digests": [item.content_digest for item in observations],
            "scope_registry_digest": canonical_digest(fixture.scope_registry),
        }
    )
    sensor_role = luna.run(
        PersonaRoleRequest(
            role_id="persona-nola-v31-smoke-semantic-sensor",
            persona_ids=(fixture.case.persona_id,),
            developer_contract=semantic_feedback_role_contract(),
            prompt=semantic_feedback_batch_prompt(observations),
            output_schema=semantic_feedback_output_schema(),
        )
    )
    sensor_raw = capture_role_result(
        raw_store,
        sensor_role,
        media_type="application/vnd.temper.persona-v31-smoke-sensor-trace+json",
    )
    sensor_receipt = _receipt(
        role="semantic_sensor",
        packet=sensor_packet,
        result=sensor_role,
        raw_digest=sensor_raw.sha256,
    )
    interpretation_receipt = semantic_receipt(
        observations,
        sensor_role,
        runtime_version="codex-cli 0.146.0",
        runtime_digest=("sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"),
    )
    interpretations = bind_semantic_feedback_output(
        observations,
        sensor_role.response,
        interpretation_receipt,
    )
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
    sensor_result = PersonaV31SensorResult(
        fixture_digest=canonical_digest(fixture),
        records=tuple(records),
        execution_receipt=sensor_receipt,
    )
    exclusive_write(output / "SMOKE-SENSOR-RESULT-v1.json", json_bytes(sensor_result))

    author_bytes = json_bytes(author_packet)
    author_role = sol.run(
        PersonaRoleRequest(
            role_id="persona-nola-v31-smoke-profile-author",
            persona_ids=(fixture.case.persona_id,),
            developer_contract=(
                "You are an isolated strong static-profile author. Use only the packet, no "
                "tools or outside context. Do not invent scope identifiers, routes, or "
                "hidden labels."
            ),
            prompt=(
                "Create the strongest concise static behavioral profile for this one fictional "
                "person at the supplied checkpoint. Extract only durable behavioral meaning. "
                "Represent artifact meaning through the semantic feature vector and provenance "
                "through exact source-turn citations; trusted code owns scope and routing. Ignore "
                "ordinary requests and one-off constraints. Keep context-specific procedures as "
                "separate claims. Return schema-valid JSON only.\n\nAUTHOR PACKET\n"
                + author_bytes.decode("utf-8")
            ),
            output_schema=persona_v3_profile_output_schema(),
        )
    )
    author_raw = capture_role_result(
        raw_store,
        author_role,
        media_type="application/vnd.temper.persona-v31-profile-author-trace+json",
    )
    draft = bind_v3_profile_output(author_role.response)
    author_receipt = _receipt(
        role="profile_author",
        packet=author_bytes,
        result=author_role,
        raw_digest=author_raw.sha256,
    )
    exclusive_write(output / "SMOKE-PROFILE-AUTHOR-v1.json", json_bytes(draft))
    exclusive_write(
        output / "SMOKE-PROFILE-AUTHOR-RECEIPT-v1.json",
        json_bytes(author_receipt),
    )

    review_packet = build_v3_profile_review_packet(author_packet, draft)
    review_bytes = json_bytes(review_packet)
    reviewer_role = sol.run(
        PersonaRoleRequest(
            role_id="persona-nola-v31-smoke-profile-reviewer",
            persona_ids=(fixture.case.persona_id,),
            developer_contract=(
                "You are a fresh isolated static-profile reviewer. You cannot see compiled "
                "material, expected answers, other conditions, later evidence, or prior sessions."
            ),
            prompt=(
                "Independently strengthen this static profile using only the supplied "
                "stage-bounded "
                "evidence. Remove unsupported, one-off, broad, ambiguous, or stale claims. Keep "
                "each durable behavior separate with exact visible-turn citations. Trusted code "
                "owns route and scope. Return one complete schema-valid replacement output only."
                "\n\nREVIEW PACKET\n" + review_bytes.decode("utf-8")
            ),
            output_schema=persona_v3_profile_output_schema(),
        )
    )
    reviewer_raw = capture_role_result(
        raw_store,
        reviewer_role,
        media_type="application/vnd.temper.persona-v31-profile-reviewer-trace+json",
    )
    reviewed = bind_v3_profile_output(reviewer_role.response)
    reviewer_receipt = _receipt(
        role="profile_reviewer",
        packet=review_bytes,
        result=reviewer_role,
        raw_digest=reviewer_raw.sha256,
    )
    exclusive_write(output / "SMOKE-PROFILE-REVIEWED-v1.json", json_bytes(reviewed))
    exclusive_write(
        output / "SMOKE-PROFILE-REVIEWER-RECEIPT-v1.json",
        json_bytes(reviewer_receipt),
    )

    compiled = bind_v31_compiled_material(fixture=fixture, records=sensor_result.records)
    static = bind_v31_profile_material(fixture=fixture, reviewed=reviewed)
    oracle = PersonaHiddenOracle.model_validate_json(
        (input_root / "SMOKE-ORACLE-v1.json").read_bytes()
    )
    if canonical_digest(oracle) != freeze.oracle_digest:
        raise RuntimeError("frozen v3.1 oracle drifted")
    compiled_score = score_v31_material(fixture, oracle, compiled)
    static_score = score_v31_material(fixture, oracle, static)
    passed = compiled_score.exact and static_score.exact and bool(compiled.claims and static.claims)
    report = PersonaV31Report(
        protocol_digest=canonical_digest(protocol),
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        freeze_digest=canonical_digest(freeze),
        scope_registry_digest=canonical_digest(fixture.scope_registry),
        role_receipts=(sensor_receipt, author_receipt, reviewer_receipt),
        compiled_material=compiled,
        static_material=static,
        compiled_score=compiled_score,
        static_score=static_score,
        full_grid_launch_gate_passed=passed,
        passed=passed,
    )
    write_or_verify(output / "SMOKE-REPORT-v1.json", json_bytes(report))
    print(canonical_json(report.model_dump(mode="json", round_trip=True)))


if __name__ == "__main__":
    main()
