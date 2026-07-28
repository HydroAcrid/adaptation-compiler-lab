"""Frozen public-development design for the compact runtime projection gate."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.benchmark.codex_development import (
    development_tree_digest,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
)
from adaptation_compiler_lab.serialization import canonical_digest


class CompactProjectionScenario(FrozenModel):
    scenario_id: Identifier
    destination_exists: bool
    storage_class: Literal["durable_release", "ephemeral_build_cache"]
    recovery_copy_approved: bool
    expected_plan: tuple[NonEmptyStr, ...]
    metric: Literal["objective", "diagnostic", "neutral"]


class CompactProjectionTask(FrozenModel):
    task_id: Identifier
    stage: Annotated[int, Field(ge=1, le=3)]
    fixture_directory: NonEmptyStr
    task_prompt: NonEmptyStr
    allowed_change_paths: tuple[
        Literal["deployment_policy.py", "src/transfer_policy.py"],
        ...,
    ] = ("deployment_policy.py",)
    visible_test_command: tuple[Literal["python3", "-m", "unittest", "-v"], ...] = (
        "python3",
        "-m",
        "unittest",
        "-v",
    )
    scenarios: Annotated[tuple[CompactProjectionScenario, ...], Field(min_length=4)]

    @field_validator("scenarios")
    @classmethod
    def scenarios_are_sorted_and_diagnostic(
        cls,
        value: tuple[CompactProjectionScenario, ...],
    ) -> tuple[CompactProjectionScenario, ...]:
        ids = tuple(item.scenario_id for item in value)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("compact projection scenarios must be sorted and unique")
        if {item.metric for item in value} != {"objective", "diagnostic", "neutral"}:
            raise ValueError("each compact projection task needs all metric groups")
        return value


class CompactProjectionComparisonDesign(FrozenModel):
    design_version: Literal[
        "1.0.0",
        "1.1.0",
        "1.2.0",
        "1.3.0",
        "1.4.0",
        "1.5.0",
        "1.6.0",
        "1.7.0",
        "1.8.0",
        "1.9.0",
        "1.10.0",
        "1.11.0",
        "1.12.0",
        "1.13.0",
        "1.14.0",
        "1.15.0",
        "1.16.0",
        "1.17.0",
        "1.18.0",
        "1.19.0",
        "2.0.0",
        "2.1.0",
    ] = "1.0.0"
    design_id: Literal["milestone-6a1-compact-runtime-public-development"] = (
        "milestone-6a1-compact-runtime-public-development"
    )
    tasks: Annotated[tuple[CompactProjectionTask, ...], Field(min_length=3, max_length=3)]
    conditions: tuple[
        Literal[BenchmarkCondition.STRONG_STATIC_PROFILE],
        Literal[BenchmarkCondition.COMPILED_ADAPTATION],
    ] = (
        BenchmarkCondition.STRONG_STATIC_PROFILE,
        BenchmarkCondition.COMPILED_ADAPTATION,
    )
    task_fixture_digests: tuple[Sha256Digest, Sha256Digest, Sha256Digest]
    independent_scorer_digest: Sha256Digest
    renderer_source_digest: Sha256Digest
    renderer_id: Literal[
        "codex-compact-runtime",
        "codex-decision-runtime",
        "codex-decision-table-runtime",
    ] = "codex-compact-runtime"
    renderer_version: Literal["1.0.0", "1.1.0", "2.0.0", "2.1.0"] = "1.0.0"
    runtime_fixture_measurements_digest: Sha256Digest
    runtime_fixture_tree_digest: Sha256Digest
    shared_execution_envelope_digest: Sha256Digest
    evidence_stage_count: Literal[3] = 3
    tasks_per_stage: Literal[1] = 1
    repetitions_per_condition_task: Literal[1] = 1
    planned_target_sessions: Literal[6] = 6
    profile_author_sessions: Literal[0, 1] = 1
    profile_review_sessions: Literal[0, 1] = 1
    instrument_smoke_sessions: Literal[1] | None = None
    isolated_judge_sessions: Literal[1] = 1
    maximum_subscription_sessions: Literal[7, 8, 9] = 9
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    target_sessions_started: Literal[False] = False
    profile_sessions_started: Literal[False] = False
    judge_sessions_started: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False
    automated_correctness_and_validity_are_primary: Literal[True] = True
    shared_envelope_identical_between_conditions: Literal[True] = True
    condition_blind_judge_is_secondary: Literal[True] = True
    renderer_tuning_after_live_output_forbidden: Literal[True] = True
    every_target_record_must_be_valid: Literal[True] = True
    zero_false_activation_required: Literal[True] = True
    zero_scope_leakage_required: Literal[True] = True
    no_automated_regression_required: Literal[True] = True
    projection_must_not_exceed_profile_without_registered_necessity: Literal[True] = True
    ai_preference_cannot_rescue_failed_primary_gate: Literal[True] = True
    supersedes_design_digest: Sha256Digest | None = None
    superseded_scorer_digest: Sha256Digest | None = None
    amendment_reason: (
        Literal[
            "strict_tuple_return_contract",
            "isolated_policy_observation",
            "preexec_failure_receipt",
            "trusted_observation_channel_and_scoped_verification",
            "restricted_policy_runtime_target_binding_and_transition_lineage",
            "observer_format_normalization",
            "codex_renderer_target_guard",
            "execution_envelope_path_validation",
            "portable_envelope_schema_alignment",
            "canonical_envelope_collection_and_lifecycle_state",
            "shared_envelope_task_path_alignment",
            "fresh_tasks_compact_projection_and_instrument_repair",
            "prelive_source_binding_and_target_sandbox_freeze",
            "stage_specific_evidence_validation",
            "target_resolver_mount_and_preact_retry",
            "nested_target_sandbox_runtime_and_live_smoke_gate",
            "smoke_role_binding_and_source_family_fix",
            "ephemeral_unified_exec_workspace_mount",
            "ephemeral_codex_workspace_mount",
            "typed_decision_projection_and_fresh_tasks",
            "complete_decision_table_and_path_audit_fix",
        ]
        | None
    ) = None
    policy_observer_digest: Sha256Digest | None = None
    scorer_sandbox_digest: Sha256Digest | None = None
    prior_failed_result_digest: Sha256Digest | None = None
    prior_failed_profile_receipt_digest: Sha256Digest | None = None
    prior_failed_target_receipt_digest: Sha256Digest | None = None
    prior_failed_smoke_receipt_digest: Sha256Digest | None = None
    scorer_sensitivity_cases: tuple[
        Literal["reference"],
        Literal["stale_rule"],
        Literal["missed_exception"],
        Literal["scope_leak"],
        Literal["unnecessary_change"],
        Literal["forbidden_path"],
    ] = (
        "reference",
        "stale_rule",
        "missed_exception",
        "scope_leak",
        "unnecessary_change",
        "forbidden_path",
    )

    @model_validator(mode="after")
    def design_is_exact(self) -> Self:
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("compact projection tasks must be sorted and unique")
        if Counter(item.stage for item in self.tasks) != Counter({1: 1, 2: 1, 3: 1}):
            raise ValueError("compact projection design needs one task per stage")
        amendment = (
            self.supersedes_design_digest,
            self.superseded_scorer_digest,
            self.amendment_reason,
        )
        isolation = (
            self.policy_observer_digest,
            self.scorer_sandbox_digest,
        )
        if self.design_version == "1.0.0" and any(
            item is not None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.0 cannot contain amendment metadata")
        if self.design_version == "1.1.0" and any(item is None for item in amendment):
            raise ValueError("compact projection v1.1 requires complete amendment metadata")
        if (
            self.design_version == "1.1.0"
            and self.amendment_reason != "strict_tuple_return_contract"
        ):
            raise ValueError("compact projection v1.1 requires its registered amendment reason")
        if self.design_version == "1.1.0" and any(item is not None for item in isolation):
            raise ValueError("compact projection v1.1 cannot contain v1.2 isolation metadata")
        if self.design_version == "1.2.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.2 requires complete isolation metadata")
        if (
            self.design_version == "1.2.0"
            and self.amendment_reason != "isolated_policy_observation"
        ):
            raise ValueError("compact projection v1.2 requires its registered amendment reason")
        if self.design_version == "1.3.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.3 requires complete isolation metadata")
        if self.design_version == "1.3.0" and self.amendment_reason != "preexec_failure_receipt":
            raise ValueError("compact projection v1.3 requires its registered amendment reason")
        if self.design_version == "1.4.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.4 requires complete isolation metadata")
        if (
            self.design_version == "1.4.0"
            and self.amendment_reason != "trusted_observation_channel_and_scoped_verification"
        ):
            raise ValueError("compact projection v1.4 requires its registered amendment reason")
        if self.design_version == "1.5.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.5 requires complete isolation metadata")
        if (
            self.design_version == "1.5.0"
            and self.amendment_reason
            != "restricted_policy_runtime_target_binding_and_transition_lineage"
        ):
            raise ValueError("compact projection v1.5 requires its registered amendment reason")
        if self.design_version == "1.6.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.6 requires complete isolation metadata")
        if (
            self.design_version == "1.6.0"
            and self.amendment_reason != "observer_format_normalization"
        ):
            raise ValueError("compact projection v1.6 requires its registered amendment reason")
        if self.design_version == "1.7.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.7 requires complete isolation metadata")
        if (
            self.design_version == "1.7.0"
            and self.amendment_reason != "codex_renderer_target_guard"
        ):
            raise ValueError("compact projection v1.7 requires its registered amendment reason")
        if self.design_version == "1.8.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.8 requires complete isolation metadata")
        if (
            self.design_version == "1.8.0"
            and self.amendment_reason != "execution_envelope_path_validation"
        ):
            raise ValueError("compact projection v1.8 requires its registered amendment reason")
        if self.design_version == "1.9.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.9 requires complete isolation metadata")
        if (
            self.design_version == "1.9.0"
            and self.amendment_reason != "portable_envelope_schema_alignment"
        ):
            raise ValueError("compact projection v1.9 requires its registered amendment reason")
        if self.design_version == "1.10.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.10 requires complete isolation metadata")
        if (
            self.design_version == "1.10.0"
            and self.amendment_reason != "canonical_envelope_collection_and_lifecycle_state"
        ):
            raise ValueError("compact projection v1.10 requires its registered amendment reason")
        if self.design_version == "1.11.0" and any(
            item is None for item in (*amendment, *isolation)
        ):
            raise ValueError("compact projection v1.11 requires complete amendment metadata")
        if (
            self.design_version == "1.11.0"
            and self.amendment_reason != "shared_envelope_task_path_alignment"
        ):
            raise ValueError("compact projection v1.11 requires its registered amendment reason")
        if self.design_version not in {
            "1.12.0",
            "1.13.0",
            "1.14.0",
            "1.15.0",
            "1.16.0",
            "1.17.0",
            "1.18.0",
            "1.19.0",
            "2.0.0",
            "2.1.0",
        } and (
            self.prior_failed_result_digest is not None
            or self.prior_failed_profile_receipt_digest is not None
            or self.prior_failed_target_receipt_digest is not None
        ):
            raise ValueError("compact projection prior-result lineage starts at v1.12")
        if (
            self.design_version
            not in {
                "1.14.0",
                "1.15.0",
                "1.16.0",
                "1.17.0",
                "1.18.0",
                "1.19.0",
                "2.0.0",
                "2.1.0",
            }
            and self.prior_failed_profile_receipt_digest is not None
        ):
            raise ValueError("compact profile-failure lineage starts at v1.14")
        if (
            self.design_version
            not in {
                "1.15.0",
                "1.16.0",
                "1.17.0",
                "1.18.0",
                "1.19.0",
                "2.0.0",
                "2.1.0",
            }
            and self.prior_failed_target_receipt_digest is not None
        ):
            raise ValueError("compact target-failure lineage starts at v1.15")
        if (
            self.design_version not in {"1.17.0", "1.18.0", "1.19.0", "2.0.0", "2.1.0"}
            and self.prior_failed_smoke_receipt_digest is not None
        ):
            raise ValueError("compact smoke-failure lineage starts at v1.17")
        if self.design_version == "1.12.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.12 requires complete amendment metadata")
            if self.amendment_reason != "fresh_tasks_compact_projection_and_instrument_repair":
                raise ValueError("compact projection v1.12 requires its amendment reason")
            if self.prior_failed_result_digest is None:
                raise ValueError("compact projection v1.12 must bind the failed prior result")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 1
                or self.maximum_subscription_sessions != 8
            ):
                raise ValueError("compact projection v1.12 requires its exact 8-session budget")
        elif self.design_version == "1.13.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.13 requires complete amendment metadata")
            if self.amendment_reason != "prelive_source_binding_and_target_sandbox_freeze":
                raise ValueError("compact projection v1.13 requires its amendment reason")
            if self.prior_failed_result_digest is None:
                raise ValueError("compact projection v1.13 must retain prior-result lineage")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 1
                or self.maximum_subscription_sessions != 8
            ):
                raise ValueError("compact projection v1.13 requires its exact 8-session budget")
        elif self.design_version == "1.14.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.14 requires complete amendment metadata")
            if self.amendment_reason != "stage_specific_evidence_validation":
                raise ValueError("compact projection v1.14 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
            ):
                raise ValueError("compact projection v1.14 must retain both failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 1
                or self.maximum_subscription_sessions != 8
            ):
                raise ValueError("compact projection v1.14 requires its exact 8-session budget")
        elif self.design_version == "1.15.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.15 requires complete amendment metadata")
            if self.amendment_reason != "target_resolver_mount_and_preact_retry":
                raise ValueError("compact projection v1.15 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
                or self.prior_failed_target_receipt_digest is None
            ):
                raise ValueError("compact projection v1.15 must retain all failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 0
                or self.maximum_subscription_sessions != 7
            ):
                raise ValueError("compact projection v1.15 requires its exact 7-session budget")
        elif self.design_version == "1.16.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.16 requires complete amendment metadata")
            if self.amendment_reason != "nested_target_sandbox_runtime_and_live_smoke_gate":
                raise ValueError("compact projection v1.16 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
                or self.prior_failed_target_receipt_digest is None
            ):
                raise ValueError("compact projection v1.16 must retain all failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 0
                or self.instrument_smoke_sessions != 1
                or self.maximum_subscription_sessions != 8
            ):
                raise ValueError("compact projection v1.16 requires its exact 8-session budget")
        elif self.design_version == "1.17.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.17 requires complete amendment metadata")
            if self.amendment_reason != "smoke_role_binding_and_source_family_fix":
                raise ValueError("compact projection v1.17 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
                or self.prior_failed_target_receipt_digest is None
                or self.prior_failed_smoke_receipt_digest is None
            ):
                raise ValueError("compact projection v1.17 must retain all failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 0
                or self.instrument_smoke_sessions != 1
                or self.maximum_subscription_sessions != 8
            ):
                raise ValueError("compact projection v1.17 requires its exact 8-session budget")
        elif self.design_version == "1.18.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.18 requires complete amendment metadata")
            if self.amendment_reason != "ephemeral_unified_exec_workspace_mount":
                raise ValueError("compact projection v1.18 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
                or self.prior_failed_target_receipt_digest is None
                or self.prior_failed_smoke_receipt_digest is None
            ):
                raise ValueError("compact projection v1.18 must retain all failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 0
                or self.instrument_smoke_sessions != 1
                or self.maximum_subscription_sessions != 8
            ):
                raise ValueError("compact projection v1.18 requires its exact 8-session budget")
        elif self.design_version == "1.19.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v1.19 requires complete amendment metadata")
            if self.amendment_reason != "ephemeral_codex_workspace_mount":
                raise ValueError("compact projection v1.19 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
                or self.prior_failed_target_receipt_digest is None
                or self.prior_failed_smoke_receipt_digest is None
            ):
                raise ValueError("compact projection v1.19 must retain all failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 0
                or self.instrument_smoke_sessions != 1
                or self.maximum_subscription_sessions != 8
            ):
                raise ValueError("compact projection v1.19 requires its exact 8-session budget")
        elif self.design_version == "2.0.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v2.0 requires complete amendment metadata")
            if self.amendment_reason != "typed_decision_projection_and_fresh_tasks":
                raise ValueError("compact projection v2.0 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
                or self.prior_failed_target_receipt_digest is None
                or self.prior_failed_smoke_receipt_digest is None
            ):
                raise ValueError("compact projection v2.0 must retain all failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 0
                or self.instrument_smoke_sessions != 1
                or self.maximum_subscription_sessions != 8
                or self.renderer_id != "codex-decision-runtime"
                or self.renderer_version != "2.0.0"
            ):
                raise ValueError("compact projection v2.0 requires its exact decision gate")
        elif self.design_version == "2.1.0":
            if any(item is None for item in (*amendment, *isolation)):
                raise ValueError("compact projection v2.1 requires complete amendment metadata")
            if self.amendment_reason != "complete_decision_table_and_path_audit_fix":
                raise ValueError("compact projection v2.1 requires its amendment reason")
            if (
                self.prior_failed_result_digest is None
                or self.prior_failed_profile_receipt_digest is None
                or self.prior_failed_target_receipt_digest is None
                or self.prior_failed_smoke_receipt_digest is None
            ):
                raise ValueError("compact projection v2.1 must retain all failure lineages")
            if (
                self.profile_author_sessions != 0
                or self.profile_review_sessions != 0
                or self.instrument_smoke_sessions != 1
                or self.maximum_subscription_sessions != 8
                or self.renderer_id != "codex-decision-table-runtime"
                or self.renderer_version != "2.1.0"
            ):
                raise ValueError("compact projection v2.1 requires its exact decision gate")
        elif (
            self.profile_author_sessions != 1
            or self.profile_review_sessions != 1
            or self.maximum_subscription_sessions != 9
        ):
            raise ValueError("compact projection v1.0-v1.11 requires the 9-session budget")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(
            self.model_dump(
                mode="json",
                exclude_none=True,
                round_trip=True,
            )
        )


def load_compact_projection_design(
    root: Path,
    *,
    version: str | None = None,
) -> CompactProjectionComparisonDesign:
    """Load and revalidate every frozen public task, fixture, scorer, and renderer."""

    if version is not None:
        if version not in {*{f"1.{minor}" for minor in range(20)}, "2.0", "2.1"}:
            raise ValueError("unsupported compact projection design version")
        preregistration = root / f"PREREGISTRATION-v{version}.json"
        if not preregistration.is_file():
            raise ValueError("requested compact projection design is unavailable")
    else:
        preregistration = next(
            path
            for path in (
                root / "PREREGISTRATION-v2.1.json",
                root / "PREREGISTRATION-v2.0.json",
                root / "PREREGISTRATION-v1.19.json",
                root / "PREREGISTRATION-v1.18.json",
                root / "PREREGISTRATION-v1.17.json",
                root / "PREREGISTRATION-v1.16.json",
                root / "PREREGISTRATION-v1.15.json",
                root / "PREREGISTRATION-v1.14.json",
                root / "PREREGISTRATION-v1.13.json",
                root / "PREREGISTRATION-v1.12.json",
                root / "PREREGISTRATION-v1.11.json",
                root / "PREREGISTRATION-v1.10.json",
                root / "PREREGISTRATION-v1.9.json",
                root / "PREREGISTRATION-v1.8.json",
                root / "PREREGISTRATION-v1.7.json",
                root / "PREREGISTRATION-v1.6.json",
                root / "PREREGISTRATION-v1.5.json",
                root / "PREREGISTRATION-v1.4.json",
                root / "PREREGISTRATION-v1.3.json",
                root / "PREREGISTRATION-v1.2.json",
                root / "PREREGISTRATION-v1.1.json",
                root / "PREREGISTRATION-v1.0.json",
            )
            if path.is_file()
        )
    checksum = preregistration.with_suffix(".sha256")
    checksum_fields = checksum.read_text(encoding="ascii").split()
    if len(checksum_fields) != 2 or checksum_fields[1] != preregistration.name:
        raise ValueError("compact projection preregistration checksum is malformed")
    if sha256_file(preregistration) != f"sha256:{checksum_fields[0]}":
        raise ValueError("compact projection preregistration checksum drifted")
    design = CompactProjectionComparisonDesign.model_validate_json(preregistration.read_bytes())
    chain = {
        "1.1.0": "1.0",
        "1.2.0": "1.1",
        "1.3.0": "1.2",
        "1.4.0": "1.3",
        "1.5.0": "1.4",
        "1.6.0": "1.5",
        "1.7.0": "1.6",
        "1.8.0": "1.7",
        "1.9.0": "1.8",
        "1.10.0": "1.9",
        "1.11.0": "1.10",
        "1.12.0": "1.11",
        "1.13.0": "1.12",
        "1.14.0": "1.13",
        "1.15.0": "1.14",
        "1.16.0": "1.15",
        "1.17.0": "1.16",
        "1.18.0": "1.17",
        "1.19.0": "1.18",
        "2.0.0": "1.19",
        "2.1.0": "2.0",
    }
    current = design
    while current.design_version in chain:
        historical_label = chain[current.design_version]
        historical_path = root / f"PREREGISTRATION-v{historical_label}.json"
        historical_checksum = root / f"PREREGISTRATION-v{historical_label}.sha256"
        historical_fields = historical_checksum.read_text(encoding="ascii").split()
        if (
            len(historical_fields) != 2
            or historical_fields[1] != historical_path.name
            or sha256_file(historical_path) != f"sha256:{historical_fields[0]}"
        ):
            raise ValueError("superseded compact projection preregistration drifted")
        historical = CompactProjectionComparisonDesign.model_validate_json(
            historical_path.read_bytes()
        )
        if current.design_version in {"1.7.0", "1.8.0", "1.9.0", "1.10.0"}:
            unchanged_fields = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
            )
            drifted = tuple(
                field
                for field in unchanged_fields
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    f"compact projection v{current.design_version.removesuffix('.0')} "
                    "rebound unchanged artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.11.0":
            unaffected_fields_v111 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "renderer_source_digest",
                "scorer_sandbox_digest",
                "task_fixture_digests",
            )
            drifted = tuple(
                field
                for field in unaffected_fields_v111
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.11 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.13.0":
            unchanged_fields_v113 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_result_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
                "tasks",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v113
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.13 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.14.0":
            unchanged_fields_v114 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_result_digest",
                "renderer_source_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
                "tasks",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v114
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.14 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.15.0":
            unchanged_fields_v115 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_profile_receipt_digest",
                "prior_failed_result_digest",
                "renderer_source_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
                "tasks",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v115
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.15 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.16.0":
            unchanged_fields_v116 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_profile_receipt_digest",
                "prior_failed_result_digest",
                "renderer_source_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
                "tasks",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v116
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.16 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.17.0":
            unchanged_fields_v117 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_profile_receipt_digest",
                "prior_failed_result_digest",
                "prior_failed_target_receipt_digest",
                "renderer_source_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
                "tasks",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v117
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.17 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.18.0":
            unchanged_fields_v118 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_profile_receipt_digest",
                "prior_failed_result_digest",
                "prior_failed_target_receipt_digest",
                "renderer_source_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
                "tasks",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v118
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.18 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "1.19.0":
            unchanged_fields_v119 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_profile_receipt_digest",
                "prior_failed_result_digest",
                "prior_failed_target_receipt_digest",
                "renderer_source_digest",
                "runtime_fixture_measurements_digest",
                "runtime_fixture_tree_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
                "task_fixture_digests",
                "tasks",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v119
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v1.19 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "2.0.0":
            unchanged_fields_v20 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_profile_receipt_digest",
                "prior_failed_smoke_receipt_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v20
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v2.0 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.design_version == "2.1.0":
            unchanged_fields_v21 = (
                "independent_scorer_digest",
                "policy_observer_digest",
                "prior_failed_profile_receipt_digest",
                "scorer_sandbox_digest",
                "shared_execution_envelope_digest",
            )
            drifted = tuple(
                field
                for field in unchanged_fields_v21
                if getattr(current, field) != getattr(historical, field)
            )
            if drifted:
                raise ValueError(
                    "compact projection v2.1 rebound unaffected artifacts: " + ", ".join(drifted)
                )
        if current.supersedes_design_digest != historical.content_digest:
            raise ValueError("compact projection supersession digest drifted")
        if current.superseded_scorer_digest != historical.independent_scorer_digest:
            raise ValueError("compact projection superseded scorer digest drifted")
        current = historical
    observed_fixtures: list[Sha256Digest] = []
    for task in design.tasks:
        fixture = (root / task.fixture_directory).resolve()
        if root.resolve() not in fixture.parents or not fixture.is_dir():
            raise ValueError(f"compact projection fixture is missing: {task.task_id}")
        manifest = fixture.parent / "task.json"
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        if raw != task.model_dump(mode="json", round_trip=True):
            raise ValueError(f"compact projection task manifest drifted: {task.task_id}")
        observed_fixtures.append(development_tree_digest(fixture))
    if tuple(observed_fixtures) != design.task_fixture_digests:
        raise ValueError("compact projection task fixture digest drifted")
    repo = root.parent
    if sha256_file(repo / "scripts" / "score_compact_projection_task.py") != (
        design.independent_scorer_digest
    ):
        raise ValueError("compact projection scorer digest drifted")
    if design.design_version in {
        "1.2.0",
        "1.3.0",
        "1.4.0",
        "1.5.0",
        "1.6.0",
        "1.7.0",
        "1.8.0",
        "1.9.0",
        "1.10.0",
        "1.11.0",
        "1.12.0",
        "1.13.0",
        "1.14.0",
        "1.15.0",
        "1.16.0",
        "1.17.0",
        "1.18.0",
        "1.19.0",
        "2.0.0",
        "2.1.0",
    }:
        if sha256_file(repo / "scripts" / "observe_compact_projection_policy.py") != (
            design.policy_observer_digest
        ):
            raise ValueError("compact projection policy observer digest drifted")
        if (
            sha256_file(repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py")
            != design.scorer_sandbox_digest
        ):
            raise ValueError("compact projection scorer sandbox digest drifted")
    renderer_source = (
        repo / "src/adaptation_compiler_lab/targets/codex_runtime_v4.py"
        if design.design_version == "2.1.0"
        else repo / "src/adaptation_compiler_lab/targets/codex_runtime_v3.py"
        if design.design_version == "2.0.0"
        else repo / "src/adaptation_compiler_lab/targets/codex_runtime_v2.py"
        if design.design_version
        in {
            "1.12.0",
            "1.13.0",
            "1.14.0",
            "1.15.0",
            "1.16.0",
            "1.17.0",
            "1.18.0",
            "1.19.0",
        }
        else repo / "src/adaptation_compiler_lab/targets/codex_runtime.py"
    )
    if sha256_file(renderer_source) != design.renderer_source_digest:
        raise ValueError("compact runtime renderer source digest drifted")
    runtime_fixture_name = {
        "1.4.0": "runtime-fixture-v1.4",
        "1.5.0": "runtime-fixture-v1.5",
        "1.6.0": "runtime-fixture-v1.5",
        "1.7.0": "runtime-fixture-v1.5",
        "1.8.0": "runtime-fixture-v1.5",
        "1.9.0": "runtime-fixture-v1.5",
        "1.10.0": "runtime-fixture-v1.5",
        "1.11.0": "runtime-fixture-v1.11",
        "1.12.0": "runtime-fixture-v1.12",
        "1.13.0": "runtime-fixture-v1.12",
        "1.14.0": "runtime-fixture-v1.12",
        "1.15.0": "runtime-fixture-v1.12",
        "1.16.0": "runtime-fixture-v1.12",
        "1.17.0": "runtime-fixture-v1.12",
        "1.18.0": "runtime-fixture-v1.12",
        "1.19.0": "runtime-fixture-v1.12",
        "2.0.0": "runtime-fixture-v2.0",
        "2.1.0": "runtime-fixture-v2.1",
    }.get(design.design_version, "runtime-fixture")
    runtime_fixture = root / runtime_fixture_name
    measurement_name = (
        "MEASUREMENTS-v1.1.json"
        if design.design_version
        in {
            "1.12.0",
            "1.13.0",
            "1.14.0",
            "1.15.0",
            "1.16.0",
            "1.17.0",
            "1.18.0",
            "1.19.0",
            "2.0.0",
            "2.1.0",
        }
        else "MEASUREMENTS-v1.0.json"
    )
    if design.design_version in {"2.0.0", "2.1.0"}:
        measurement_name = (
            "MEASUREMENTS-v2.1.json"
            if design.design_version == "2.1.0"
            else "MEASUREMENTS-v2.0.json"
        )
    if sha256_file(runtime_fixture / measurement_name) != (
        design.runtime_fixture_measurements_digest
    ):
        raise ValueError("compact runtime measurements digest drifted")
    if development_tree_digest(runtime_fixture) != design.runtime_fixture_tree_digest:
        raise ValueError("compact runtime fixture tree digest drifted")
    if sha256_file(runtime_fixture / "shared-execution-envelope.md") != (
        design.shared_execution_envelope_digest
    ):
        raise ValueError("shared execution envelope digest drifted")
    return design
