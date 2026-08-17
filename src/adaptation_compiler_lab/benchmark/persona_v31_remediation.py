"""One-session neutral-schema diagnostic for the failed v3.1 compiled sensor."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import model_validator

from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaMaterialSnapshot,
    PersonaObjectiveScore,
)
from adaptation_compiler_lab.benchmark.persona_v31 import PersonaV31SensorResult
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest


class PersonaV31RemediationProtocol(FrozenModel):
    protocol_version: Literal["1.0.0"] = "1.0.0"
    protocol_id: Literal["persona-v31-neutral-schema-remediation"] = (
        "persona-v31-neutral-schema-remediation"
    )
    purpose: Literal["instrument_schema_diagnosis_only"] = "instrument_schema_diagnosis_only"
    prior_smoke_result_preserved: Literal[True] = True
    same_public_calibration_fixture: Literal[True] = True
    fresh_effectiveness_evidence: Literal[False] = False
    semantic_prompt_changed: Literal[False] = False
    model_or_reasoning_changed: Literal[False] = False
    host_policy_changed: Literal[False] = False
    oracle_changed: Literal[False] = False
    output_schema_only_change: Literal[True] = True
    overlapping_learning_branches_before: Literal[4] = 4
    neutral_learning_branches_after: Literal[1] = 1
    isolated_luna_sessions: Literal[1] = 1
    profile_sessions: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    counts_toward_effectiveness_evidence: Literal[False] = False
    full_grid_execution_authorized: Literal[False] = False


class PersonaV31RemediationFreeze(FrozenModel):
    freeze_version: Literal["1.0.0"] = "1.0.0"
    protocol_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    prior_smoke_freeze_digest: Sha256Digest
    prior_smoke_report_digest: Sha256Digest
    unchanged_role_contract_digest: Sha256Digest
    unchanged_prompt_template_digest: Sha256Digest
    unchanged_batch_input_digest: Sha256Digest
    unchanged_batch_prompt_digest: Sha256Digest
    previous_output_schema_digest: Sha256Digest
    remediated_output_schema_digest: Sha256Digest
    benchmark_module_digest: Sha256Digest
    runner_module_digest: Sha256Digest
    execution_started: Literal[False] = False
    session_maximum: Literal[1] = 1
    full_grid_execution_authorized: Literal[False] = False


class PersonaV31RemediationReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    protocol_digest: Sha256Digest
    freeze_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    prior_smoke_report_digest: Sha256Digest
    remediated_sensor_result: PersonaV31SensorResult
    remediated_compiled_material: PersonaMaterialSnapshot
    remediated_compiled_score: PersonaObjectiveScore
    task_only_false_activations: int
    schema_hypothesis_supported: bool
    instrument_remediation_passed: bool
    prior_smoke_result_changed: Literal[False] = False
    counts_toward_effectiveness_evidence: Literal[False] = False
    isolated_luna_sessions: Literal[1] = 1
    provider_billed_calls: Literal[0] = 0
    full_grid_execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def report_is_exact(self) -> Self:
        passed = self.remediated_compiled_score.exact and self.task_only_false_activations == 0
        if self.schema_hypothesis_supported is not passed:
            raise ValueError("v3.1 schema hypothesis flag drifted from objective evidence")
        if self.instrument_remediation_passed is not passed:
            raise ValueError("v3.1 remediation pass flag drifted from objective evidence")
        return self


def persona_v31_remediation_schemas() -> dict[str, dict[str, object]]:
    return {
        "persona-v31-remediation-protocol.schema.json": (
            PersonaV31RemediationProtocol.model_json_schema()
        ),
        "persona-v31-remediation-freeze.schema.json": (
            PersonaV31RemediationFreeze.model_json_schema()
        ),
        "persona-v31-remediation-report.schema.json": (
            PersonaV31RemediationReport.model_json_schema()
        ),
    }
