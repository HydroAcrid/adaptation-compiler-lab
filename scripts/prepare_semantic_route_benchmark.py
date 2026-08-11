"""Prepare, freeze, blindly audit, and summarize semantic route discrimination."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from adaptation_compiler_lab.automatic_runtime.semantic_evaluation import (
    SemanticEvaluationReport,
    load_semantic_feedback_corpus,
)
from adaptation_compiler_lab.automatic_runtime.semantic_route_benchmark import (
    BlindRouteClass,
    BlindRouteReason,
    BlindRouteScope,
    SemanticRouteBlindAudit,
    SemanticRouteGeneration,
    SemanticRoutePlan,
    SemanticRouteProtocol,
    attest_semantic_route_blind_audit,
    attest_semantic_route_generation,
    build_semantic_route_design,
    freeze_semantic_route_corpus,
    semantic_route_blind_audit_prompt,
    semantic_route_generation_prompt,
    summarize_semantic_route_benchmark,
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
    """Adapt Pydantic output to the CLI all-properties-required contract."""

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
    return cast(dict[str, Any], schema)


def _blind_output_schema() -> dict[str, Any]:
    """Encode route/reason/scope coherence directly in structured output."""

    schema = _strict_model_output_schema(SemanticRouteBlindAudit)
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict) or "SemanticRouteBlindEntry" not in definitions:
        raise ValueError("blind route schema is missing its entry definition")
    case_id = {
        "maxLength": 128,
        "minLength": 1,
        "pattern": "^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$",
        "type": "string",
    }
    required = ["case_id", "classification", "scope", "reason"]
    branches: list[dict[str, Any]] = []
    reason_by_class = {
        BlindRouteClass.MEMORY: BlindRouteReason.NON_NORMATIVE_FACT,
        BlindRouteClass.POSITIVE_EXAMPLE: BlindRouteReason.ENDORSED_REUSE,
        BlindRouteClass.PREFERENCE: BlindRouteReason.STABLE_CHOICE,
        BlindRouteClass.PROCEDURE: BlindRouteReason.ORDERED_TRIGGER_WORKFLOW,
        BlindRouteClass.PROMPT_RULE: BlindRouteReason.HARD_INVARIANT,
        BlindRouteClass.REVOCATION: BlindRouteReason.EXACT_ARTIFACT_REMOVAL,
    }
    for route_class, reason in reason_by_class.items():
        branches.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": {
                    "case_id": case_id,
                    "classification": {"type": "string", "const": route_class.value},
                    "scope": {
                        "type": "string",
                        "enum": [
                            BlindRouteScope.CURRENT_CONTEXT.value,
                            BlindRouteScope.PERMANENT_PROFILE.value,
                        ],
                    },
                    "reason": {"type": "string", "const": reason.value},
                },
            }
        )
    for route_class, scope, reason in (
        (
            BlindRouteClass.AMBIGUOUS,
            BlindRouteScope.AMBIGUOUS,
            BlindRouteReason.AMBIGUOUS,
        ),
        (
            BlindRouteClass.NO_DURABLE_SIGNAL,
            BlindRouteScope.NO_DURABLE_SIGNAL,
            BlindRouteReason.NO_DURABLE_SIGNAL,
        ),
    ):
        branches.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": {
                    "case_id": case_id,
                    "classification": {"type": "string", "const": route_class.value},
                    "scope": {"type": "string", "const": scope.value},
                    "reason": {"type": "string", "const": reason.value},
                },
            }
        )
    definitions["SemanticRouteBlindEntry"] = {"anyOf": branches}
    return schema


def _prepare(arguments: argparse.Namespace) -> None:
    created_at = datetime.fromisoformat(arguments.created_at.replace("Z", "+00:00"))
    plan, protocol = build_semantic_route_design(
        created_at=created_at,
        revision=arguments.revision,
    )
    suffix = arguments.revision
    _write_json(arguments.output / f"PLAN-{suffix}.json", plan.model_dump(mode="json"))
    _write_json(arguments.output / f"PROTOCOL-{suffix}.json", protocol.model_dump(mode="json"))
    generation_schema = _strict_model_output_schema(SemanticRouteGeneration)
    generation_properties = generation_schema.get("properties")
    if not isinstance(generation_properties, dict):
        raise ValueError("semantic route generation schema has no properties")
    generation_properties["generation_version"] = {
        "const": {
            "v1": "1.0.0",
            "v2": "2.0.0",
            "v3": "3.0.0",
            "v4": "4.0.0",
        }[arguments.revision],
        "title": "Generation Version",
        "type": "string",
    }
    _write_json(
        arguments.output / f"GENERATION_SCHEMA-{suffix}.json",
        generation_schema,
    )
    _write_text(
        arguments.output / f"GENERATOR_PACKET-{suffix}.txt",
        semantic_route_generation_prompt(plan),
    )


def _attest_generation(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticRoutePlan)
    proposal = _load_model(arguments.proposal, SemanticRouteGeneration)
    generation = attest_semantic_route_generation(plan, proposal)
    _write_json(arguments.output, generation.model_dump(mode="json"))


def _freeze(arguments: argparse.Namespace) -> None:
    plan = _load_model(arguments.plan, SemanticRoutePlan)
    generation = _load_model(arguments.generation, SemanticRouteGeneration)
    corpus = freeze_semantic_route_corpus(plan, generation)
    suffix = {
        "4.0.0": "v4",
        "5.0.0": "v5",
        "6.0.0": "v6",
    }[corpus.corpus_version]
    _write_json(arguments.output / f"CORPUS-{suffix}.json", corpus.model_dump(mode="json"))
    _write_text(arguments.output / f"CORPUS-{suffix}.sha256", corpus.content_digest)


def _prepare_audit(arguments: argparse.Namespace) -> None:
    generation = _load_model(arguments.generation, SemanticRouteGeneration)
    _write_json(arguments.output / "BLIND_AUDIT_SCHEMA-v1.json", _blind_output_schema())
    _write_text(
        arguments.output / f"BLIND_AUDITOR_PACKET-{arguments.auditor_id}.txt",
        semantic_route_blind_audit_prompt(
            generation,
            auditor_id=arguments.auditor_id,
        ),
    )


def _attest_audit(arguments: argparse.Namespace) -> None:
    generation = _load_model(arguments.generation, SemanticRouteGeneration)
    proposal = _load_model(arguments.proposal, SemanticRouteBlindAudit)
    audit = attest_semantic_route_blind_audit(
        generation,
        proposal,
        auditor_id=arguments.auditor_id,
    )
    _write_json(arguments.output, audit.model_dump(mode="json"))


def _summarize(arguments: argparse.Namespace) -> None:
    created_at = datetime.fromisoformat(arguments.created_at.replace("Z", "+00:00"))
    protocol = _load_model(arguments.protocol, SemanticRouteProtocol)
    plan = _load_model(arguments.plan, SemanticRoutePlan)
    generation = _load_model(arguments.generation, SemanticRouteGeneration)
    corpus = load_semantic_feedback_corpus(arguments.corpus)
    auditor_a = _load_model(arguments.auditor_a, SemanticRouteBlindAudit)
    auditor_b = _load_model(arguments.auditor_b, SemanticRouteBlindAudit)
    summary = summarize_semantic_route_benchmark(
        created_at=created_at,
        protocol=protocol,
        plan=plan,
        generation=generation,
        corpus=corpus,
        auditor_a=auditor_a,
        auditor_b=auditor_b,
        calibration_report=_load_report(arguments.calibration_report),
        holdout_report=_load_report(arguments.holdout_report),
    )
    _write_json(arguments.output / "EVALUATION_SUMMARY-v1.json", summary.model_dump(mode="json"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--created-at", required=True)
    prepare.add_argument("--revision", choices=("v1", "v2", "v3", "v4"), default="v1")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.set_defaults(handler=_prepare)

    attest_generation = commands.add_parser("attest-generation")
    attest_generation.add_argument("--plan", type=Path, required=True)
    attest_generation.add_argument("--proposal", type=Path, required=True)
    attest_generation.add_argument("--output", type=Path, required=True)
    attest_generation.set_defaults(handler=_attest_generation)

    freeze = commands.add_parser("freeze")
    freeze.add_argument("--plan", type=Path, required=True)
    freeze.add_argument("--generation", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.set_defaults(handler=_freeze)

    prepare_audit = commands.add_parser("prepare-audit")
    prepare_audit.add_argument("--generation", type=Path, required=True)
    prepare_audit.add_argument("--auditor-id", required=True)
    prepare_audit.add_argument("--output", type=Path, required=True)
    prepare_audit.set_defaults(handler=_prepare_audit)

    attest_audit = commands.add_parser("attest-audit")
    attest_audit.add_argument("--generation", type=Path, required=True)
    attest_audit.add_argument("--proposal", type=Path, required=True)
    attest_audit.add_argument("--auditor-id", required=True)
    attest_audit.add_argument("--output", type=Path, required=True)
    attest_audit.set_defaults(handler=_attest_audit)

    summarize = commands.add_parser("summarize")
    summarize.add_argument("--created-at", required=True)
    summarize.add_argument("--protocol", type=Path, required=True)
    summarize.add_argument("--plan", type=Path, required=True)
    summarize.add_argument("--generation", type=Path, required=True)
    summarize.add_argument("--corpus", type=Path, required=True)
    summarize.add_argument("--auditor-a", type=Path, required=True)
    summarize.add_argument("--auditor-b", type=Path, required=True)
    summarize.add_argument("--calibration-report", type=Path, required=True)
    summarize.add_argument("--holdout-report", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)
    summarize.set_defaults(handler=_summarize)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
