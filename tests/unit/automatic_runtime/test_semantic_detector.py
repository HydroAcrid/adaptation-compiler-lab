from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime import (
    AutomationDisposition,
    FeedbackDetectorMode,
    FeedbackSignalKind,
    SemanticFeedbackInterpretation,
    SemanticFeedbackSignal,
    SemanticInterpreterReceipt,
    SemanticScopeHint,
    SemanticSignalClarity,
    SemanticSignalDurability,
    initial_runtime_state,
)
from adaptation_compiler_lab.automatic_runtime.codex_dogfood import CodexDogfoodSchemaSet
from adaptation_compiler_lab.automatic_runtime.detector import (
    SemanticInterpretationError,
    detect_feedback,
)
from adaptation_compiler_lab.automatic_runtime.semantic_interpreter import (
    CodexSemanticFeedbackInterpreter,
    SemanticInterpreterError,
)
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import VerifiedCodexRuntime
from adaptation_compiler_lab.domain import ArtifactRoute
from tests.unit.automatic_runtime.test_runtime import DIGEST, NOW, _observation, _runtime


def _receipt(tmp_path: Path) -> SemanticInterpreterReceipt:
    executable = tmp_path / "codex"
    executable.write_bytes(b"pinned semantic test runtime")
    return SemanticInterpreterReceipt(
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        source_runtime_version="codex-cli 0.146.0",
        source_runtime_digest="sha256:" + "1" * 64,
        prompt_digest="sha256:" + "2" * 64,
        output_schema_digest="sha256:" + "3" * 64,
        batch_input_digest="sha256:" + "4" * 64,
        output_digest="sha256:" + "5" * 64,
        external_session_digest="sha256:" + "6" * 64,
        external_turn_digest="sha256:" + "7" * 64,
        input_count=1,
        created_at=NOW,
    )


def _interpretation(
    tmp_path: Path,
    *,
    text: str,
    quote: str,
    behavior: str,
) -> SemanticFeedbackInterpretation:
    observation = _observation(1, text)
    start = text.index(quote)
    return SemanticFeedbackInterpretation(
        observation_id=observation.observation_id,
        observation_digest=observation.content_digest,
        signals=(
            SemanticFeedbackSignal(
                signal_kind=FeedbackSignalKind.PREFERENCE,
                normalized_behavior=behavior,
                requested_route=ArtifactRoute.PREFERENCE,
                supporting_quote=quote,
                support_start=start,
                support_end=start + len(quote),
                durability=SemanticSignalDurability.DURABLE,
                clarity=SemanticSignalClarity.CLEAR,
                scope_hint=SemanticScopeHint.PERMANENT_PROFILE,
            ),
        ),
        receipt=_receipt(tmp_path),
    )


def test_natural_preference_is_reviewed_then_calibrated_for_promotion(
    tmp_path: Path,
) -> None:
    text = (
        "Hmmm, I prefer names that represent real things. I don't like generic corney “techy” names"
    )
    observation = _observation(1, text)
    interpretation = _interpretation(
        tmp_path,
        text=text,
        quote=text,
        behavior="Use names that represent real domain concepts and avoid generic techy names.",
    )
    runtime, policy = _runtime(tmp_path)
    state = initial_runtime_state(policy)

    review = detect_feedback(
        observation,
        policy,
        state,
        mode=FeedbackDetectorMode.REVIEW,
        semantic_interpretation=interpretation,
    )
    assert review.disposition is AutomationDisposition.REVIEW_REQUIRED
    assert review.detector_id == "codex-semantic-feedback"
    assert review.semantic_candidate_count == 1
    assert review.supporting_span_digests

    promoted = runtime.learn(
        observation,
        state=state,
        processed_at=NOW + timedelta(minutes=1, seconds=1),
        detector_mode=FeedbackDetectorMode.CALIBRATED,
        semantic_interpretation=interpretation,
    )
    assert promoted.cycle.disposition is AutomationDisposition.PROMOTED
    assert promoted.state.release is not None
    assert promoted.state.release.governed_release.active_artifacts[
        0
    ].behavioral_contract.required_behaviors == (
        "Use names that represent real domain concepts and avoid generic techy names.",
    )


def test_task_only_semantic_signal_is_not_durable_learning(tmp_path: Path) -> None:
    text = "For this one file, rename x to request_count."
    observation = _observation(1, text)
    quote = "For this one file"
    interpretation = _interpretation(
        tmp_path,
        text=text,
        quote=quote,
        behavior="Rename x to request_count in this file.",
    )
    interpretation = interpretation.model_copy(
        update={
            "signals": (
                interpretation.signals[0].model_copy(
                    update={"durability": SemanticSignalDurability.TASK_ONLY}
                ),
            )
        }
    )
    _runtime_instance, policy = _runtime(tmp_path)

    detected = detect_feedback(
        observation,
        policy,
        initial_runtime_state(policy),
        mode=FeedbackDetectorMode.CALIBRATED,
        semantic_interpretation=interpretation,
    )
    assert detected.disposition is AutomationDisposition.NO_EXPLICIT_SIGNAL


