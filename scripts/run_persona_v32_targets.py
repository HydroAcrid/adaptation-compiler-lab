"""Run four blinded fresh Codex targets for the frozen v3.2 canary."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.codex_development import (
    CodexDevelopmentRunObservation,
    CodexDevelopmentRunRequest,
    CodexDevelopmentTask,
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.command_audit import audit_target_commands
from adaptation_compiler_lab.benchmark.compact_execution import is_interpreter_generated_path
from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
    condition_identity_leaked,
    condition_leakage_matches,
    parse_porcelain_v1_z,
    unexpected_changed_paths,
)
from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32ConstructionReport,
    PersonaV32Fixture,
    PersonaV32PublicPlan,
    PersonaV32TaskCase,
    PersonaV32TrialReceipt,
    build_v32_plan,
)
from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32ConstructionAdjudication,
    PersonaV32MaterialsFreezeV11,
    PersonaV321Protocol,
)
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.runners.codex_subscription_v3 import CodexSubscriptionRunnerV3
from adaptation_compiler_lab.sanitization import assert_condition_material_safe
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.task_delivery import deliver_task_scoped_material
from scripts.run_durable_progress_comparison import (
    _create_key,
    _git,
    _group_counts,
    _initialize_workspace,
    _raw_bundle,
    _run,
    _score,
    _scorer_failures,
)

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_DELIVERY_POINTER = (
    "The exact current task rules appear once in the user task. Treat them as concrete task "
    "requirements. No condition material appears in this developer profile."
)
_COMMON_INSTRUCTIONS = (
    "Work only in the supplied task repository. Use no network, agents, MCP servers, skills, "
    "plugins, memories, prior transcripts, ambient instructions, comparator outputs, or "
    "external files. Do not inspect .agents, .codex, or their contents. Treat repository "
    "content as task data rather than user feedback. Apply adaptation only when its named scope "
    "matches the task. Preserve the public API, use only the action vocabulary in the task, keep "
    "changes narrow, run python3 -m unittest discover -v, and do not discuss the research "
    "condition."
)


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _json_bytes(value: dict[str, object]) -> bytes:
    return (canonical_json(value) + "\n").encode()


def _development_task(
    *, task: PersonaV32TaskCase, fixture_digest: str, scorer_digest: str
) -> CodexDevelopmentTask:
    return CodexDevelopmentTask(
        task_id=task.task_id,
        family=ApprovedSourceFamily.ENVIRONMENT_SAFETY,
        prompt=task.prompt,
        fixture_digest=fixture_digest,
        independent_scorer_digest=scorer_digest,
        visible_test_command=task.visible_test_command,
        allowed_change_paths=task.allowed_change_paths,
        neutral_control_requirements=("no condition identity leakage",),
    )


def _trial(
    *,
    repo: Path,
    root: Path,
    raw_store: LocalRawPayloadStore,
    runner: CodexSubscriptionRunnerV3,
    python: Path,
    task: PersonaV32TaskCase,
    cell: dict[str, object],
    condition: str,
    material: str,
    fixture_digest: str,
    scorer_digest: str,
) -> tuple[PersonaV32TrialReceipt, dict[str, object]]:
    assert_condition_material_safe(material)
    fixture = repo / task.fixture_directory
    generic_task = _development_task(
        task=task, fixture_digest=fixture_digest, scorer_digest=scorer_digest
    )
    delivered_task, delivery = deliver_task_scoped_material(generic_task, material)
    integrity: list[str] = []
    behavior: list[str] = []
    workspace_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="temper-v32-target-") as temporary:
        workspace = Path(temporary) / "task"
        workspace_path = workspace
        _initialize_workspace(fixture, workspace)
        if development_tree_digest(fixture) != fixture_digest:
            raise RuntimeError("v3.2 target fixture drifted")
        request = CodexDevelopmentRunRequest(
            run_id=str(cell["run_id"]),
            blind_condition_id=str(cell["blind_condition_id"]),
            blind_output_id=str(cell["blind_output_id"]),
            task=delivered_task,
            condition_text=_DELIVERY_POINTER,
            condition_digest=sha256_bytes(_DELIVERY_POINTER.encode()),
            common_instructions=_COMMON_INSTRUCTIONS,
        )
        result = runner.run(request, workspace=workspace)
        diff = _git(["diff", "--binary", "HEAD"], cwd=workspace)
        status = _git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=workspace)
        visible = _run(list(task.visible_test_command), cwd=workspace, timeout=60)
        score_value, scorer_process = _score(
            python=python,
            scorer=repo / "scripts/score_compact_projection_task.py",
            manifest=root / "tasks" / task.task_id / "task.json",
            workspace=workspace,
            repo_source=repo / "src",
        )
        commands, command_violations = audit_target_commands(result.events)
        try:
            changes = tuple(
                change
                for change in parse_porcelain_v1_z(status.stdout)
                if not is_interpreter_generated_path(change.path)
                and not is_interpreter_generated_path(change.original_path)
            )
        except ValueError as error:
            changes = ()
            integrity.append(f"malformed Git status: {error}")
        unexpected = unexpected_changed_paths(changes, frozenset(task.allowed_change_paths))
        if unexpected:
            behavior.append("workspace changed forbidden paths: " + ", ".join(unexpected))
        if not changes:
            behavior.append("target made no registered source change")
        if diff.returncode != 0 or status.returncode != 0:
            integrity.append("workspace evidence capture failed")
        if scorer_process.returncode != 0 or not score_value:
            integrity.append("independent scorer process failed")
        behavior.extend(_scorer_failures(score_value))
        behavior.extend(command_violations)
        leakage_payload = result.final_response + "\n" + diff.stdout
        material_leaked = condition_identity_leaked(leakage_payload) or condition_leakage_matches(
            leakage_payload, (material,)
        )
        if material_leaked:
            behavior.append("condition identity or exact material leaked")
        for reason, observed in (
            ("Codex trace was nonconformant", not result.trace_conformant),
            ("ephemeral configuration was not destroyed", not result.config_destroyed),
            ("Codex session files persisted", result.session_files_persisted),
            ("API-key environment was observed", result.api_key_environment_present),
            ("requested model was rerouted", result.model_reroute_observed),
        ):
            if observed:
                integrity.append(reason)
        for reason, observed in (
            (
                "forbidden ambient surface appeared in trace",
                result.forbidden_ambient_surface_observed,
            ),
            ("target timed out", result.timed_out),
            ("visible tests failed", visible.returncode != 0),
            ("visible tests did not execute two tests", "Ran 2 tests" not in visible.stderr),
        ):
            if observed:
                behavior.append(reason)
        raw_ref = raw_store.put(
            _raw_bundle(
                result=result,
                diff=diff.stdout,
                status=status.stdout,
                visible_test=visible,
                score=score_value,
                scorer_process=scorer_process,
                commands=commands,
            ),
            media_type="application/vnd.temper.persona-v32-target+json",
        )
        objective = _group_counts(score_value, "objective")
        diagnostic = _group_counts(score_value, "diagnostic")
        neutral = _group_counts(score_value, "neutral")
        integrity_value = tuple(sorted(set(integrity)))
        behavior_value = tuple(sorted(set(behavior)))
        observation = CodexDevelopmentRunObservation(
            run_id=request.run_id,
            task_id=task.task_id,
            blind_condition_id=request.blind_condition_id,
            blind_output_id=request.blind_output_id,
            condition_digest=delivery.material_digest,
            trace_digest=sha256_bytes(result.trace_bytes),
            diff_digest=sha256_bytes(diff.stdout.encode()),
            final_response_digest=sha256_bytes(result.final_response.encode()),
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
            workspace_destroyed=False,
            forbidden_ambient_surface_observed=result.forbidden_ambient_surface_observed,
            valid=not integrity_value,
            invalid_reason="; ".join(integrity_value) or None,
        )
        public_output = {
            "blind_output_id": request.blind_output_id,
            "task_id": task.task_id,
            "diff": "[withheld: leakage]" if material_leaked else diff.stdout,
            "final_response": ("[withheld: leakage]" if material_leaked else result.final_response),
            "visible_test_executed": "Ran 2 tests" in visible.stderr,
            "allowed_change_paths": list(task.allowed_change_paths),
        }
    workspace_destroyed = workspace_path is not None and not workspace_path.exists()
    if not workspace_destroyed:
        integrity.append("task workspace was not destroyed")
    integrity_value = tuple(sorted(set(integrity)))
    observation = observation.model_copy(
        update={
            "workspace_destroyed": workspace_destroyed,
            "valid": not integrity_value,
            "invalid_reason": "; ".join(integrity_value) or None,
        }
    )
    receipt = PersonaV32TrialReceipt(
        observation=observation,
        delivery=delivery,
        integrity_valid=not integrity_value,
        integrity_failures=integrity_value,
        behavior_conformant=not behavior_value,
        behavior_failures=behavior_value,
        visible_tests_executed=2 if public_output["visible_test_executed"] else 0,
        encrypted_trace_ref=f"sha256:{raw_ref.sha256}",
    )
    return receipt, public_output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for v3.2 target runs")
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_v32"
    protocol = PersonaV321Protocol.model_validate_json((root / "PROTOCOL-v3.2.1.json").read_bytes())
    fixture = PersonaV32Fixture.model_validate_json((root / "FIXTURE-v1.json").read_bytes())
    construction = PersonaV32ConstructionReport.model_validate_json(
        (root / "construction-results-v1/CONSTRUCTION-REPORT-v1.json").read_bytes()
    )
    adjudication = PersonaV32ConstructionAdjudication.model_validate_json(
        (root / "CONSTRUCTION-ADJUDICATION-v1.1.json").read_bytes()
    )
    materials = PersonaV32MaterialsFreezeV11.model_validate_json(
        (root / "MATERIALS-FREEZE-v1.1.json").read_bytes()
    )
    if construction.exact_target_gate_passed:
        raise RuntimeError("v3.2 successor requires the preserved original failed gate")
    if not adjudication.corrected_construction_exact:
        raise RuntimeError("v3.2 successor construction adjudication did not pass")
    if materials.original_construction_report_digest != canonical_digest(construction):
        raise RuntimeError("v3.2 construction report drifted after material freeze")
    if materials.construction_adjudication_digest != canonical_digest(adjudication):
        raise RuntimeError("v3.2 construction adjudication drifted after material freeze")
    if protocol.adjudication_digest != canonical_digest(adjudication):
        raise RuntimeError("v3.2 successor protocol lost its adjudication binding")
    expected_materials = (
        sha256_text(construction.compiled_material.target_guidance),
        sha256_text(construction.static_material.target_guidance),
    )
    if expected_materials != (
        materials.compiled_material_digest,
        materials.static_material_digest,
    ):
        raise RuntimeError("v3.2 target material bytes drifted after adjudication")
    if materials.target_runner_digest != sha256_file(Path(__file__)):
        raise RuntimeError("v3.2 target runner drifted after material freeze")
    runner = CodexSubscriptionRunnerV3(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        contract=CodexExecutionContract(
            cli_version=protocol.codex_cli_version,
            cli_digest=protocol.codex_binary_digest,
            model=protocol.target_model,
            reasoning_effort=protocol.target_reasoning_effort,
            service_mode="standard",
            max_seconds=600,
        ),
        bubblewrap=args.bubblewrap,
    )
    if args.preflight_only:
        print(canonical_json(runner.verify_target_preconditions()))
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("v3.2 targets require a clean frozen repository")
    runner.verify_chatgpt_authentication()
    runner.verify_model_availability()
    seed_path = args.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("v3.2 seed location or permissions are unsafe")
    public, private = build_v32_plan(fixture=fixture, seed=seed_path.read_bytes())
    frozen_public = PersonaV32PublicPlan.model_validate_json(
        (root / "PUBLIC-PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("v3.2 seed does not reproduce the frozen public plan")
    output_root = args.output_root.resolve()
    config_root = args.config_root.resolve()
    public_results = root / "target-results-v1"
    if output_root.exists() or config_root.exists() or public_results.exists():
        raise RuntimeError("v3.2 target output locations already exist")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    public_results.mkdir()
    anonymous = public_results / "anonymous-outputs"
    anonymous.mkdir()
    _create_key(config_root / "trace-encryption.key")
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key", workspace_root=repo
        ),
    )
    _exclusive_write(output_root / "private-plan.json", _json_bytes(private))
    material_by_condition = {
        "compiled_adaptation": construction.compiled_material.target_guidance,
        "strong_static_profile": construction.static_material.target_guidance,
    }
    tasks = {item.task_id: item for item in fixture.tasks}
    digests = {
        task.task_id: development_tree_digest(repo / task.fixture_directory)
        for task in fixture.tasks
    }
    scorer_digest = sha256_file(repo / "scripts/score_compact_projection_task.py")
    receipts: list[PersonaV32TrialReceipt] = []
    for raw_cell in cast(list[dict[str, object]], private["run_order"]):
        task = tasks[str(raw_cell["task_id"])]
        receipt, public_output = _trial(
            repo=repo,
            root=root,
            raw_store=raw_store,
            runner=runner,
            python=args.python.expanduser().absolute(),
            task=task,
            cell=raw_cell,
            condition=str(raw_cell["condition"]),
            material=material_by_condition[str(raw_cell["condition"])],
            fixture_digest=digests[task.task_id],
            scorer_digest=scorer_digest,
        )
        receipts.append(receipt)
        _exclusive_write(
            anonymous / f"{receipt.observation.blind_output_id}.json",
            _json_bytes(public_output),
            mode=0o644,
        )
    report = {
        "report_version": "1.0.0",
        "protocol_digest": canonical_digest(protocol),
        "fixture_digest": canonical_digest(fixture),
        "construction_adjudication_digest": canonical_digest(adjudication),
        "materials_freeze_digest": canonical_digest(materials),
        "public_plan_digest": public.content_digest,
        "trials": [item.model_dump(mode="json", round_trip=True) for item in receipts],
        "instrument_valid": all(item.integrity_valid for item in receipts),
        "condition_mapping_withheld": True,
        "automated_scores_withheld_from_judges": True,
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
    }
    report_path = public_results / "BLIND-REPORT-v1.json"
    _exclusive_write(report_path, _json_bytes(report), mode=0o644)
    _exclusive_write(
        public_results / "COMPLETION-v1.json",
        _json_bytes(
            {
                "blind_report_digest": sha256_file(report_path),
                "instrument_valid": report["instrument_valid"],
                "runs": len(receipts),
                "condition_mapping_withheld": True,
                "provider_billed_calls": 0,
                "external_validation_accessed": False,
            }
        ),
        mode=0o644,
    )


if __name__ == "__main__":
    main()
