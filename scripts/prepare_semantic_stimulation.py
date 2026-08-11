"""Prepare, audit, freeze, and summarize the repository-informed stimulation gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticEvaluationReport,
    load_semantic_feedback_corpus,
    repair_semantic_evaluation_failures,
)
from adaptation_compiler_lab.automatic_runtime.semantic_stimulation import (
    RepositoryArchetype,
    SemanticStimulationAuditProposal,
    SemanticStimulationGeneration,
    SemanticStimulationIncrementalAudit,
    SemanticStimulationPlan,
    SemanticStimulationProtocol,
    SemanticStimulationRemediation,
    apply_semantic_stimulation_remediation,
    attest_semantic_stimulation_audit,
    attest_semantic_stimulation_generation,
    attest_semantic_stimulation_incremental_audit,
    attest_semantic_stimulation_remediation,
    build_semantic_stimulation_design,
    compose_semantic_stimulation_audit,
    freeze_semantic_stimulation_corpus,
    semantic_stimulation_audit_prompt,
    semantic_stimulation_generation_prompt,
    semantic_stimulation_incremental_audit_prompt,
    semantic_stimulation_remediation_prompt,
    summarize_semantic_stimulation,
)
from adaptation_compiler_lab.serialization import canonical_json


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def _load_model(path: Path, model: type[Any]) -> Any:
    return model.model_validate_json(path.read_text(encoding="utf-8"), strict=True)


def _load_report(path: Path) -> SemanticEvaluationReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "report" in payload:
        payload = payload["report"]
    return SemanticEvaluationReport.model_validate_json(
        json.dumps(payload, ensure_ascii=False),
        strict=True,
    )


def _strict_model_output_schema(model: type[Any]) -> dict[str, Any]:
    """Adapt a Pydantic schema to the CLI's all-properties-required contract."""

    schema = model.model_json_schema(mode="validation")

    def normalize(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
                value["additionalProperties"] = False
            for nested in value.values():
                normalize(nested)
        elif isinstance(value, list):
            for nested in value:
                normalize(nested)

    normalize(schema)
    return schema


def _audit_model_output_schema(
    model: type[SemanticStimulationAuditProposal | SemanticStimulationIncrementalAudit],
) -> dict[str, Any]:
    """Encode the audit entry's cross-field verdict/reason invariant for the model."""

    schema = _strict_model_output_schema(model)
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict) or "SemanticStimulationAuditEntry" not in definitions:
        raise ValueError("semantic stimulation audit schema is missing its entry definition")
    case_id = {
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$",
        "type": "string",
    }
    required = ["case_id", "verdict", "reason"]
    definitions["SemanticStimulationAuditEntry"] = {
        "anyOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": {
                    "case_id": case_id,
                    "verdict": {"type": "string", "const": "pass"},
                    "reason": {"type": "string", "const": "clean"},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": {
                    "case_id": case_id,
                    "verdict": {
                        "type": "string",
                        "enum": ["ambiguous", "fail"],
                    },
                    "reason": {
                        "type": "string",
                        "enum": [
                            "durability_mismatch",
                            "identifying_detail",
                            "label_mismatch",
                            "scope_mismatch",
                            "unexpressed_assumption",
                        ],
                    },
                },
            },
        ]
    }
    return schema


def _prepare(arguments: argparse.Namespace) -> None:
    archetypes = tuple(
        RepositoryArchetype.model_validate_json(path.read_text(encoding="utf-8"), strict=True)
        for path in sorted(arguments.archetypes.glob("context-*.json"))
    )
    plan, protocol = build_semantic_stimulation_design(
        archetypes,
        created_at=datetime.fromisoformat(arguments.created_at.replace("Z", "+00:00")),
    )
    _write_json(arguments.output / "PLAN-v1.json", plan.model_dump(mode="json"))
    _write_json(arguments.output / "PROTOCOL-v1.json", protocol.model_dump(mode="json"))
    _write_json(
        arguments.output / "GENERATION_SCHEMA-v1.json",
        _strict_model_output_schema(SemanticStimulationGeneration),
    )
    _write_text(
        arguments.output / "GENERATOR_PACKET-v1.txt",
        semantic_stimulation_generation_prompt(plan),
    )


