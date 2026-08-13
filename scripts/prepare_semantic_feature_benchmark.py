"""Prepare, attest, freeze, audit, and summarize Milestone 6A.2I."""

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
from adaptation_compiler_lab.automatic_runtime.semantic_feature_benchmark import (
    SemanticArchitectureBinding,
    SemanticFeatureBlindAudit,
    SemanticFeatureGeneration,
    SemanticFeaturePlan,
    SemanticFeatureProtocol,
    SemanticFeatureRemediation,
    apply_semantic_feature_remediation,
    attest_semantic_feature_audit,
    attest_semantic_feature_generation,
    build_semantic_feature_design,
    freeze_semantic_feature_corpus,
    revise_semantic_feature_audit_protocol,
    semantic_feature_audit_prompt,
    semantic_feature_generation_prompt,
    semantic_feature_remediation_prompt,
    summarize_semantic_feature_benchmark,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def _load(path: Path, model: type[Any]) -> Any:
    return model.model_validate_json(path.read_text(encoding="utf-8"), strict=True)


def _report(path: Path) -> SemanticEvaluationReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "report" in payload:
        payload = payload["report"]
    return SemanticEvaluationReport.model_validate_json(
        json.dumps(payload, ensure_ascii=False),
        strict=True,
    )


def _strict_schema(model: type[Any]) -> dict[str, Any]:
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


def _created(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _architecture_bindings(root: Path) -> tuple[SemanticArchitectureBinding, ...]:
    return tuple(
        SemanticArchitectureBinding(component=name, digest=sha256_file(root / relative))
        for name, relative in sorted(
            {
                "benchmark": (
                    "src/adaptation_compiler_lab/automatic_runtime/semantic_feature_benchmark.py"
                ),
                "detector": "src/adaptation_compiler_lab/automatic_runtime/detector.py",
                "evaluation": (
                    "src/adaptation_compiler_lab/automatic_runtime/semantic_evaluation.py"
                ),
                "interpreter": (
                    "src/adaptation_compiler_lab/automatic_runtime/semantic_interpreter.py"
                ),
                "models": "src/adaptation_compiler_lab/automatic_runtime/models.py",
                "router": "src/adaptation_compiler_lab/automatic_runtime/semantic_routing.py",
            }.items()
        )
    )


def _prepare(arguments: argparse.Namespace) -> None:
    calibration = load_semantic_feedback_corpus(arguments.calibration)
    root = arguments.repository.resolve()
    bindings = _architecture_bindings(root)
    prior_plan = (
        None if arguments.prior_plan is None else _load(arguments.prior_plan, SemanticFeaturePlan)
    )
    prior_protocol = (
        None
        if arguments.prior_protocol is None
        else _load(arguments.prior_protocol, SemanticFeatureProtocol)
    )
    plan, protocol = build_semantic_feature_design(
        created_at=_created(arguments.created_at),
        calibration_corpus_digest=calibration.content_digest,
        architecture_bindings=bindings,
        revision=arguments.revision,
        prior_plan_digest=None if prior_plan is None else prior_plan.content_digest,
        prior_protocol_digest=(None if prior_protocol is None else prior_protocol.content_digest),
    )
    suffix = arguments.revision
    _write_json(arguments.output / f"PLAN-{suffix}.json", plan.model_dump(mode="json"))
    _write_json(arguments.output / f"PROTOCOL-{suffix}.json", protocol.model_dump(mode="json"))
    generation_schema = _strict_schema(SemanticFeatureGeneration)
    properties = generation_schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("feature generation schema lacks properties")
    properties["generation_version"] = {
        "type": "string",
        "const": {
            "v1": "1.0.0",
            "v2": "2.0.0",
            "v3": "3.0.0",
            "v4": "4.0.0",
            "v5": "5.0.0",
        }[arguments.revision],
    }
    _write_json(
        arguments.output / f"GENERATION_SCHEMA-{suffix}.json",
        generation_schema,
    )
    _write_text(
        arguments.output / f"GENERATOR_PACKET-{suffix}.txt",
        semantic_feature_generation_prompt(plan),
    )


def _attest_generation(arguments: argparse.Namespace) -> None:
    plan = _load(arguments.plan, SemanticFeaturePlan)
    proposal = _load(arguments.proposal, SemanticFeatureGeneration)
    result = attest_semantic_feature_generation(plan, proposal)
    _write_json(arguments.output, result.model_dump(mode="json"))


def _prepare_remediation(arguments: argparse.Namespace) -> None:
    plan = _load(arguments.plan, SemanticFeaturePlan)
    generation = _load(arguments.generation, SemanticFeatureGeneration)
    _write_json(
        arguments.output / "REMEDIATION_SCHEMA-v1.json",
        _strict_schema(SemanticFeatureRemediation),
    )
    _write_text(
        arguments.output / "REMEDIATION_PACKET-v1.txt",
        semantic_feature_remediation_prompt(plan, generation),
    )


def _apply_remediation(arguments: argparse.Namespace) -> None:
    plan = _load(arguments.plan, SemanticFeaturePlan)
    generation = _load(arguments.generation, SemanticFeatureGeneration)
    proposal = _load(arguments.proposal, SemanticFeatureRemediation)
    result = apply_semantic_feature_remediation(plan, generation, proposal)
    _write_json(arguments.output, result.model_dump(mode="json"))


def _freeze(arguments: argparse.Namespace) -> None:
    calibration = load_semantic_feedback_corpus(arguments.calibration)
    plan = _load(arguments.plan, SemanticFeaturePlan)
    generation = _load(arguments.generation, SemanticFeatureGeneration)
    corpus = freeze_semantic_feature_corpus(
        calibration,
        plan,
        generation,
        frozen_at=_created(arguments.frozen_at),
    )
    _write_json(arguments.output / "CORPUS-v7.json", corpus.model_dump(mode="json"))
    _write_text(arguments.output / "CORPUS-v7.sha256", corpus.content_digest)


def _prepare_audit(arguments: argparse.Namespace) -> None:
    generation = _load(arguments.generation, SemanticFeatureGeneration)
    _write_json(
        arguments.output / "BLIND_AUDIT_SCHEMA-v1.json",
        _strict_schema(SemanticFeatureBlindAudit),
    )
    _write_text(
        arguments.output / f"BLIND_AUDITOR_PACKET-{arguments.auditor_id}.txt",
        semantic_feature_audit_prompt(generation, auditor_id=arguments.auditor_id),
    )


def _revise_audit_protocol(arguments: argparse.Namespace) -> None:
    plan = _load(arguments.plan, SemanticFeaturePlan)
    prior = _load(arguments.prior_protocol, SemanticFeatureProtocol)
    protocol = revise_semantic_feature_audit_protocol(
        created_at=_created(arguments.created_at),
        plan=plan,
        prior_protocol=prior,
        architecture_bindings=_architecture_bindings(arguments.repository.resolve()),
    )
    _write_json(arguments.output, protocol.model_dump(mode="json"))


def _attest_audit(arguments: argparse.Namespace) -> None:
    generation = _load(arguments.generation, SemanticFeatureGeneration)
    proposal = _load(arguments.proposal, SemanticFeatureBlindAudit)
    result = attest_semantic_feature_audit(
        generation,
        proposal,
        auditor_id=arguments.auditor_id,
    )
    _write_json(arguments.output, result.model_dump(mode="json"))


def _summarize(arguments: argparse.Namespace) -> None:
    protocol = _load(arguments.protocol, SemanticFeatureProtocol)
    plan = _load(arguments.plan, SemanticFeaturePlan)
    generation = _load(arguments.generation, SemanticFeatureGeneration)
    corpus = load_semantic_feedback_corpus(arguments.corpus)
    auditor_a = _load(arguments.auditor_a, SemanticFeatureBlindAudit)
    auditor_b = _load(arguments.auditor_b, SemanticFeatureBlindAudit)
    summary = summarize_semantic_feature_benchmark(
        created_at=_created(arguments.created_at),
        protocol=protocol,
        plan=plan,
        generation=generation,
        corpus=corpus,
        auditor_a=auditor_a,
        auditor_b=auditor_b,
        report=_report(arguments.report),
    )
    _write_json(arguments.output / "EVALUATION_SUMMARY-v1.json", summary.model_dump(mode="json"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--created-at", required=True)
    prepare.add_argument("--revision", choices=("v1", "v2", "v3", "v4", "v5"), default="v1")
    prepare.add_argument("--prior-plan", type=Path)
    prepare.add_argument("--prior-protocol", type=Path)
    prepare.add_argument("--repository", type=Path, required=True)
    prepare.add_argument("--calibration", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.set_defaults(handler=_prepare)

    attest_generation = commands.add_parser("attest-generation")
    attest_generation.add_argument("--plan", type=Path, required=True)
    attest_generation.add_argument("--proposal", type=Path, required=True)
    attest_generation.add_argument("--output", type=Path, required=True)
    attest_generation.set_defaults(handler=_attest_generation)

    prepare_remediation = commands.add_parser("prepare-remediation")
    prepare_remediation.add_argument("--plan", type=Path, required=True)
    prepare_remediation.add_argument("--generation", type=Path, required=True)
    prepare_remediation.add_argument("--output", type=Path, required=True)
    prepare_remediation.set_defaults(handler=_prepare_remediation)

    apply_remediation = commands.add_parser("apply-remediation")
    apply_remediation.add_argument("--plan", type=Path, required=True)
    apply_remediation.add_argument("--generation", type=Path, required=True)
    apply_remediation.add_argument("--proposal", type=Path, required=True)
    apply_remediation.add_argument("--output", type=Path, required=True)
    apply_remediation.set_defaults(handler=_apply_remediation)

    freeze = commands.add_parser("freeze")
    freeze.add_argument("--calibration", type=Path, required=True)
    freeze.add_argument("--plan", type=Path, required=True)
    freeze.add_argument("--generation", type=Path, required=True)
    freeze.add_argument("--frozen-at", required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.set_defaults(handler=_freeze)

    prepare_audit = commands.add_parser("prepare-audit")
    prepare_audit.add_argument("--generation", type=Path, required=True)
    prepare_audit.add_argument("--auditor-id", required=True)
    prepare_audit.add_argument("--output", type=Path, required=True)
    prepare_audit.set_defaults(handler=_prepare_audit)

    revise_audit = commands.add_parser("revise-audit-protocol")
    revise_audit.add_argument("--created-at", required=True)
    revise_audit.add_argument("--repository", type=Path, required=True)
    revise_audit.add_argument("--plan", type=Path, required=True)
    revise_audit.add_argument("--prior-protocol", type=Path, required=True)
    revise_audit.add_argument("--output", type=Path, required=True)
    revise_audit.set_defaults(handler=_revise_audit_protocol)

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
    summarize.add_argument("--report", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)
    summarize.set_defaults(handler=_summarize)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    arguments.handler(arguments)


if __name__ == "__main__":
    main()
