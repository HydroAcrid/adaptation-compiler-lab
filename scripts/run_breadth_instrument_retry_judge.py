"""Run the isolated blind judge for the valid v3 retry grid."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.breadth_instrument_repair import (
    BreadthInstrumentJudgeDecision,
    BreadthInstrumentPublicPlan,
    load_breadth_instrument_contract,
    load_breadth_instrument_design,
)
from adaptation_compiler_lab.benchmark.breadth_instrument_retry import (
    load_breadth_instrument_retry_contract,
    load_breadth_instrument_retry_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_structured_role import CodexStructuredRoleRunner
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from scripts.run_breadth_instrument_judge import (
    _assert_valid,
    _canonical_bytes,
    _exclusive_write,
    _pairs,
    _raw_bundle,
    _strict_schema,
)
from scripts.run_durable_progress_comparison import _create_key

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _packet(
    root: Path,
    pairs: dict[str, tuple[str, str]],
) -> str:
    tasks = {item.task_id: item.task for item in load_breadth_instrument_design(root).tasks}
    outputs = root / "results-v2/anonymous-outputs"
    sections = []
    for task_id, output_ids in pairs.items():
        task = tasks[task_id]
        sections.append(f"## Task {task_id}\n\n{task.prompt}\n")
        for label, output_id in zip(("First", "Second"), output_ids, strict=True):
            value = json.loads((outputs / f"{output_id}.json").read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("blind_output_id") != output_id:
                raise RuntimeError("v3 retry anonymous output binding drifted")
            sections.append(
                f"### {label}: {output_id}\n\n"
                f"Allowed paths: {canonical_json({'paths': value['allowed_change_paths']})}\n\n"
                f"Visible tests executed: {value['visible_test_executed']}\n\n"
                f"Diff:\n```diff\n{value['diff']}\n```\n\n"
                f"Final response:\n{value['final_response']}\n"
            )
    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for the v3 retry judge")
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
    runner = CodexStructuredRoleRunner(
        executable=arguments.codex_executable,
        saved_auth_file=arguments.saved_auth,
        bubblewrap=arguments.bubblewrap,
        model=contract.judge_model,
        reasoning_effort=contract.judge_reasoning_effort,
        max_seconds=contract.max_seconds_per_session,
    )
    if arguments.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    results = root / "results-v2"
    report_path = results / "blind-report.json"
    completion = json.loads((results / "completion.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(completion, dict)
        or not isinstance(report, dict)
        or completion.get("blind_report_digest") != sha256_file(report_path)
        or report.get("instrument_valid") is not True
        or report.get("condition_mapping_withheld") is not True
    ):
        raise RuntimeError("v3 retry judge requires a complete valid blind report")
    public = BreadthInstrumentPublicPlan.model_validate_json(
        (root / "RETRY_PUBLIC_PLAN-v1.json").read_bytes()
    )
    pairs = _pairs(public)
    packet = _packet(root, pairs)
    prompt = (
        "Return one pair_ratings entry for every task. Copy task_id and ordered_output_ids exactly "
        "from JUDGE BINDINGS. Judge implementation quality, instruction adherence, blocker "
        "handling, maintainability, and unsupported verification claims. Visible-test execution "
        "is evidence, but no unshown score is available. Use no tools and do not infer condition "
        f"identity.\n\nJUDGE BINDINGS\n{canonical_json({'pairs': pairs})}\n\n{packet}"
    )
    output_root = arguments.output_root.resolve()
    config_root = arguments.config_root.resolve()
    receipt_path = results / "judge-receipt.json"
    if output_root.exists() or config_root.exists() or receipt_path.exists():
        raise RuntimeError("v3 retry judge output already exists")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    _create_key(config_root / "trace-encryption.key")
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key",
            workspace_root=repo,
        ),
    )
    result = runner.run(
        role_id="breadth-instrument-v3-condition-blind-judge",
        developer_contract=(
            "You are a fresh condition-blind software-quality judge. You have no tools, "
            "repository, model-condition material, automated scores, condition mapping, external "
            "study, or prior context. Return only JSON matching the schema. A tie uses null; a "
            "non-tie selects the exact corresponding output ID."
        ),
        prompt=prompt,
        output_schema=_strict_schema(),
    )
    _assert_valid(result)
    decision = BreadthInstrumentJudgeDecision.model_validate_json(result.response)
    observed = {item.task_id: item.ordered_output_ids for item in decision.pair_ratings}
    if observed != pairs:
        raise RuntimeError("v3 retry judge changed anonymous pair bindings")
    raw_ref = raw_store.put(
        _raw_bundle(result, decision),
        media_type="application/vnd.adaptation-compiler-lab.breadth-v3-judge+json",
    )
    receipt: dict[str, object] = {
        "receipt_version": "1.0.0",
        "api_key_environment_present": False,
        "authentication": "saved_chatgpt",
        "blind_packet_digest": sha256_bytes(packet.encode()),
        "blind_report_digest": sha256_file(report_path),
        "condition_mapping_access": False,
        "decision": decision.model_dump(mode="json", round_trip=True),
        "decision_digest": canonical_digest(decision),
        "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
        "external_validation_accessed": False,
        "model": result.model,
        "provider_billed_calls": 0,
        "reasoning_effort": result.reasoning_effort,
    }
    _exclusive_write(receipt_path, _canonical_bytes(receipt), mode=0o644)


if __name__ == "__main__":
    main()
