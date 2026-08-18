"""Run the three isolated construction roles for the frozen v3.2 canary."""

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
    semantic_feedback_batch_prompt,
    semantic_feedback_output_schema,
    semantic_feedback_role_contract,
)
from adaptation_compiler_lab.automatic_runtime.service import initial_runtime_state
from adaptation_compiler_lab.benchmark.persona_instrument import bind_sensor_record
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3ProfileAuthorPacket,
    bind_v3_profile_output,
    build_v3_profile_review_packet,
    persona_v3_profile_output_schema,
)
from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32ConstructionReport,
    PersonaV32Fixture,
    PersonaV32Freeze,
    PersonaV32Oracle,
    PersonaV32Protocol,
    PersonaV32RoleReceipt,
    PersonaV32SensorResult,
    bind_v32_compiled_material,
    bind_v32_profile_material,
    build_v32_observations,
    score_v32_material,
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
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_RUNTIME_DIGEST = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"


def _receipt(
    *, role: str, packet: bytes, result: StructuredRoleRawResult, raw_digest: str
) -> PersonaV32RoleReceipt:
    return PersonaV32RoleReceipt(
        execution_id=f"v32-canary-{role}-maren",
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


def _policy(fixture: PersonaV32Fixture) -> StandingAutomationPolicy:
    observations = build_v32_observations(fixture)
    return StandingAutomationPolicy(
        policy_id="persona-maren-v32-canary-review",
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


def _load_and_verify(
    repo: Path, root: Path
) -> tuple[
    PersonaV32Protocol,
    PersonaV32Fixture,
    PersonaV32Oracle,
    PersonaV3ProfileAuthorPacket,
    PersonaV32Freeze,
]:
    protocol = PersonaV32Protocol.model_validate_json((root / "PROTOCOL-v3.2.json").read_bytes())
    fixture = PersonaV32Fixture.model_validate_json((root / "FIXTURE-v1.json").read_bytes())
    oracle = PersonaV32Oracle.model_validate_json((root / "ORACLE-v1.json").read_bytes())
    author = PersonaV3ProfileAuthorPacket.model_validate_json(
        (root / "AUTHOR-PACKET-v1.json").read_bytes()
    )
    freeze = PersonaV32Freeze.model_validate_json((root / "FREEZE-v1.json").read_bytes())
    expected = {
        "protocol_digest": canonical_digest(protocol),
        "fixture_digest": canonical_digest(fixture),
        "oracle_digest": canonical_digest(oracle),
        "author_packet_digest": sha256_bytes(json_bytes(author)),
        "benchmark_module_digest": sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v32.py"
        ),
        "construction_runner_digest": sha256_file(repo / "scripts/run_persona_v32_construction.py"),
        "target_runner_digest": sha256_file(repo / "scripts/run_persona_v32_targets.py"),
        "judge_runner_digest": sha256_file(repo / "scripts/run_persona_v32_judges.py"),
        "scorer_digest": sha256_file(repo / "scripts/score_compact_projection_task.py"),
    }
    for field, value in expected.items():
        if getattr(freeze, field) != value:
            raise RuntimeError(f"frozen v3.2 construction input drifted: {field}")
    return protocol, fixture, oracle, author, freeze


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--create-key-if-missing", action="store_true")
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for the v3.2 subscription canary")
    repo = args.repo.resolve()
    root = args.input.resolve()
    if root != repo / "development_benchmark_persona_v32":
        raise RuntimeError("v3.2 construction input path drifted")
    protocol, fixture, oracle, author_packet, freeze = _load_and_verify(repo, root)
    luna = CodexPersonaV3RoleRunner(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        bubblewrap=args.bubblewrap,
        model=protocol.semantic_sensor_model,
        reasoning_effort=protocol.semantic_sensor_reasoning_effort,
        max_seconds=240,
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
    output = root / "construction-results-v1"
    if output.exists():
        raise RuntimeError("v3.2 construction results already exist")
    output.mkdir()
    raw_root = require_external_raw_root(args.raw_root, workspace_root=repo)
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_store = LocalRawPayloadStore(
        raw_root,
        encryption_key=load_or_create_key(
            args.key_file, repo=repo, create_if_missing=args.create_key_if_missing
        ),
    )
    observations = build_v32_observations(fixture)
    sensor_packet = json_bytes(
        {
            "fixture_digest": canonical_digest(fixture),
            "observation_digests": [item.content_digest for item in observations],
            "scope_registry_digest": canonical_digest(fixture.scope_registry),
        }
    )
    sensor_role = luna.run(
        PersonaRoleRequest(
            role_id="persona-maren-v32-semantic-sensor",
            persona_ids=(fixture.case.persona_id,),
            developer_contract=semantic_feedback_role_contract(),
            prompt=semantic_feedback_batch_prompt(observations),
            output_schema=semantic_feedback_output_schema(),
        )
    )
    sensor_raw = capture_role_result(
        raw_store,
        sensor_role,
        media_type="application/vnd.temper.persona-v32-sensor-trace+json",
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
        runtime_version=protocol.codex_cli_version,
        runtime_digest=_RUNTIME_DIGEST,
    )
    interpretations = bind_semantic_feedback_output(
        observations, sensor_role.response, interpretation_receipt
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
                review_receipt_digest=review_digest if approved else None,
            )
        )
    sensor_result = PersonaV32SensorResult(
        fixture_digest=canonical_digest(fixture),
        records=tuple(records),
        execution_receipt=sensor_receipt,
    )
    exclusive_write(output / "SENSOR-RESULT-v1.json", json_bytes(sensor_result))

    author_bytes = json_bytes(author_packet)
    author_role = sol.run(
        PersonaRoleRequest(
            role_id="persona-maren-v32-profile-author",
            persona_ids=(fixture.case.persona_id,),
            developer_contract=(
                "You are an isolated strong static-profile author. Use only the packet, no "
                "tools or outside context. Do not invent scope identifiers or routes."
            ),
            prompt=(
                "Create the strongest concise static behavioral profile for this fictional "
                "person at the supplied checkpoint. Extract only durable behavioral meaning, "
                "keep context-specific procedures separate, cite exact visible source turns, "
                "and ignore ordinary requests or one-off constraints. Trusted code owns scope "
                "and routing. Return schema-valid JSON only.\n\nAUTHOR PACKET\n"
                + author_bytes.decode()
            ),
            output_schema=persona_v3_profile_output_schema(),
        )
    )
    author_raw = capture_role_result(
        raw_store,
        author_role,
        media_type="application/vnd.temper.persona-v32-profile-author+json",
    )
    draft = bind_v3_profile_output(author_role.response)
    author_receipt = _receipt(
        role="profile_author",
        packet=author_bytes,
        result=author_role,
        raw_digest=author_raw.sha256,
    )
    exclusive_write(output / "PROFILE-AUTHOR-v1.json", json_bytes(draft))
    exclusive_write(output / "PROFILE-AUTHOR-RECEIPT-v1.json", json_bytes(author_receipt))

    review_packet = build_v3_profile_review_packet(author_packet, draft)
    review_bytes = json_bytes(review_packet)
    reviewer_role = sol.run(
        PersonaRoleRequest(
            role_id="persona-maren-v32-profile-reviewer",
            persona_ids=(fixture.case.persona_id,),
            developer_contract=(
                "You are a fresh isolated static-profile reviewer. You cannot see compiled "
                "material, expected answers, target tasks, condition mappings, or prior sessions."
            ),
            prompt=(
                "Independently strengthen the draft using only the supplied evidence. Remove "
                "unsupported, one-off, broad, ambiguous, or stale claims. Keep each durable "
                "behavior separate with exact visible-turn citations. Return one complete "
                "schema-valid replacement output only.\n\nREVIEW PACKET\n" + review_bytes.decode()
            ),
            output_schema=persona_v3_profile_output_schema(),
        )
    )
    reviewer_raw = capture_role_result(
        raw_store,
        reviewer_role,
        media_type="application/vnd.temper.persona-v32-profile-reviewer+json",
    )
    reviewed = bind_v3_profile_output(reviewer_role.response)
    reviewer_receipt = _receipt(
        role="profile_reviewer",
        packet=review_bytes,
        result=reviewer_role,
        raw_digest=reviewer_raw.sha256,
    )
    exclusive_write(output / "PROFILE-REVIEWED-v1.json", json_bytes(reviewed))
    exclusive_write(output / "PROFILE-REVIEWER-RECEIPT-v1.json", json_bytes(reviewer_receipt))

    compiled = bind_v32_compiled_material(fixture=fixture, records=sensor_result.records)
    static = bind_v32_profile_material(fixture=fixture, reviewed=reviewed)
    compiled_score = score_v32_material(fixture, oracle, compiled)
    static_score = score_v32_material(fixture, oracle, static)
    report = PersonaV32ConstructionReport(
        protocol_digest=canonical_digest(protocol),
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        freeze_digest=canonical_digest(freeze),
        role_receipts=(sensor_receipt, author_receipt, reviewer_receipt),
        compiled_material=compiled,
        static_material=static,
        compiled_score=compiled_score,
        static_score=static_score,
        compiled_material_bytes=len(compiled.target_guidance.encode()),
        static_material_bytes=len(static.target_guidance.encode()),
        exact_target_gate_passed=compiled_score.exact and static_score.exact,
    )
    exclusive_write(output / "CONSTRUCTION-REPORT-v1.json", json_bytes(report))
    print(canonical_json(report.model_dump(mode="json", round_trip=True)))
    if not report.exact_target_gate_passed:
        raise RuntimeError("v3.2 construction was not exact; target execution remains blocked")


if __name__ == "__main__":
    main()
