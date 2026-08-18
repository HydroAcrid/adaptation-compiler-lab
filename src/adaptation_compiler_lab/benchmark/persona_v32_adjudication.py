"""Condition-neutral pre-target adjudication for the v3.2 route-oracle defect."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.automatic_runtime.models import SemanticWorkflowStructure
from adaptation_compiler_lab.automatic_runtime.semantic_routing import route_semantic_features
from adaptation_compiler_lab.benchmark.persona_v3 import PersonaV3ProfileOutput
from adaptation_compiler_lab.benchmark.persona_v32 import (
    PersonaV32ConstructionReport,
    PersonaV32FinalReport,
    PersonaV32JudgeDecision,
    PersonaV32Oracle,
    PersonaV32TaskOutcome,
    PersonaV32TrialReceipt,
)
from adaptation_compiler_lab.domain import ArtifactRoute, FrozenModel, NonEmptyStr, Sha256Digest
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


class PersonaV321Protocol(FrozenModel):
    protocol_version: Literal["3.2.1"] = "3.2.1"
    benchmark_id: Literal["temper-persona-v32-behavioral-canary"] = (
        "temper-persona-v32-behavioral-canary"
    )
    status: Literal["condition_neutral_oracle_repair_frozen"] = (
        "condition_neutral_oracle_repair_frozen"
    )
    superseded_protocol_digest: Sha256Digest
    superseded_freeze_digest: Sha256Digest
    failed_construction_report_digest: Sha256Digest
    corrected_oracle_digest: Sha256Digest
    adjudication_digest: Sha256Digest
    original_construction_sessions: Literal[3] = 3
    additional_construction_sessions: Literal[0] = 0
    target_sessions: Literal[4] = 4
    isolated_judge_sessions: Literal[2] = 2
    maximum_subscription_sessions: Literal[9] = 9
    target_tasks_changed: Literal[False] = False
    task_oracles_changed: Literal[False] = False
    target_material_bytes_changed: Literal[False] = False
    condition_mapping_changed: Literal[False] = False
    target_output_seen: Literal[False] = False
    target_tuning_permitted: Literal[False] = False
    original_result_rewritten: Literal[False] = False
    counts_toward_effectiveness_evidence: Literal[True] = True
    codex_cli_version: Literal["codex-cli 0.146.0"] = "codex-cli 0.146.0"
    codex_binary_digest: Literal[
        "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    ] = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    target_reasoning_effort: Literal["medium"] = "medium"
    judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    judge_reasoning_effort: Literal["xhigh"] = "xhigh"
    provider_billed_calls: Literal[0] = 0
    api_keys_permitted: Literal[False] = False
    sealed_external_validation_access_permitted: Literal[False] = False


class PersonaV32ConstructionAdjudication(FrozenModel):
    adjudication_version: Literal["1.1.0"] = "1.1.0"
    original_protocol_digest: Sha256Digest
    original_freeze_digest: Sha256Digest
    original_oracle_digest: Sha256Digest
    original_report_digest: Sha256Digest
    static_reviewed_output_digest: Sha256Digest
    route_policy_source_digest: Sha256Digest
    corrected_oracle_digest: Sha256Digest
    original_turn_2_route: Literal[ArtifactRoute.PREFERENCE] = ArtifactRoute.PREFERENCE
    corrected_turn_2_route: Literal[ArtifactRoute.PROCEDURE] = ArtifactRoute.PROCEDURE
    compiled_observed_turn_2_route: Literal[ArtifactRoute.PROCEDURE] = ArtifactRoute.PROCEDURE
    static_observed_turn_2_route: Literal[ArtifactRoute.PROCEDURE] = ArtifactRoute.PROCEDURE
    static_turn_2_workflow: Literal[SemanticWorkflowStructure.ORDERED_SEQUENCE] = (
        SemanticWorkflowStructure.ORDERED_SEQUENCE
    )
    deterministic_static_route: Literal[ArtifactRoute.PROCEDURE] = ArtifactRoute.PROCEDURE
    task_oracle_digest_before: Sha256Digest
    task_oracle_digest_after: Sha256Digest
    compiled_material_digest_before: Sha256Digest
    compiled_material_digest_after: Sha256Digest
    static_material_digest_before: Sha256Digest
    static_material_digest_after: Sha256Digest
    original_compiled_score_preserved: Literal[True] = True
    original_static_score_preserved: Literal[True] = True
    target_tasks_unchanged: Literal[True] = True
    task_oracles_unchanged: Literal[True] = True
    target_material_bytes_unchanged: Literal[True] = True
    condition_mapping_unchanged: Literal[True] = True
    target_sessions_started: Literal[False] = False
    judge_sessions_started: Literal[False] = False
    adjudication_sessions: Literal[0] = 0
    condition_neutral: Literal[True] = True
    corrected_construction_exact: Literal[True] = True
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def unchanged_bindings_are_exact(self) -> Self:
        if self.task_oracle_digest_before != self.task_oracle_digest_after:
            raise ValueError("v3.2 adjudication changed a target-task oracle")
        if self.compiled_material_digest_before != self.compiled_material_digest_after:
            raise ValueError("v3.2 adjudication changed compiled target material")
        if self.static_material_digest_before != self.static_material_digest_after:
            raise ValueError("v3.2 adjudication changed static target material")
        return self


class PersonaV32MaterialsFreezeV11(FrozenModel):
    freeze_version: Literal["1.1.0"] = "1.1.0"
    successor_protocol_digest: Sha256Digest
    original_construction_report_digest: Sha256Digest
    construction_adjudication_digest: Sha256Digest
    corrected_oracle_digest: Sha256Digest
    compiled_material_digest: Sha256Digest
    static_material_digest: Sha256Digest
    compiled_material_bytes: int = Field(ge=1, le=3000)
    static_material_bytes: int = Field(ge=1, le=3000)
    target_runner_digest: Sha256Digest
    judge_runner_digest: Sha256Digest
    unblinder_digest: Sha256Digest
    target_sessions_started: Literal[False] = False
    corrected_construction_exact: Literal[True] = True
    task_oracles_unchanged: Literal[True] = True
    target_material_bytes_unchanged: Literal[True] = True
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32JudgeInstrumentIncident(FrozenModel):
    incident_version: Literal["1.0.0"] = "1.0.0"
    incident_id: Literal["persona-v32-judge-role-binding-001"] = (
        "persona-v32-judge-role-binding-001"
    )
    failure_code: Literal["role_id_did_not_start_with_bound_persona"] = (
        "role_id_did_not_start_with_bound_persona"
    )
    target_report_already_complete: Literal[True] = True
    judge_model_session_started: Literal[False] = False
    judge_output_produced: Literal[False] = False
    target_result_changed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32JudgeAmendment(FrozenModel):
    amendment_version: Literal["1.2.0"] = "1.2.0"
    superseded_material_freeze_digest: Sha256Digest
    incident_digest: Sha256Digest
    prior_judge_runner_digest: Sha256Digest
    amended_judge_runner_digest: Sha256Digest
    amended_unblinder_digest: Sha256Digest
    role_binding_change: Literal["persona_prefix_matches_single_blind_judge_id"] = (
        "persona_prefix_matches_single_blind_judge_id"
    )
    additional_target_sessions: Literal[0] = 0
    failed_judge_sessions: Literal[0] = 0
    replacement_judge_sessions_authorized: Literal[2] = 2
    tasks_unchanged: Literal[True] = True
    task_oracles_unchanged: Literal[True] = True
    target_outputs_unchanged: Literal[True] = True
    target_materials_unchanged: Literal[True] = True
    condition_mapping_unchanged: Literal[True] = True
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32MaterialsFreezeV12(PersonaV32MaterialsFreezeV11):
    judge_amendment_version: Literal["1.2.0"] = "1.2.0"
    superseded_material_freeze_digest: Sha256Digest
    judge_incident_digest: Sha256Digest
    judge_amendment_digest: Sha256Digest


class PersonaV32UnblindInstrumentIncident(FrozenModel):
    incident_version: Literal["1.0.0"] = "1.0.0"
    incident_id: Literal["persona-v32-strict-json-binding-001"] = (
        "persona-v32-strict-json-binding-001"
    )
    failure_code: Literal["strict_python_validation_rejected_json_shapes"] = (
        "strict_python_validation_rejected_json_shapes"
    )
    target_report_complete: Literal[True] = True
    judge_receipts_complete: Literal[True] = True
    condition_mapping_authorized_after_judging: Literal[True] = True
    final_report_produced: Literal[False] = False
    model_session_started: Literal[False] = False
    target_or_judge_result_changed: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32UnblindAmendment(FrozenModel):
    amendment_version: Literal["1.3.0"] = "1.3.0"
    superseded_material_freeze_digest: Sha256Digest
    incident_digest: Sha256Digest
    prior_unblinder_digest: Sha256Digest
    amended_unblinder_digest: Sha256Digest
    binding_change: Literal["strict_json_deserialization_before_model_binding"] = (
        "strict_json_deserialization_before_model_binding"
    )
    target_report_unchanged: Literal[True] = True
    judge_receipts_unchanged: Literal[True] = True
    condition_mapping_unchanged: Literal[True] = True
    scoring_logic_unchanged: Literal[True] = True
    model_sessions: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32MaterialsFreezeV13(PersonaV32MaterialsFreezeV12):
    unblind_amendment_version: Literal["1.3.0"] = "1.3.0"
    superseded_unblind_material_freeze_digest: Sha256Digest
    unblind_incident_digest: Sha256Digest
    unblind_amendment_digest: Sha256Digest


class PersonaV32FinalReportV11(PersonaV32FinalReport):
    amendment_version: Literal["1.1.0"] = "1.1.0"
    original_protocol_digest: Sha256Digest
    original_freeze_digest: Sha256Digest
    corrected_oracle_digest: Sha256Digest
    construction_adjudication_digest: Sha256Digest
    original_construction_gate_passed: Literal[False] = False
    corrected_construction_gate_passed: Literal[True] = True
    task_outcomes: Annotated[tuple[PersonaV32TaskOutcome, ...], Field(min_length=2, max_length=2)]


class PersonaV32ScoringInstrumentIncident(FrozenModel):
    """Durable invalidation of the first post-unblind score and gate."""

    incident_version: Literal["1.0.0"] = "1.0.0"
    incident_id: Literal["persona-v32-policy-observer-gate-002"] = (
        "persona-v32-policy-observer-gate-002"
    )
    original_final_report_digest: Sha256Digest
    target_blind_report_digest: Sha256Digest
    invalidation_note_digest: Sha256Digest
    affected_task_id: Literal["tide-ledger-incident-transfer"] = "tide-ledger-incident-transfer"
    affected_output_ids: Annotated[tuple[str, ...], Field(min_length=2, max_length=2)]
    original_checks_passed_per_output: Literal[0] = 0
    original_checks_total_per_output: Literal[8] = 8
    original_report_gate_passed: Literal[True] = True
    observer_rejected_capability_free_python: Literal[True] = True
    gate_omitted_direct_check_total_requirement: Literal[True] = True
    original_report_invalid: Literal[True] = True
    target_outputs_changed: Literal[False] = False
    judge_results_changed: Literal[False] = False
    task_oracles_changed: Literal[False] = False
    condition_mapping_changed: Literal[False] = False
    model_sessions: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32ScoringAmendment(FrozenModel):
    """Post-unblind, condition-symmetric repair for frozen-output rescoring."""

    amendment_version: Literal["1.4.0"] = "1.4.0"
    incident_digest: Sha256Digest
    invalidated_final_report_digest: Sha256Digest
    prior_observer_digest: Sha256Digest
    amended_observer_digest: Sha256Digest
    prior_scorer_digest: Sha256Digest
    amended_scorer_digest: Sha256Digest
    frozen_rescorer_digest: Sha256Digest
    amended_unblinder_digest: Sha256Digest
    supported_capability_free_forms: tuple[
        Literal["tuple_concatenation"],
        Literal["local_list_append_extend_and_tuple_conversion"],
    ] = (
        "tuple_concatenation",
        "local_list_append_extend_and_tuple_conversion",
    )
    direct_check_totals_required: Literal[True] = True
    negative_behavior_controls_required: Literal[True] = True
    forbidden_capability_controls_required: Literal[True] = True
    post_unblind_repair: Literal[True] = True
    original_results_preserved: Literal[True] = True
    exact_frozen_diffs_only: Literal[True] = True
    target_outputs_unchanged: Literal[True] = True
    judge_results_unchanged: Literal[True] = True
    task_oracles_unchanged: Literal[True] = True
    condition_materials_unchanged: Literal[True] = True
    condition_mapping_unchanged: Literal[True] = True
    target_or_judge_model_sessions: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32FrozenRescoreTrial(FrozenModel):
    rescore_version: Literal["1.4.0"] = "1.4.0"
    blind_output_id: NonEmptyStr
    task_id: NonEmptyStr
    original_diff_digest: Sha256Digest
    original_scorer_output_digest: Sha256Digest
    corrected_scorer_output_digest: Sha256Digest
    objective_checks_passed: int = Field(ge=0)
    objective_checks_total: int = Field(ge=1)
    diagnostic_checks_passed: int = Field(ge=0)
    diagnostic_checks_total: int = Field(ge=1)
    neutral_checks_passed: int = Field(ge=0)
    neutral_checks_total: int = Field(ge=1)
    behavior_failures: tuple[str, ...]
    behavior_conformant: bool

    @model_validator(mode="after")
    def conformance_matches_direct_checks(self) -> Self:
        passed = (
            self.objective_checks_passed
            + self.diagnostic_checks_passed
            + self.neutral_checks_passed
        )
        total = (
            self.objective_checks_total + self.diagnostic_checks_total + self.neutral_checks_total
        )
        if self.behavior_conformant != (passed == total and not self.behavior_failures):
            raise ValueError("v3.2 frozen rescore conformance is inconsistent")
        return self


class PersonaV32FrozenRescoreReport(FrozenModel):
    report_version: Literal["1.4.0"] = "1.4.0"
    scoring_amendment_digest: Sha256Digest
    invalidated_final_report_digest: Sha256Digest
    target_blind_report_digest: Sha256Digest
    corrected_observer_digest: Sha256Digest
    corrected_scorer_digest: Sha256Digest
    trials: Annotated[tuple[PersonaV32FrozenRescoreTrial, ...], Field(min_length=4, max_length=4)]
    all_observer_receipts_succeeded: bool
    all_check_totals_passed: bool
    exact_frozen_diffs_only: Literal[True] = True
    original_results_preserved: Literal[True] = True
    target_outputs_changed: Literal[False] = False
    target_model_sessions: Literal[0] = 0
    judge_model_sessions: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def summary_matches_trials(self) -> Self:
        expected = all(item.behavior_conformant for item in self.trials)
        if self.all_check_totals_passed != expected:
            raise ValueError("v3.2 frozen rescore summary is inconsistent")
        if len({item.blind_output_id for item in self.trials}) != len(self.trials):
            raise ValueError("v3.2 frozen rescore repeated an output")
        return self


class PersonaV32FinalReportV14(PersonaV32FinalReport):
    amendment_version: Literal["1.4.0"] = "1.4.0"
    original_protocol_digest: Sha256Digest
    original_freeze_digest: Sha256Digest
    corrected_oracle_digest: Sha256Digest
    construction_adjudication_digest: Sha256Digest
    original_construction_gate_passed: Literal[False] = False
    corrected_construction_gate_passed: Literal[True] = True
    task_outcomes: Annotated[tuple[PersonaV32TaskOutcome, ...], Field(min_length=2, max_length=2)]
    invalidated_final_report_digest: Sha256Digest
    scoring_incident_digest: Sha256Digest
    scoring_amendment_digest: Sha256Digest
    frozen_rescore_report_digest: Sha256Digest
    original_final_report_invalidated: Literal[True] = True
    post_unblind_instrument_repair: Literal[True] = True


class PersonaV32FinalizationInstrumentIncident(FrozenModel):
    incident_version: Literal["1.0.0"] = "1.0.0"
    incident_id: Literal["persona-v32-rescore-json-binding-003"] = (
        "persona-v32-rescore-json-binding-003"
    )
    scoring_amendment_digest: Sha256Digest
    frozen_rescore_report_digest: Sha256Digest
    prior_unblinder_digest: Sha256Digest
    failure_code: Literal["strict_python_validation_rejected_json_shapes"] = (
        "strict_python_validation_rejected_json_shapes"
    )
    frozen_rescore_complete: Literal[True] = True
    final_report_produced: Literal[False] = False
    target_or_judge_result_changed: Literal[False] = False
    model_session_started: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32FinalizationAmendment(FrozenModel):
    amendment_version: Literal["1.4.1"] = "1.4.1"
    superseded_scoring_amendment_digest: Sha256Digest
    incident_digest: Sha256Digest
    frozen_rescore_report_digest: Sha256Digest
    prior_unblinder_digest: Sha256Digest
    amended_unblinder_digest: Sha256Digest
    binding_change: Literal["strict_json_deserialization_before_final_report_binding"] = (
        "strict_json_deserialization_before_final_report_binding"
    )
    frozen_rescore_unchanged: Literal[True] = True
    target_outputs_unchanged: Literal[True] = True
    judge_results_unchanged: Literal[True] = True
    task_oracles_unchanged: Literal[True] = True
    model_sessions: Literal[0] = 0
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32FinalReportV141(PersonaV32FinalReportV14):
    amendment_version: Literal["1.4.1"] = "1.4.1"  # type: ignore[assignment]
    finalization_incident_digest: Sha256Digest
    finalization_amendment_digest: Sha256Digest


def corrected_v32_oracle(original: PersonaV32Oracle) -> PersonaV32Oracle:
    claims = tuple(
        claim.model_copy(
            update={"route": ArtifactRoute.PROCEDURE} if claim.source_turn == 2 else {}
        )
        for claim in original.material.active_claims
    )
    return original.model_copy(
        update={"material": original.material.model_copy(update={"active_claims": claims})}
    )


def bind_v32_trial_receipt(value: Mapping[str, object]) -> PersonaV32TrialReceipt:
    """Bind JSON-shaped receipt data through Pydantic's strict JSON boundary."""

    return PersonaV32TrialReceipt.model_validate_json(canonical_json(value), strict=True)


