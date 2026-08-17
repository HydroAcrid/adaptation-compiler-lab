"""Execute exactly three isolated roles for the frozen persona v3 construction smoke."""

from __future__ import annotations

import argparse
import base64
import json
import os
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel

from adaptation_compiler_lab.automatic_runtime.detector import detect_feedback
from adaptation_compiler_lab.automatic_runtime.models import (
    AutomationDisposition,
    DetectedFeedback,
    FeedbackDetectorMode,
    InteractionObservation,
    SemanticFeedbackInterpretation,
    SemanticInterpreterReceipt,
    SemanticRouteResolution,
    SemanticSignalClarity,
    SemanticSignalDurability,
    SemanticTransitionIntent,
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
    PersonaV3ProfileOutput,
    PersonaV3Protocol,
    PersonaV3RoleReceipt,
    PersonaV3SensorResult,
    PersonaV3SmokeFixture,
    PersonaV3SmokeFreeze,
    PersonaV3SmokeReport,
    bind_v3_compiled_material,
    bind_v3_profile_material,
    bind_v3_profile_output,
    build_v3_observations,
    build_v3_profile_review_packet,
    persona_v3_profile_output_schema,
    score_v3_smoke_material,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.domain import ArtifactRoute, PermittedUse
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
    require_external_raw_root,
)
from adaptation_compiler_lab.runners.codex_persona import PersonaRoleRequest
from adaptation_compiler_lab.runners.codex_persona_v3 import (
    V3_CODEX_DIGEST,
    V3_CODEX_VERSION,
    CodexPersonaV3RoleRunner,
)
from adaptation_compiler_lab.runners.codex_structured_role import StructuredRoleRawResult
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"existing v3 smoke output drifted: {path.name}")
        return
    _exclusive_write(path, payload)


def _key(path: Path, *, repo: Path, create_if_missing: bool) -> RawEncryptionKey:
    resolved = path.expanduser().resolve()
    require_external_raw_root(resolved.parent, workspace_root=repo).mkdir(
        parents=True, exist_ok=True
    )
    if not resolved.exists():
        if not create_if_missing:
            return RawEncryptionKey.from_file(resolved, workspace_root=repo)
        _exclusive_write(resolved, base64.b64encode(os.urandom(32)) + b"\n", mode=0o600)
    return RawEncryptionKey.from_file(resolved, workspace_root=repo)


def _capture(
    raw_store: LocalRawPayloadStore,
    result: StructuredRoleRawResult,
    *,
    media_type: str,
) -> RawPayloadRef:
    return raw_store.put(
        _json_bytes(
            {
                "response": result.response,
                "stderr": result.stderr,
                "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
                "metadata": {
                    "command_digest": result.command_digest,
                    "environment_digest": result.environment_digest,
                    "started_at": result.started_at.isoformat(),
                    "finished_at": result.finished_at.isoformat(),
                    "duration_seconds": result.duration_seconds,
                    "input_tokens": result.input_tokens,
                    "cached_input_tokens": result.cached_input_tokens,
                    "output_tokens": result.output_tokens,
                    "reasoning_output_tokens": result.reasoning_output_tokens,
                },
            }
        ),
        media_type=media_type,
    )


def _receipt(
    *,
    role: str,
    packet: bytes,
    result: StructuredRoleRawResult,
    raw_ref: RawPayloadRef,
) -> PersonaV3RoleReceipt:
    typed_role = cast(
        Literal["semantic_sensor", "profile_author", "profile_reviewer"],
        role,
    )
    return PersonaV3RoleReceipt(
        execution_id=f"v3-smoke-{role}-sable",
        role=typed_role,
        packet_digest=sha256_bytes(packet),
        model=cast(Literal["gpt-5.6-luna", "gpt-5.6-sol"], result.model),
        reasoning_effort=cast(Literal["medium", "xhigh"], result.reasoning_effort),
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
        reasoning_output_tokens=result.reasoning_output_tokens,
        trace_digest=sha256_bytes(result.trace_bytes),
        encrypted_trace_ref=f"sha256:{raw_ref.sha256}",
        command_digest=result.command_digest,
        environment_digest=result.environment_digest,
    )


