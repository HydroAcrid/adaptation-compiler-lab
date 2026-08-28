from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import CodexDogfoodSchemaSet
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import VerifiedCodexRuntime
from adaptation_compiler_lab.domain import ArtifactRef
from adaptation_compiler_lab.instruction_environment import CodexInstructionSourceAdapter
from adaptation_compiler_lab.instruction_environment.codex_semantic import (
    CodexInstructionRelationAnalyzer,
    CodexInstructionSemanticAnalyzer,
    InstructionSemanticTransportError,
)
from adaptation_compiler_lab.instruction_environment.models import (
    NativeInstructionClauseV1,
    NativeInstructionKind,
    NativeNormStrength,
)
from adaptation_compiler_lab.instruction_environment.semantic import (
    InstructionRelationPairV1,
)
from adaptation_compiler_lab.runtime.models import RuntimeClause, RuntimeClauseRole

DIGEST = "sha256:" + "a" * 64


@dataclass
class _SemanticRpc:
    response: str
    calls: list[tuple[str, JsonObject]] = field(default_factory=list)
    notifications: list[JsonObject] = field(default_factory=list)
    item_type: str = "agentMessage"

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
                    "id": "instruction-thread",
                    "sessionId": "instruction-session",
                    "source": "appServer",
                    "modelProvider": "openai",
                    "createdAt": 1,
                    "updatedAt": 1,
                    "status": {"type": "idle"},
                    "cwd": root,
                    "cliVersion": "0.150.0-alpha.8",
                    "name": "Instruction semantics",
                    "preview": "",
                    "ephemeral": True,
                    "turns": [],
                },
            }
        if method == "turn/start":
            item: JsonObject = {
                "id": "instruction-item",
                "type": self.item_type,
            }
            if self.item_type == "agentMessage":
                item["text"] = self.response
            elif self.item_type == "commandExecution":
                item.update(
                    {
                        "command": "echo forbidden",
                        "commandActions": [],
                        "cwd": str(params["cwd"]),
                        "status": "completed",
                    }
                )
            self.notifications = [
                {
                    "method": "item/completed",
                    "params": {
                        "completedAtMs": 1,
                        "threadId": "instruction-thread",
                        "turnId": "instruction-turn",
                        "item": item,
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "instruction-thread",
                        "turn": {
                            "id": "instruction-turn",
                            "items": [],
                            "itemsView": "full",
                            "status": "completed",
                        },
                    },
                },
            ]
            return {
                "turn": {
                    "id": "instruction-turn",
                    "items": [],
                    "itemsView": "full",
                    "status": "inProgress",
                }
            }
        raise AssertionError(f"unexpected method: {method}")

    def next_notification(self, *, timeout_seconds: float | None = None) -> JsonObject:
        assert timeout_seconds is not None and timeout_seconds > 0
        return self.notifications.pop(0)


def _analyzer(tmp_path: Path, rpc: _SemanticRpc) -> CodexInstructionSemanticAnalyzer:
    executable = tmp_path / "codex"
    executable.write_bytes(b"verified semantic runtime")
    workspace = tmp_path / "empty-workspace"
    workspace.mkdir()
    return CodexInstructionSemanticAnalyzer(
        rpc,
        schemas=CodexDogfoodSchemaSet(),
        runtime=VerifiedCodexRuntime(
            executable=executable,
            version="codex-cli 0.150.0-alpha.8",
            schema_bundle_digest=DIGEST,
        ),
        workspace_root=workspace,
    )


def _clause(tmp_path: Path) -> NativeInstructionClauseV1:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(
        "Always run the focused test before reporting success.\n", encoding="utf-8"
    )
    return (
        CodexInstructionSourceAdapter()
        .discover(project_id="temper", project_root=project)[0]
        .clauses[0]
    )


def test_luna_clause_classifier_is_ephemeral_schema_bound_and_tool_free(tmp_path: Path) -> None:
    clause = _clause(tmp_path)
    rpc = _SemanticRpc(
        response=json.dumps(
            {
                "prompt_version": "native-instruction-semantics-v1",
                "items": [
                    {
                        "clause_index": 0,
                        "kind": "norm",
                        "norm_strength": "invariant",
                        "polarity": "positive",
                        "explicit_exception": False,
                        "scope_labels": list(clause.scope_labels),
                        "confidence": 0.98,
                    }
                ],
            }
        )
    )

    result = _analyzer(tmp_path, rpc).analyze((clause,))[clause.clause_id]

    assert result.kind is NativeInstructionKind.NORM
    assert result.norm_strength is NativeNormStrength.INVARIANT
    thread_params = rpc.calls[0][1]
    assert thread_params["ephemeral"] is True
    assert thread_params["dynamicTools"] == []
    assert thread_params["selectedCapabilityRoots"] == []
    assert thread_params["sandbox"] == "read-only"
    assert thread_params["runtimeWorkspaceRoots"] == [thread_params["cwd"]]
    assert isinstance(rpc.calls[1][1]["outputSchema"], dict)


def test_luna_clause_classifier_rejects_tool_items(tmp_path: Path) -> None:
    clause = _clause(tmp_path)
    rpc = _SemanticRpc(response="{}", item_type="commandExecution")

    with pytest.raises(InstructionSemanticTransportError, match="disallowed"):
        _analyzer(tmp_path, rpc).analyze((clause,))


def test_luna_relation_sensor_compares_exact_pairs_without_tools(tmp_path: Path) -> None:
    clause = _clause(tmp_path)
    pair = InstructionRelationPairV1.bind(
        RuntimeClause(
            text="Verify the relevant test before claiming completion.",
            roles=(RuntimeClauseRole.ACTIONABLE_BEHAVIOR,),
            source_artifact_refs=(
                ArtifactRef(
                    record_id="artifact-one",
                    record_version="1.0.0",
                    content_digest=DIGEST,
                ),
            ),
        ),
        clause,
    )
    rpc = _SemanticRpc(
        response=json.dumps(
            {
                "prompt_version": "native-instruction-semantics-v1",
                "items": [
                    {
                        "pair_index": 0,
                        "relation": "semantic_equivalent",
                        "confidence": 0.94,
                    }
                ],
            }
        )
    )
    executable = tmp_path / "relation-codex"
    executable.write_bytes(b"verified relation runtime")
    workspace = tmp_path / "relation-workspace"
    workspace.mkdir()
    analyzer = CodexInstructionRelationAnalyzer(
        rpc,
        schemas=CodexDogfoodSchemaSet(),
        runtime=VerifiedCodexRuntime(
            executable=executable,
            version="codex-cli 0.150.0-alpha.8",
            schema_bundle_digest=DIGEST,
        ),
        workspace_root=workspace,
    )

    result = analyzer.compare((pair,))[pair.pair_id]

    assert result.relation.value == "semantic_equivalent"
    assert rpc.calls[0][1]["dynamicTools"] == []
    assert rpc.calls[0][1]["selectedCapabilityRoots"] == []
