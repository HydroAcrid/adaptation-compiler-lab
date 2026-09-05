"""Run one live edit, test, and hidden-score gate for the Mode evaluation v2 repair."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.modes.evaluation import (
    load_mode_evaluation_contract,
    load_mode_evaluation_fixture,
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
    validate_instrument_sources,
    verify_scorer_runtime,
    write_new,
)
from scripts.run_durable_progress_comparison import _git
from scripts.run_mode_evaluation import _execute_cell

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--raw-key-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("Codex/OpenAI API keys are forbidden for the Mode v2 smoke")
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
    target_preflight = runner.verify_target_preconditions()
    if arguments.preflight_only:
        print(
            canonical_digest(
                {
                    "contract_digest": contract.content_digest,
                    "scorer_runtime": scorer_runtime,
                    "target_preflight": target_preflight,
                }
            )
        )
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("Mode evaluation v2 smoke requires a clean committed repository")
    output_root = benchmark / "smoke-v2"
    if output_root.exists():
        raise RuntimeError("Mode evaluation v2 smoke already exists")
    raw_key = RawEncryptionKey.from_file(arguments.raw_key_file, workspace_root=repo)
    raw_store = LocalRawPayloadStore(
        require_external_raw_root(arguments.raw_root, workspace_root=repo),
        encryption_key=raw_key,
    )
    fixture = load_mode_evaluation_fixture(benchmark / "tasks/mode-v2-smoke.json")
    trial, public_output = _execute_cell(
        repo=repo,
        benchmark=benchmark,
        output_root=output_root,
        raw_store=raw_store,
        runner=runner,
        python=arguments.python.expanduser().resolve(),
        fixture=fixture,
        cell={
            "run_id": "mode-v2-smoke-run",
            "blind_condition_id": "mode-v2-smoke-core",
            "blind_output_id": "mode-v2-smoke-output",
        },
        condition="core-only",
        scorer_digest=sha256_file(repo / "scripts/score_mode_evaluation_task.py"),
    )
    edit_observed = bool(str(public_output.get("diff", "")).strip())
    hidden_scorer_passed = trial.get("checks_passed") == 3 and trial.get("checks_total") == 3
    visible_tests_passed = public_output.get("visible_tests_passed") is True
    valid = all(
        (
            trial.get("integrity_valid") is True,
            trial.get("behavior_conformant") is True,
            trial.get("activation_exact") is True,
            trial.get("deactivation_exact") is True,
            trial.get("workspace_destroyed") is True,
            edit_observed,
            hidden_scorer_passed,
            visible_tests_passed,
        )
    )
    receipt: dict[str, object] = {
        "receipt_version": "2.0.0",
        "contract_digest": contract.content_digest,
        "source_commit": _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip(),
        "valid": valid,
        "edit_observed": edit_observed,
        "visible_tests_passed": visible_tests_passed,
        "hidden_scorer_passed": hidden_scorer_passed,
        "workspace_destroyed": trial.get("workspace_destroyed") is True,
        "integrity_failures": trial.get("integrity_failures", []),
        "behavior_failures": trial.get("behavior_failures", []),
        "scorer_runtime": scorer_runtime,
        "trial_digest": canonical_digest(trial),
        "encrypted_trace_ref": trial.get("encrypted_trace_ref"),
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
    }
    write_new(output_root / "smoke-receipt.json", receipt)
    write_new(
        output_root / "completion.json",
        {"smoke_receipt_digest": canonical_digest(receipt)},
    )
    if not valid:
        raise RuntimeError("Mode evaluation v2 repair smoke failed")


if __name__ == "__main__":
    main()
