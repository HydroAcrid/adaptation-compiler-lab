"""Execute the smoke-gated v2 repair of the frozen Mode comparison."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.modes.evaluation import (
    build_mode_evaluation_plan,
    load_mode_evaluation_contract,
)
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    require_external_raw_root,
)
from adaptation_compiler_lab.runners.codex_mode_target import CodexModeTargetRunner
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.serialization import canonical_digest
from scripts.mode_evaluation_v2_common import (
    require_valid_smoke,
    validate_instrument_sources,
    verify_scorer_runtime,
    write_new,
)
from scripts.run_durable_progress_comparison import _git
from scripts.run_mode_evaluation import _execute_cell, _load_public_plan

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--raw-key-file", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()

    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("Codex/OpenAI API keys are forbidden for Mode evaluation v2")
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    contract = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v2.json")
    validate_instrument_sources(repo, contract)
    scorer_runtime = verify_scorer_runtime(repo=repo, python=arguments.python)
    runner = CodexModeTargetRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        contract=CodexExecutionContract(
            cli_version=contract.target_cli_version,
            cli_digest=contract.target_cli_digest,
            model=contract.target_model,
            reasoning_effort=contract.target_reasoning_effort,
            service_mode="standard",
            max_seconds=contract.target_timeout_seconds,
        ),
        bubblewrap=arguments.bubblewrap,
    )
    preflight = runner.verify_target_preconditions()
    if arguments.preflight_only:
        print(
            canonical_digest(
                {
                    "contract_digest": contract.content_digest,
                    "scorer_runtime": scorer_runtime,
                    "target_preflight": preflight,
                }
            )
        )
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("Mode evaluation v2 requires a clean committed repository")
    smoke = require_valid_smoke(benchmark=benchmark, contract=contract)
    seed_file = arguments.seed_file.expanduser().resolve()
    if seed_file.is_relative_to(repo) or seed_file.stat().st_mode & 0o077:
        raise RuntimeError("Mode evaluation v2 seed must be private and outside the repository")
    public_plan = _load_public_plan(benchmark / "PUBLIC_PLAN-v2.json")
    expected_public, private_plan = build_mode_evaluation_plan(
        contract,
        seed=seed_file.read_bytes(),
    )
    if expected_public.content_digest != public_plan.content_digest:
        raise RuntimeError("Mode evaluation v2 public plan does not match the private seed")
    assignments = private_plan.get("condition_assignments")
    private_order = private_plan.get("run_order")
    if not isinstance(assignments, list) or not all(isinstance(item, dict) for item in assignments):
        raise RuntimeError("Mode evaluation v2 private assignments are invalid")
    if not isinstance(private_order, list) or not all(
        isinstance(item, dict) for item in private_order
    ):
        raise RuntimeError("Mode evaluation v2 private run order is invalid")
    mapping = {str(item["blind_condition_id"]): str(item["condition"]) for item in assignments}
    private_cells = {str(item["run_id"]): item for item in private_order}
    fixtures = {item.task_id: item for item in contract.fixtures}
    output_root = arguments.output_root.expanduser().resolve()
    if output_root != benchmark / "results-v2":
        raise RuntimeError("Mode evaluation v2 output must use the frozen results-v2 directory")
    output_root.mkdir(parents=True, exist_ok=False)
    raw_key = RawEncryptionKey.from_file(arguments.raw_key_file, workspace_root=repo)
    raw_store = LocalRawPayloadStore(
        require_external_raw_root(arguments.raw_root, workspace_root=repo),
        encryption_key=raw_key,
    )
    scorer_digest = sha256_file(repo / "scripts/score_mode_evaluation_task.py")
    trials: list[dict[str, object]] = []
    for cell in public_plan.run_order:
        private = private_cells[cell.run_id]
        if private["blind_condition_id"] != cell.blind_condition_id:
            raise RuntimeError("Mode evaluation v2 private/public cell mismatch")
        condition = mapping[cell.blind_condition_id]
        fixture = fixtures[cell.task_id]
        print(f"running {cell.sequence}/30: {cell.task_id} -> {cell.blind_output_id}", flush=True)
        trial, _ = _execute_cell(
            repo=repo,
            benchmark=benchmark,
            output_root=output_root,
            raw_store=raw_store,
            runner=runner,
            python=arguments.python.expanduser().resolve(),
            fixture=fixture,
            cell=cell.model_dump(mode="json"),
            condition=condition,
            scorer_digest=scorer_digest,
        )
        trials.append(trial)
    report: dict[str, object] = {
        "report_version": "2.0.0",
        "repair_of_report_digest": (
            "sha256:39126997857d169ae7c8f71b8c27663c6ecbc5f4ba577b72010a48e84c5d2914"
        ),
        "contract_digest": contract.content_digest,
        "public_plan_digest": public_plan.content_digest,
        "smoke_receipt_digest": canonical_digest(smoke),
        "source_commit": _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip(),
        "trials": trials,
        "all_trial_integrity_valid": all(bool(item["integrity_valid"]) for item in trials),
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
        "unblinded": False,
    }
    write_new(output_root / "blind-trial-report.json", report)
    write_new(output_root / "completion.json", {"report_digest": canonical_digest(report)})


if __name__ == "__main__":
    main()
