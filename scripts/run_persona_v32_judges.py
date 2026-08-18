"""Run one fresh condition-blind judge per frozen v3.2 task pair."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32Fixture,
    PersonaV32JudgeDecision,
    PersonaV32Protocol,
    PersonaV32PublicPlan,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_persona import PersonaRoleRequest
from adaptation_compiler_lab.runners.codex_persona_v3 import CodexPersonaV3RoleRunner
from adaptation_compiler_lab.runners.persona_smoke_support import capture_role_result
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from scripts.run_durable_progress_comparison import _create_key

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _json_bytes(value: dict[str, object]) -> bytes:
    return (canonical_json(value) + "\n").encode()


def _schema() -> dict[str, object]:
    schema = PersonaV32JudgeDecision.model_json_schema()

    def close(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            prefix = node.get("prefixItems")
            if isinstance(prefix, list) and prefix:
                node["items"] = prefix[0]
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for value in node:
                close(value)

    close(schema)
    return schema


def _pairs(plan: PersonaV32PublicPlan) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for index in range(0, 4, 2):
        first, second = plan.run_order[index : index + 2]
        if first.task_id != second.task_id:
            raise RuntimeError("v3.2 public plan is not task-blocked")
        result[first.task_id] = (first.blind_output_id, second.blind_output_id)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for v3.2 judges")
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_v32"
    protocol = PersonaV32Protocol.model_validate_json((root / "PROTOCOL-v3.2.json").read_bytes())
    fixture = PersonaV32Fixture.model_validate_json((root / "FIXTURE-v1.json").read_bytes())
    plan = PersonaV32PublicPlan.model_validate_json((root / "PUBLIC-PLAN-v1.json").read_bytes())
    completion = root / "target-results-v1/COMPLETION-v1.json"
    blind_report = root / "target-results-v1/BLIND-REPORT-v1.json"
    completion_value = __import__("json").loads(completion.read_text(encoding="utf-8"))
    if (
        completion_value.get("instrument_valid") is not True
        or completion_value.get("condition_mapping_withheld") is not True
        or completion_value.get("blind_report_digest") != sha256_file(blind_report)
    ):
        raise RuntimeError("v3.2 judges require a complete integrity-valid blind report")
    runner = CodexPersonaV3RoleRunner(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        bubblewrap=args.bubblewrap,
        model=protocol.judge_model,
        reasoning_effort=protocol.judge_reasoning_effort,
        max_seconds=600,
    )
    if args.preflight_only:
        print(canonical_json(runner.verify_preconditions()))
        return
    output_root = args.output_root.resolve()
    config_root = args.config_root.resolve()
    public_output = root / "judge-results-v1"
    if output_root.exists() or config_root.exists() or public_output.exists():
        raise RuntimeError("v3.2 judge outputs already exist")
    output_root.mkdir(parents=True, mode=0o700)
    config_root.mkdir(parents=True, mode=0o700)
    public_output.mkdir()
    _create_key(config_root / "trace-encryption.key")
    raw_store = LocalRawPayloadStore(
        output_root / "encrypted",
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key", workspace_root=repo
        ),
    )
    pairs = _pairs(plan)
    task_by_id = {task.task_id: task for task in fixture.tasks}
    anonymous_root = root / "target-results-v1/anonymous-outputs"
    for task_id, output_ids in pairs.items():
        task = task_by_id[task_id]
        outputs = []
        for label, output_id in zip(("First", "Second"), output_ids, strict=True):
            value = (anonymous_root / f"{output_id}.json").read_text(encoding="utf-8")
            outputs.append(f"### {label}: {output_id}\n\n{value}")
        packet = f"TASK ID: {task_id}\n\nTASK REQUEST:\n{task.prompt}\n\n" + "\n\n".join(outputs)
        prompt = (
            "Judge the two anonymous coding outputs. Copy task_id and ordered_output_ids exactly. "
            "Evaluate implementation quality, instruction adherence, blocker handling, and "
            "unsupported verification claims separately. The visible-test flag is evidence; do "
            "not infer hidden tests or conditions. A tie requires preferred_output_id null. Return "
            "schema-valid JSON only.\n\nBINDING\n"
            + canonical_json({"task_id": task_id, "ordered_output_ids": list(output_ids)})
            + "\n\nANONYMOUS PACKET\n"
            + packet
        )
        role = runner.run(
            PersonaRoleRequest(
                role_id=f"persona-v32-blind-judge-{task_id}",
                persona_ids=(f"judge-{task_id}",),
                developer_contract=(
                    "You are a fresh condition-blind software-quality judge. You have no prior "
                    "context, tools, repository, adaptation material, automated scores, or "
                    "condition mapping. Do not infer condition identity."
                ),
                prompt=prompt,
                output_schema=_schema(),
            )
        )
        decision = PersonaV32JudgeDecision.model_validate_json(role.response)
        if decision.rating.task_id != task_id or decision.rating.ordered_output_ids != output_ids:
            raise RuntimeError("v3.2 judge response changed its anonymous binding")
        raw = capture_role_result(
            raw_store,
            role,
            media_type="application/vnd.temper.persona-v32-blind-judge+json",
        )
        receipt = {
            "receipt_version": "1.0.0",
            "task_id": task_id,
            "blind_packet_digest": sha256_bytes(packet.encode()),
            "condition_mapping_access": False,
            "decision": decision.model_dump(mode="json", round_trip=True),
            "decision_digest": canonical_digest(decision),
            "encrypted_trace_ref": f"sha256:{raw.sha256}",
            "model": role.model,
            "reasoning_effort": role.reasoning_effort,
            "usage": {
                "input_tokens": role.input_tokens,
                "cached_input_tokens": role.cached_input_tokens,
                "output_tokens": role.output_tokens,
                "reasoning_output_tokens": role.reasoning_output_tokens,
            },
            "provider_billed_calls": 0,
            "external_validation_accessed": False,
        }
        _exclusive_write(
            public_output / f"JUDGE-{task_id}-v1.json",
            _json_bytes(receipt),
            mode=0o644,
        )


if __name__ == "__main__":
    main()
