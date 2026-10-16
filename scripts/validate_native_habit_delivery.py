"""Exercise native style delivery in disposable homes, never the owner's profile.

This developer probe records encrypted observations. It does not issue calibration,
enable personalization, observe real conversations, or replace an installed app.
The fixture habit tests publication/consumption, not autonomous inference or usefulness.
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any
from unittest.mock import patch

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    codex_dogfood_schemas,
    require_chatgpt_account,
)
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _load_config,
    _registration_signer,
    _runtime_secrets,
)
from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, safe_analysis_failure
from adaptation_compiler_lab.autonomy.calibration import (
    NATIVE_CHECKS,
    native_binding,
    verify_native_observations,
)
from adaptation_compiler_lab.autonomy.codex_capacity import CodexAnalysisContract
from adaptation_compiler_lab.autonomy.codex_transport import (
    ConfiguredNativeRelationSensor,
    analysis_profile,
    isolated_environment,
    read_capacity,
    verify_model,
)
from adaptation_compiler_lab.autonomy.models import (
    HabitHypothesisV1,
    HabitState,
    StyleCategory,
    TaskClass,
)
from adaptation_compiler_lab.autonomy.native_policy import NativeStylePolicy
from adaptation_compiler_lab.autonomy.publisher import END, START, compile_profile, managed_region
from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.autonomy.styles import StyleKey, style_contract
from adaptation_compiler_lab.connectors.codex_app_server import (
    CodexAppServerProcess,
    CodexProtocolError,
)
from adaptation_compiler_lab.connectors.pins import (
    load_dogfood_runtime_pins,
    sha256_file,
    verify_codex_runtime,
)
from adaptation_compiler_lab.instruction_environment.codex_semantic import (
    instruction_relation_analyzer_digest,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore


def native_turn(
    rpc: Any,
    schemas: Any,
    contract: Any,
    *,
    home: Path,
    workspace: Path,
    model: str,
    effort: str,
    prompt: str,
    timeout: float = 180,
) -> dict[str, Any]:
    capacity = read_capacity(rpc, contract)
    if capacity is None or capacity < 20:
        raise ValueError("subscription capacity is unknown or below the background threshold")
    verify_model(rpc, contract, model=model, effort=effort)
    params = {
        "allowProviderModelFallback": False,
        "approvalPolicy": "never",
        "cwd": str(workspace),
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
        "threadSource": "temperNativeDeliveryValidation",
    }
    schemas.validate("thread_start_params", params)
    created = rpc.request("thread/start", params)
    schemas.validate("thread_start_response", created)
    sandbox = created.get("sandbox")
    sources = created.get("instructionSources")
    if (
        created.get("model") != model
        or created.get("approvalPolicy") != "never"
        or not isinstance(sandbox, dict)
        or sandbox.get("type") != "readOnly"
        or sandbox.get("networkAccess", False) is not False
        or not isinstance(sources, list)
        or {Path(source).resolve() for source in sources} != {(home / "AGENTS.md").resolve()}
    ):
        raise ValueError("native fixture instructions, model or sandbox could not be verified")
    thread_id = created["thread"]["id"]
    turn_params = {
        "threadId": thread_id,
        "cwd": str(workspace),
        "model": model,
        "effort": effort,
        "input": [{"type": "text", "text": prompt, "text_elements": []}],
    }
    schemas.validate("turn_start_params", turn_params)
    started = rpc.request("turn/start", turn_params)
    schemas.validate("turn_start_response", started)
    turn_id = started["turn"]["id"]
    messages = []
    input_seen = False
    deadline = monotonic() + timeout
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ValueError("sensor timed out")
        try:
            notification = rpc.next_notification(timeout_seconds=min(30, remaining))
        except CodexProtocolError as error:
            if str(error) != "Codex app-server notification timed out":
                raise
            continue
        method, values = notification.get("method"), notification.get("params")
        if not isinstance(values, dict):
            raise ValueError("sensor notification is malformed")
        if "rerout" in str(method).casefold() or "fromModel" in values or "toModel" in values:
            raise ValueError("semantic model substitution is forbidden")
        if method in {"item/started", "item/completed"}:
            item = values.get("item")
            if (
                values.get("threadId") != thread_id
                or values.get("turnId") != turn_id
                or not isinstance(item, dict)
                or item.get("type") not in {"userMessage", "agentMessage", "reasoning"}
            ):
                raise ValueError("sensor attempted a disallowed tool")
            if method == "item/completed":
                schemas.validate("item_completed", values)
                if item["type"] == "userMessage":
                    if item.get("content") != turn_params["input"]:
                        raise ValueError("sensor input changed")
                    input_seen = True
                if item["type"] == "agentMessage":
                    if not isinstance(item.get("text"), str) or not item["text"]:
                        raise ValueError("sensor final message is unavailable")
                    messages.append(item["text"])
        elif method == "turn/completed":
            schemas.validate("turn_completed", values)
            completed = values.get("turn")
            if (
                values.get("threadId") != thread_id
                or not isinstance(completed, dict)
                or completed.get("id") != turn_id
                or completed.get("status") != "completed"
                or not input_seen
                or len(messages) != 1
            ):
                raise ValueError("sensor lacks exactly one successful result")
            return {
                "native_turn_completed": True,
                "thread_id": thread_id,
                "workspace": str(workspace),
                "response": messages[0],
                "instruction_sources": sources,
            }


def validate(config_path: Path) -> dict[str, Any]:
    config = _load_config(config_path)
    if config.windows_interop:
        raise ValueError("native delivery validation requires the native platform")
    pin = load_dogfood_runtime_pins(config.runtime_pin_path).codex
    runtime = verify_codex_runtime(config.codex_executable, pin)
    schemas = codex_dogfood_schemas(pin)
    contract = CodexAnalysisContract(runtime)
    now = datetime.now(UTC)
    run_name = "native-delivery-" + now.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)
    root = config.state_root / "autonomy/validation" / run_name
    store = AutonomyStore(
        root / "events.sqlite3",
        signer=_registration_signer(config),
        raw_store=LocalRawPayloadStore(
            root / "raw",
            encryption_key=_runtime_secrets(config).raw_encryption_key(
                workspace_root=config.repository_root
            ),
        ),
    )
    binding = {
        "model": config.semantic_model,
        "effort": config.semantic_reasoning_effort,
        "runtime_pin_digest": sha256_file(config.runtime_pin_path),
    }
    store.append(
        "native-run-binding",
        "native_delivery_binding",
        {
            "producer_digest": sha256_file(Path(__file__)),
            "native_binding": native_binding(),
            "runtime": binding,
            "started_at": now.isoformat(),
            "fixture_only": True,
        },
        at=now,
    )
    print(json.dumps({"native_validation_started": run_name, "fixture_only": True}), flush=True)
    checks: dict[str, Any] = {}

    def save(payload: bytes) -> dict[str, Any]:
        return asdict(store.save_raw(payload))

    def save_file(payload: bytes) -> dict[str, Any]:
        # Content-addressed publisher backups already use text/markdown. The
        # same bytes must keep that media type when referenced by the probe.
        return asdict(store.save_raw(payload, media_type="text/markdown"))

    # All grants, habits, instruction files and fault injection below are fictional
    # test state. The owner's real autonomy store and source home are never targets.
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=root) as temporary:
        # Windows packaged-app virtualization can give this folder an AppData
        # alias. The compiler resolves roots; the native client must receive the
        # same workspace identity rather than a different spelling of that path.
        base = Path(temporary).resolve()
        home, project, other = base / "home", base / "work-a", base / "work-b"
        for path in (home, project, other):
            path.mkdir(mode=0o700)
        auth = config.source_codex_home / "auth.json"
        if not auth.is_file() or auth.is_symlink():
            raise ValueError("saved ChatGPT authentication is unavailable")
        shutil.copyfile(auth, home / "auth.json")
        (home / "auth.json").chmod(0o600)
        (home / "config.toml").write_text(
            analysis_profile().replace(
                "project_doc_max_bytes = 0", "project_doc_max_bytes = 32768"
            ),
            encoding="utf-8",
        )
        path = home / "AGENTS.md"
        path.write_text(
            "# Fictional delivery control\nWhen asked for the native-delivery-check, "
            "return its marker value only if the Temper workspace and task scope match "
            "your current workspace and task. Otherwise reply exactly No Temper profile applies.\n",
            encoding="utf-8",
        )
        service = AutonomyApplicationService(
            store=store,
            projects={"fixture-project": project},
            codex_home=home,
        )
        preview = service.preview_grant(
            ("fixture-project",),
            (StyleCategory.PRESENTATION_STYLE,),
        )
        service.confirm_grant(
            preview["preview_token"],
            confirmed=True,
            idempotency_key="fixture-consent",
        )
        grant = service.grant()
        assert grant is not None
        category, task, behavior = style_contract(StyleKey.NUMBERED_STEPS)
        habit = HabitHypothesisV1(
            habit_id="fictional-delivery-habit",
            behavior=behavior,
            style_key=StyleKey.NUMBERED_STEPS,
            category=StyleCategory(category),
            project_id="fixture-project",
            task_class=TaskClass(task),
            origin="inferred",
            support_episode_ids=("fictional-a", "fictional-b", "fictional-c"),
            support_dates=("2026-10-10", "2026-10-11"),
            state=HabitState.TRIAL,
            first_seen_at=now,
            last_seen_at=now,
            trial_started_at=now,
            trial_expires_at=now + timedelta(days=14),
            evaluation_version=EVALUATION_VERSION,
        )
        profile, ids = compile_profile((habit,), service.projects)
        token = "native-delivery-" + secrets.token_hex(16)
        # Marker is measurement instrumentation, not a learned preference.
        profile += "\nnative-delivery-check: " + token + "\n"
        confirmation = service.store.latest("grant_confirmation")
        assert confirmation is not None
        service.publisher.publish(
            grant,
            profile,
            ids,
            at=now,
            initial_digest=confirmation["native_before_digest"],
        )
        published = path.read_bytes()
        with CodexAppServerProcess(
            runtime,
            codex_home=home,
            schemas=schemas,
            experimental_api=True,
            isolated_environment=isolated_environment(home),
        ) as rpc:
            require_chatgpt_account(rpc, schemas=schemas)
            prompts = (
                (
                    "instruction_loading",
                    project,
                    "For a presentation task here, what is the native-delivery-check "
                    "in your loaded instructions? "
                    "Reply only its value.",
                ),
                (
                    "applicable_behavior",
                    project,
                    "Explain how to stop and restart a fictional queue worker safely "
                    "in exactly two steps.",
                ),
                (
                    "unrelated_project",
                    other,
                    "For a presentation task here, what is the native-delivery-check "
                    "in your loaded instructions? "
                    "Reply only its value.",
                ),
                (
                    "current_request_override",
                    project,
                    "For this answer only, ignore the delivery-check reply convention "
                    "and reply exactly ",
                ),
            )
            requested = "request-override-" + secrets.token_hex(16)
            for name, workspace, prompt in prompts:
                row = native_turn(
                    rpc,
                    schemas,
                    contract,
                    home=home,
                    workspace=workspace,
                    model=config.semantic_model,
                    effort=config.semantic_reasoning_effort,
                    prompt=prompt + requested if name == "current_request_override" else prompt,
                )
                if path.read_bytes() != published:
                    raise AutonomyIntegrityError("fixture instructions changed during native turn")
                checks[name] = {**row, "runtime": binding}
                if name in {"instruction_loading", "current_request_override"}:
                    checks[name]["expected_token"] = (
                        token if name == "instruction_loading" else requested
                    )
                if name == "applicable_behavior":
                    checks[name]["style_key"] = "numbered_steps"
                store.append(
                    name,
                    "native_turn",
                    {"raw_ref": save(json.dumps(checks[name]).encode())},
                    at=now,
                )
                print(
                    json.dumps({"native_check_completed": name, "personal_capture": False}),
                    flush=True,
                )

        policy = NativeStylePolicy(
            projects=service.projects,
            codex_home=home,
            cli_version=pin.executable.package_version,
            store=store,
            analyzer_digest=instruction_relation_analyzer_digest(
                model=config.semantic_model,
                reasoning_effort=config.semantic_reasoning_effort,
            ),
        )
        (project / "AGENTS.md").write_text(
            "Sequential instructions must be a single prose paragraph. Never number their steps.\n",
            encoding="utf-8",
        )
        decision = policy.analyze(habit, ConfiguredNativeRelationSensor(config_path))
        checks["native_policy_conflict"] = {
            "state": decision["state"],
            "blocked": policy.blocked(habit),
        }

        interrupted: list[bytes] = []
        append = store.append

        def fail_publication(key: str, kind: str, payload: Any, *, at: datetime) -> bool:
            if kind == "publication":
                interrupted.append(path.read_bytes())
                raise RuntimeError("fictional post-replacement persistence failure")
            return append(key, kind, payload, at=at)

        before = path.read_bytes()
        with patch.object(store, "append", fail_publication):
            try:
                service.publisher.publish(grant, profile + "\n", ids, at=now)
            except RuntimeError as error:
                if str(error) != "fictional post-replacement persistence failure":
                    raise
        assert len(interrupted) == 1
        checks["publication_rollback"] = {
            "interrupted": True,
            "before_ref": save_file(before),
            "interrupted_ref": save_file(interrupted[0]),
            "after_ref": save_file(path.read_bytes()),
        }
        before = path.read_bytes()
        service.revoke_grant(key="fictional-revocation")
        checks["revocation"] = {
            "grant_enabled": service.grant() is not None,
            "profile": ""
            if (not service.status()["published"] and managed_region(path.read_bytes()) is None)
            else "managed-profile-remains",
            "before_ref": save_file(before),
            "after_ref": save_file(path.read_bytes()),
        }
        preview = service.preview_grant(("fixture-project",), (StyleCategory.PRESENTATION_STYLE,))
        service.confirm_grant(
            preview["preview_token"],
            confirmed=True,
            idempotency_key="fictional-owner-edit-consent",
        )
        new_grant = service.grant()
        assert new_grant is not None
        service.publisher.publish(new_grant, profile, ids, at=now)
        path.write_bytes(path.read_bytes().replace(END.encode(), b"Owner edit.\n" + END.encode()))
        before = path.read_bytes()
        blocked = False
        try:
            service.publisher.publish(new_grant, profile + "\n", ids, at=now)
        except AutonomyIntegrityError:
            blocked = True
        checks["owner_edit_pause"] = {
            "blocked": blocked,
            "before_ref": save_file(before),
            "after_ref": save_file(path.read_bytes()),
        }
        assert START.encode() in before

    observations = {
        "protocol": "native-calibration-observations-v1",
        "native_binding": native_binding(),
        "runtime": binding,
        "checks": checks,
    }
    passed = verify_native_observations(observations, store, binding)
    reference = save(json.dumps(observations).encode())
    store.append(
        "native-delivery-validation",
        "native_delivery_validation",
        {
            "native_evidence_ref": reference,
            "native_binding": native_binding(),
            "runtime": binding,
            "producer_digest": sha256_file(Path(__file__)),
            "passed": passed,
            "recorded_at": now.isoformat(),
            "raw_retention_days": 30,
        },
        at=now,
    )
    return {
        "passed": passed,
        "run_name": run_name,
        "checks_recorded": sorted(checks),
        "expected_checks": sorted(NATIVE_CHECKS),
        "temporary_auth_and_state_removed": True,
        "personal_capture": False,
        "personal_runtime_changed": False,
        "calibration_issued": False,
        "automatic_serving_enabled": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-now", action="store_true", required=True)
    args = parser.parse_args()
    try:
        result = validate(args.config)
        print(json.dumps(result), flush=True)
        raise SystemExit(0 if result["passed"] else 1)
    except Exception as error:
        print(
            json.dumps(
                {
                    "passed": False,
                    "error_type": type(error).__name__,
                    **safe_analysis_failure(error),
                    "personal_runtime_changed": False,
                }
            ),
            flush=True,
        )
        raise SystemExit(1) from None
