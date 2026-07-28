"""Run the one frozen eight-cell retry through the smoke-validated v3 runner."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, cast

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentPublicPlan,
    build_breadth_instrument_plan,
    load_breadth_instrument_contract,
    load_breadth_instrument_design,
)
from adaptation_compiler_lab.benchmark.breadth_instrument_retry import (
    load_breadth_instrument_retry_contract,
    load_breadth_instrument_retry_design,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.task_channel_comparison import (
    FairComparisonTrialReceipt,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.runners.codex_subscription_v3 import (
    CodexSubscriptionRunnerV3,
)
from adaptation_compiler_lab.serialization import canonical_json
from scripts.run_breadth_instrument import (
    _canonical_bytes,
    _exclusive_write,
    _trial,
)
from scripts.run_durable_progress_comparison import _create_key, _git, _progress

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for the v3 breadth retry")
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_instrument_repair"
    base_design = load_breadth_instrument_design(root)
    base_contract = load_breadth_instrument_contract(root, design=base_design)
    retry_design = load_breadth_instrument_retry_design(
        root,
        base_design=base_design,
        base_contract=base_contract,
    )
    contract = load_breadth_instrument_retry_contract(root, retry_design=retry_design)
    runner = CodexSubscriptionRunnerV3(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        contract=CodexExecutionContract(
            cli_version=contract.cli_version,
            cli_digest=contract.cli_digest,
            model=contract.target_model,
            reasoning_effort=contract.target_reasoning_effort,
            service_mode=contract.service_mode,
            max_seconds=contract.max_seconds_per_session,
        ),
        bubblewrap=arguments.bubblewrap,
    )
    if arguments.preflight_only:
        print(
            canonical_json(
                {
                    "api_key_environment_present": False,
                    "contract_digest": contract.content_digest,
                    **runner.verify_target_preconditions(),
                }
            )
        )
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("v3 breadth retry requires a clean repository")
    source_commit = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()
    runner.verify_chatgpt_authentication()
    runner.verify_model_availability()
    seed_path = arguments.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("v3 breadth retry seed boundary is invalid")
    public, private = build_breadth_instrument_plan(
        design_digest=retry_design.content_digest,
        tasks=base_design.tasks,
        seed=seed_path.read_bytes(),
    )
    frozen_public = BreadthInstrumentPublicPlan.model_validate_json(
        (root / "RETRY_PUBLIC_PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("v3 breadth retry seed does not reproduce the frozen plan")
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    public_results = root / "results-v2"
    if output_root.exists() or config_root.exists() or public_results.exists():
        raise RuntimeError("v3 breadth retry output location already exists")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    public_results.mkdir(parents=True, mode=0o755)
    public_outputs = public_results / "anonymous-outputs"
    public_outputs.mkdir(mode=0o755)
    _create_key(config_root / "trace-encryption.key")
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key",
            workspace_root=repo,
        ),
    )
    _exclusive_write(output_root / "private-plan.json", _canonical_bytes(private))
    assignments = cast(list[dict[str, object]], private["condition_assignments"])
    conditions = {
        str(item["blind_condition_id"]): BenchmarkCondition(str(item["condition"]))
        for item in assignments
    }
    tasks = {item.task_id: item for item in base_design.tasks}
    receipts: list[FairComparisonTrialReceipt] = []
    try:
        for cell in cast(list[dict[str, object]], private["run_order"]):
            task_id = str(cell["task_id"])
            _progress(f"Starting v3 retry cell {cell['sequence']}/8: {task_id}.")
            receipt, output = _trial(
                repo=repo,
                root=root,
                raw_store=raw_store,
                runner=cast(Any, runner),
                bubblewrap=arguments.bubblewrap,
                wrapped=tasks[task_id],
                cell=cell,
                condition=conditions[str(cell["blind_condition_id"])],
            )
            receipts.append(receipt)
            _exclusive_write(
                public_outputs / f"{receipt.observation.blind_output_id}.json",
                _canonical_bytes(output),
                mode=0o644,
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
                    "runs_completed": len(receipts),
                    "source_commit": source_commit,
                }
            ),
        )
        raise
    blind_report: dict[str, object] = {
        "report_version": "1.0.0",
        "retry_design_digest": retry_design.content_digest,
        "contract_digest": contract.content_digest,
        "public_plan_digest": public.content_digest,
        "source_commit": source_commit,
        "condition_mapping_withheld": True,
        "automated_scores_withheld_from_judge": True,
        "trials": [item.model_dump(mode="json", round_trip=True) for item in receipts],
        "instrument_valid": all(item.integrity_valid for item in receipts),
        "provider_billed_calls": 0,
        "external_validation_accessed": False,
    }
    report_path = public_results / "blind-report.json"
    _exclusive_write(report_path, _canonical_bytes(blind_report), mode=0o644)
    _exclusive_write(
        public_results / "completion.json",
        _canonical_bytes(
            {
                "blind_report_digest": sha256_file(report_path),
                "condition_mapping_withheld": True,
                "external_validation_accessed": False,
                "instrument_valid": blind_report["instrument_valid"],
                "provider_billed_calls": 0,
                "runs": len(receipts),
                "source_commit": source_commit,
            }
        ),
        mode=0o644,
    )
    _progress("v3 Milestone 6A.4 retry grid frozen.")


if __name__ == "__main__":
    main()
