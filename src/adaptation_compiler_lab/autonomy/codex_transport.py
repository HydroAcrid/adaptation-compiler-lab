"""Fresh auth-only Codex contexts for the inferred-habit lane; no API-key provider."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, cast

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodRpc,
    CodexDogfoodSchemaSet,
    codex_dogfood_schemas,
    require_chatgpt_account,
)
from adaptation_compiler_lab.autonomy.analyzer import HabitBatchV1, SchemaBoundHabitSensor
from adaptation_compiler_lab.autonomy.codex_capacity import (
    CodexAnalysisContract,
    remaining_subscription_capacity,
    require_catalog_model,
)
from adaptation_compiler_lab.autonomy.models import HabitHypothesisV1, StyleEpisodeV1
from adaptation_compiler_lab.connectors.codex_app_server import (
    CodexAppServerProcess,
    CodexProtocolError,
)
from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import (
    RuntimeConformanceError,
    load_dogfood_runtime_pins,
    verify_codex_runtime,
)
from adaptation_compiler_lab.instruction_environment.codex_semantic import (
    bind_instruction_relation_output,
    instruction_relation_analyzer_digest,
    instruction_relation_contract,
    instruction_relation_output_schema,
    instruction_relation_prompt,
)
from adaptation_compiler_lab.instruction_environment.semantic import (
    ClauseRelationAnalysisV1,
    InstructionRelationPairV1,
)
from adaptation_compiler_lab.serialization import canonical_digest

# These flags are known in the exact native client. Other clients require their own admission.
DISABLED_CAPABILITIES = (
    "apps",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode",
    "code_mode_host",
    "computer_use",
    "goals",
    "hooks",
    "image_generation",
    "in_app_browser",
    "memories",
    "multi_agent",
    "plugin_sharing",
    "plugins",
    "remote_plugin",
    "shell_snapshot",
    "shell_tool",
    "skill_mcp_dependency_install",
    "skill_search",
    "sleep_tool",
    "tool_suggest",
    "unified_exec",
    "view_image",
    "workspace_dependencies",
)


def analysis_profile() -> str:
    return (
        'forced_login_method = "chatgpt"\ncli_auth_credentials_store = "file"\n'
        'web_search = "disabled"\nproject_doc_max_bytes = 0\n'
        "[analytics]\nenabled = false\n[agents]\nenabled = false\n"
        "[memories]\ngenerate_memories = false\nuse_memories = false\n"
        "[features]\n" + "".join(f"{name} = false\n" for name in DISABLED_CAPABILITIES)
    )


def isolated_environment(home: Path) -> dict[str, str]:
    allowed = (
        "SystemRoot",
        "WINDIR",
        "ComSpec",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    )
    result = {name: os.environ[name] for name in allowed if name in os.environ}
    result.update(
        HOME=str(home),
        USERPROFILE=str(home),
        APPDATA=str(home / "AppData/Roaming"),
        LOCALAPPDATA=str(home / "AppData/Local"),
    )
    return result


@contextmanager
def configured_analysis_session(
    config_path: Path,
) -> Iterator[
    tuple[Any, CodexDogfoodSchemaSet, CodexAnalysisContract, CodexAppServerProcess, Path]
]:
    from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
        _load_config,
        _registration_signer,
    )

    config = _load_config(config_path)
    _registration_signer(config)  # Locked or rebound secure stores stop analysis.
    if config.windows_interop:
        raise ValueError("analysis requires a native platform contract")
    pin = load_dogfood_runtime_pins(config.runtime_pin_path).codex
    runtime = verify_codex_runtime(config.codex_executable, pin)
    contract = CodexAnalysisContract(runtime)
    schemas = codex_dogfood_schemas(pin)
    auth = config.source_codex_home / "auth.json"
    if not auth.is_file() or auth.is_symlink():
        raise ValueError("saved ChatGPT authentication is unavailable")
    root = config.state_root / "autonomy" / "sessions"
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("analysis authentication must stay outside Git")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="sensor-", dir=root) as temporary:
        base = Path(temporary)
        home, workspace = base / "home", base / "workspace"
        home.mkdir(mode=0o700)
        workspace.mkdir(mode=0o700)
        shutil.copyfile(auth, home / "auth.json")
        (home / "auth.json").chmod(0o600)
        (home / "config.toml").write_text(analysis_profile(), encoding="utf-8")
        (home / "config.toml").chmod(0o600)
        with CodexAppServerProcess(
            runtime,
            codex_home=home,
            schemas=schemas,
            experimental_api=True,
            isolated_environment=isolated_environment(home),
        ) as rpc:
            require_chatgpt_account(rpc, schemas=schemas)
            yield config, schemas, contract, rpc, workspace


def read_capacity(rpc: CodexDogfoodRpc, contract: CodexAnalysisContract) -> float | None:
    params: JsonObject = {"excludeResetCreditDetails": True, "supportsLunaReserve": False}
    contract.validate("NullableGetAccountRateLimitsParams.json", params)
    response = rpc.request("account/rateLimits/read", params)
    contract.validate("GetAccountRateLimitsResponse.json", response)
    return remaining_subscription_capacity(response, now=datetime.now(UTC))


def verify_model(
    rpc: CodexDogfoodRpc, contract: CodexAnalysisContract, *, model: str, effort: str
) -> None:
    cursor: str | None = None
    models: list[Any] = []
    seen: set[str] = set()
    for _ in range(10):
        params: JsonObject = {"limit": 100, "includeHidden": True, "cursor": cursor}
        contract.validate("ModelListParams.json", params)
        response = rpc.request("model/list", params)
        contract.validate("ModelListResponse.json", response)
        models.extend(cast(list[Any], response["data"]))
        cursor = cast(str | None, response.get("nextCursor"))
        if cursor is None:
            require_catalog_model({"data": models}, model=model, effort=effort)
            return
        if cursor in seen:
            break
        seen.add(cursor)
    raise ValueError("model catalog pagination did not terminate")


def run_habit_turn(
    rpc: CodexDogfoodRpc,
    schemas: CodexDogfoodSchemaSet,
    *,
    workspace: Path,
    model: str,
    effort: str,
    contract: str,
    prompt: str,
    output_schema: dict[str, object],
    timeout: float = 300,
) -> str:
    if any(workspace.iterdir()):
        raise ValueError("habit sensor workspace is not empty")
    params: JsonObject = {
        "allowProviderModelFallback": False,
        "approvalPolicy": "never",
        "baseInstructions": "",
        "cwd": str(workspace),
        "developerInstructions": contract,
        "dynamicTools": [],
        "environments": [],
        "ephemeral": True,
        "experimentalRawEvents": False,
        "model": model,
        "personality": "none",
        "runtimeWorkspaceRoots": [str(workspace)],
        "sandbox": "read-only",
        "selectedCapabilityRoots": [],
        "serviceTier": "standard",
        "threadSource": "temperAutonomousStyleSensor",
    }
    schemas.validate("thread_start_params", params)
    started = rpc.request("thread/start", params)
    schemas.validate("thread_start_response", started)
    if (
        started.get("model") != model
        or started.get("approvalPolicy") != "never"
        or started.get("instructionSources") != []
        or not isinstance(started.get("sandbox"), dict)
        or cast(dict[str, Any], started["sandbox"]).get("type") != "readOnly"
        or cast(dict[str, Any], started["sandbox"]).get("networkAccess", False) is not False
    ):
        raise ValueError("sensor model, ambient instructions, or sandbox could not be verified")
    thread_id = cast(dict[str, Any], started["thread"]).get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise ValueError("sensor thread is unavailable")
    turn_params: JsonObject = {
        "clientUserMessageId": "temper-sensor-" + str(canonical_digest({"prompt": prompt}))[7:31],
        "cwd": str(workspace),
        "effort": effort,
        "model": model,
        "input": [{"type": "text", "text": prompt, "text_elements": []}],
        "outputSchema": cast(JsonObject, output_schema),
        "threadId": thread_id,
    }
    schemas.validate("turn_start_params", turn_params)
    started_turn = rpc.request("turn/start", turn_params)
    schemas.validate("turn_start_response", started_turn)
    turn_id = cast(dict[str, Any], started_turn["turn"]).get("id")
    messages: list[str] = []
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        try:
            notification = rpc.next_notification(timeout_seconds=min(30, remaining))
        except CodexProtocolError as error:
            if str(error) != "Codex app-server notification timed out":
                raise
            # A quiet interval is not a new model attempt or an overall turn timeout.
            continue
        method = notification.get("method")
        values = notification.get("params")
        if not isinstance(values, dict):
            raise ValueError("sensor notification is malformed")
        if "rerout" in str(method).casefold() or "fromModel" in values or "toModel" in values:
            raise ValueError("semantic model substitution is forbidden")
        if method in {"item/started", "item/completed"}:
            if values.get("threadId") != thread_id or values.get("turnId") != turn_id:
                raise ValueError("sensor item crossed its isolated context")
            item = values.get("item")
            if not isinstance(item, dict) or item.get("type") not in {
                "userMessage",
                "agentMessage",
                "reasoning",
            }:
                raise ValueError("sensor attempted a disallowed tool")
            if method == "item/completed":
                schemas.validate("item_completed", values)
                if item["type"] == "userMessage" and item.get("content") != turn_params["input"]:
                    raise ValueError("sensor input changed")
                if item["type"] == "agentMessage":
                    text = item.get("text")
                    if not isinstance(text, str) or not text:
                        raise ValueError("sensor final message is unavailable")
                    messages.append(text)
        elif method == "turn/completed":
            schemas.validate("turn_completed", values)
            completed = values.get("turn")
            if (
                values.get("threadId") != thread_id
                or not isinstance(completed, dict)
                or completed.get("id") != turn_id
                or completed.get("status") != "completed"
                or len(messages) != 1
            ):
                raise ValueError("sensor lacks exactly one successful result")
            return messages[0]
    raise ValueError("sensor timed out")


def _alias_habit_references(
    prompt: str, output_schema: dict[str, object]
) -> tuple[str, dict[str, object], Callable[[str], str]]:
    """Use short opaque wire references; restore host identities before validation.

    The pinned native decoder fails with long content-addressed enum values.
    Only reference fields change. Conversation text, policy, task identity and
    evidence quotes remain verbatim; aliases never enter the signed host ledger.
    """
    body = json.loads(prompt)
    episodes = {item["episode_id"]: f"e{index}" for index, item in enumerate(body["episodes"])}
    habits = {
        item["habit_id"]: f"h{index}"
        for index, item in enumerate(body["known_habits_for_counterevidence_only"])
    }
    for item in body["episodes"]:
        item["episode_id"] = episodes[item["episode_id"]]
    for item in body["known_habits_for_counterevidence_only"]:
        item["habit_id"] = habits[item["habit_id"]]
    for item in body.get("candidate_styles_to_review", []):
        item["evidence_episode_ids"] = [episodes[key] for key in item["evidence_episode_ids"]]
    schema = deepcopy(output_schema)
    definitions = cast(dict[str, Any], schema["$defs"])
    for name, field, aliases in (
        ("EvidenceQuoteV1", "episode_id", episodes),
        ("ClassifiedEvidenceV1", "episode_id", episodes),
        ("ReviewedEvidenceV1", "episode_id", episodes),
        ("KnownHabitAssessmentV1", "habit_id", habits),
    ):
        if name in definitions:
            reference = definitions[name]["properties"][field]
            if "enum" in reference:
                reference["enum"] = [aliases[key] for key in reference["enum"]]
    reverse = {
        "episode_id": {alias: original for original, alias in episodes.items()},
        "habit_id": {alias: original for original, alias in habits.items()},
    }

    def decode(result: str) -> str:
        value = json.loads(result)

        def restore(node: Any) -> None:
            if isinstance(node, list):
                for child in node:
                    restore(child)
            elif isinstance(node, dict):
                for field, child in tuple(node.items()):
                    if field in reverse:
                        if not isinstance(child, str) or child not in reverse[field]:
                            raise ValueError("sensor invented supporting tasks or evidence quotes")
                        node[field] = reverse[field][child]
                    else:
                        restore(child)

        restore(value)
        return json.dumps(value, ensure_ascii=False)

    return json.dumps(body, ensure_ascii=False), schema, decode


class ConfiguredCodexHabitSensor:
    analysis_sessions = SchemaBoundHabitSensor.analysis_sessions

    def __init__(
        self,
        config_path: Path,
        *,
        on_result: Callable[[str, str], None] | None = None,
        candidate_model: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.on_result = on_result
        if candidate_model is not None and (
            not candidate_model or candidate_model.strip() != candidate_model
        ):
            raise ValueError("developer candidate requires an exact nonempty model ID")
        self.candidate_model = candidate_model

    def remaining_capacity(self) -> float | None:
        try:
            with configured_analysis_session(self.config_path) as (_, _, contract, rpc, _):
                return read_capacity(rpc, contract)
        except (OSError, ValueError, RuntimeConformanceError):
            return None

    def analyze(
        self,
        episodes: Sequence[StyleEpisodeV1],
        *,
        context: str,
        existing_habits: Sequence[HabitHypothesisV1] = (),
    ) -> HabitBatchV1:
        stages = iter(("proposal", "evidence_review"))

        def run(instructions: str, prompt: str, output: dict[str, object]) -> str:
            stage = next(stages)
            wire_prompt, wire_output, decode = _alias_habit_references(prompt, output)
            with configured_analysis_session(self.config_path) as (
                config,
                schemas,
                contract,
                rpc,
                workspace,
            ):
                remaining = read_capacity(rpc, contract)
                if remaining is None or remaining < 20:
                    raise ValueError(
                        "subscription capacity is unknown or below the background threshold"
                    )
                verify_model(
                    rpc,
                    contract,
                    model=self.candidate_model or config.semantic_model,
                    effort=config.semantic_reasoning_effort,
                )
                result = run_habit_turn(
                    rpc,
                    schemas,
                    workspace=workspace,
                    model=self.candidate_model or config.semantic_model,
                    effort=config.semantic_reasoning_effort,
                    contract=instructions,
                    prompt=wire_prompt,
                    output_schema=wire_output,
                )
                result = decode(result)
                if self.on_result is not None:
                    self.on_result(stage, result)
                return result

        return SchemaBoundHabitSensor(run).analyze(
            episodes, context=context, existing_habits=existing_habits
        )


class ConfiguredNativeRelationSensor:
    """One fresh, auth-only, quota-checked context per independent comparison pass."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def compare(
        self, pairs: Sequence[InstructionRelationPairV1]
    ) -> Mapping[str, ClauseRelationAnalysisV1]:
        if not pairs:
            return {}
        prompt = instruction_relation_prompt(pairs)
        if len(prompt.encode("utf-8")) > 65_536:
            raise ValueError("native relation input exceeds its bounded batch")
        with configured_analysis_session(self.config_path) as (
            config,
            schemas,
            contract,
            rpc,
            workspace,
        ):
            remaining = read_capacity(rpc, contract)
            if remaining is None or remaining < 20:
                raise ValueError("native relation analysis is deferred by subscription capacity")
            verify_model(
                rpc, contract, model=config.semantic_model, effort=config.semantic_reasoning_effort
            )
            output = run_habit_turn(
                rpc,
                schemas,
                workspace=workspace,
                model=config.semantic_model,
                effort=config.semantic_reasoning_effort,
                contract=instruction_relation_contract(),
                prompt=prompt,
                output_schema=instruction_relation_output_schema(),
            )
            return bind_instruction_relation_output(
                pairs,
                output,
                interpreter_digest=canonical_digest(
                    {
                        "analyzer": instruction_relation_analyzer_digest(
                            model=config.semantic_model,
                            reasoning_effort=config.semantic_reasoning_effort,
                        ),
                        "output": output,
                        "pin": config.runtime_pin_path.read_bytes().hex(),
                    }
                ),
            )
