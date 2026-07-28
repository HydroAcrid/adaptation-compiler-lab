"""Read-only integrity audit for immutable Milestone 6A public artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.benchmark.codex_development import (
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.longitudinal import (
    load_longitudinal_comparison,
)
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    LongitudinalBlindReport,
    LongitudinalJudgeDecision,
    load_compiled_materials,
    load_evidence_packets,
    load_execution_amendment,
    load_execution_protocol,
)
from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
    verify_private_plan_digest,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class LongitudinalIntegrityError(ValueError):
    """A frozen Milestone 6A binding no longer matches."""


class HistoricalByteDiscrepancy(FrozenModel):
    """Known receipt defect retained without rewriting historical evidence."""

    stage: int
    recorded_bytes: int
    exact_written_bytes: int


class Milestone6AIntegrityAudit(FrozenModel):
    """Deterministic summary of the public 6A digest chain."""

    audit_version: Literal["1.0.0"] = "1.0.0"
    outcome: Literal["pass"] = "pass"
    private_plan_digest: Sha256Digest
    seed_commitment: Sha256Digest
    blind_report_digest: Sha256Digest
    judge_decision_digest: Sha256Digest
    checks: tuple[str, ...]
    historical_profile_byte_discrepancies: tuple[HistoricalByteDiscrepancy, ...]
    frozen_artifacts_modified: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LongitudinalIntegrityError(f"{path.name} is not a JSON object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LongitudinalIntegrityError(message)


def audit_milestone_6a_integrity(
    benchmark_root: Path,
    *,
    private_plan_path: Path,
    randomization_seed_path: Path,
) -> Milestone6AIntegrityAudit:
    """Verify public bindings plus the exact private plan without opening raw traces."""

    root = benchmark_root.resolve()
    results = root / "results"
    design = load_longitudinal_comparison(root)
    protocol = load_execution_protocol(root)
    amendment = load_execution_amendment(root)
    packets = load_evidence_packets(root)
    compiled = load_compiled_materials(root)
    completion = _object(results / "completion.json")
    profile_receipt = _object(root / "profile-construction-receipt.json")
    judge_receipt = _object(results / "judge-receipt.json")
    unblinded = _object(results / "unblinded-result.json")
    blind_report = LongitudinalBlindReport.model_validate_json(
        (results / "blind-report.json").read_bytes()
    )

    preregistration_hex = (
        (root / "PREREGISTRATION-v1.0.sha256").read_text(encoding="ascii").split()[0]
    )
    preregistration_digest = f"sha256:{preregistration_hex}"
    _require(
        sha256_file(root / "PREREGISTRATION-v1.0.json") == preregistration_digest,
        "preregistration checksum file no longer matches",
    )
    _require(
        protocol.preregistration_sha256 == preregistration_digest,
        "execution protocol no longer binds the preregistration",
    )
    _require(protocol.design_digest == design.content_digest, "design digest drifted")
    _require(
        tuple(item.content_digest for item in packets) == protocol.evidence_packet_digests,
        "evidence packet digest drifted",
    )
    _require(
        tuple(sha256_bytes(item.encode("utf-8")) for item in compiled)
        == protocol.compiled_material_digests,
        "compiled material digest drifted",
    )
    _require(
        sha256_file(root / "DOGFOOD_METRICS-v1.0.json") == protocol.dogfood_metrics_digest,
        "dogfood metrics digest drifted",
    )
    repo = root.parent
    _require(
        sha256_file(repo / "src/adaptation_compiler_lab/benchmark/longitudinal_scoring.py")
        == protocol.independent_scorer_digest,
        "frozen independent scorer digest drifted",
    )
    fixture_digests = tuple(
        development_tree_digest(root / task.fixture_directory) for task in design.tasks
    )
    _require(fixture_digests == protocol.task_fixture_digests, "task fixture digest drifted")

    expected_private_plan = completion.get("private_plan_ref_digest")
    if not isinstance(expected_private_plan, str):
        raise LongitudinalIntegrityError("completion omitted private-plan digest")
    try:
        private_plan_digest = verify_private_plan_digest(
            private_plan_path.resolve(),
            expected_private_plan,
        )
    except ValueError as error:
        raise LongitudinalIntegrityError(str(error)) from error
    private_plan = _object(private_plan_path.resolve())
    try:
        encoded_seed = randomization_seed_path.resolve().read_bytes().strip()
        seed = base64.b64decode(encoded_seed, validate=True)
    except (OSError, ValueError) as error:
        raise LongitudinalIntegrityError(
            "randomization seed is unavailable or malformed"
        ) from error
    _require(len(seed) == 32, "randomization seed length drifted")
    seed_commitment = sha256_bytes(seed)
    _require(
        private_plan.get("seed_commitment") == seed_commitment,
        "private plan no longer binds the randomization seed",
    )
    _require(
        completion.get("seed_commitment") == seed_commitment,
        "completion no longer binds the randomization seed",
    )
    _require(
        unblinded.get("randomization_seed_commitment") == seed_commitment,
        "unblinded result no longer binds the randomization seed",
    )
    _require(
        unblinded.get("private_plan_digest") == private_plan_digest,
        "unblinded result no longer binds the private plan",
    )

    _require(blind_report.design_digest == design.content_digest, "blind report design drifted")
    _require(
        blind_report.execution_protocol_digest == canonical_digest(protocol),
        "blind report protocol binding drifted",
    )
    _require(
        blind_report.execution_amendment_digest == amendment.content_digest,
        "blind report amendment binding drifted",
    )
    _require(
        blind_report.profile_construction_receipt_digest
        == sha256_file(root / "profile-construction-receipt.json"),
        "blind report profile receipt binding drifted",
    )
    _require(
        completion.get("blind_report_digest") == blind_report.content_digest,
        "completion blind-report binding drifted",
    )
    _require(
        completion.get("judge_input_bindings_digest")
        == sha256_file(results / "judge-input-bindings.json"),
        "completion judge-input binding drifted",
    )

    decision_value = judge_receipt.get("decision")
    if not isinstance(decision_value, dict):
        raise LongitudinalIntegrityError("judge receipt omitted its decision")
    decision = LongitudinalJudgeDecision.model_validate_json(canonical_json(decision_value))
    decision_digest = canonical_digest(decision)
    _require(
        judge_receipt.get("decision_digest") == decision_digest,
        "judge decision digest drifted",
    )
    _require(
        judge_receipt.get("blind_packet_digest") == sha256_file(results / "blind-rating-packet.md"),
        "judge blind-packet binding drifted",
    )
    _require(
        judge_receipt.get("judge_input_bindings_digest")
        == sha256_file(results / "judge-input-bindings.json"),
        "judge input-binding digest drifted",
    )
    _require(
        judge_receipt.get("execution_amendment_digest") == amendment.content_digest,
        "judge amendment binding drifted",
    )
    _require(
        unblinded.get("blind_report_digest") == blind_report.content_digest,
        "unblinded blind-report binding drifted",
    )
    _require(
        unblinded.get("judge_decision_digest") == decision_digest,
        "unblinded judge binding drifted",
    )
    _require(
        unblinded.get("design_digest") == design.content_digest,
        "unblinded design binding drifted",
    )
    _require(
        unblinded.get("execution_amendment_digest") == amendment.content_digest,
        "unblinded amendment binding drifted",
    )

    stages = profile_receipt.get("stages")
    if not isinstance(stages, list) or len(stages) != 3:
        raise LongitudinalIntegrityError("profile receipt stages are malformed")
    discrepancies: list[HistoricalByteDiscrepancy] = []
    for stage, receipt_value in enumerate(stages, start=1):
        if not isinstance(receipt_value, dict):
            raise LongitudinalIntegrityError("profile receipt stage is malformed")
        profile_path = root / "condition-materials" / f"strong-profile-stage-{stage}.md"
        exact_bytes = profile_path.read_bytes()
        _require(
            receipt_value.get("profile_digest")
            == f"sha256:{hashlib.sha256(exact_bytes).hexdigest()}",
            f"profile Stage {stage} digest drifted",
        )
        recorded = receipt_value.get("profile_bytes")
        if not isinstance(recorded, int):
            raise LongitudinalIntegrityError("profile byte measurement is malformed")
        if recorded != len(exact_bytes):
            discrepancies.append(
                HistoricalByteDiscrepancy(
                    stage=stage,
                    recorded_bytes=recorded,
                    exact_written_bytes=len(exact_bytes),
                )
            )
    _require(
        tuple(
            (item.stage, item.exact_written_bytes - item.recorded_bytes) for item in discrepancies
        )
        == ((1, 1), (2, 1), (3, 1)),
        "historical profile-byte discrepancy changed unexpectedly",
    )

    return Milestone6AIntegrityAudit(
        private_plan_digest=private_plan_digest,
        seed_commitment=seed_commitment,
        blind_report_digest=blind_report.content_digest,
        judge_decision_digest=decision_digest,
        checks=(
            "blind_and_unblinded_result_chain",
            "compiled_materials",
            "evidence_packets",
            "frozen_independent_scorer",
            "judge_bindings",
            "preregistration_and_design",
            "private_plan_exact_bytes",
            "profile_material_digests",
            "randomization_seed_commitment",
            "task_fixtures",
        ),
        historical_profile_byte_discrepancies=tuple(discrepancies),
    )
