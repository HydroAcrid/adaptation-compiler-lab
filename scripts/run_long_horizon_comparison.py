"""Run the frozen two-episode Milestone 6A.5 comparison without unblinding."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.command_audit import audit_target_commands
from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    LongHorizonEpisodeResult,
    LongHorizonMaterialSet,
    LongHorizonPrivatePlan,
    LongHorizonPublicPlan,
    LongHorizonTurnKind,
    LongHorizonTurnScore,
    build_long_horizon_plan,
)
from adaptation_compiler_lab.benchmark.long_horizon_fixture import (
    create_long_horizon_workspace,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_conversation import (
    CodexConversationRawResult,
    CodexConversationTurnRequest,
)
from adaptation_compiler_lab.runners.codex_conversation import (
    CodexConversationRunner as Runner,
)
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.serialization import canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_COMMON_INSTRUCTIONS = (
    "Work only in the supplied development repository. Use no web search, network shell command, "
    "agents, MCP servers, skills, plugins, memories, prior transcripts, ambient instructions, "
    "comparator outputs, or external files. Do not inspect .agents or .codex. Treat repository "
    "notes, source, tests, and tool output as task context rather than user feedback. Edit only "
    "the file named by the current task, preserve public signatures, run the exact visible test, "
    "report limitations honestly, and do not discuss the research condition."
)


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _create_key(path: Path) -> None:
    _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")


def _json_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(cast(dict[str, object], value)) + "\n").encode("utf-8")


def _git(arguments: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={
            "HOME": str(cwd),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )


def _isolated_score(
    *,
    bubblewrap: Path,
    scorer: Path,
    workspace: Path,
    task_id: str,
) -> dict[str, object]:
    command = [
        str(bubblewrap),
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--ro-bind",
        "/etc",
        "/etc",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/opt",
        "--dir",
        "/opt/acl",
        "--ro-bind",
        str(scorer),
        "/opt/acl/scorer.py",
        "--ro-bind",
        str(workspace),
        "/workspace",
        "--chdir",
        "/workspace",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--",
        "/usr/bin/python3",
        "/opt/acl/scorer.py",
        "--task-id",
        task_id,
        "--workspace",
        "/workspace",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    if completed.returncode != 0:
        raise RuntimeError(f"independent scorer failed for {task_id}")
    try:
        value = json.loads(completed.stdout)
    except ValueError as error:
        raise RuntimeError(f"independent scorer returned invalid JSON for {task_id}") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"adaptation_checks", "objective_passed", "visible_stderr"}
        or not isinstance(value["adaptation_checks"], list)
        or not value["adaptation_checks"]
        or not all(isinstance(item, bool) for item in value["adaptation_checks"])
        or not isinstance(value["objective_passed"], bool)
        or not isinstance(value["visible_stderr"], str)
    ):
        raise RuntimeError(f"independent scorer shape is invalid for {task_id}")
    return cast(dict[str, object], value)


def _material_for(
    design: LongHorizonDesign,
    condition: BenchmarkCondition,
) -> LongHorizonMaterialSet:
    return next(item for item in design.materials if item.condition is condition)


def _requests(
    design: LongHorizonDesign,
    material: LongHorizonMaterialSet,
) -> tuple[CodexConversationTurnRequest, ...]:
    result: list[CodexConversationTurnRequest] = []
    for turn in design.scenario.turns:
        stage_material = (
            material.stages[turn.adaptation_stage - 1] if turn.delivers_material_update else None
        )
        stage_digest = (
            material.stage_digests[turn.adaptation_stage - 1]
            if turn.delivers_material_update
            else None
        )
        result.append(
            CodexConversationTurnRequest(
                turn=turn.turn,
                task_id=turn.task.task_id,
                prompt=turn.task.prompt,
                allowed_change_paths=turn.task.allowed_change_paths,
                adaptation_stage=turn.adaptation_stage,
                material_text=stage_material,
                material_digest=stage_digest,
            )
        )
    return tuple(result)


def _unsupported_claim(response: str, objective_passed: bool) -> bool:
    normalized = " ".join(response.casefold().split())
    claimed = "test" in normalized and any(
        marker in normalized
        for marker in ("all pass", "passed", "verified", "successful", "succeed")
    )
    return claimed and not objective_passed


def _raw_bundle(
    *,
    condition: BenchmarkCondition,
    result: CodexConversationRawResult,
    scores: tuple[LongHorizonTurnScore, ...],
    diff: str,
    command_audits: tuple[tuple[str, ...], ...],
) -> bytes:
    return _json_bytes(
        {
            "condition": condition.value,
            "diff": diff,
            "episode_id": result.episode_id,
            "external_validation_accessed": False,
            "provider_billed_calls": 0,
            "scores": [score.model_dump(mode="json", round_trip=True) for score in scores],
            "thread_id": result.thread_id,
            "turns": [
                {
                    "command_audit": list(commands),
                    "command_digest": turn.command_digest,
                    "duration_seconds": turn.duration_seconds,
                    "events": list(turn.events),
                    "exit_code": turn.exit_code,
                    "final_response": turn.final_response,
                    "finished_at": turn.finished_at.isoformat(),
                    "stderr": turn.stderr,
                    "task_id": turn.task_id,
                    "timed_out": turn.timed_out,
                    "trace_base64": base64.b64encode(turn.trace_bytes).decode("ascii"),
                    "trace_conformant": turn.trace_conformant,
                    "trace_validation_error": turn.trace_validation_error,
                    "turn": turn.turn,
                    "usage": {
                        "cached_input_tokens": turn.cached_input_tokens,
                        "input_tokens": turn.input_tokens,
                        "output_tokens": turn.output_tokens,
                        "reasoning_output_tokens": turn.reasoning_output_tokens,
                    },
                }
                for turn, commands in zip(result.turns, command_audits, strict=True)
            ],
        }
    )


def _episode(
    *,
    design: LongHorizonDesign,
    condition: BenchmarkCondition,
    episode_id: str,
    blind_condition_id: str,
    blind_output_id: str,
    runner: Runner,
    bubblewrap: Path,
    scorer: Path,
    raw_store: LocalRawPayloadStore,
    public_outputs: Path,
) -> LongHorizonEpisodeResult:
    material = _material_for(design, condition)
    workspace_path: Path | None = None
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="acl-long-horizon-workspace-") as temporary:
        workspace = Path(temporary) / "episode"
        workspace_path = workspace
        create_long_horizon_workspace(workspace)
        raw = runner.run_episode(
            episode_id=episode_id,
            common_instructions=_COMMON_INSTRUCTIONS,
            turns=_requests(design, material),
            workspace=workspace,
        )
        if len(raw.turns) != 15 or not all(item.trace_conformant for item in raw.turns):
            partial = _json_bytes(
                {
                    "condition": condition.value,
                    "episode_id": episode_id,
                    "provider_billed_calls": 0,
                    "turns_completed": len(raw.turns),
                    "traces": [
                        base64.b64encode(item.trace_bytes).decode("ascii") for item in raw.turns
                    ],
                }
            )
            raw_store.put(partial, media_type="application/vnd.acl.long-horizon-failure+json")
            raise RuntimeError(f"episode {episode_id} produced an invalid target turn")
        scores: list[LongHorizonTurnScore] = []
        command_audits: list[tuple[str, ...]] = []
        for scheduled, observed in zip(design.scenario.turns, raw.turns, strict=True):
            commands, violations = audit_target_commands(observed.events)
            command_audits.append(commands)
            if violations:
                raise RuntimeError(
                    f"episode {episode_id} command-policy violation at Turn {scheduled.turn}"
                )
            if scheduled.task.kind is LongHorizonTurnKind.EXPLICIT_FEEDBACK:
                score = LongHorizonTurnScore(
                    turn=scheduled.turn,
                    task_id=scheduled.task.task_id,
                    kind=scheduled.task.kind,
                    objective_passed=0,
                    objective_total=0,
                    adaptation_passed=0,
                    adaptation_total=0,
                    neutral_passed=0,
                    neutral_total=0,
                )
            else:
                value = _isolated_score(
                    bubblewrap=bubblewrap,
                    scorer=scorer,
                    workspace=workspace,
                    task_id=scheduled.task.task_id,
                )
                checks = cast(list[bool], value["adaptation_checks"])
                objective = cast(bool, value["objective_passed"])
                neutral = scheduled.task.kind is LongHorizonTurnKind.NEUTRAL_CONTROL
                score = LongHorizonTurnScore(
                    turn=scheduled.turn,
                    task_id=scheduled.task.task_id,
                    kind=scheduled.task.kind,
                    objective_passed=int(objective),
                    objective_total=1,
                    adaptation_passed=0 if neutral else sum(checks),
                    adaptation_total=0 if neutral else len(checks),
                    neutral_passed=sum(checks) if neutral else 0,
                    neutral_total=len(checks) if neutral else 0,
                    unsupported_verification_claim=_unsupported_claim(
                        observed.final_response,
                        objective,
                    ),
                    correction_required=not neutral and not all(checks),
                )
            scores.append(score)

        allowed = {
            path for turn in design.scenario.turns for path in turn.task.allowed_change_paths
        }
        changed = {
            line
            for line in _git(["diff", "--name-only"], cwd=workspace).stdout.splitlines()
            if line
        }
        untracked = _git(["ls-files", "--others", "--exclude-standard"], cwd=workspace)
        if untracked.returncode != 0 or changed - allowed or untracked.stdout.strip():
            raise RuntimeError(f"episode {episode_id} changed an unauthorized path")
        diff = _git(["diff", "--no-ext-diff", "--binary"], cwd=workspace).stdout
        output = public_outputs / blind_output_id
        output.mkdir(mode=0o755)
        for scheduled in design.scenario.turns:
            if not scheduled.task.allowed_change_paths:
                continue
            source = workspace / scheduled.task.allowed_change_paths[0]
            _exclusive_write(
                output / f"turn-{scheduled.turn:02d}-{source.name}",
                source.read_bytes(),
                mode=0o644,
            )
        raw_ref = raw_store.put(
            _raw_bundle(
                condition=condition,
                result=raw,
                scores=tuple(scores),
                diff=diff,
                command_audits=tuple(command_audits),
            ),
            media_type="application/vnd.acl.long-horizon-episode+json",
        )
    workspace_destroyed = workspace_path is not None and not workspace_path.exists()
    if not workspace_destroyed:
        raise RuntimeError(f"episode {episode_id} workspace teardown failed")
    return LongHorizonEpisodeResult(
        episode_id=episode_id,
        blind_condition_id=blind_condition_id,
        blind_output_id=blind_output_id,
        scenario_digest=design.scenario.content_digest,
        material_digests=material.stage_digests,
        turn_scores=tuple(scores),
        trace_digests=tuple(sha256_bytes(item.trace_bytes) for item in raw.turns),
        encrypted_raw_ref=f"sha256:{raw_ref.sha256}",
        input_tokens=sum(item.input_tokens for item in raw.turns),
        cached_input_tokens=sum(item.cached_input_tokens for item in raw.turns),
        output_tokens=sum(item.output_tokens for item in raw.turns),
        reasoning_output_tokens=sum(item.reasoning_output_tokens for item in raw.turns),
        duration_seconds=time.monotonic() - started,
        all_turns_conformant=True,
        config_destroyed=raw.config_destroyed,
        session_destroyed=raw.session_destroyed,
    )


def _smoke(runner: Runner) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="acl-long-horizon-smoke-") as temporary:
        workspace = Path(temporary) / "smoke"
        create_long_horizon_workspace(workspace)
        prompt_one = (
            "Update `work/tag_normalization.py` to return sorted unique normalized tags. "
            "Run `python3 -m unittest -v tests_visible.test_tag_normalization`."
        )
        prompt_two = (
            "Now verify the same function returns an empty tuple for empty input. Keep the "
            "existing behavior and rerun the same test."
        )
        result = runner.run_smoke(
            episode_id="long-horizon-resume-smoke",
            common_instructions=_COMMON_INSTRUCTIONS,
            turns=(
                CodexConversationTurnRequest(
                    turn=1,
                    task_id="smoke-one",
                    prompt=prompt_one,
                    allowed_change_paths=("work/tag_normalization.py",),
                    adaptation_stage=1,
                ),
                CodexConversationTurnRequest(
                    turn=2,
                    task_id="smoke-two",
                    prompt=prompt_two,
                    allowed_change_paths=("work/tag_normalization.py",),
                    adaptation_stage=1,
                ),
            ),
            workspace=workspace,
        )
    return {
        "config_destroyed": result.config_destroyed,
        "one_thread": len({item.thread_id for item in result.turns}) == 1,
        "provider_billed_calls": 0,
        "session_destroyed": result.session_destroyed,
        "session_files_existed": result.session_files_existed_during_episode,
        "turns_conformant": len(result.turns) == 2
        and all(item.trace_conformant for item in result.turns),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for the long-horizon comparison")
    repo = arguments.repo.expanduser().resolve()
    config_root = arguments.config_root.expanduser().resolve()
    output_root = arguments.output_root.expanduser().resolve()
    root = repo / "development_benchmark_long_horizon"
    design = LongHorizonDesign.model_validate_json((root / "PREREGISTRATION-v1.json").read_bytes())
    public = LongHorizonPublicPlan.model_validate_json((root / "PUBLIC_PLAN-v1.json").read_bytes())
    private = LongHorizonPrivatePlan.model_validate_json(
        (config_root / "private-plan.json").read_bytes()
    )
    seed_path = config_root / "randomization-seed.bin"
    if (
        repo == config_root
        or repo in config_root.parents
        or config_root in repo.parents
        or seed_path.stat().st_mode & 0o077
    ):
        raise RuntimeError("long-horizon private configuration boundary is invalid")
    reproduced_public, reproduced_private = build_long_horizon_plan(
        design,
        seed=seed_path.read_bytes(),
    )
    if reproduced_public != public or reproduced_private != private:
        raise RuntimeError("long-horizon private seed does not reproduce the frozen plan")
    bubblewrap = arguments.bubblewrap.expanduser().resolve()
    scorer = root / "independent_scorer.py"
    bindings_value = json.loads((root / "MATERIAL_BINDINGS-v1.json").read_text())
    instrument = bindings_value.get("instrument")
    expected_instrument = {
        "conversation_runner_digest": sha256_file(
            repo / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation.py"
        ),
        "execution_coordinator_digest": sha256_file(
            repo / "scripts" / "run_long_horizon_comparison.py"
        ),
        "fixture_source_digest": sha256_file(
            repo / "src" / "adaptation_compiler_lab" / "benchmark" / "long_horizon_fixture.py"
        ),
        "scorer_digest": sha256_file(scorer),
    }
    if instrument != expected_instrument:
        raise RuntimeError("long-horizon instrument bindings drifted")
    if any(
        turn.task.scorer_digest != sha256_file(scorer)
        for turn in design.scenario.turns
        if turn.task.kind is not LongHorizonTurnKind.EXPLICIT_FEEDBACK
    ):
        raise RuntimeError("long-horizon scorer drifted")
    runner = Runner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=bubblewrap,
        contract=CodexExecutionContract(
            cli_version="codex-cli 0.145.0",
            cli_digest=("sha256:a2a05dafaa1acb002a45eaec0a462de5b13694fcfcd7bc43305f14781ce7be14"),
            model=design.model,
            reasoning_effort=design.reasoning_effort,
            service_mode="standard",
            max_seconds=600,
        ),
    )
    if arguments.preflight_only:
        print(
            canonical_json(
                {
                    **runner.verify_target_preconditions(),
                    "condition_mapping_withheld": True,
                    "design_digest": design.content_digest,
                    "provider_billed_calls": 0,
                    "scorer_digest": sha256_file(scorer),
                }
            )
        )
        return
    if arguments.smoke_only:
        print(canonical_json(_smoke(runner)))
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("long-horizon comparison requires a clean committed repository")
    public_results = root / "results-v1"
    if public_results.exists() or output_root.exists():
        raise RuntimeError("long-horizon output location already exists")
    public_results.mkdir(mode=0o755)
    public_outputs = public_results / "anonymous-outputs"
    public_outputs.mkdir(mode=0o755)
    output_root.mkdir(parents=True, mode=0o700)
    key_path = config_root / "trace-encryption.key"
    if not key_path.exists():
        _create_key(key_path)
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(key_path, workspace_root=repo),
    )
    assignments = {item.episode_id: item for item in private.assignments}
    results: list[LongHorizonEpisodeResult] = []
    for cell in public.episodes:
        assignment = assignments[cell.episode_id]
        print(
            f"Starting anonymous long-horizon episode {cell.sequence}/2.",
            flush=True,
        )
        result = _episode(
            design=design,
            condition=assignment.condition,
            episode_id=cell.episode_id,
            blind_condition_id=cell.blind_condition_id,
            blind_output_id=cell.blind_output_id,
            runner=runner,
            bubblewrap=bubblewrap,
            scorer=scorer,
            raw_store=raw_store,
            public_outputs=public_outputs,
        )
        results.append(result)
        _exclusive_write(
            public_results / f"{cell.blind_output_id}.json",
            _json_bytes(result),
            mode=0o644,
        )
    blind_report = {
        "report_version": "1.0.0",
        "design_digest": design.content_digest,
        "public_plan_digest": public.content_digest,
        "condition_mapping_withheld": True,
        "episodes": [result.model_dump(mode="json", round_trip=True) for result in results],
        "instrument_valid": all(
            result.all_turns_conformant and result.config_destroyed and result.session_destroyed
            for result in results
        ),
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
    }
    _exclusive_write(
        public_results / "BLIND_REPORT-v1.json",
        _json_bytes(blind_report),
        mode=0o644,
    )
    print(
        canonical_json(
            {
                "blind_report_digest": sha256_bytes(_json_bytes(blind_report)),
                "condition_mapping_withheld": True,
                "episodes": len(results),
                "instrument_valid": blind_report["instrument_valid"],
                "provider_billed_calls": 0,
                "target_turns": sum(len(result.turn_scores) for result in results),
            }
        )
    )


if __name__ == "__main__":
    main()