def _trace_thread_id(trace: bytes) -> str:
    identifiers = []
    for line in trace.decode("utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if value.get("type") == "thread.started" and isinstance(value.get("thread_id"), str):
            identifiers.append(cast(str, value["thread_id"]))
    if len(identifiers) != 1:
        raise RuntimeError("v3 semantic trace lacks one fresh thread")
    return identifiers[0]


def _semantic_receipt(
    observations: tuple[InteractionObservation, ...],
    result: StructuredRoleRawResult,
) -> SemanticInterpreterReceipt:
    thread_id = _trace_thread_id(result.trace_bytes)
    input_digest = semantic_feedback_batch_input_digest(observations)
    return SemanticInterpreterReceipt(
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        source_runtime_version=V3_CODEX_VERSION,
        source_runtime_digest=V3_CODEX_DIGEST,
        prompt_digest=semantic_feedback_prompt_digest(),
        output_schema_digest=canonical_digest(semantic_feedback_output_schema()),
        batch_input_digest=input_digest,
        output_digest=sha256_text(result.response),
        external_session_digest=sha256_text(thread_id),
        external_turn_digest=canonical_digest(
            {"batch_input_digest": input_digest, "thread_id_digest": sha256_text(thread_id)}
        ),
        input_count=len(observations),
        created_at=result.started_at,
    )


def _policy(fixture: PersonaV3SmokeFixture) -> StandingAutomationPolicy:
    observations = build_v3_observations(fixture)
    broad_scope = fixture.scope_registry.binding_for_turn(1).scope
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
        policy_id="persona-sable-v3-smoke-review",
        subject_id=fixture.case.persona_id,
        scope=broad_scope,
        permitted_uses=uses,
        allowed_routes=routes,
        allowed_target_families=("codex",),
        effective_at=observations[0].observed_at - timedelta(minutes=2),
        expires_at=observations[-1].observed_at + timedelta(days=30),
    )


def _approve(
    interpretation: SemanticFeedbackInterpretation,
    detection: DetectedFeedback,
) -> tuple[bool, tuple[str, ...]]:
    reasons: set[str] = set()
    selected = tuple(
        item
        for item in interpretation.signals
        if item.signal_kind is detection.signal_kind
        and item.normalized_behavior == detection.normalized_behavior
        and item.requested_route == detection.requested_route
    )
    if detection.disposition is not AutomationDisposition.REVIEW_REQUIRED:
        reasons.add("detector output is not an actionable review candidate")
    if len(interpretation.signals) != 1 or len(selected) != 1:
        reasons.add("review requires exactly one unambiguous semantic signal")
    if selected:
        signal = selected[0]
        if signal.durability is not SemanticSignalDurability.DURABLE:
            reasons.add("signal is not explicitly durable")
        if signal.clarity is not SemanticSignalClarity.CLEAR:
            reasons.add("signal is semantically ambiguous")
        if signal.route_resolution is not SemanticRouteResolution.RESOLVED:
            reasons.add("artifact route is ambiguous")
        if signal.semantic_features is None:
            reasons.add("semantic feature vector is unavailable")
        elif signal.semantic_features.transition_intent is not SemanticTransitionIntent.ADDITION:
            reasons.add("smoke review accepts only content additions")
    if not reasons:
        reasons.add("one clear durable addition passed deterministic review")
        return True, tuple(reasons)
    return False, tuple(sorted(reasons))


