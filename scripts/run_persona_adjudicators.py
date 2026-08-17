"""Adjudicate only xhigh persona-judge disagreements in fresh max contexts."""

from __future__ import annotations

import argparse
import base64
import json
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel

from adaptation_compiler_lab.benchmark.persona_evaluation import (
    PersonaCondition,
    PersonaConditionMaterial,
    PersonaExecutionReceipt,
    PersonaJudgeDecision,
    PersonaModelJudgeDecision,
    PersonaTrack,
    bind_judge_decision,
    build_judge_packet,
    persona_judge_output_schema,
    validate_judge_decision,
)
from adaptation_compiler_lab.benchmark.persona_fixture import build_persona_benchmark_plan
from adaptation_compiler_lab.connectors.pins import sha256_bytes
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from adaptation_compiler_lab.runners.codex_persona import (
    CodexPersonaRoleRunner,
    PersonaRoleRequest,
)
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _json_bytes(value: BaseModel | Mapping[str, object]) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", round_trip=True)
    return (canonical_json(value) + "\n").encode("utf-8")


def _key(path: Path) -> RawEncryptionKey:
    if not path.exists():
        _exclusive_write(path, base64.b64encode(os.urandom(32)) + b"\n")
    return RawEncryptionKey.from_file(path, workspace_root=Path.cwd())


def _preferred(decision: PersonaJudgeDecision, track: PersonaTrack) -> str | None:
    return next(item for item in decision.decisions if item.track is track).preferred_alternative_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--saved-auth", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    args = parser.parse_args()
    if any(os.environ.get(name) for name in ("CODEX_API_KEY", "OPENAI_API_KEY")):
        raise RuntimeError("API keys are forbidden for persona adjudication")
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_evaluation"
    decision_root = root / "judge-results"
    output_root = root / "adjudicator-results"
    output_root.mkdir(parents=True, exist_ok=True)
    packet_root = root / "adjudicator-packets"
    packet_root.mkdir(parents=True, exist_ok=True)
    raw_root = args.raw_root.resolve()
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_store = LocalRawPayloadStore(raw_root, encryption_key=_key(args.key_file.resolve()))
    seed = base64.b64decode(args.seed_file.read_text(encoding="ascii").strip(), validate=True)
    plan = build_persona_benchmark_plan()
    personas = {item.persona_id: item for item in plan.personas}
    material_document = json.loads((root / "MATERIALS-v1.json").read_text(encoding="utf-8"))
    materials = tuple(
        PersonaConditionMaterial.model_validate_json(json.dumps(item))
        for item in material_document["materials"]
    )
    runner = CodexPersonaRoleRunner(
        executable=args.codex_executable,
        saved_auth_file=args.saved_auth,
        bubblewrap=args.bubblewrap,
        model="gpt-5.6-sol",
        reasoning_effort="max",
        max_seconds=900,
    )
    disagreements: list[str] = []
    for case in plan.cases:
        first = PersonaJudgeDecision.model_validate_json(
            (decision_root / f"{case.case_id}-r1.decision.json").read_bytes()
        )
        second = PersonaJudgeDecision.model_validate_json(
            (decision_root / f"{case.case_id}-r2.decision.json").read_bytes()
        )
        if all(_preferred(first, track) == _preferred(second, track) for track in PersonaTrack):
            continue
        disagreements.append(case.case_id)
        decision_path = output_root / f"{case.case_id}.decision.json"
        receipt_path = output_root / f"{case.case_id}.receipt.json"
        if decision_path.exists() and receipt_path.exists():
            continue
        selected = [item for item in materials if item.case_id == case.case_id]
        compiled = next(item for item in selected if item.condition is PersonaCondition.COMPILED)
        comparator = next(
            item for item in selected if item.condition is not PersonaCondition.COMPILED
        )
        packet, _ = build_judge_packet(
            seed=seed,
            persona=personas[case.persona_id],
            case=case,
            compiled=compiled,
            comparator=comparator,
            replicate=3,
        )
        packet_bytes = _json_bytes(packet)
        packet_path = packet_root / f"{case.case_id}.json"
        if not packet_path.exists():
            _exclusive_write(packet_path, packet_bytes)
        print(f"starting max adjudicator: {case.case_id}", flush=True)
        result = runner.run(
            PersonaRoleRequest(
                role_id=f"persona-{case.persona_id}-adjudicator-{case.case_id}",
                persona_ids=(case.persona_id,),
                developer_contract=(
                    "You are a fresh final evaluator. You cannot see earlier votes. Judge only "
                    "this one fictional persona and anonymous packet, use no tools, and return "
                    "schema-valid JSON."
                ),
                prompt=(
                    "Independently decide both anonymous pairs. Copy every binding exactly. A tie "
                    "is allowed when the alternatives are materially equivalent.\n\n"
                    f"PERSONA PACKET\n{packet_bytes.decode('utf-8')}"
                ),
                output_schema=persona_judge_output_schema(),
            )
        )
        decision = validate_judge_decision(
            packet,
            bind_judge_decision(
                packet,
                PersonaModelJudgeDecision.model_validate_json(result.response),
            ),
        )
        raw_ref = raw_store.put(
            _json_bytes(
                {
                    "response": result.response,
                    "stderr": result.stderr,
                    "trace_base64": base64.b64encode(result.trace_bytes).decode("ascii"),
                }
            ),
            media_type="application/vnd.temper.persona-adjudicator-trace+json",
        )
        receipt = PersonaExecutionReceipt(
            execution_id=f"adjudicator-{packet.packet_id}",
            role="adjudicator",
            persona_id=case.persona_id,
            case_id=case.case_id,
            packet_digest=sha256_bytes(packet_bytes),
            model="gpt-5.6-sol",
            reasoning_effort="max",
            input_tokens=result.input_tokens,
            cached_input_tokens=result.cached_input_tokens,
            output_tokens=result.output_tokens,
            reasoning_output_tokens=result.reasoning_output_tokens,
            trace_digest=sha256_bytes(result.trace_bytes),
            command_digest=result.command_digest,
            environment_digest=result.environment_digest,
        )
        _exclusive_write(decision_path, _json_bytes(decision))
        _exclusive_write(
            receipt_path,
            _json_bytes(
                {
                    **receipt.model_dump(mode="json", round_trip=True),
                    "encrypted_trace_ref": f"sha256:{raw_ref.sha256}",
                }
            ),
        )
    print(canonical_json({"disagreement_case_ids": disagreements}))


if __name__ == "__main__":
    main()
