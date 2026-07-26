"""Run the four-cell public Claude benchmark repair under a USD $1 hard cap."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from run_claude_development_gate import (
    COMMON_TASK_ENVELOPE,
    EXPECTED_COMPILED_V2_MATERIAL_DIGEST,
    EXPECTED_COMPILED_V2_TEXT_DIGEST,
    EXPECTED_STRONG_TEXT_DIGEST,
    _canonical_bytes,
    _command_audit_digest,
    _comparison_invalid_reasons,
    _counts,
    _create_secret,
    _encrypted_bundle,
    _encrypted_ref,
    _exclusive_write,
    _git,
    _initialize_workspace,
    _leakage_observed,
    _load_api_environment,
    _load_condition_texts,
    _remove_interpreter_artifacts,
    _run,
    _score,
    _successful_audited_aliases,
    _terminal_evidence,
    _visible_fixture_manifest,
)

from adaptation_compiler_lab.benchmark.claude_development import (
    ClaudeDevelopmentRunObservation,
)
from adaptation_compiler_lab.benchmark.claude_repair import (
    ClaudeRepairBlindReport,
    ClaudeRepairCompletionReceipt,
    ClaudeRepairProgressReceipt,
    build_claude_repair_plan,
    load_claude_repair_design,
)
from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.randomization import RandomizationSeed
from adaptation_compiler_lab.connectors.models import TargetRunRequest
from adaptation_compiler_lab.connectors.pins import (
    DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK,
    RuntimePinSet,
    load_runtime_pins,
    sha256_bytes,
    sha256_file,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.claude_code import (
    ClaudeCodeTargetRunner,
    ClaudeRuntimePaths,
    TargetExecutionError,
    serialize_target_trace,
)
from adaptation_compiler_lab.serialization import canonical_digest

BENCHMARK_ID = "claude-haiku-compiler-v2-public-repair"
EXPECTED_EXECUTION = {
    "planned_runs": 4,
    "repetitions_per_condition": 1,
    "max_seconds_per_run": 600,
    "max_turns_per_run": 20,
    "max_usd_per_run": 0.25,
    "max_usd_total": 1.0,
    "retry_allowed": False,
    "command_timeout_seconds": 120,
    "command_cpu_seconds": 30,
    "command_memory_mb": 512,
    "command_file_size_mb": 16,
    "command_process_limit": 256,
    "command_process_limit_scope": "additional_uid_tasks_within_outer_pid_boundary",
    "command_open_files_limit": 64,
}
EXPECTED_VALIDITY = {
    "all_4_records_required": True,
    "trace_conformance_required": True,
    "terminal_success_required": True,
    "condition_leakage_forbidden": True,
    "workspace_and_config_teardown_required": True,
    "quality_scores_are_outcomes_not_validity_requirements": True,
    "test_alias_use_is_instruction_adherence_not_validity": True,
    "proven_policy_denials_are_instruction_adherence_not_instrument_failure": True,
    "every_executed_bash_trace_requires_digest_matched_os_policy_audit": True,
    "structured_preexecution_denials_require_result_id_binding": True,
    "approved_alias_preexecution_denial_invalidates": True,
    "unblocked_out_of_manifest_command_invalidates_and_stops_grid": True,
    "bare_mode_observed_tool_inventory": ["Bash", "Edit", "Read"],
    "visible_fixture_manifest_required": True,
    "generated_alias_bootstrap_match_required": True,
    "unmatched_denied_internal_policy_entries_allowed": True,
    "unmatched_allowed_policy_executions_forbidden": True,
}
EXPECTED_BLINDING = {
    "fresh_randomization_seed_outside_repository": True,
    "fresh_condition_ids_and_run_order": True,
    "condition_mapping_withheld_until_all_kevin_ratings": True,
    "objective_scores_withheld_until_all_kevin_ratings": True,
    "anonymous_outputs_and_diffs_only": True,
}
EXPECTED_BOUNDARIES = {
    "held_out": False,
    "new_versioned_public_tasks": True,
    "prior_v2_9_outputs_and_scores_known": True,
    "condition_materials_unchanged_after_prior_results": True,
    "milestone_6_custody_accessed": False,
    "milestone_6_materials_modified": False,
    "full_paid_milestone_6_pilot_authorized": False,
    "general_thesis_claim_allowed": False,
}


def _write_blind_packet(
    path: Path,
    *,
    design: Any,
    public_plan: Any,
    safe_outputs: dict[str, tuple[str, str]],
) -> None:
    lines = [
        "# Claude Haiku repaired public benchmark blind packet",
        "",
        (
            "This is a four-cell public development comparison, not the frozen Milestone 6 "
            "study. Condition identities, objective scores, run order, token use, and cost remain "
            "withheld until Kevin rates both pairs."
        ),
        "",
        (
            "For each task, choose First, Second, or Tie based on the implementation, instruction "
            "adherence, verification, and fit with Kevin's preferences. Do not infer a condition."
        ),
        "",
    ]
    for task in design.tasks:
        lines.extend((f"## {task.task_id}", "", task.prompt, ""))
        cells = sorted(
            (item for item in public_plan.run_order if item.task_id == task.task_id),
            key=lambda item: item.blind_output_id,
        )
        if len(cells) != 2:
            raise RuntimeError("repaired blind packet pair is incomplete")
        for label, cell in zip(("First", "Second"), cells, strict=True):
            response, diff = safe_outputs[cell.blind_output_id]
            lines.extend(
                (
                    f"### {label} ({cell.blind_output_id})",
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
        lines.extend(("Rating: **[First / Second / Tie]**", "", "Why:", ""))
    _exclusive_write(path, ("\n".join(lines).rstrip() + "\n").encode("utf-8"), mode=0o644)


def _validate_preregistration(
    *,
    preregistration: dict[str, Any],
    repo: Path,
    design: Any,
    runtime_lock_digest: str,
    source_commit: str,
) -> dict[str, tuple[str, ...]]:
    if preregistration.get("schema_version") != "1.0.0":
        raise RuntimeError("Claude repair preregistration schema drifted")
    if preregistration.get("benchmark_id") != BENCHMARK_ID:
        raise RuntimeError("Claude repair benchmark identity drifted")
    if preregistration.get("design_digest") != design.content_digest:
        raise RuntimeError("Claude repair design drifted")
    implementation_commit = preregistration.get("implementation_commit")
    if not isinstance(implementation_commit, str) or len(implementation_commit) != 40:
        raise RuntimeError("Claude repair implementation commit is invalid")
    ancestor = _git(["merge-base", "--is-ancestor", implementation_commit, source_commit], cwd=repo)
    if ancestor.returncode != 0:
        raise RuntimeError("Claude repair implementation commit is not an ancestor")
    if preregistration.get("execution") != EXPECTED_EXECUTION:
        raise RuntimeError("Claude repair execution contract drifted")
    if preregistration.get("validity") != EXPECTED_VALIDITY:
        raise RuntimeError("Claude repair validity policy drifted")
    if preregistration.get("blinding") != EXPECTED_BLINDING:
        raise RuntimeError("Claude repair blinding policy drifted")
    if preregistration.get("boundaries") != EXPECTED_BOUNDARIES:
        raise RuntimeError("Claude repair boundary declaration drifted")
    if preregistration.get("conditions") != [
        BenchmarkCondition.STRONG_STATIC_PROFILE.value,
        BenchmarkCondition.COMPILED_ADAPTATION.value,
    ]:
        raise RuntimeError("Claude repair conditions drifted")
    if preregistration.get("materials") != {
        "compiled_v2": EXPECTED_COMPILED_V2_TEXT_DIGEST,
        "compiled_lineage": EXPECTED_COMPILED_V2_MATERIAL_DIGEST,
        "strong_static_profile": EXPECTED_STRONG_TEXT_DIGEST,
    }:
        raise RuntimeError("Claude repair condition materials changed")
    if preregistration.get("runtime") != {
        "claude_code_version": design.cli_version,
        "model_id": design.model,
        "runtime_lock_digest": runtime_lock_digest,
        "runner_boundary": "instrument-canary-success-v12-plus-outer-policy-shell-v8",
    }:
        raise RuntimeError("Claude repair runtime binding drifted")
    expected_tasks = [
        {
            "task_id": task.task_id,
            "family": task.family.value,
            "fixture_digest": task.fixture_digest,
            "independent_scorer_digest": task.independent_scorer_digest,
        }
        for task in design.tasks
    ]
    if preregistration.get("tasks") != expected_tasks:
        raise RuntimeError("Claude repair task bindings drifted")
    repair_root = repo / "development_benchmark_claude_repair"
    if preregistration.get("conformance_digest") != development_tree_digest(
        repair_root / "conformance"
    ):
        raise RuntimeError("Claude repair conformance assets drifted")
    expected_prior = {
        "v2_9_rating_digest": sha256_file(
            repo / "development_benchmark_claude" / "results" / "kevin-blind-rating-v2.9.json"
        ),
        "v2_9_result_digest": sha256_file(
            repo / "development_benchmark_claude" / "results" / "unblinded-result-v2.9.json"
        ),
        "v2_9_analysis_digest": sha256_file(repo / "CLAUDE_CORRECTED_COMPARISON.md"),
    }
    if preregistration.get("prior_evidence") != expected_prior:
        raise RuntimeError("Claude repair prior-evidence binding drifted")
    raw_manifests = preregistration.get("command_manifests")
    task_ids = {task.task_id for task in design.tasks}
    if not isinstance(raw_manifests, dict) or set(raw_manifests) != task_ids:
        raise RuntimeError("Claude repair command manifests are incomplete")
    manifests: dict[str, tuple[str, ...]] = {}
    for task_id, commands in raw_manifests.items():
        if commands != ["python3 -m unittest -v"]:
            raise RuntimeError("Claude repair command manifest drifted")
        manifests[task_id] = tuple(commands)
    return manifests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--pilot-config-root", type=Path, required=True)
    parser.add_argument("--api-env-file", type=Path, required=True)
    parser.add_argument("--claude-executable", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--socat", type=Path, required=True)
    parser.add_argument("--sandbox-library-path", type=Path, required=True)
    parser.add_argument(
        "--runtime-lock",
        type=Path,
        default=DEFAULT_HAIKU_DEVELOPMENT_RUNTIME_LOCK,
    )
    parser.add_argument("--preregistration", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    pilot_root = arguments.pilot_root.resolve()
    pilot_config_root = arguments.pilot_config_root.resolve()
    preregistration_path = arguments.preregistration.resolve()
    if output_root.exists() or config_root.exists():
        raise RuntimeError("Claude repair roots already exist; refusing to overwrite")
    if not preregistration_path.is_relative_to(repo) or not preregistration_path.is_file():
        raise RuntimeError("Claude repair preregistration must be a repository file")
    source_status = _git(["status", "--porcelain"], cwd=repo)
    if source_status.returncode != 0 or source_status.stdout:
        raise RuntimeError("Claude repair requires a clean repository")
    source_commit_result = _git(["rev-parse", "HEAD"], cwd=repo)
    if source_commit_result.returncode != 0:
        raise RuntimeError("unable to resolve Claude repair source commit")
    source_commit = source_commit_result.stdout.strip()

    preregistration = json.loads(preregistration_path.read_text(encoding="utf-8"))
    design = load_claude_repair_design(
        repo / "development_benchmark_claude_repair",
        frozen_at=datetime.fromisoformat(preregistration["frozen_at"]),
    )
    pins: RuntimePinSet = load_runtime_pins(arguments.runtime_lock)
    runtime_lock_digest = sha256_file(arguments.runtime_lock)
    if (
        pins.claude_code.model_id != design.model
        or pins.claude_code.executable.package_version != design.cli_version
    ):
        raise RuntimeError("Claude repair runtime lock drifted from the design")
    command_manifests = _validate_preregistration(
        preregistration=preregistration,
        repo=repo,
        design=design,
        runtime_lock_digest=runtime_lock_digest,
        source_commit=source_commit,
    )

    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    os.chmod(output_root, 0o700)
    os.chmod(config_root, 0o700)
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
    created_at = datetime.now(UTC)
    private_plan, public_plan = build_claude_repair_plan(
        design=design,
        seed=seed,
        created_at=created_at,
    )
    private_plan_ref = encrypted_store.put(
        _canonical_bytes(private_plan),
        media_type="application/vnd.adaptation-compiler-lab.claude-repair-plan+json",
    )
    _exclusive_write(output_root / "public-plan.json", _canonical_bytes(public_plan), mode=0o644)

    condition_texts = _load_condition_texts(
        repo=repo,
        pilot_root=pilot_root,
        pilot_config_root=pilot_config_root,
    )
    assignment_by_blind = {
        item.blind_condition_id: item.condition for item in private_plan.condition_assignments
    }
    material_by_blind = {
        blind_id: condition_texts[condition] for blind_id, condition in assignment_by_blind.items()
    }
    runner = ClaudeCodeTargetRunner(
        paths=ClaudeRuntimePaths(
            executable=arguments.claude_executable,
            bubblewrap=arguments.bubblewrap,
            socat=arguments.socat,
            sandbox_library_path=arguments.sandbox_library_path,
        ),
        pins=pins,
        environment=_load_api_environment(arguments.api_env_file),
    )
    preregistration_digest = sha256_file(preregistration_path)
    environment_digest = canonical_digest(
        {
            "design_digest": design.content_digest,
            "model": design.model,
            "preregistration_digest": preregistration_digest,
            "runtime_lock_digest": runtime_lock_digest,
            "source_commit": source_commit,
        }
    )
    _exclusive_write(
        output_root / "frozen-input-manifest.json",
        _canonical_bytes(
            {
                "compiled_v2_material_digest": EXPECTED_COMPILED_V2_MATERIAL_DIGEST,
                "conformance_digest": preregistration["conformance_digest"],
                "design_digest": design.content_digest,
                "environment_digest": environment_digest,
                "materials": preregistration["materials"],
                "milestone_6_custody_accessed": False,
                "preregistration_digest": preregistration_digest,
                "runtime_lock_digest": runtime_lock_digest,
                "source_commit": source_commit,
                "tasks": preregistration["tasks"],
            }
        ),
        mode=0o644,
    )

    task_by_id = {task.task_id: task for task in design.tasks}
    repair_root = repo / "development_benchmark_claude_repair"
    task_root_by_id = {
        json.loads((path / "task.json").read_text(encoding="utf-8"))["task_id"]: path
        for path in (repair_root / "tasks").iterdir()
        if path.is_dir()
    }
    if set(task_root_by_id) != set(task_by_id):
        raise RuntimeError("Claude repair task roots do not match the design")

    observations: list[ClaudeDevelopmentRunObservation] = []
    safe_outputs: dict[str, tuple[str, str]] = {}
    total_cost = 0.0
    for cell in private_plan.run_order:
        if total_cost >= EXPECTED_EXECUTION["max_usd_total"]:
            raise RuntimeError("Claude repair total budget was exhausted")
        task = task_by_id[cell.task_id]
        task_root = task_root_by_id[cell.task_id]
        condition_text = material_by_blind[cell.blind_condition_id]
        condition_digest = sha256_bytes(condition_text.encode("utf-8"))
        workspace_path: Path | None = None
        observation_values: dict[str, Any]
        with tempfile.TemporaryDirectory(prefix="acl-claude-repair-workspace-") as temporary:
            workspace = Path(temporary) / "task"
            workspace_path = workspace
            _initialize_workspace(task_root / "fixture", workspace)
            visible_manifest = _visible_fixture_manifest(workspace)
            condition_file = workspace / ".acl-condition.md"
            condition_file.write_text(condition_text, encoding="utf-8")
            condition_file.chmod(0o600)
            request = TargetRunRequest(
                run_id=cell.run_id,
                workspace_root=workspace,
                prompt=COMMON_TASK_ENVELOPE + task.prompt + visible_manifest,
                condition_file=condition_file,
                condition_digest=condition_digest,
                allowed_bash_commands=command_manifests[cell.task_id],
                command_timeout_seconds=EXPECTED_EXECUTION["command_timeout_seconds"],
                command_cpu_seconds=EXPECTED_EXECUTION["command_cpu_seconds"],
                command_memory_mb=EXPECTED_EXECUTION["command_memory_mb"],
                command_file_size_mb=EXPECTED_EXECUTION["command_file_size_mb"],
                command_process_limit=EXPECTED_EXECUTION["command_process_limit"],
                command_open_files_limit=EXPECTED_EXECUTION["command_open_files_limit"],
                max_seconds=EXPECTED_EXECUTION["max_seconds_per_run"],
                max_turns=EXPECTED_EXECUTION["max_turns_per_run"],
                max_usd=EXPECTED_EXECUTION["max_usd_per_run"],
                model_id=design.model,
            )
            trace_conformant = True
            runner_failure_reason: str | None = None
            runner_failure_code: str | None = None
            runner_failure_subject_digest: str | None = None
            try:
                result = runner.run(request)
            except TargetExecutionError as exc:
                if exc.evidence is None:
                    raise
                result = exc.evidence
                trace_conformant = False
                runner_failure_reason = str(exc)
                runner_failure_code = exc.failure_code
                runner_failure_subject_digest = exc.failure_subject_digest
            if condition_file.exists():
                condition_file.unlink()
            _remove_interpreter_artifacts(workspace)
            diff_completed = _git(["diff", "--binary", "HEAD"], cwd=workspace)
            status_completed = _git(["status", "--porcelain"], cwd=workspace)
            if diff_completed.returncode != 0 or status_completed.returncode != 0:
                raise RuntimeError("unable to capture Claude repair changes")
            visible_test = _git(
                ["diff", "--check"],
                cwd=workspace,
            )
            if visible_test.returncode != 0:
                raise RuntimeError("Claude repair patch contains whitespace errors")
            visible_test = _run(
                list(task.visible_test_command),
                cwd=workspace,
                timeout=60,
            )
            _remove_interpreter_artifacts(workspace)
            scorer_value, scorer_output = _score(
                task_root / "independent" / "score.py",
                workspace,
            )
            (
                final_response,
                cost,
                input_tokens,
                cache_creation_input_tokens,
                cache_read_input_tokens,
                output_tokens,
                terminal_reasons,
            ) = _terminal_evidence(result.events)
            total_cost += cost
            if total_cost > EXPECTED_EXECUTION["max_usd_total"]:
                raise RuntimeError("Claude repair total budget exceeded its hard gate")
            leakage = _leakage_observed(
                final_response + "\n" + diff_completed.stdout,
                tuple(condition_texts.values()),
            )
            objective_passed, objective_total = _counts(scorer_value["objective"])
            diagnostic_passed, diagnostic_total = _counts(scorer_value["diagnostic"])
            neutral_passed, neutral_total = _counts(scorer_value["neutral"])
            accepted_aliases = {entry.alias for entry in result.command_audit}
            successful_aliases = _successful_audited_aliases(
                result.events,
                accepted_aliases=accepted_aliases,
            )
            invalid_reasons = _comparison_invalid_reasons(
                terminal_reasons=terminal_reasons,
                runner_failure_reason=runner_failure_reason,
                timed_out=result.timed_out,
                exit_code=result.exit_code,
                config_destroyed=result.config_destroyed,
                condition_leakage_observed=leakage,
            )
            trace_bytes = serialize_target_trace(result.events)
            bundle_ref = encrypted_store.put(
                _encrypted_bundle(
                    events=result.events,
                    stderr=result.stderr,
                    final_response=final_response,
                    diff=diff_completed.stdout,
                    status=status_completed.stdout,
                    visible_test=visible_test,
                    scorer_output=scorer_output,
                ),
                media_type="application/vnd.adaptation-compiler-lab.claude-repair-run+json",
            )
            safe_outputs[cell.blind_output_id] = (
                final_response if not leakage else "[withheld: condition-leakage scan failed]",
                diff_completed.stdout
                if not leakage
                else "[withheld: condition-leakage scan failed]",
            )
            observation_values = {
                "run_id": cell.run_id,
                "task_id": cell.task_id,
                "blind_condition_id": cell.blind_condition_id,
                "blind_output_id": cell.blind_output_id,
                "repetition": 1,
                "condition_digest": condition_digest,
                "trace_digest": sha256_bytes(trace_bytes),
                "diff_digest": sha256_bytes(diff_completed.stdout.encode("utf-8")),
                "final_response_digest": sha256_bytes(final_response.encode("utf-8")),
                "scorer_output_digest": sha256_bytes(scorer_output),
                "command_digest": result.command_digest,
                "command_manifest_digest": result.command_manifest_digest,
                "bash_policy_audit_digest": result.bash_policy_audit_digest,
                "command_audit_digest": _command_audit_digest(result.command_audit),
                "denied_command_audit_digest": _command_audit_digest(result.denied_command_audit),
                "accepted_aliases": tuple(sorted(accepted_aliases)),
                "successful_aliases": tuple(sorted(successful_aliases)),
                "denied_command_attempts": len(result.denied_command_audit),
                "visible_test_returncode": visible_test.returncode,
                "runner_failure_code": runner_failure_code,
                "runner_failure_subject_digest": runner_failure_subject_digest,
                "environment_digest": environment_digest,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "duration_seconds": (result.finished_at - result.started_at).total_seconds(),
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "output_tokens": output_tokens,
                "total_cost_usd": cost,
                "objective_checks_passed": objective_passed,
                "objective_checks_total": objective_total,
                "diagnostic_checks_passed": diagnostic_passed,
                "diagnostic_checks_total": diagnostic_total,
                "neutral_checks_passed": neutral_passed,
                "neutral_checks_total": neutral_total,
                "timed_out": result.timed_out,
                "exit_code": result.exit_code,
                "trace_conformant": trace_conformant,
                "config_destroyed": result.config_destroyed,
                "condition_leakage_observed": leakage,
                "valid": not invalid_reasons,
                "invalid_reason": "; ".join(invalid_reasons) or None,
            }
        workspace_destroyed = workspace_path is not None and not workspace_path.exists()
        if not workspace_destroyed:
            existing_reason = cast(str | None, observation_values["invalid_reason"])
            observation_values["invalid_reason"] = "; ".join(
                item
                for item in (existing_reason, "disposable task workspace was not destroyed")
                if item
            )
            observation_values["valid"] = False
        observation = ClaudeDevelopmentRunObservation(
            **observation_values,
            workspace_destroyed=workspace_destroyed,
        )
        observations.append(observation)
        with (output_root / "progress.jsonl").open("ab") as stream:
            stream.write(
                _canonical_bytes(
                    ClaudeRepairProgressReceipt(
                        blind_condition_id=cell.blind_condition_id,
                        blind_output_id=cell.blind_output_id,
                        bundle_ref=_encrypted_ref(bundle_ref),
                        completed=len(observations),
                        run_id=cell.run_id,
                        task_id=cell.task_id,
                        valid=observation.valid,
                    )
                )
            )
            stream.flush()
            os.fsync(stream.fileno())
        (output_root / "progress.jsonl").chmod(0o600)
        if not observation.valid:
            break

    invalid_observations = [item for item in observations if not item.valid]
    if invalid_observations:
        _exclusive_write(
            output_root / "failure.json",
            _canonical_bytes(
                {
                    "benchmark_id": BENCHMARK_ID,
                    "completed_runs": len(observations),
                    "invalid_runs": [
                        {
                            "blind_condition_id": item.blind_condition_id,
                            "blind_output_id": item.blind_output_id,
                            "invalid_reason": item.invalid_reason,
                            "runner_failure_code": item.runner_failure_code,
                            "runner_failure_subject_digest": item.runner_failure_subject_digest,
                            "run_id": item.run_id,
                            "task_id": item.task_id,
                        }
                        for item in invalid_observations
                    ],
                    "milestone_6_custody_accessed": False,
                    "preregistration_digest": preregistration_digest,
                    "private_plan_ref": _encrypted_ref(private_plan_ref),
                    "raw_retention_deadline": datetime.now(UTC) + timedelta(days=30),
                    "scores_released": False,
                    "source_commit": source_commit,
                    "stopped_early": len(observations) < EXPECTED_EXECUTION["planned_runs"],
                    "status": "instrument_failure_no_comparison",
                    "total_cost_usd": total_cost,
                }
            ),
            mode=0o644,
        )
        raise SystemExit(2)

    blind_report = ClaudeRepairBlindReport(
        design_digest=design.content_digest,
        observations=tuple(sorted(observations, key=lambda item: item.run_id)),
        created_at=datetime.now(UTC),
    )
    blind_report_ref = encrypted_store.put(
        _canonical_bytes(blind_report),
        media_type="application/vnd.adaptation-compiler-lab.claude-repair-report+json",
    )
    _write_blind_packet(
        output_root / "blind-rating-packet.md",
        design=design,
        public_plan=public_plan,
        safe_outputs=safe_outputs,
    )
    completed_at = datetime.now(UTC)
    _exclusive_write(
        output_root / "completion.json",
        _canonical_bytes(
            ClaudeRepairCompletionReceipt(
                blind_packet_digest=sha256_file(output_root / "blind-rating-packet.md"),
                blind_report_digest=blind_report.content_digest,
                blind_report_ref=_encrypted_ref(blind_report_ref),
                completed_at=completed_at,
                private_plan_ref=_encrypted_ref(private_plan_ref),
                raw_retention_deadline=completed_at + timedelta(days=30),
                total_cost_usd=total_cost,
            )
        ),
        mode=0o644,
    )


if __name__ == "__main__":
    main()
