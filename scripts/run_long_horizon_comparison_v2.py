"""Run the v1.1 long-horizon instrument rerun with restored resume writes."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    LongHorizonEpisodeResult,
    LongHorizonPrivatePlan,
    LongHorizonPublicPlan,
    build_long_horizon_plan,
)
from adaptation_compiler_lab.benchmark.long_horizon_fixture import (
    create_long_horizon_workspace,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from adaptation_compiler_lab.runners.codex_conversation import (
    CodexConversationTurnRequest,
)
from adaptation_compiler_lab.runners.codex_conversation_v2 import (
    CodexConversationRunnerV2,
)
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.serialization import canonical_json
from scripts.run_long_horizon_comparison import (
    _COMMON_INSTRUCTIONS,
    _create_key,
    _episode,
    _exclusive_write,
    _git,
    _isolated_score,
    _json_bytes,
)

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_RAW_MAGIC = b"ACLAB-RAW-1\n"
_RAW_MEDIA_TYPE = "application/vnd.acl.long-horizon-episode+json"


def _use_terminal_cumulative_usage(
    result: LongHorizonEpisodeResult,
    raw_store: LocalRawPayloadStore,
) -> LongHorizonEpisodeResult:
    """Replace the v1 sum-of-snapshots metric with the terminal thread total."""

    digest = result.encrypted_raw_ref.removeprefix("sha256:")
    relative_path = f"sha256/{digest[:2]}/{digest}"
    stored = (raw_store.root / relative_path).read_bytes()
    if not stored.startswith(_RAW_MAGIC):
        raise RuntimeError("v1.1 raw result was not encrypted")
    envelope = json.loads(stored.removeprefix(_RAW_MAGIC))
    plaintext_size = envelope.get("plaintext_size")
    if not isinstance(plaintext_size, int):
        raise RuntimeError("v1.1 raw-result envelope has no plaintext size")
    reference = RawPayloadRef(
        sha256=digest,
        size_bytes=plaintext_size,
        media_type=_RAW_MEDIA_TYPE,
        relative_path=relative_path,
    )
    bundle = json.loads(raw_store.read(reference))
    turns = bundle.get("turns")
    if not isinstance(turns, list) or len(turns) != 15:
        raise RuntimeError("v1.1 raw result does not contain 15 turns")
    usage = turns[-1].get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("v1.1 terminal turn has no usage object")
    expected = {
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    }
    if set(usage) != expected or any(
        not isinstance(usage[name], int) or usage[name] < 0 for name in expected
    ):
        raise RuntimeError("v1.1 terminal usage object is invalid")
    return result.model_copy(
        update={
            "input_tokens": usage["input_tokens"],
            "cached_input_tokens": usage["cached_input_tokens"],
            "output_tokens": usage["output_tokens"],
            "reasoning_output_tokens": usage["reasoning_output_tokens"],
        }
    )


def _smoke(
    *,
    design: LongHorizonDesign,
    runner: CodexConversationRunnerV2,
    bubblewrap: Path,
    scorer: Path,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="acl-long-horizon-v2-smoke-") as temporary:
        workspace = Path(temporary) / "smoke"
        create_long_horizon_workspace(workspace)
        first = design.scenario.turns[0].task
        second = design.scenario.turns[1].task
        material = design.materials[0]
        result = runner.run_smoke(
            episode_id="long-horizon-v2-write-smoke",
            common_instructions=_COMMON_INSTRUCTIONS,
            turns=(
                CodexConversationTurnRequest(
                    turn=1,
                    task_id=first.task_id,
                    prompt=first.prompt,
                    allowed_change_paths=first.allowed_change_paths,
                    adaptation_stage=1,
                    material_text=material.stages[0],
                    material_digest=material.stage_digests[0],
                ),
                CodexConversationTurnRequest(
                    turn=2,
                    task_id=second.task_id,
                    prompt=second.prompt,
                    allowed_change_paths=second.allowed_change_paths,
                    adaptation_stage=1,
                ),
            ),
            workspace=workspace,
        )
        changed = set(_git(["diff", "--name-only"], cwd=workspace).stdout.splitlines())
        expected = {
            first.allowed_change_paths[0],
            second.allowed_change_paths[0],
        }
        scores = tuple(
            _isolated_score(
                bubblewrap=bubblewrap,
                scorer=scorer,
                workspace=workspace,
                task_id=task.task_id,
            )
            for task in (first, second)
        )
    return {
        "both_registered_files_changed": changed == expected,
        "config_destroyed": result.config_destroyed,
        "one_thread": len({item.thread_id for item in result.turns}) == 1,
        "provider_billed_calls": 0,
        "session_destroyed": result.session_destroyed,
        "turns_conformant": len(result.turns) == 2
        and all(item.trace_conformant for item in result.turns),
        "visible_tests_passed": all(value["objective_passed"] for value in scores),
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
        raise RuntimeError("API keys are forbidden for the long-horizon rerun")
    repo = arguments.repo.expanduser().resolve()
    root = repo / "development_benchmark_long_horizon"
    config_root = arguments.config_root.expanduser().resolve()
    output_root = arguments.output_root.expanduser().resolve()
    design = LongHorizonDesign.model_validate_json((root / "PREREGISTRATION-v1.json").read_bytes())
    public = LongHorizonPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.1.json").read_bytes()
    )
    private = LongHorizonPrivatePlan.model_validate_json(
        (config_root / "private-plan.json").read_bytes()
    )
    seed_path = config_root / "randomization-seed.bin"
    reproduced_public, reproduced_private = build_long_horizon_plan(
        design,
        seed=seed_path.read_bytes(),
    )
    if reproduced_public != public or reproduced_private != private:
        raise RuntimeError("rerun seed does not reproduce the frozen plan")
    bindings = json.loads((root / "RERUN_BINDINGS-v1.1.json").read_text())
    expected_instrument = {
        "conversation_runner_v1_digest": sha256_file(
            repo / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation.py"
        ),
        "conversation_runner_v2_digest": sha256_file(
            repo / "src" / "adaptation_compiler_lab" / "runners" / "codex_conversation_v2.py"
        ),
        "original_coordinator_digest": sha256_file(
            repo / "scripts" / "run_long_horizon_comparison.py"
        ),
        "rerun_coordinator_digest": sha256_file(
            repo / "scripts" / "run_long_horizon_comparison_v2.py"
        ),
        "scorer_digest": sha256_file(root / "independent_scorer.py"),
    }
    if (
        bindings.get("instrument") != expected_instrument
        or bindings.get("design_digest") != design.content_digest
        or bindings.get("public_plan_digest") != public.content_digest
    ):
        raise RuntimeError("long-horizon rerun bindings drifted")
    bubblewrap = arguments.bubblewrap.expanduser().resolve()
    scorer = root / "independent_scorer.py"
    runner = CodexConversationRunnerV2(
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
                    "instrument_version": "1.1.0",
                    "provider_billed_calls": 0,
                }
            )
        )
        return
    if arguments.smoke_only:
        print(
            canonical_json(
                _smoke(
                    design=design,
                    runner=runner,
                    bubblewrap=bubblewrap,
                    scorer=scorer,
                )
            )
        )
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("long-horizon rerun requires a clean committed repository")
    public_results = root / "results-v1.1"
    if public_results.exists() or output_root.exists():
        raise RuntimeError("long-horizon rerun output location already exists")
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
    results = []
    for cell in public.episodes:
        assignment = assignments[cell.episode_id]
        print(f"Starting anonymous v1.1 episode {cell.sequence}/2.", flush=True)
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
        result = _use_terminal_cumulative_usage(result, raw_store)
        results.append(result)
        _exclusive_write(
            public_results / f"{cell.blind_output_id}.json",
            _json_bytes(result),
            mode=0o644,
        )
    report = {
        "report_version": "1.1.0",
        "design_digest": design.content_digest,
        "public_plan_digest": public.content_digest,
        "instrument_version": "1.1.0",
        "usage_semantics": "terminal_cumulative_thread_snapshot",
        "original_run_preserved": True,
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
        public_results / "BLIND_REPORT-v1.1.json",
        _json_bytes(report),
        mode=0o644,
    )
    print(
        canonical_json(
            {
                "blind_report_digest": sha256_bytes(_json_bytes(report)),
                "condition_mapping_withheld": True,
                "instrument_valid": report["instrument_valid"],
                "provider_billed_calls": 0,
                "target_turns": 30,
            }
        )
    )


if __name__ == "__main__":
    main()
