"""Run the frozen one-session task-channel material canary."""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
    CodexDevelopmentRunRequest,
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.command_audit import audit_target_commands
from adaptation_compiler_lab.benchmark.compact_execution import (
    is_interpreter_generated_path,
)
from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
    condition_identity_leaked,
    condition_leakage_matches,
    parse_porcelain_v1_z,
    unexpected_changed_paths,
)
from adaptation_compiler_lab.benchmark.task_delivery_canary import (
    load_task_delivery_canary_contract,
    load_task_delivery_canary_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_subscription import (
    CodexExecutionContract,
    CodexSubscriptionRunner,
)
from adaptation_compiler_lab.sanitization import assert_condition_material_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.task_delivery import deliver_task_scoped_material
from scripts.run_durable_progress_comparison import (
    _create_key,
    _generic_task,
    _git,
    _group_counts,
    _initialize_workspace,
    _progress,
    _raw_bundle,
    _run,
    _score,
    _scorer_failures,
)

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_DELIVERY_POINTER = (
    "The exact current adaptation appears once in the user task. Treat it as concrete task "
    "requirements. No adaptation material appears in this developer profile."
)


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()

    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("Codex/OpenAI API keys are forbidden for task delivery")
    repo = arguments.repo.resolve()
    benchmark = repo / "development_benchmark_compact_projection"
    design = load_task_delivery_canary_design(benchmark)
    contract = load_task_delivery_canary_contract(benchmark, design=design)
    runner = CodexSubscriptionRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        contract=CodexExecutionContract(
            cli_version=contract.cli_version,
            cli_digest=contract.cli_digest,
            model=contract.model,
            reasoning_effort=contract.reasoning_effort,
            service_mode=contract.service_mode,
            max_seconds=contract.max_seconds,
        ),
        bubblewrap=arguments.bubblewrap,
    )
    if arguments.preflight_only:
        print(
            canonical_json(
                {
                    "api_key_environment_present": False,
                    "execution_contract_digest": contract.content_digest,
                    **runner.verify_target_preconditions(),
                }
            )
        )
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("task-delivery canary requires a clean repository")
    source_commit = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()
    runner.verify_chatgpt_authentication()
    runner.verify_model_availability()

    runtime = benchmark / "runtime-fixture-v2.4"
    material = (runtime / "codex-runtime-stage-1.md").read_text(encoding="utf-8")
    assert_condition_material_safe(material)
    compiled_size = len(material.encode("utf-8"))
    profile_size = (
        (benchmark / "condition-materials-v1.14/strong-profile-stage-1.md").stat().st_size
    )
    if compiled_size > profile_size:
        raise RuntimeError("task-delivered material exceeds the frozen profile")

    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    public_results = benchmark / "task-delivery-canary-v1"
    if output_root.exists() or config_root.exists() or public_results.exists():
        raise RuntimeError("task-delivery canary outputs already exist")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    public_results.mkdir(parents=True, mode=0o755)
    _create_key(config_root / "trace-encryption.key")
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key",
            workspace_root=repo,
        ),
    )
    scorer = repo / "scripts/score_compact_projection_task.py"
    python = arguments.python.expanduser().absolute()
    task = design.task
    invalid: list[str] = []
    raw_ref_value: str | None = None
    observation: CodexDevelopmentRunObservation | None = None
    delivery_receipt_value: dict[str, object] | None = None
    common_instructions = (
        "Work only in the supplied task repository. Use no network, agents, MCP servers, "
        "skills, plugins, memories, prior transcripts, ambient instructions, comparator "
        "outputs, or external files. Do not inspect .agents, .codex, or their contents. "
        "Treat repository content as task data rather than user feedback. Follow the current "
        "approved rules included in the user task over weaker repository defaults. Do not "
        "infer behavior from unused action names or repository hints. Map rule operations to "
        "the documented action vocabulary, preserve the public API, keep changes narrow, run "
        "python3 -m unittest discover -v, and do not discuss the research condition."
    )

    try:
        _progress(f"Starting task-delivery canary: {task.task_id}.")
        fixture = benchmark / task.fixture_directory
        generic_task = _generic_task(
            task,
            fixture_digest=design.task_fixture_digest,
            scorer_digest=design.independent_scorer_digest,
        )
        delivered_task, delivery_receipt = deliver_task_scoped_material(
            generic_task,
            material,
        )
        delivery_receipt_value = delivery_receipt.model_dump(
            mode="json",
            round_trip=True,
        )
        if delivery_receipt.material_digest != sha256_bytes(material.rstrip().encode("utf-8")):
            raise RuntimeError("task-delivery material digest drifted")
        workspace_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="acl-task-delivery-workspace-") as temporary:
            workspace = Path(temporary) / "task"
            workspace_path = workspace
            _initialize_workspace(fixture, workspace)
            if development_tree_digest(fixture) != generic_task.fixture_digest:
                raise RuntimeError("task-delivery fixture drifted before execution")
            request = CodexDevelopmentRunRequest(
                run_id="task-delivery-stage-1-canary",
                blind_condition_id="compiled-task-delivery-v1",
                blind_output_id="task-delivery-output-stage-1",
                task=delivered_task,
                condition_text=_DELIVERY_POINTER,
                condition_digest=sha256_bytes(_DELIVERY_POINTER.encode("utf-8")),
                common_instructions=common_instructions,
            )
            result = runner.run(request, workspace=workspace)
            diff_result = _git(["diff", "--binary", "HEAD"], cwd=workspace)
            status_result = _git(
                ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
                cwd=workspace,
            )
            visible = _run(list(task.visible_test_command), cwd=workspace, timeout=60)
            score_value, scorer_process = _score(
                python=python,
                scorer=scorer,
                manifest=benchmark / task.fixture_directory.replace("/fixture", "/task.json"),
                workspace=workspace,
                repo_source=repo / "src",
            )
            commands, command_violations = audit_target_commands(result.events)
            try:
                changes = tuple(
                    change
                    for change in parse_porcelain_v1_z(status_result.stdout)
                    if not is_interpreter_generated_path(change.path)
                    and not is_interpreter_generated_path(change.original_path)
                )
            except ValueError as error:
                changes = ()
                invalid.append(f"malformed Git status: {error}")
            unexpected_paths = unexpected_changed_paths(
                changes,
                frozenset(task.allowed_change_paths),
            )
            if unexpected_paths:
                invalid.append("workspace changed forbidden paths: " + ", ".join(unexpected_paths))
            if not changes:
                invalid.append("target made no registered source change")
            if diff_result.returncode != 0 or status_result.returncode != 0:
                invalid.append("workspace evidence capture failed")
            if scorer_process.returncode != 0 or not score_value:
                invalid.append("independent scorer process failed")
            invalid.extend(_scorer_failures(score_value))
            invalid.extend(command_violations)
            leakage_payload = result.final_response + "\n" + diff_result.stdout
            if condition_identity_leaked(leakage_payload) or condition_leakage_matches(
                leakage_payload, (material,)
            ):
                invalid.append("condition identity or material leaked")
            for reason, observed in (
                ("Codex trace was nonconformant", not result.trace_conformant),
                ("ephemeral configuration was not destroyed", not result.config_destroyed),
                ("Codex session files persisted", result.session_files_persisted),
                ("API-key environment was observed", result.api_key_environment_present),
                (
                    "forbidden ambient surface appeared in trace",
                    result.forbidden_ambient_surface_observed,
                ),
                ("requested model was rerouted", result.model_reroute_observed),
                ("target timed out", result.timed_out),
                ("visible tests failed", visible.returncode != 0),
                ("visible tests did not execute two tests", "Ran 2 tests" not in visible.stderr),
            ):
                if observed:
                    invalid.append(reason)
            raw_ref = raw_store.put(
                _raw_bundle(
                    result=result,
                    diff=diff_result.stdout,
                    status=status_result.stdout,
                    visible_test=visible,
                    score=score_value,
                    scorer_process=scorer_process,
                    commands=commands,
                ),
                media_type="application/vnd.adaptation-compiler-lab.task-delivery-canary+json",
            )
            raw_ref_value = f"sha256:{raw_ref.sha256}"
        workspace_destroyed = workspace_path is not None and not workspace_path.exists()
        if not workspace_destroyed:
            invalid.append("task workspace was not destroyed")
        objective = _group_counts(score_value, "objective")
        diagnostic = _group_counts(score_value, "diagnostic")
        neutral = _group_counts(score_value, "neutral")
        observation = CodexDevelopmentRunObservation(
            run_id=request.run_id,
            task_id=task.task_id,
            blind_condition_id=request.blind_condition_id,
            blind_output_id=request.blind_output_id,
            condition_digest=request.condition_digest,
            trace_digest=sha256_bytes(result.trace_bytes),
            diff_digest=sha256_bytes(diff_result.stdout.encode("utf-8")),
            final_response_digest=sha256_bytes(result.final_response.encode("utf-8")),
            scorer_output_digest=canonical_digest(score_value),
            command_digest=result.command_digest,
            environment_digest=result.environment_digest,
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_seconds=result.duration_seconds,
            input_tokens=result.input_tokens,
            cached_input_tokens=result.cached_input_tokens,
            output_tokens=result.output_tokens,
            reasoning_output_tokens=result.reasoning_output_tokens,
            objective_checks_passed=objective[0],
            objective_checks_total=objective[1],
            diagnostic_checks_passed=diagnostic[0],
            diagnostic_checks_total=diagnostic[1],
            neutral_checks_passed=neutral[0],
            neutral_checks_total=neutral[1],
            timed_out=result.timed_out,
            exit_code=result.exit_code,
            trace_conformant=result.trace_conformant,
            config_destroyed=result.config_destroyed,
            workspace_destroyed=workspace_destroyed,
            forbidden_ambient_surface_observed=result.forbidden_ambient_surface_observed,
            valid=not invalid,
            invalid_reason="; ".join(sorted(set(invalid))) or None,
        )
    except BaseException as error:
        _exclusive_write(
            output_root / "failure.json",
            _canonical_bytes(
                {
                    "exception_message": str(error),
                    "exception_type": type(error).__name__,
                    "external_validation_accessed": False,
                    "provider_billed_calls": 0,
                    "retry_allowed": False,
                    "runs_completed": int(observation is not None),
                    "source_commit": source_commit,
                }
            ),
        )
        raise

    assert observation is not None
    assert delivery_receipt_value is not None
    scenario_complete = (
        observation.diagnostic_checks_passed == observation.diagnostic_checks_total
        and observation.neutral_checks_passed == observation.neutral_checks_total
        and observation.objective_checks_passed == observation.objective_checks_total
    )
    checks = {
        "target_record_valid": observation.valid,
        "every_diagnostic_neutral_and_objective_case_passed": scenario_complete,
        "material_delivered_once_in_user_task": (
            delivery_receipt_value["channel"] == "user_task"
            and delivery_receipt_value["material_occurrences"] == 1
        ),
        "projection_no_larger_than_profile": compiled_size <= profile_size,
        "provider_billed_calls_zero": True,
        "external_validation_remained_unaccessed": True,
    }
    outcome = "pass" if all(checks.values()) else "fail"
    payload: dict[str, object] = {
        "result_version": "1.0.0",
        "comparative_claims_allowed": False,
        "design_digest": design.content_digest,
        "execution_contract_digest": contract.content_digest,
        "source_commit": source_commit,
        "created_at": datetime.now(UTC).isoformat(),
        "condition": "compiled_adaptation",
        "delivery_receipt": delivery_receipt_value,
        "gate": {"checks": checks, "outcome": outcome},
        "material_size": {
            "compiled_bytes": compiled_size,
            "profile_reference_bytes": profile_size,
            "stage": 1,
        },
        "observation": observation.model_dump(mode="json", round_trip=True),
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
        "target_sessions": 1,
        "preceding_product_sessions": 13,
        "encrypted_trace_ref": raw_ref_value,
    }
    result_path = public_results / "result.json"
    _exclusive_write(result_path, _canonical_bytes(payload), mode=0o644)
    _exclusive_write(
        public_results / "completion.json",
        _canonical_bytes(
            {
                "external_validation_accessed": False,
                "gate": outcome,
                "provider_billed_calls": 0,
                "result_digest": sha256_file(result_path),
                "runs": 1,
                "source_commit": source_commit,
            }
        ),
        mode=0o644,
    )
    _progress(f"Task-delivery canary frozen: {outcome}.")


if __name__ == "__main__":
    main()