def _prepare_audit(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    generation = _load_model(arguments.generation, SemanticStimulationGeneration)
    _write_json(
        arguments.output / "AUDIT_SCHEMA-v1.json",
        _audit_model_output_schema(SemanticStimulationAuditProposal),
    )
    _write_text(
        arguments.output / "AUDITOR_PACKET-v1.txt",
        semantic_stimulation_audit_prompt(plan, generation),
    )


def _attest_generation(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    proposal = _load_model(arguments.proposal, SemanticStimulationGeneration)
    receipt = attest_semantic_stimulation_generation(plan, proposal)
    _write_json(arguments.output, receipt.model_dump(mode="json"))


def _attest_audit(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    generation = _load_model(arguments.generation, SemanticStimulationGeneration)
    proposal = _load_model(arguments.proposal, SemanticStimulationAuditProposal)
    receipt = attest_semantic_stimulation_audit(plan, generation, proposal)
    _write_json(arguments.output, receipt.model_dump(mode="json"))


def _prepare_incremental_audit(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    base_generation = _load_model(arguments.base_generation, SemanticStimulationGeneration)
    base_audit = _load_model(arguments.base_audit, SemanticStimulationAuditProposal)
    revised_generation = _load_model(arguments.revised_generation, SemanticStimulationGeneration)
    _write_json(
        arguments.output / "INCREMENTAL_AUDIT_SCHEMA-v1.json",
        _audit_model_output_schema(SemanticStimulationIncrementalAudit),
    )
    _write_text(
        arguments.output / "INCREMENTAL_AUDITOR_PACKET-v1.txt",
        semantic_stimulation_incremental_audit_prompt(
            plan,
            base_generation,
            base_audit,
            revised_generation,
        ),
    )


def _attest_incremental_audit(arguments: argparse.Namespace) -> None:
    base_generation = _load_model(arguments.base_generation, SemanticStimulationGeneration)
    base_audit = _load_model(arguments.base_audit, SemanticStimulationAuditProposal)
    revised_generation = _load_model(arguments.revised_generation, SemanticStimulationGeneration)
    proposal = _load_model(arguments.proposal, SemanticStimulationIncrementalAudit)
    receipt = attest_semantic_stimulation_incremental_audit(
        base_generation,
        base_audit,
        revised_generation,
        proposal,
    )
    _write_json(arguments.output, receipt.model_dump(mode="json"))


def _compose_audit(arguments: argparse.Namespace) -> None:
    base_generation = _load_model(arguments.base_generation, SemanticStimulationGeneration)
    base_audit = _load_model(arguments.base_audit, SemanticStimulationAuditProposal)
    revised_generation = _load_model(arguments.revised_generation, SemanticStimulationGeneration)
    incremental_audit = _load_model(
        arguments.incremental_audit,
        SemanticStimulationIncrementalAudit,
    )
    receipt = compose_semantic_stimulation_audit(
        base_generation,
        base_audit,
        revised_generation,
        incremental_audit,
    )
    _write_json(arguments.output, receipt.model_dump(mode="json"))


def _prepare_remediation(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    generation = _load_model(arguments.generation, SemanticStimulationGeneration)
    audit = _load_model(arguments.audit, SemanticStimulationAuditProposal)
    _write_json(
        arguments.output / "REMEDIATION_SCHEMA-v1.json",
        _strict_model_output_schema(SemanticStimulationRemediation),
    )
    _write_text(
        arguments.output / "REMEDIATION_PACKET-v1.txt",
        semantic_stimulation_remediation_prompt(plan, generation, audit),
    )


def _apply_remediation(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    generation = _load_model(arguments.generation, SemanticStimulationGeneration)
    audit = _load_model(arguments.audit, SemanticStimulationAuditProposal)
    remediation = _load_model(arguments.remediation, SemanticStimulationRemediation)
    revised = apply_semantic_stimulation_remediation(plan, generation, audit, remediation)
    _write_json(arguments.output, revised.model_dump(mode="json"))


def _attest_remediation(arguments: argparse.Namespace) -> None:
    generation = _load_model(arguments.generation, SemanticStimulationGeneration)
    audit = _load_model(arguments.audit, SemanticStimulationAuditProposal)
    proposal = _load_model(arguments.proposal, SemanticStimulationRemediation)
    receipt = attest_semantic_stimulation_remediation(generation, audit, proposal)
    _write_json(arguments.output, receipt.model_dump(mode="json"))


def _freeze(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    generation = _load_model(arguments.generation, SemanticStimulationGeneration)
    audit = _load_model(arguments.audit, SemanticStimulationAuditProposal)
    corpus = freeze_semantic_stimulation_corpus(plan, generation, audit)
    _write_json(arguments.output / "CORPUS-v3.json", corpus.model_dump(mode="json"))
    _write_text(arguments.output / "CORPUS-v3.sha256", corpus.content_digest)


def _summarize(arguments: argparse.Namespace) -> None:
    protocol = _load_model(arguments.protocol, SemanticStimulationProtocol)
    plan = _load_model(arguments.plan, SemanticStimulationPlan)
    generation = _load_model(arguments.generation, SemanticStimulationGeneration)
    audit = _load_model(arguments.audit, SemanticStimulationAuditProposal)
    corpus = load_semantic_feedback_corpus(arguments.corpus)
    calibration_report = _load_report(arguments.calibration_report)
    holdout_report = _load_report(arguments.holdout_report)
    summary = summarize_semantic_stimulation(
        created_at=datetime.fromisoformat(arguments.created_at.replace("Z", "+00:00")),
        protocol=protocol,
        plan=plan,
        generation=generation,
        audit=audit,
        corpus=corpus,
        calibration_report=calibration_report,
        holdout_report=holdout_report,
    )
    _write_json(arguments.output / "EVALUATION_SUMMARY-v1.json", summary.model_dump(mode="json"))


def _prepare_runtime_config(arguments: argparse.Namespace) -> None:
    """Create an evaluation-only WSL endpoint without copying production state."""

    payload = json.loads(arguments.source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dogfood runtime config must be a JSON object")
    state_root = arguments.state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    payload.update(
        {
            "repository_root": str(arguments.repository.resolve()),
            "state_root": str(state_root),
            "database_path": str(state_root / "runtime.sqlite3"),
            "raw_store_path": str(state_root / "raw"),
            "source_codex_home": str(arguments.codex_home.resolve()),
            "codex_executable": str(arguments.codex_executable.resolve()),
            "windows_interop": False,
            "runtime_pin_path": str(arguments.runtime_pin.resolve()),
            "target_codex_home": None,
            "target_codex_executable": None,
            "target_windows_interop": None,
            "target_runtime_pin_path": None,
            "gateway_workspace_root": str(state_root / "gateway-workspaces"),
            "feedback_detector_mode": "review",
            "semantic_promotion_evaluation_digest": None,
        }
    )
    _write_json(arguments.output, payload)


def _repair_report(arguments: argparse.Namespace) -> None:
    report = _load_report(arguments.input)
    repaired = repair_semantic_evaluation_failures(report)
    _write_json(
        arguments.output,
        {
            "report": repaired.model_dump(mode="json"),
            "report_digest": repaired.content_digest,
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--archetypes", type=Path, required=True)
    prepare.add_argument("--created-at", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.set_defaults(handler=_prepare)

    prepare_audit = commands.add_parser("prepare-audit")
    prepare_audit.add_argument("--plan", type=Path, required=True)
    prepare_audit.add_argument("--generation", type=Path, required=True)
    prepare_audit.add_argument("--output", type=Path, required=True)
    prepare_audit.set_defaults(handler=_prepare_audit)

    attest_generation = commands.add_parser("attest-generation")
    attest_generation.add_argument("--plan", type=Path, required=True)
    attest_generation.add_argument("--proposal", type=Path, required=True)
    attest_generation.add_argument("--output", type=Path, required=True)
    attest_generation.set_defaults(handler=_attest_generation)

    attest_audit = commands.add_parser("attest-audit")
    attest_audit.add_argument("--plan", type=Path, required=True)
    attest_audit.add_argument("--generation", type=Path, required=True)
    attest_audit.add_argument("--proposal", type=Path, required=True)
    attest_audit.add_argument("--output", type=Path, required=True)
    attest_audit.set_defaults(handler=_attest_audit)

    prepare_incremental_audit = commands.add_parser("prepare-incremental-audit")
    prepare_incremental_audit.add_argument("--plan", type=Path, required=True)
    prepare_incremental_audit.add_argument("--base-generation", type=Path, required=True)
    prepare_incremental_audit.add_argument("--base-audit", type=Path, required=True)
    prepare_incremental_audit.add_argument("--revised-generation", type=Path, required=True)
    prepare_incremental_audit.add_argument("--output", type=Path, required=True)
    prepare_incremental_audit.set_defaults(handler=_prepare_incremental_audit)

    attest_incremental_audit = commands.add_parser("attest-incremental-audit")
    attest_incremental_audit.add_argument("--base-generation", type=Path, required=True)
    attest_incremental_audit.add_argument("--base-audit", type=Path, required=True)
    attest_incremental_audit.add_argument("--revised-generation", type=Path, required=True)
    attest_incremental_audit.add_argument("--proposal", type=Path, required=True)
    attest_incremental_audit.add_argument("--output", type=Path, required=True)
    attest_incremental_audit.set_defaults(handler=_attest_incremental_audit)

    compose_audit = commands.add_parser("compose-audit")
    compose_audit.add_argument("--base-generation", type=Path, required=True)
    compose_audit.add_argument("--base-audit", type=Path, required=True)
    compose_audit.add_argument("--revised-generation", type=Path, required=True)
    compose_audit.add_argument("--incremental-audit", type=Path, required=True)
    compose_audit.add_argument("--output", type=Path, required=True)
    compose_audit.set_defaults(handler=_compose_audit)

    prepare_remediation = commands.add_parser("prepare-remediation")
    prepare_remediation.add_argument("--plan", type=Path, required=True)
    prepare_remediation.add_argument("--generation", type=Path, required=True)
    prepare_remediation.add_argument("--audit", type=Path, required=True)
    prepare_remediation.add_argument("--output", type=Path, required=True)
    prepare_remediation.set_defaults(handler=_prepare_remediation)

    apply_remediation = commands.add_parser("apply-remediation")
    apply_remediation.add_argument("--plan", type=Path, required=True)
    apply_remediation.add_argument("--generation", type=Path, required=True)
    apply_remediation.add_argument("--audit", type=Path, required=True)
    apply_remediation.add_argument("--remediation", type=Path, required=True)
    apply_remediation.add_argument("--output", type=Path, required=True)
    apply_remediation.set_defaults(handler=_apply_remediation)

    attest_remediation = commands.add_parser("attest-remediation")
    attest_remediation.add_argument("--generation", type=Path, required=True)
    attest_remediation.add_argument("--audit", type=Path, required=True)
    attest_remediation.add_argument("--proposal", type=Path, required=True)
    attest_remediation.add_argument("--output", type=Path, required=True)
    attest_remediation.set_defaults(handler=_attest_remediation)

    freeze = commands.add_parser("freeze")
    freeze.add_argument("--plan", type=Path, required=True)
    freeze.add_argument("--generation", type=Path, required=True)
    freeze.add_argument("--audit", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.set_defaults(handler=_freeze)

    summarize = commands.add_parser("summarize")
    summarize.add_argument("--protocol", type=Path, required=True)
    summarize.add_argument("--plan", type=Path, required=True)
    summarize.add_argument("--generation", type=Path, required=True)
    summarize.add_argument("--audit", type=Path, required=True)
    summarize.add_argument("--corpus", type=Path, required=True)
    summarize.add_argument("--calibration-report", type=Path, required=True)
    summarize.add_argument("--holdout-report", type=Path, required=True)
    summarize.add_argument("--created-at", required=True)
    summarize.add_argument("--output", type=Path, required=True)
    summarize.set_defaults(handler=_summarize)

    runtime_config = commands.add_parser("prepare-runtime-config")
    runtime_config.add_argument("--source", type=Path, required=True)
    runtime_config.add_argument("--repository", type=Path, required=True)
    runtime_config.add_argument("--state-root", type=Path, required=True)
    runtime_config.add_argument("--codex-home", type=Path, required=True)
    runtime_config.add_argument("--codex-executable", type=Path, required=True)
    runtime_config.add_argument("--runtime-pin", type=Path, required=True)
    runtime_config.add_argument("--output", type=Path, required=True)
    runtime_config.set_defaults(handler=_prepare_runtime_config)

    repair_report = commands.add_parser("repair-report")
    repair_report.add_argument("--input", type=Path, required=True)
    repair_report.add_argument("--output", type=Path, required=True)
    repair_report.set_defaults(handler=_repair_report)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