def bind_v32_judge_decision(value: Mapping[str, object]) -> PersonaV32JudgeDecision:
    """Bind JSON-shaped judge data without weakening strict model validation."""

    return PersonaV32JudgeDecision.model_validate_json(canonical_json(value), strict=True)


def strict_v32_scorer_failures(score: Mapping[str, object]) -> tuple[str, ...]:
    """Require both successful observer receipts and true direct checks."""

    failures: list[str] = []
    receipts = score.get("receipts")
    if not isinstance(receipts, dict):
        failures.append("independent scorer returned no receipts")
    else:
        for scenario_id, value in receipts.items():
            if not isinstance(value, dict) or value.get("status") != "succeeded":
                failures.append(f"independent scorer failed safely for {scenario_id}")
    groups = score.get("checks")
    if not isinstance(groups, dict):
        failures.append("independent scorer returned no check groups")
    else:
        for group, values in groups.items():
            if not isinstance(values, dict) or not values:
                failures.append(f"independent scorer returned an invalid {group} group")
                continue
            for scenario_id, passed in values.items():
                if passed is not True:
                    failures.append(f"automated check failed for {group}/{scenario_id}")
    return tuple(failures)


def build_v32_construction_adjudication(
    *,
    original_protocol_digest: Sha256Digest,
    original_freeze_digest: Sha256Digest,
    original_oracle: PersonaV32Oracle,
    report: PersonaV32ConstructionReport,
    reviewed: PersonaV3ProfileOutput,
    route_policy_source_digest: Sha256Digest,
) -> tuple[PersonaV32Oracle, PersonaV32ConstructionAdjudication]:
    corrected = corrected_v32_oracle(original_oracle)
    if report.exact_target_gate_passed:
        raise ValueError("v3.2 adjudication requires the preserved failed report")
    if report.compiled_score.route_mismatch_source_turns != (2,) or (
        report.static_score.route_mismatch_source_turns != (2,)
    ):
        raise ValueError("v3.2 adjudication cannot repair a different mismatch")
    for material in (report.compiled_material, report.static_material):
        by_turn = {claim.source_turns[-1]: claim for claim in material.claims}
        if tuple(sorted(by_turn)) != (2, 6) or by_turn[2].route is not ArtifactRoute.PROCEDURE:
            raise ValueError("v3.2 adjudication requires matching two-claim procedure states")
    static_turn_2 = next(claim for claim in reviewed.snapshot.claims if claim.source_turns == (2,))
    decision = route_semantic_features(static_turn_2.semantic_features)
    if (
        static_turn_2.semantic_features.workflow_structure
        is not SemanticWorkflowStructure.ORDERED_SEQUENCE
        or decision.selected_route is not ArtifactRoute.PROCEDURE
    ):
        raise ValueError("v3.2 static evidence does not support the route adjudication")
    task_digest = canonical_digest(
        {"tasks": [item.model_dump(mode="json", round_trip=True) for item in original_oracle.tasks]}
    )
    compiled_digest = canonical_digest(report.compiled_material)
    static_digest = canonical_digest(report.static_material)
    adjudication = PersonaV32ConstructionAdjudication(
        original_protocol_digest=original_protocol_digest,
        original_freeze_digest=original_freeze_digest,
        original_oracle_digest=canonical_digest(original_oracle),
        original_report_digest=canonical_digest(report),
        static_reviewed_output_digest=canonical_digest(reviewed),
        route_policy_source_digest=route_policy_source_digest,
        corrected_oracle_digest=canonical_digest(corrected),
        task_oracle_digest_before=task_digest,
        task_oracle_digest_after=canonical_digest(
            {"tasks": [item.model_dump(mode="json", round_trip=True) for item in corrected.tasks]}
        ),
        compiled_material_digest_before=compiled_digest,
        compiled_material_digest_after=canonical_digest(report.compiled_material),
        static_material_digest_before=static_digest,
        static_material_digest_after=canonical_digest(report.static_material),
    )
    return corrected, adjudication


