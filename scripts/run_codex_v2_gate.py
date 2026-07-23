"""Run the six-cell Luna v2 development gate without opening Milestone 6 custody."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from run_codex_calibration import (
    COMMON_INSTRUCTIONS,
    EXPECTED_CLI_DIGEST,
    EXPECTED_CONDITION_SET_DIGEST,
    _canonical_bytes,
    _counts,
    _create_secret,
    _encrypted_bundle,
    _exclusive_write,
    _git,
    _initialize_workspace,
    _leakage_observed,
    _ref_value,
    _run,
    _score,
)

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
    CodexDevelopmentRunRequest,
)
from adaptation_compiler_lab.benchmark.codex_v2_gate import (
    CodexV2GateBlindReport,
    CodexV2GateDesign,
    build_codex_v2_gate_plan,
    load_codex_v2_gate_design,
)
from adaptation_compiler_lab.benchmark.materials import (
    FrozenConditionMaterial,
    FrozenConditionSet,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from adaptation_compiler_lab.runners.codex_subscription import (
    CodexExecutionContract,
    CodexSubscriptionRunner,
)
from adaptation_compiler_lab.serialization import canonical_json

_FORBIDDEN_COORDINATOR_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _assert_no_api_key_environment() -> None:
    if any(os.environ.get(name) for name in _FORBIDDEN_COORDINATOR_ENV):
        raise RuntimeError("Codex/OpenAI API-key environment is forbidden for subscription runs")


def _validate_preregistration(
    preregistration: dict[str, Any],
    *,
    design: CodexV2GateDesign,
) -> None:
    if preregistration.get("benchmark_id") != design.design_id:
        raise RuntimeError("v2 preregistration benchmark identity drifted")
    if preregistration.get("condition_set_digest") != EXPECTED_CONDITION_SET_DIGEST:
        raise RuntimeError("v2 preregistration condition-set commitment drifted")
    if preregistration.get("conditions") != [condition.value for condition in design.conditions]:
        raise RuntimeError("v2 preregistration conditions drifted")
    if (
        preregistration.get("held_out") is not False
        or preregistration.get("milestone_6_custody_accessed") is not False
        or preregistration.get("cross_agent_claim_allowed") is not False
    ):
        raise RuntimeError("v2 preregistration crossed its development-only boundary")
    expected_tasks = [
        {
            "family": task.family.value,
            "fixture_digest": task.fixture_digest,
            "independent_scorer_digest": task.independent_scorer_digest,
            "task_id": task.task_id,
        }
        for task in design.tasks
    ]
    observed_tasks = [
        {
            "family": task.get("family"),
            "fixture_digest": task.get("fixture_digest"),
            "independent_scorer_digest": task.get("independent_scorer_digest"),
            "task_id": task.get("task_id"),
        }
        for task in preregistration.get("tasks", [])
        if isinstance(task, dict)
    ]
    if observed_tasks != expected_tasks:
        raise RuntimeError("v2 preregistration task bytes drifted")
    execution = preregistration.get("execution")
    if not isinstance(execution, dict):
        raise RuntimeError("v2 preregistration execution contract is missing")
    expected_execution = {
        "authentication": design.authentication,
        "cli_digest": EXPECTED_CLI_DIGEST,
        "cli_version": design.cli_version,
        "ephemeral_session": True,
        "model": design.model,
        "planned_runs": design.planned_runs,
        "reasoning_effort": design.reasoning_effort,
        "retry_allowed": design.retry_allowed,
        "service_mode": design.service_mode,
        "turns_per_run": 1,
        "timeout_seconds": design.max_seconds,
    }
    if execution != expected_execution:
        raise RuntimeError("v2 preregistration execution contract drifted")


def _write_blind_packet(
    path: Path,
    *,
    design: CodexV2GateDesign,
    run_order: tuple[Any, ...],
    safe_outputs: dict[str, tuple[str, str]],
) -> None:
    lines = [
        "# Codex development v2 — remaining-task blind rating packet",
        "",
        "Condition identities, objective scores, token usage, and run order are withheld.",
        (
            "For each task, rate the first output, the second output, or a tie, "
            "and briefly explain why."
        ),
        "",
    ]
    for task in design.tasks:
        task_cells = sorted(
            (cell for cell in run_order if cell.task_id == task.task_id),
            key=lambda item: item.sequence,
        )
        lines.extend((f"## {task.task_id}", "", "Task:", "", task.prompt, ""))
        for position, cell in zip(("First", "Second"), task_cells, strict=True):
            response, diff = safe_outputs[cell.blind_output_id]
            lines.extend(
                (
                    f"### {position} output — `{cell.blind_output_id}`",
                    "",
                    "Final response:",
                    "",
                    "```text",
                    response.rstrip(),
                    "```",
                    "",
                    "Patch:",
                    "",
                    "```diff",
                    diff.rstrip(),
                    "```",
                    "",
                )
            )
    _exclusive_write(path, ("\n".join(lines).rstrip() + "\n").encode("utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--pilot-config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main() -> None:
    arguments = _build_parser().parse_args()
    _assert_no_api_key_environment()
    repo = arguments.repo.resolve()
    contract = CodexExecutionContract(
        cli_version="codex-cli 0.145.0",
        cli_digest=EXPECTED_CLI_DIGEST,
        model="gpt-5.6-luna",
        reasoning_effort="medium",
        service_mode="standard",
        max_seconds=600,
    )
    runner = CodexSubscriptionRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        contract=contract,
    )
    if arguments.preflight_only:
        print(
            canonical_json(
                {
                    "api_key_environment_present": False,
                    "authentication": runner.verify_chatgpt_authentication(),
                    "model_catalog": runner.verify_model_availability(),
                }
            )
        )
        return

    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    if output_root.exists() or config_root.exists():
        raise RuntimeError("v2 gate roots already exist; refusing to overwrite")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    os.chmod(output_root, 0o700)
    os.chmod(config_root, 0o700)

    source_status = _git(["status", "--porcelain"], cwd=repo)
    if source_status.returncode != 0 or source_status.stdout:
        raise RuntimeError("v2 gate requires a clean pinned repository state")
    source_commit = _git(["rev-parse", "HEAD"], cwd=repo)
    if source_commit.returncode != 0:
        raise RuntimeError("unable to resolve v2 gate repository commit")

    created_at = datetime.now(UTC)
    design = load_codex_v2_gate_design(
        repo / "development_benchmark_v2",
        frozen_at=created_at,
    )
    preregistration_path = repo / "development_benchmark_v2" / "remaining-gate-preregistration.json"
    preregistration_bytes = preregistration_path.read_bytes()
    preregistration = json.loads(preregistration_bytes)
    if not isinstance(preregistration, dict):
        raise RuntimeError("v2 preregistration is not an object")
    _validate_preregistration(preregistration, design=design)

    _create_secret(config_root / "randomization-seed.key")
    _create_secret(config_root / "development-encryption.key")
    seed = RandomizationSeed.from_file(
        config_root / "randomization-seed.key",
        workspace_root=repo,
    )
    encryption_key = RawEncryptionKey.from_file(
        config_root / "development-encryption.key",
        workspace_root=repo,
    )
    encrypted_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=encryption_key,
    )
    private_plan, public_plan = build_codex_v2_gate_plan(
        design=design,
        seed=seed,
        created_at=created_at,
    )
    private_plan_ref = encrypted_store.put(
        _canonical_bytes(private_plan),
        media_type="application/vnd.adaptation-compiler-lab.codex-v2-gate-plan+json",
    )
    _exclusive_write(output_root / "design.json", _canonical_bytes(design))
    _exclusive_write(output_root / "public-plan.json", _canonical_bytes(public_plan))

    freeze_manifest = json.loads(
        (arguments.pilot_root / "exports" / "condition-freeze-manifest-v3.json").read_text(
            encoding="utf-8"
        )
    )
    if freeze_manifest["condition_set_digest"] != EXPECTED_CONDITION_SET_DIGEST:
        raise RuntimeError("frozen condition-set commitment changed")
    source_key = RawEncryptionKey.from_file(
        arguments.pilot_config_root / "raw-evidence.key",
        workspace_root=repo,
    )
    source_store = LocalRawPayloadStore(
        arguments.pilot_root / "raw-evidence",
        encryption_key=source_key,
    )
    condition_bytes = source_store.read(RawPayloadRef(**freeze_manifest["encrypted_ref"]))
    condition_set = FrozenConditionSet.model_validate_json(condition_bytes)
    if condition_set.content_digest != EXPECTED_CONDITION_SET_DIGEST:
        raise RuntimeError("decrypted condition set failed its frozen commitment")
    selected_materials: dict[BenchmarkCondition, FrozenConditionMaterial] = {
        material.condition: material
        for material in condition_set.materials
        if material.condition
        in {
            BenchmarkCondition.STRONG_STATIC_PROFILE,
            BenchmarkCondition.COMPILED_ADAPTATION,
        }
    }
    if set(selected_materials) != set(design.conditions):
        raise RuntimeError("v2 gate conditions are incomplete")
    material_by_blind = {
        assignment.blind_condition_id: selected_materials[assignment.condition]
        for assignment in private_plan.condition_assignments
    }

    if (
        contract.cli_version != design.cli_version
        or contract.model != design.model
        or contract.reasoning_effort != design.reasoning_effort
        or contract.service_mode != design.service_mode
        or contract.max_seconds != design.max_seconds
    ):
        raise RuntimeError("runtime contract drifted from the frozen v2 gate design")
    login_status = runner.verify_chatgpt_authentication()
    model_status = runner.verify_model_availability()
    _exclusive_write(
        output_root / "preflight.json",
        _canonical_bytes(
            {
                "api_key_environment_present": False,
                "authentication": login_status,
                "checked_at": datetime.now(UTC).isoformat(),
                "model_catalog": model_status,
            }
        ),
    )
    _exclusive_write(
        output_root / "frozen-input-manifest.json",
        _canonical_bytes(
            {
                "condition_set_digest": condition_set.content_digest,
                "design_digest": design.content_digest,
                "materials": [
                    {
                        "content_digest": selected_materials[condition].content_digest,
                        "target_tokens": selected_materials[condition].target_tokens,
                        "utf8_bytes": selected_materials[condition].utf8_bytes,
                    }
                    for condition in design.conditions
                ],
                "milestone_6_custody_accessed": False,
                "preregistration_sha256": _digest(preregistration_bytes),
                "source_commit": source_commit.stdout.strip(),
                "tasks": [
                    {
                        "fixture_digest": task.fixture_digest,
                        "independent_scorer_digest": task.independent_scorer_digest,
                        "task_id": task.task_id,
                    }
                    for task in design.tasks
                ],
            }
        ),
    )

    task_by_id = {task.task_id: task for task in design.tasks}
    task_root_by_id = {
        task.task_id: repo / "development_benchmark_v2" / "tasks" / task.family.value
        for task in design.tasks
    }
    observations: list[CodexDevelopmentRunObservation] = []
    safe_outputs: dict[str, tuple[str, str]] = {}
    for cell in private_plan.run_order:
        task = task_by_id[cell.task_id]
        task_root = task_root_by_id[cell.task_id]
        material = material_by_blind[cell.blind_condition_id]
        workspace_path: Path | None = None
        invalid_reasons: list[str]
        with tempfile.TemporaryDirectory(prefix="acl-codex-v2-gate-workspace-") as temporary:
            workspace = Path(temporary) / "task"
            workspace_path = workspace
            _initialize_workspace(task_root / "fixture", workspace)
            request = CodexDevelopmentRunRequest(
                run_id=cell.run_id,
                blind_condition_id=cell.blind_condition_id,
                blind_output_id=cell.blind_output_id,
                task=task,
                condition_text=material.text,
                condition_digest=material.content_digest,
                common_instructions=COMMON_INSTRUCTIONS,
            )
            result = runner.run(request, workspace=workspace)
            diff_completed = _git(["diff", "--binary", "HEAD"], cwd=workspace)
            status_completed = _git(["status", "--porcelain"], cwd=workspace)
            if diff_completed.returncode != 0 or status_completed.returncode != 0:
                raise RuntimeError("unable to capture v2 gate workspace changes")
            visible_test = _run(list(task.visible_test_command), cwd=workspace, timeout=60)
            scorer_value, scorer_output = _score(
                task_root / "independent" / "score.py",
                workspace,
            )
            leakage = _leakage_observed(
                result.final_response + "\n" + diff_completed.stdout,
                condition_set,
            )
            objective_passed, objective_total = _counts(scorer_value["objective"])
            diagnostic_passed, diagnostic_total = _counts(scorer_value["diagnostic"])
            neutral_passed, neutral_total = _counts(scorer_value["neutral"])
            invalid_reasons = [
                reason
                for reason, observed in (
                    ("Codex trace was nonconformant", not result.trace_conformant),
                    ("ephemeral configuration was not destroyed", not result.config_destroyed),
                    ("Codex session files persisted", result.session_files_persisted),
                    ("API-key environment was observed", result.api_key_environment_present),
                    (
                        "forbidden ambient surface appeared in the trace",
                        result.forbidden_ambient_surface_observed,
                    ),
                    ("requested model was rerouted", result.model_reroute_observed),
                    ("condition material leaked into visible output", leakage),
                )
                if observed
            ]
            bundle_ref = encrypted_store.put(
                _encrypted_bundle(
                    result=result,
                    diff=diff_completed.stdout,
                    status=status_completed.stdout,
                    visible_test=visible_test,
                    scorer_output=scorer_output,
                ),
                media_type="application/vnd.adaptation-compiler-lab.codex-v2-gate-run+json",
            )
            safe_outputs[cell.blind_output_id] = (
                result.final_response
                if not leakage
                else "[withheld: condition-leakage scan failed]",
                diff_completed.stdout
                if not leakage
                else "[withheld: condition-leakage scan failed]",
            )
        workspace_destroyed = workspace_path is not None and not workspace_path.exists()
        if not workspace_destroyed:
            invalid_reasons.append("task workspace was not destroyed")
        observation = CodexDevelopmentRunObservation(
            blind_condition_id=cell.blind_condition_id,
            blind_output_id=cell.blind_output_id,
            cached_input_tokens=result.cached_input_tokens,
            command_digest=result.command_digest,
            condition_digest=material.content_digest,
            config_destroyed=result.config_destroyed,
            diagnostic_checks_passed=diagnostic_passed,
            diagnostic_checks_total=diagnostic_total,
            diff_digest=_digest(diff_completed.stdout.encode()),
            duration_seconds=result.duration_seconds,
            environment_digest=result.environment_digest,
            exit_code=result.exit_code,
            final_response_digest=_digest(result.final_response.encode()),
            finished_at=result.finished_at,
            forbidden_ambient_surface_observed=result.forbidden_ambient_surface_observed,
            input_tokens=result.input_tokens,
            invalid_reason="; ".join(invalid_reasons) or None,
            neutral_checks_passed=neutral_passed,
            neutral_checks_total=neutral_total,
            objective_checks_passed=objective_passed,
            objective_checks_total=objective_total,
            output_tokens=result.output_tokens,
            reasoning_output_tokens=result.reasoning_output_tokens,
            run_id=cell.run_id,
            scorer_output_digest=_digest(scorer_output),
            started_at=result.started_at,
            task_id=cell.task_id,
            timed_out=result.timed_out,
            trace_conformant=result.trace_conformant,
            trace_digest=_digest(result.trace_bytes),
            valid=not invalid_reasons,
            workspace_destroyed=workspace_destroyed,
        )
        observations.append(observation)
        with (output_root / "progress.jsonl").open("ab") as stream:
            stream.write(
                _canonical_bytes(
                    {
                        "blind_condition_id": cell.blind_condition_id,
                        "blind_output_id": cell.blind_output_id,
                        "bundle_ref": _ref_value(bundle_ref),
                        "completed": len(observations),
                        "run_id": cell.run_id,
                        "task_id": cell.task_id,
                        "valid": observation.valid,
                    }
                )
            )
            stream.flush()
            os.fsync(stream.fileno())
        (output_root / "progress.jsonl").chmod(0o600)

    blind_report = CodexV2GateBlindReport(
        design_digest=design.content_digest,
        observations=tuple(sorted(observations, key=lambda item: item.run_id)),
        created_at=datetime.now(UTC),
    )
    _exclusive_write(output_root / "blind-report.json", _canonical_bytes(blind_report))
    _write_blind_packet(
        output_root / "blind-rating-packet.md",
        design=design,
        run_order=public_plan.run_order,
        safe_outputs=safe_outputs,
    )
    _exclusive_write(
        output_root / "blind-summary.json",
        _canonical_bytes(
            {
                "condition_mapping_withheld": True,
                "milestone_6_custody_accessed": False,
                "scores_withheld_from_preference_scorer": True,
                "results": [
                    {
                        "blind_condition_id": item.blind_condition_id,
                        "diagnostic": [
                            item.diagnostic_checks_passed,
                            item.diagnostic_checks_total,
                        ],
                        "neutral": [item.neutral_checks_passed, item.neutral_checks_total],
                        "objective": [
                            item.objective_checks_passed,
                            item.objective_checks_total,
                        ],
                        "task_id": item.task_id,
                        "valid": item.valid,
                    }
                    for item in observations
                ],
            }
        ),
    )
    _exclusive_write(
        output_root / "completion.json",
        _canonical_bytes(
            {
                "blind_report_digest": blind_report.content_digest,
                "completed_at": datetime.now(UTC).isoformat(),
                "condition_set_digest": condition_set.content_digest,
                "milestone_6_custody_accessed": False,
                "private_plan_ref": _ref_value(private_plan_ref),
                "runs": len(observations),
                "token_usage": {
                    "cached_input_tokens": sum(item.cached_input_tokens for item in observations),
                    "input_tokens": sum(item.input_tokens for item in observations),
                    "output_tokens": sum(item.output_tokens for item in observations),
                    "reasoning_output_tokens": sum(
                        item.reasoning_output_tokens for item in observations
                    ),
                },
            }
        ),
    )


if __name__ == "__main__":
    main()
