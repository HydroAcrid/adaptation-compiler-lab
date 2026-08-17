"""Shared non-agent orchestration helpers for versioned persona construction smokes."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from adaptation_compiler_lab.automatic_runtime.models import (
    AutomationDisposition,
    DetectedFeedback,
    InteractionObservation,
    SemanticFeedbackInterpretation,
    SemanticInterpreterReceipt,
    SemanticRouteResolution,
    SemanticSignalClarity,
    SemanticSignalDurability,
    SemanticTransitionIntent,
)
from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    semantic_feedback_batch_input_digest,
    semantic_feedback_output_schema,
    semantic_feedback_prompt_digest,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
    require_external_raw_root,
)
from adaptation_compiler_lab.runners.codex_structured_role import StructuredRoleRawResult
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text


def json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def write_or_verify(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"existing persona smoke output drifted: {path.name}")
        return
    exclusive_write(path, payload)


def load_or_create_key(
    path: Path,
    *,
    repo: Path,
    create_if_missing: bool,
) -> RawEncryptionKey:
    resolved = path.expanduser().resolve()
    require_external_raw_root(resolved.parent, workspace_root=repo).mkdir(
        parents=True,
        exist_ok=True,
    )
    if not resolved.exists():
        if not create_if_missing:
            return RawEncryptionKey.from_file(resolved, workspace_root=repo)
        exclusive_write(resolved, base64.b64encode(os.urandom(32)) + b"\n", mode=0o600)
    return RawEncryptionKey.from_file(resolved, workspace_root=repo)


def capture_role_result(
    raw_store: LocalRawPayloadStore,
    result: StructuredRoleRawResult,
    *,
    media_type: str,
) -> RawPayloadRef:
    return raw_store.put(
        json_bytes(
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


def trace_thread_id(trace: bytes) -> str:
    identifiers = []
    for line in trace.decode("utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if value.get("type") == "thread.started" and isinstance(value.get("thread_id"), str):
            identifiers.append(cast(str, value["thread_id"]))
    if len(identifiers) != 1:
        raise RuntimeError("persona semantic trace lacks one fresh thread")
    return identifiers[0]


def semantic_receipt(
    observations: Sequence[InteractionObservation],
    result: StructuredRoleRawResult,
    *,
    runtime_version: str,
    runtime_digest: str,
) -> SemanticInterpreterReceipt:
    thread_id = trace_thread_id(result.trace_bytes)
    input_digest = semantic_feedback_batch_input_digest(observations)
    return SemanticInterpreterReceipt(
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        source_runtime_version=runtime_version,
        source_runtime_digest=runtime_digest,
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


def approve_addition(
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
        return True, ("one clear durable addition passed deterministic review",)
    return False, tuple(sorted(reasons))