@pytest.mark.parametrize(
    ("text", "behavior"),
    [
        (
            "Show me astronomy-related open-source projects.",
            "Prefer hearing about astronomy-related open-source projects.",
        ),
        (
            "Use Rust for this parser.",
            "Prefer Rust for parsers.",
        ),
        (
            "Write this explanation for a beginner.",
            "Prefer beginner-level explanations.",
        ),
    ],
)
def test_current_task_topic_cannot_become_durable_preference(
    tmp_path: Path,
    text: str,
    behavior: str,
) -> None:
    observation = _observation(1, text)
    interpretation = _interpretation(
        tmp_path,
        text=text,
        quote=text,
        behavior=behavior,
    )
    interpretation = interpretation.model_copy(
        update={
            "signals": (
                interpretation.signals[0].model_copy(
                    update={"durability": SemanticSignalDurability.TASK_ONLY}
                ),
            )
        }
    )
    _runtime_instance, policy = _runtime(tmp_path)

    detected = detect_feedback(
        observation,
        policy,
        initial_runtime_state(policy),
        mode=FeedbackDetectorMode.CALIBRATED,
        semantic_interpretation=interpretation,
    )

    assert detected.disposition is AutomationDisposition.NO_EXPLICIT_SIGNAL
    assert detected.normalized_behavior is None


def test_semantic_receipt_preserves_v1_1_read_compatibility(tmp_path: Path) -> None:
    payload = _receipt(tmp_path).model_dump(mode="python")
    payload["interpreter_version"] = "1.1.0"

    restored = SemanticInterpreterReceipt.model_validate(payload, strict=True)

    assert restored.interpreter_version == "1.1.0"


def test_task_only_correction_becomes_evaluation_candidate(tmp_path: Path) -> None:
    text = "nah thats not what i meant—diagnose why it failed before trying another patch"
    observation = _observation(1, text)
    interpretation = _interpretation(
        tmp_path,
        text=text,
        quote=text,
        behavior="Diagnose why a fix failed before trying another patch.",
    )
    interpretation = interpretation.model_copy(
        update={
            "signals": (
                interpretation.signals[0].model_copy(
                    update={
                        "signal_kind": FeedbackSignalKind.CORRECTION,
                        "requested_route": ArtifactRoute.PROCEDURE,
                        "durability": SemanticSignalDurability.TASK_ONLY,
                    }
                ),
            )
        }
    )
    _runtime_instance, policy = _runtime(tmp_path)

    detected = detect_feedback(
        observation,
        policy,
        initial_runtime_state(policy),
        mode=FeedbackDetectorMode.CALIBRATED,
        semantic_interpretation=interpretation,
    )

    assert detected.disposition is AutomationDisposition.REVIEW_REQUIRED
    assert detected.signal_kind is FeedbackSignalKind.CORRECTION
    assert "not durable learning" in detected.reasons[0]


def test_semantic_support_must_match_exact_authoritative_text(tmp_path: Path) -> None:
    observation = _observation(1, "Names should describe real things.")
    interpretation = _interpretation(
        tmp_path,
        text=observation.text,
        quote="Names should describe real things.",
        behavior="Use names that describe real things.",
    )
    interpretation = interpretation.model_copy(
        update={
            "signals": (
                interpretation.signals[0].model_copy(
                    update={"support_end": interpretation.signals[0].support_end - 1}
                ),
            )
        }
    )
    _runtime_instance, policy = _runtime(tmp_path)

    with pytest.raises(SemanticInterpretationError, match="exact user text"):
        detect_feedback(
            observation,
            policy,
            initial_runtime_state(policy),
            mode=FeedbackDetectorMode.REVIEW,
            semantic_interpretation=interpretation,
        )


@dataclass
class _SemanticRpc:
    response: str
    calls: list[tuple[str, JsonObject]] = field(default_factory=list)
    notifications: list[JsonObject] = field(default_factory=list)

    def request(self, method: str, params: JsonObject) -> JsonObject:
        self.calls.append((method, params))
        if method == "thread/start":
            root = str(params["cwd"])
            return {
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "cwd": root,
                "instructionSources": [],
                "model": "gpt-5.6-luna",
                "modelProvider": "openai",
                "runtimeWorkspaceRoots": [root],
                "sandbox": {"type": "readOnly", "networkAccess": False},
                "thread": {
                    "id": "semantic-thread",
                    "sessionId": "semantic-session",
                    "source": "appServer",
                    "modelProvider": "openai",
                    "createdAt": 1,
                    "updatedAt": 1,
                    "status": {"type": "idle"},
                    "cwd": root,
                    "cliVersion": "0.146.0",
                    "name": "Semantic feedback",
                    "preview": "",
                    "ephemeral": True,
                    "turns": [],
                },
            }
        if method == "turn/start":
            self.notifications = [
                {
                    "method": "item/completed",
                    "params": {
                        "completedAtMs": 1,
                        "threadId": "semantic-thread",
                        "turnId": "semantic-turn",
                        "item": {
                            "id": "semantic-agent",
                            "type": "agentMessage",
                            "text": self.response,
                        },
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "semantic-thread",
                        "turn": {
                            "id": "semantic-turn",
                            "items": [],
                            "itemsView": "full",
                            "status": "completed",
                        },
                    },
                },
            ]
            return {
                "turn": {
                    "id": "semantic-turn",
                    "items": [],
                    "itemsView": "full",
                    "status": "inProgress",
                }
            }
        raise AssertionError(f"unexpected method: {method}")

    def next_notification(self, *, timeout_seconds: float | None = None) -> JsonObject:
        assert timeout_seconds is not None and timeout_seconds > 0
        return self.notifications.pop(0)


