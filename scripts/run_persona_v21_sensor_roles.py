"""Run the 18 isolated Luna semantic-sensor sessions for persona v2.1."""

from __future__ import annotations

import argparse
import atexit
import base64
import fcntl
import json
import os
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

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
    PersonaSensorRecord,
    PersonaSensorReviewDecision,
    PersonaV21ExecutionReceipt,
    PersonaV21SensorBatch,
    PersonaV21SensorResult,
    bind_sensor_record,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ArtifactRoute,
    PermittedUse,
    SourceClass,
    TaskRecordRef,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    require_external_raw_root,
)
from adaptation_compiler_lab.runners.codex_persona import PersonaRoleRequest
from adaptation_compiler_lab.runners.codex_persona_v21 import (
    V21_CODEX_DIGEST,
    V21_CODEX_VERSION,
    CodexPersonaV21RoleRunner,
)
from adaptation_compiler_lab.runners.codex_structured_role import StructuredRoleRawResult
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_SOURCE_SCHEMA_DIGEST = canonical_digest(PersonaV21SensorBatch.model_json_schema())


def _exclusive_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _single_writer(raw_root: Path) -> object:
    lock = (raw_root / "persona-v21-sensor.lock").open("a+b")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock.close()
        raise RuntimeError("another v2.1 semantic sensor coordinator is active") from error

    def release() -> None:
        if not lock.closed:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    atexit.register(release)
    return lock


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _policy(batch: PersonaV21SensorBatch, cutoff: datetime) -> StandingAutomationPolicy:
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
        policy_id=f"persona-{batch.persona_id}-v21-review",
        subject_id=batch.persona_id,
        scope=batch.scope,
        permitted_uses=uses,
        allowed_routes=routes,
        allowed_target_families=("codex",),
        effective_at=cutoff - timedelta(minutes=1),
        expires_at=cutoff + timedelta(days=30),
    )