def persona_v32_adjudication_schemas() -> dict[str, dict[str, object]]:
    return {
        "persona-v321-protocol.schema.json": PersonaV321Protocol.model_json_schema(),
        "persona-v32-construction-adjudication.schema.json": (
            PersonaV32ConstructionAdjudication.model_json_schema()
        ),
        "persona-v32-materials-freeze-v11.schema.json": (
            PersonaV32MaterialsFreezeV11.model_json_schema()
        ),
        "persona-v32-final-report-v11.schema.json": PersonaV32FinalReportV11.model_json_schema(),
        "persona-v32-judge-incident.schema.json": (
            PersonaV32JudgeInstrumentIncident.model_json_schema()
        ),
        "persona-v32-judge-amendment.schema.json": PersonaV32JudgeAmendment.model_json_schema(),
        "persona-v32-materials-freeze-v12.schema.json": (
            PersonaV32MaterialsFreezeV12.model_json_schema()
        ),
        "persona-v32-unblind-incident.schema.json": (
            PersonaV32UnblindInstrumentIncident.model_json_schema()
        ),
        "persona-v32-unblind-amendment.schema.json": (
            PersonaV32UnblindAmendment.model_json_schema()
        ),
        "persona-v32-materials-freeze-v13.schema.json": (
            PersonaV32MaterialsFreezeV13.model_json_schema()
        ),
        "persona-v32-scoring-incident.schema.json": (
            PersonaV32ScoringInstrumentIncident.model_json_schema()
        ),
        "persona-v32-scoring-amendment.schema.json": (
            PersonaV32ScoringAmendment.model_json_schema()
        ),
        "persona-v32-frozen-rescore.schema.json": (
            PersonaV32FrozenRescoreReport.model_json_schema()
        ),
        "persona-v32-final-report-v14.schema.json": PersonaV32FinalReportV14.model_json_schema(),
        "persona-v32-finalization-incident.schema.json": (
            PersonaV32FinalizationInstrumentIncident.model_json_schema()
        ),
        "persona-v32-finalization-amendment.schema.json": (
            PersonaV32FinalizationAmendment.model_json_schema()
        ),
        "persona-v32-final-report-v141.schema.json": (
            PersonaV32FinalReportV141.model_json_schema()
        ),
    }
