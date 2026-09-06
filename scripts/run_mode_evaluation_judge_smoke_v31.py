"""Run one tool-free trace smoke for the frozen v3.1 judge repair."""

from __future__ import annotations

import argparse
import base64
import json
import os
from dataclasses import replace
from pathlib import Path

from adaptation_compiler_lab.modes.evaluation import load_mode_evaluation_contract
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    require_external_raw_root,
)
from adaptation_compiler_lab.runners.codex_mode_judge_v31 import (
    CODE_MODE_DISABLED_NOTICE,
    CodexModeJudgeV31Runner,
    reconcile_disabled_host_notice,
)
from adaptation_compiler_lab.runners.codex_subscription import CodexExecutionContract
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from scripts.mode_evaluation_v31_judge_common import validate_repair_sources, write_new
from scripts.run_durable_progress_comparison import _git

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--raw-key-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for the Mode judge v3.1 smoke")
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    repair_contract = validate_repair_sources(repo)
    target_contract = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v3.json")
    runner = CodexModeJudgeV31Runner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        contract=CodexExecutionContract(
            cli_version=target_contract.target_cli_version,
            cli_digest=target_contract.target_cli_digest,
            model=target_contract.judge_model,
            reasoning_effort=target_contract.judge_reasoning_effort,
            service_mode="standard",
            max_seconds=target_contract.judge_timeout_seconds,
        ),
    )
    preflight = runner.verify_preconditions()
    if arguments.preflight_only:
        print(canonical_json(preflight))
        return
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("Mode judge v3.1 smoke requires a clean committed repository")
    output_root = benchmark / "judge-smoke-v31"
    if output_root.exists():
        raise RuntimeError("Mode judge v3.1 smoke already exists")
    result = runner.run(
        role_id="mode-evaluation-v31-trace-smoke",
        developer_contract="Return strict JSON only. Do not use tools.",
        prompt="Return an object with ok set to true.",
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean", "const": True}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    )
    events = tuple(
        json.loads(line) for line in result.trace_bytes.decode("utf-8").splitlines() if line.strip()
    )
    notices = [
        item["message"]
        for event in events
        if isinstance((item := event.get("item")), dict)
        and item.get("type") == "error"
        and isinstance(item.get("message"), str)
    ]
    injected_trace = (
        result.trace_bytes
        + (
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": "true"},
                }
            )
            + "\n"
        ).encode()
    )
    tool_case = replace(
        result,
        trace_bytes=injected_trace,
        response="",
        trace_conformant=False,
        trace_validation_error="structured role used a tool",
        tool_use_observed=True,
    )
    genuine_tool_rejected = not reconcile_disabled_host_notice(tool_case).trace_conformant
    valid = (
        result.trace_conformant
        and not result.tool_use_observed
        and notices == [CODE_MODE_DISABLED_NOTICE]
        and json.loads(result.response) == {"ok": True}
        and genuine_tool_rejected
        and result.config_destroyed
        and result.workspace_destroyed
        and not result.session_files_persisted
    )
    raw_key = RawEncryptionKey.from_file(arguments.raw_key_file, workspace_root=repo)
    raw_store = LocalRawPayloadStore(
        require_external_raw_root(arguments.raw_root, workspace_root=repo),
        encryption_key=raw_key,
    )
    raw_ref = raw_store.put(
        (
            canonical_json(
                {
                    "response": result.response,
                    "stderr": result.stderr,
                    "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
                }
            )
            + "\n"
        ).encode(),
        media_type="application/vnd.temper.mode-evaluation-v31-judge-smoke+json",
    )
    receipt: dict[str, object] = {
        "receipt_version": "3.1.0",
        "repair_contract_digest": canonical_digest(repair_contract),
        "source_commit": _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip(),
        "valid": valid,
        "exact_notice_normalized": notices == [CODE_MODE_DISABLED_NOTICE],
        "genuine_tool_rejection_tested": genuine_tool_rejected,
        "trace_conformant": result.trace_conformant,
        "workspace_destroyed": result.workspace_destroyed,
        "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
        "input_tokens": result.input_tokens,
        "cached_input_tokens": result.cached_input_tokens,
        "output_tokens": result.output_tokens,
        "reasoning_output_tokens": result.reasoning_output_tokens,
        "provider_billed_calls": 0,
        "condition_mapping_access": False,
        "external_validation_accessed": False,
    }
    write_new(output_root / "smoke-receipt.json", receipt)
    write_new(
        output_root / "completion.json",
        {"smoke_receipt_digest": canonical_digest(receipt)},
    )
    if not valid:
        raise RuntimeError("Mode judge v3.1 trace smoke failed")


if __name__ == "__main__":
    main()