def _trace_thread_id(trace: bytes) -> str:
    values = []
    for line in trace.decode("utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if value.get("type") == "thread.started" and isinstance(value.get("thread_id"), str):
            values.append(cast(str, value["thread_id"]))
    if len(values) != 1:
        raise RuntimeError("semantic sensor trace lacks one fresh external thread")
    return values[0]


def _semantic_receipt(
    observations: tuple[InteractionObservation, ...],
    result: StructuredRoleRawResult,
) -> SemanticInterpreterReceipt:
    thread_id = _trace_thread_id(result.trace_bytes)
    input_digest = semantic_feedback_batch_input_digest(observations)
    return SemanticInterpreterReceipt(
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        source_runtime_version=V21_CODEX_VERSION,
        source_runtime_digest=V21_CODEX_DIGEST,
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


def _review(
    *,
    batch: PersonaV21SensorBatch,
    turn: int,
    interpretation: SemanticFeedbackInterpretation,
    detection: DetectedFeedback,
    host_target_available: bool,
) -> PersonaSensorReviewDecision:
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
        transition = (
            None if signal.semantic_features is None else signal.semantic_features.transition_intent
        )
        if (
            transition
            in {
                SemanticTransitionIntent.CORRECTION,
                SemanticTransitionIntent.REVOCATION,
            }
            and not host_target_available
        ):
            reasons.add("lifecycle transition lacks a trusted host-bound target")
    approved = not reasons
    if approved:
        reasons.add("one clear durable signal passed deterministic review")
    return PersonaSensorReviewDecision(
        batch_id=batch.batch_id,
        persona_id=batch.persona_id,
        turn=turn,
        observation_digest=detection.observation_digest,
        interpretation_receipt_digest=interpretation.receipt.content_digest,
        detection_digest=detection.content_digest,
        approved=approved,
        reasons=tuple(sorted(reasons)),
    )


def _execution_receipt(
    *,
    batch: PersonaV21SensorBatch,
    packet_bytes: bytes,
    result: StructuredRoleRawResult,
    encrypted_trace_ref: str,
) -> PersonaV21ExecutionReceipt:
    return PersonaV21ExecutionReceipt(
        execution_id=f"v21-semantic-sensor-{batch.batch_id}",
        role="semantic_sensor",
        persona_id=batch.persona_id,
        packet_digest=sha256_bytes(packet_bytes),
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
        reasoning_output_tokens=result.reasoning_output_tokens,
        trace_digest=sha256_bytes(result.trace_bytes),
        encrypted_trace_ref=encrypted_trace_ref,
        command_digest=result.command_digest,
        environment_digest=result.environment_digest,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for v2.1 semantic sensor roles")
    runner = CodexPersonaV21RoleRunner(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        bubblewrap=args.bubblewrap,
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        max_seconds=180,
    )
    if args.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw_root = require_external_raw_root(args.raw_root, workspace_root=Path.cwd())
    raw_root.mkdir(parents=True, exist_ok=True)
    coordinator_lock = _single_writer(raw_root)
    raw_store = LocalRawPayloadStore(
        raw_root,
        encryption_key=RawEncryptionKey.from_file(
            args.key_file.resolve(), workspace_root=Path.cwd()
        ),
    )
    batch_paths = sorted(args.batches.resolve().glob("*.json"))
    if len(batch_paths) != 18:
        raise ValueError("v2.1 semantic sensor requires exactly 18 registered batches")
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("semantic sensor limit must be positive")
        batch_paths = batch_paths[: args.limit]

    prior_records: dict[tuple[str, int], PersonaSensorRecord] = {}
    for existing in sorted(output.glob("*.result.json")):
        restored = PersonaV21SensorResult.model_validate_json(existing.read_bytes())
        for record in restored.records:
            prior_records[(restored.persona_id, record.turn)] = record

    for batch_path in batch_paths:
        packet_bytes = batch_path.read_bytes()
        batch = PersonaV21SensorBatch.model_validate_json(packet_bytes)
        result_path = output / f"{batch.batch_id}.result.json"
        if result_path.exists():
            continue
        cutoff = datetime.fromisoformat(batch.construction_cutoff.replace("Z", "+00:00"))
        target_by_turn = {item.turn: item.affected_source_turn for item in batch.target_bindings}
        observations = []
        for message in batch.messages:
            source_turn = target_by_turn.get(message.turn)
            target = (
                None if source_turn is None else prior_records.get((batch.persona_id, source_turn))
            )
            affected_claim_id = None if target is None or not target.approved else target.claim_id
            observations.append(
                InteractionObservation(
                    observation_id=f"{batch.batch_id}-turn-{message.turn}",
                    subject_id=batch.persona_id,
                    task_ref=TaskRecordRef(
                        record_id=f"persona-{batch.persona_id}-stage-{batch.stage}",
                        record_version="1.0.0",
                    ),
                    turn_id=f"turn-{message.turn}",
                    actor=ActorRef(actor_id=batch.persona_id, kind=ActorKind.USER),
                    source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
                    text=message.message,
                    scope=batch.scope,
                    observed_at=cutoff + timedelta(minutes=message.turn),
                    source_system="local_interaction_runtime",
                    source_version="temper-persona-v21-synthetic-1",
                    source_schema_digest=_SOURCE_SCHEMA_DIGEST,
                    affected_artifact_id=affected_claim_id,
                )
            )
        typed_observations = tuple(observations)
        role_result = runner.run(
            PersonaRoleRequest(
                role_id=f"persona-{batch.persona_id}-v21-stage-{batch.stage}-semantic-sensor",
                persona_ids=(batch.persona_id,),
                developer_contract=semantic_feedback_role_contract(),
                prompt=semantic_feedback_batch_prompt(typed_observations),
                output_schema=semantic_feedback_output_schema(),
            )
        )
        semantic_receipt = _semantic_receipt(typed_observations, role_result)
        try:
            interpretations = bind_semantic_feedback_output(
                typed_observations,
                role_result.response,
                semantic_receipt,
            )
        except ValueError as error:
            invalid_raw = raw_store.put(
                _json_bytes(
                    {
                        "batch": batch.model_dump(mode="json", round_trip=True),
                        "response": role_result.response,
                        "stderr": role_result.stderr,
                        "trace_base64": base64.b64encode(role_result.trace_bytes).decode("ascii"),
                    }
                ),
                media_type="application/vnd.temper.persona-v21-invalid-sensor-trace+json",
            )
            _exclusive_write(
                output / f"{batch.batch_id}.invalid.json",
                _json_bytes(
                    {
                        "batch_id": batch.batch_id,
                        "error_class": type(error).__name__,
                        "response_digest": sha256_text(role_result.response),
                        "trace_digest": sha256_bytes(role_result.trace_bytes),
                        "encrypted_trace_ref": f"sha256:{invalid_raw.sha256}",
                        "result_written": False,
                    }
                ),
            )
            raise
        role_capture = raw_store.put(
            _json_bytes(
                {
                    "batch": batch.model_dump(mode="json", round_trip=True),
                    "interpretations": [
                        interpretations[item.observation_id].model_dump(
                            mode="json", round_trip=True
                        )
                        for item in typed_observations
                    ],
                    "role_metadata": {
                        "command_digest": role_result.command_digest,
                        "environment_digest": role_result.environment_digest,
                        "started_at": role_result.started_at.isoformat(),
                        "finished_at": role_result.finished_at.isoformat(),
                        "duration_seconds": role_result.duration_seconds,
                        "input_tokens": role_result.input_tokens,
                        "cached_input_tokens": role_result.cached_input_tokens,
                        "output_tokens": role_result.output_tokens,
                        "reasoning_output_tokens": role_result.reasoning_output_tokens,
                        "model": role_result.model,
                        "reasoning_effort": role_result.reasoning_effort,
                    },
                    "response": role_result.response,
                    "stderr": role_result.stderr,
                    "trace_base64": base64.b64encode(role_result.trace_bytes).decode("ascii"),
                }
            ),
            media_type="application/vnd.temper.persona-v21-sensor-role-capture+json",
        )
        policy = _policy(batch, cutoff)
        state = initial_runtime_state(policy)
        records = []
        reviews = []
        detections = []
        try:
            for message, observation in zip(batch.messages, typed_observations, strict=True):
                interpretation = interpretations[observation.observation_id]
                detection = detect_feedback(
                    observation,
                    policy,
                    state,
                    mode=FeedbackDetectorMode.REVIEW,
                    semantic_interpretation=interpretation,
                )
                review = _review(
                    batch=batch,
                    turn=message.turn,
                    interpretation=interpretation,
                    detection=detection,
                    host_target_available=observation.affected_artifact_id is not None,
                )
                record = bind_sensor_record(
                    persona_id=batch.persona_id,
                    turn=message.turn,
                    evidence=message,
                    observation=observation,
                    interpretation=interpretation,
                    detection=detection,
                    approved=review.approved,
                    review_receipt_digest=(review.content_digest if review.approved else None),
                )
                records.append(record)
                reviews.append(review)
                detections.append(detection)
        except ValueError as error:
            suffix = sha256_text(role_result.response).removeprefix("sha256:")[:12]
            _exclusive_write(
                output / f"{batch.batch_id}.{suffix}.invalid.json",
                _json_bytes(
                    {
                        "batch_id": batch.batch_id,
                        "error_class": type(error).__name__,
                        "response_digest": sha256_text(role_result.response),
                        "trace_digest": sha256_bytes(role_result.trace_bytes),
                        "encrypted_trace_ref": f"sha256:{role_capture.sha256}",
                        "result_written": False,
                    }
                ),
            )
            raise
        raw_ref = raw_store.put(
            _json_bytes(
                {
                    "batch": batch.model_dump(mode="json", round_trip=True),
                    "interpretations": [
                        interpretations[item.observation_id].model_dump(
                            mode="json", round_trip=True
                        )
                        for item in typed_observations
                    ],
                    "detections": [
                        item.model_dump(mode="json", round_trip=True) for item in detections
                    ],
                    "response": role_result.response,
                    "stderr": role_result.stderr,
                    "trace_base64": base64.b64encode(role_result.trace_bytes).decode("ascii"),
                }
            ),
            media_type="application/vnd.temper.persona-v21-semantic-sensor-trace+json",
        )
        execution_receipt = _execution_receipt(
            batch=batch,
            packet_bytes=packet_bytes,
            result=role_result,
            encrypted_trace_ref=f"sha256:{raw_ref.sha256}",
        )
        completed = PersonaV21SensorResult(
            batch_id=batch.batch_id,
            persona_id=batch.persona_id,
            stage=batch.stage,
            batch_digest=sha256_bytes(packet_bytes),
            records=tuple(records),
            reviews=tuple(reviews),
            execution_receipt=execution_receipt,
        )
        _exclusive_write(result_path, _json_bytes(completed))
        for record in completed.records:
            prior_records[(batch.persona_id, record.turn)] = record
        print(f"completed v2.1 semantic sensor: {batch.batch_id}", flush=True)
    del coordinator_lock


if __name__ == "__main__":
    main()