def test_codex_semantic_interpreter_is_ephemeral_schema_bound_and_tool_free(
    tmp_path: Path,
) -> None:
    text = "tbh generic techy names are corny, use names for real things"
    observation = _observation(1, text)
    response = json.dumps(
        {
            "prompt_version": "semantic-feedback-candidates-v3",
            "items": [
                {
                    "observation_id": observation.observation_id,
                    "signals": [
                        {
                            "signal_kind": "preference",
                            "normalized_behavior": (
                                "Use names that represent real domain concepts and avoid "
                                "generic techy names."
                            ),
                            "requested_route": "preference",
                            "affected_artifact_id": None,
                            "supporting_quote": text,
                            "durability": "durable",
                            "clarity": "clear",
                            "scope_hint": "permanent_profile",
                        }
                    ],
                }
            ],
        }
    )
    rpc = _SemanticRpc(response=response)
    executable = tmp_path / "codex"
    executable.write_bytes(b"semantic runtime")
    workspace = tmp_path / "semantic-workspace"
    workspace.mkdir()
    interpreter = CodexSemanticFeedbackInterpreter(
        rpc,
        schemas=CodexDogfoodSchemaSet(),
        runtime=VerifiedCodexRuntime(
            executable=executable,
            version="codex-cli 0.146.0",
            schema_bundle_digest=DIGEST,
        ),
        workspace_root=workspace,
        clock=lambda: NOW,
    )

    result = interpreter.interpret_batch((observation,))
    assert tuple(result) == (observation.observation_id,)
    assert result[observation.observation_id].signals[0].supporting_quote == text
    thread_params = rpc.calls[0][1]
    assert thread_params["ephemeral"] is True
    assert thread_params["dynamicTools"] == []
    assert thread_params["selectedCapabilityRoots"] == []
    assert thread_params["sandbox"] == "read-only"
    turn_params = rpc.calls[1][1]
    assert isinstance(turn_params["outputSchema"], dict)
    developer_instructions = thread_params["developerInstructions"]
    assert isinstance(developer_instructions, str)
    assert (
        "The topic, object, format, technology, or domain requested for the current task"
        in developer_instructions
    )


def test_codex_semantic_interpreter_rejects_tool_use(tmp_path: Path) -> None:
    observation = _observation(1, "I prefer descriptive names")
    rpc = _SemanticRpc(
        response=json.dumps(
            {
                "prompt_version": "semantic-feedback-candidates-v3",
                "items": [{"observation_id": observation.observation_id, "signals": []}],
            }
        )
    )
    executable = tmp_path / "codex"
    executable.write_bytes(b"semantic runtime")
    workspace = tmp_path / "semantic-workspace"
    workspace.mkdir()
    interpreter = CodexSemanticFeedbackInterpreter(
        rpc,
        schemas=CodexDogfoodSchemaSet(),
        runtime=VerifiedCodexRuntime(
            executable=executable,
            version="codex-cli 0.146.0",
            schema_bundle_digest=DIGEST,
        ),
        workspace_root=workspace,
        clock=lambda: NOW,
    )
    original = rpc.request

    def request_with_tool(method: str, params: JsonObject) -> JsonObject:
        result = original(method, params)
        if method == "turn/start":
            rpc.notifications.insert(
                0,
                {
                    "method": "item/completed",
                    "params": {
                        "completedAtMs": 1,
                        "threadId": "semantic-thread",
                        "turnId": "semantic-turn",
                        "item": {
                            "id": "semantic-command",
                            "type": "commandExecution",
                            "command": "Get-ChildItem",
                            "commandActions": [],
                            "cwd": str(tmp_path),
                            "status": "completed",
                            "aggregatedOutput": "",
                            "durationMs": 1,
                            "exitCode": 0,
                            "processId": None,
                        },
                    },
                },
            )
        return result

    rpc.request = request_with_tool  # type: ignore[method-assign]
    with pytest.raises(SemanticInterpreterError, match="disallowed item types"):
        interpreter.interpret_batch((observation,))