def _load_and_verify_freeze(
    *,
    repo: Path,
    input_root: Path,
) -> tuple[
    PersonaV3Protocol,
    PersonaV3SmokeFixture,
    PersonaV3ProfileAuthorPacket,
    PersonaV3SmokeFreeze,
]:
    protocol = PersonaV3Protocol.model_validate_json((input_root / "PROTOCOL-v3.json").read_bytes())
    fixture = PersonaV3SmokeFixture.model_validate_json(
        (input_root / "SMOKE-FIXTURE-v1.json").read_bytes()
    )
    author = PersonaV3ProfileAuthorPacket.model_validate_json(
        (input_root / "SMOKE-AUTHOR-PACKET-v1.json").read_bytes()
    )
    freeze = PersonaV3SmokeFreeze.model_validate_json(
        (input_root / "SMOKE-FREEZE-v1.json").read_bytes()
    )
    observations = build_v3_observations(fixture)
    expected = {
        "protocol_digest": canonical_digest(protocol),
        "fixture_digest": canonical_digest(fixture),
        "author_packet_digest": sha256_bytes(_json_bytes(author)),
        "semantic_role_contract_digest": sha256_text(semantic_feedback_role_contract()),
        "semantic_prompt_template_digest": semantic_feedback_prompt_digest(),
        "semantic_batch_input_digest": semantic_feedback_batch_input_digest(observations),
        "semantic_batch_prompt_digest": sha256_text(semantic_feedback_batch_prompt(observations)),
        "semantic_output_schema_digest": canonical_digest(semantic_feedback_output_schema()),
        "profile_output_schema_digest": canonical_digest(persona_v3_profile_output_schema()),
        "benchmark_module_digest": sha256_file(
            repo / "src/adaptation_compiler_lab/benchmark/persona_v3.py"
        ),
        "runner_module_digest": sha256_file(repo / "scripts/run_persona_v3_smoke.py"),
    }
    for field, value in expected.items():
        if getattr(freeze, field) != value:
            raise RuntimeError(f"frozen v3 smoke input drifted: {field}")
    if author.protocol_digest != freeze.protocol_digest:
        raise RuntimeError("v3 author packet protocol binding drifted")
    if author.scope_registry_digest != canonical_digest(fixture.scope_registry):
        raise RuntimeError("v3 author packet scope-registry binding drifted")
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
        raise RuntimeError("OpenAI API keys are forbidden for the v3 subscription smoke")

    repo = args.repo.resolve()
    input_root = args.input.resolve()
    output = args.output.resolve()
    if not input_root.is_relative_to(repo) or not output.is_relative_to(repo):
        raise RuntimeError("v3 public smoke inputs and outputs must remain in the repository")
    protocol, fixture, author_packet, freeze = _load_and_verify_freeze(
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
        encryption_key=_key(
            args.key_file,
            repo=repo,
            create_if_missing=args.create_key_if_missing,
        ),
    )
    observations = build_v3_observations(fixture)
    sensor_packet = _json_bytes(
        {
            "fixture_digest": canonical_digest(fixture),
            "observation_digests": [item.content_digest for item in observations],
            "scope_registry_digest": canonical_digest(fixture.scope_registry),
        }
    )
    sensor_result_path = output / "SMOKE-SENSOR-RESULT-v1.json"
    if sensor_result_path.exists():
        sensor_result = PersonaV3SensorResult.model_validate_json(sensor_result_path.read_bytes())
    else:
        sensor_role = luna.run(
            PersonaRoleRequest(
                role_id="persona-sable-v3-smoke-semantic-sensor",
                persona_ids=(fixture.case.persona_id,),
                developer_contract=semantic_feedback_role_contract(),
                prompt=semantic_feedback_batch_prompt(observations),
                output_schema=semantic_feedback_output_schema(),
            )
        )
        sensor_raw = _capture(
            raw_store,
            sensor_role,
            media_type="application/vnd.temper.persona-v3-smoke-sensor-trace+json",
        )
        receipt = _receipt(
            role="semantic_sensor",
            packet=sensor_packet,
            result=sensor_role,
            raw_ref=sensor_raw,
        )
        semantic_receipt = _semantic_receipt(observations, sensor_role)
        interpretations = bind_semantic_feedback_output(
            observations,
            sensor_role.response,
            semantic_receipt,
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
            approved, reasons = _approve(interpretation, detection)
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
        sensor_result = PersonaV3SensorResult(
            fixture_digest=canonical_digest(fixture),
            records=tuple(records),
            execution_receipt=receipt,
        )
        _exclusive_write(sensor_result_path, _json_bytes(sensor_result))

    author_output_path = output / "SMOKE-PROFILE-AUTHOR-v1.json"
    author_receipt_path = output / "SMOKE-PROFILE-AUTHOR-RECEIPT-v1.json"
    author_bytes = _json_bytes(author_packet)
    if author_output_path.exists() and author_receipt_path.exists():
        draft = PersonaV3ProfileOutput.model_validate_json(author_output_path.read_bytes())
        author_receipt = PersonaV3RoleReceipt.model_validate_json(author_receipt_path.read_bytes())
    elif author_output_path.exists() or author_receipt_path.exists():
        raise RuntimeError("partial v3 author output exists")
    else:
        author_prompt = (
            "Create the strongest concise static behavioral profile for this one fictional "
            "person at the supplied checkpoint. Extract only durable behavioral meaning. "
            "Represent artifact meaning through the semantic feature vector and provenance through "
            "exact source-turn citations; trusted code owns scope and routing. Ignore ordinary "
            "requests and one-off constraints. Keep narrow exceptions as separate claims. "
            "Return schema-valid JSON only.\n\nAUTHOR PACKET\n" + author_bytes.decode("utf-8")
        )
        author_role = sol.run(
            PersonaRoleRequest(
                role_id="persona-sable-v3-smoke-profile-author",
                persona_ids=(fixture.case.persona_id,),
                developer_contract=(
                    "You are an isolated strong static-profile author. Use only the packet, no "
                    "tools or outside context. Do not invent scope identifiers, routes, or "
                    "hidden labels."
                ),
                prompt=author_prompt,
                output_schema=persona_v3_profile_output_schema(),
            )
        )
        author_raw = _capture(
            raw_store,
            author_role,
            media_type="application/vnd.temper.persona-v3-smoke-profile-author-trace+json",
        )
        draft = bind_v3_profile_output(author_role.response)
        author_receipt = _receipt(
            role="profile_author",
            packet=author_bytes,
            result=author_role,
            raw_ref=author_raw,
        )
        _exclusive_write(author_output_path, _json_bytes(draft))
        _exclusive_write(author_receipt_path, _json_bytes(author_receipt))

    review_packet = build_v3_profile_review_packet(author_packet, draft)
    review_bytes = _json_bytes(review_packet)
    reviewed_output_path = output / "SMOKE-PROFILE-REVIEWED-v1.json"
    reviewer_receipt_path = output / "SMOKE-PROFILE-REVIEWER-RECEIPT-v1.json"
    if reviewed_output_path.exists() and reviewer_receipt_path.exists():
        reviewed = PersonaV3ProfileOutput.model_validate_json(reviewed_output_path.read_bytes())
        reviewer_receipt = PersonaV3RoleReceipt.model_validate_json(
            reviewer_receipt_path.read_bytes()
        )
    elif reviewed_output_path.exists() or reviewer_receipt_path.exists():
        raise RuntimeError("partial v3 reviewer output exists")
    else:
        reviewer_prompt = (
            "Independently strengthen this static profile using only the supplied stage-bounded "
            "evidence. Remove unsupported, one-off, broad, ambiguous, or stale claims. Ensure a "
            "narrow durable exception remains separate from the normal behavior and retains exact "
            "visible-turn citations. Trusted code owns route and scope. Return one complete "
            "schema-valid replacement output only.\n\nREVIEW PACKET\n"
            + review_bytes.decode("utf-8")
        )
        reviewer_role = sol.run(
            PersonaRoleRequest(
                role_id="persona-sable-v3-smoke-profile-reviewer",
                persona_ids=(fixture.case.persona_id,),
                developer_contract=(
                    "You are a fresh isolated static-profile reviewer. You cannot see compiled "
                    "material, expected answers, other conditions, later evidence, or prior "
                    "sessions."
                ),
                prompt=reviewer_prompt,
                output_schema=persona_v3_profile_output_schema(),
            )
        )
        reviewer_raw = _capture(
            raw_store,
            reviewer_role,
            media_type="application/vnd.temper.persona-v3-smoke-profile-reviewer-trace+json",
        )
        reviewed = bind_v3_profile_output(reviewer_role.response)
        reviewer_receipt = _receipt(
            role="profile_reviewer",
            packet=review_bytes,
            result=reviewer_role,
            raw_ref=reviewer_raw,
        )
        _exclusive_write(reviewed_output_path, _json_bytes(reviewed))
        _exclusive_write(reviewer_receipt_path, _json_bytes(reviewer_receipt))

    compiled = bind_v3_compiled_material(fixture=fixture, records=sensor_result.records)
    static = bind_v3_profile_material(fixture=fixture, reviewed=reviewed)
    oracle = PersonaHiddenOracle.model_validate_json(
        (input_root / "SMOKE-ORACLE-v1.json").read_bytes()
    )
    if canonical_digest(oracle) != freeze.oracle_digest:
        raise RuntimeError("frozen v3 smoke oracle drifted")
    compiled_score = score_v3_smoke_material(fixture, oracle, compiled)
    static_score = score_v3_smoke_material(fixture, oracle, static)
    passed = compiled_score.exact and static_score.exact and bool(compiled.claims and static.claims)
    report = PersonaV3SmokeReport(
        protocol_digest=canonical_digest(protocol),
        fixture_digest=canonical_digest(fixture),
        oracle_digest=canonical_digest(oracle),
        freeze_digest=canonical_digest(freeze),
        scope_registry_digest=canonical_digest(fixture.scope_registry),
        role_receipts=(sensor_result.execution_receipt, author_receipt, reviewer_receipt),
        compiled_material=compiled,
        static_material=static,
        compiled_score=compiled_score,
        static_score=static_score,
        full_grid_launch_gate_passed=passed,
        passed=passed,
    )
    _write_or_verify(output / "SMOKE-REPORT-v1.json", _json_bytes(report))
    print(canonical_json(report.model_dump(mode="json", round_trip=True)))


if __name__ == "__main__":
    main()
