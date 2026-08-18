"""Fresh post-remediation behavioral canary for compiled and static adaptation."""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.automatic_runtime.models import InteractionObservation
from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentRunObservation
from adaptation_compiler_lab.benchmark.compact_execution import CompactJudgePair
from adaptation_compiler_lab.benchmark.persona_instrument import (
    PersonaEvidenceMessage,
    PersonaExpectedClaim,
    PersonaHiddenOracle,
    PersonaMaterialClaim,
    PersonaMaterialSnapshot,
    PersonaMaterialSource,
    PersonaObjectiveScore,
    PersonaPublicCase,
    PersonaSensorRecord,
    PersonaStageEvidence,
    render_neutral_guidance,
    score_objective_state,
)
from adaptation_compiler_lab.benchmark.persona_static_gate import (
    PersonaHostScopeBinding,
    PersonaHostScopeRegistry,
    compile_host_scoped_sensor_material,
)
from adaptation_compiler_lab.benchmark.persona_v3 import (
    PersonaV3ProfileAuthorPacket,
    PersonaV3ProfileOutput,
)
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ArtifactRoute,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Scope,
    Sha256Digest,
    SourceClass,
    TaskRecordRef,
    scope_is_within,
)
from adaptation_compiler_lab.serialization import canonical_digest
from adaptation_compiler_lab.targets.task_delivery import TaskMaterialDeliveryReceipt


class PersonaV32Protocol(FrozenModel):
    """Exact limits and claims for the first fresh behavioral post-fix canary."""

    protocol_version: Literal["3.2.0"] = "3.2.0"
    benchmark_id: Literal["temper-persona-v32-behavioral-canary"] = (
        "temper-persona-v32-behavioral-canary"
    )
    status: Literal["fresh_behavioral_canary_authorized"] = "fresh_behavioral_canary_authorized"
    fresh_persona_and_tasks: Literal[True] = True
    prior_calibration_fixture_reuse: Literal[False] = False
    construction_sessions: Literal[3] = 3
    target_sessions: Literal[4] = 4
    isolated_judge_sessions: Literal[2] = 2
    maximum_subscription_sessions: Literal[9] = 9
    task_count: Literal[2] = 2
    applicable_task_count: Literal[1] = 1
    unrelated_control_count: Literal[1] = 1
    automated_correctness_primary: Literal[True] = True
    isolated_judgment_secondary: Literal[True] = True
    construction_must_be_exact_before_targets: Literal[True] = True
    tuning_after_target_output_forbidden: Literal[True] = True
    full_v3_grid_authorized: Literal[False] = False
    codex_cli_version: Literal["codex-cli 0.146.0"] = "codex-cli 0.146.0"
    codex_binary_digest: Literal[
        "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    ] = "sha256:2e863156ed35ecc5253b1e2f907a9143077b9f7cb51942070c61996471ff6e04"
    semantic_sensor_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    semantic_sensor_reasoning_effort: Literal["medium"] = "medium"
    profile_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    profile_reasoning_effort: Literal["xhigh"] = "xhigh"
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    target_reasoning_effort: Literal["medium"] = "medium"
    judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    judge_reasoning_effort: Literal["xhigh"] = "xhigh"
    saved_chatgpt_authentication_only: Literal[True] = True
    api_keys_permitted: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    sealed_external_validation_access_permitted: Literal[False] = False


class PersonaV32TaskCase(FrozenModel):
    """A target-visible descriptor with no hidden expected outcomes."""

    task_id: Identifier
    project_id: Identifier
    context_label: NonEmptyStr
    applicable_adaptation: bool
    fixture_directory: NonEmptyStr
    prompt: NonEmptyStr
    allowed_change_paths: tuple[Literal["src/transfer_policy.py"]] = ("src/transfer_policy.py",)
    visible_test_command: tuple[
        Literal["python3"],
        Literal["-m"],
        Literal["unittest"],
        Literal["discover"],
        Literal["-v"],
    ] = ("python3", "-m", "unittest", "discover", "-v")


class PersonaV32TaskScenario(FrozenModel):
    scenario_id: Identifier
    destination_exists: bool
    storage_class: Literal["durable_release", "ephemeral_build_cache"]
    recovery_copy_approved: bool
    expected_plan: tuple[NonEmptyStr, ...]
    metric: Literal["objective", "diagnostic", "neutral"]


class PersonaV32TaskOracle(FrozenModel):
    task_id: Identifier
    scenarios: Annotated[tuple[PersonaV32TaskScenario, ...], Field(min_length=8, max_length=8)]

    @model_validator(mode="after")
    def scenarios_are_complete(self) -> Self:
        ids = tuple(item.scenario_id for item in self.scenarios)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("v3.2 task scenarios must be sorted and unique")
        if {item.metric for item in self.scenarios} != {"objective", "diagnostic", "neutral"}:
            raise ValueError("v3.2 task oracle requires every metric group")
        return self


class PersonaV32Fixture(FrozenModel):
    fixture_version: Literal["1.0.0"] = "1.0.0"
    fixture_id: Literal["temper-v32-maren-tide-ledger-stage-2"] = (
        "temper-v32-maren-tide-ledger-stage-2"
    )
    synthetic_only: Literal[True] = True
    counts_toward_effectiveness_evidence: Literal[True] = True
    case: PersonaPublicCase
    evidence: PersonaStageEvidence
    scope_registry: PersonaHostScopeRegistry
    tasks: Annotated[tuple[PersonaV32TaskCase, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def fixture_is_fresh_and_complete(self) -> Self:
        if self.case.persona_id != "maren" or self.evidence.persona_id != "maren":
            raise ValueError("v3.2 requires the fresh Maren persona")
        if self.case.stage != 2 or self.evidence.stage != 2 or self.scope_registry.stage != 2:
            raise ValueError("v3.2 requires checkpoint two")
        if self.scope_registry.persona_id != self.case.persona_id:
            raise ValueError("v3.2 scope registry crossed personas")
        visible = {message.turn for message in self.evidence.messages}
        if {item.source_turn for item in self.scope_registry.bindings} != visible:
            raise ValueError("v3.2 requires one host scope binding per evidence turn")
        if Counter(task.applicable_adaptation for task in self.tasks) != Counter(
            {True: 1, False: 1}
        ):
            raise ValueError("v3.2 requires one applicable task and one unrelated control")
        if tuple(task.task_id for task in self.tasks) != tuple(
            sorted(task.task_id for task in self.tasks)
        ):
            raise ValueError("v3.2 tasks must be sorted")
        return self


class PersonaV32Oracle(FrozenModel):
    oracle_version: Literal["1.0.0"] = "1.0.0"
    material: PersonaHiddenOracle
    tasks: Annotated[tuple[PersonaV32TaskOracle, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def oracle_is_bound(self) -> Self:
        if self.material.persona_id != "maren":
            raise ValueError("v3.2 oracle crossed personas")
        if tuple(item.task_id for item in self.tasks) != tuple(
            sorted(item.task_id for item in self.tasks)
        ):
            raise ValueError("v3.2 task oracles must be sorted")
        return self


class PersonaV32PlanCell(FrozenModel):
    sequence: Annotated[int, Field(ge=1, le=4)]
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class PersonaV32PublicPlan(FrozenModel):
    plan_version: Literal["1.0.0"] = "1.0.0"
    seed_commitment: Sha256Digest
    blind_condition_ids: tuple[Identifier, Identifier]
    run_order: Annotated[tuple[PersonaV32PlanCell, ...], Field(min_length=4, max_length=4)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def plan_is_complete(self) -> Self:
        if self.blind_condition_ids != tuple(sorted(set(self.blind_condition_ids))):
            raise ValueError("v3.2 blind condition IDs must be sorted and unique")
        if tuple(item.sequence for item in self.run_order) != tuple(range(1, 5)):
            raise ValueError("v3.2 run sequence must be contiguous")
        if len({(item.task_id, item.blind_condition_id) for item in self.run_order}) != 4:
            raise ValueError("v3.2 public plan must cover every task-condition cell")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class PersonaV32Freeze(FrozenModel):
    freeze_version: Literal["1.0.0"] = "1.0.0"
    protocol_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    author_packet_digest: Sha256Digest
    semantic_role_contract_digest: Sha256Digest
    semantic_prompt_digest: Sha256Digest
    semantic_output_schema_digest: Sha256Digest
    profile_output_schema_digest: Sha256Digest
    benchmark_module_digest: Sha256Digest
    construction_runner_digest: Sha256Digest
    target_runner_digest: Sha256Digest
    judge_runner_digest: Sha256Digest
    scorer_digest: Sha256Digest
    task_fixture_digests: tuple[Sha256Digest, Sha256Digest]
    public_plan_digest: Sha256Digest
    seed_commitment: Sha256Digest
    execution_started: Literal[False] = False
    full_v3_grid_authorized: Literal[False] = False
    sealed_external_validation_accessed: Literal[False] = False


class PersonaV32RoleReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    execution_id: Identifier
    role: Literal["semantic_sensor", "profile_author", "profile_reviewer"]
    persona_id: Literal["maren"] = "maren"
    packet_digest: Sha256Digest
    model: Literal["gpt-5.6-luna", "gpt-5.6-sol"]
    reasoning_effort: Literal["medium", "xhigh"]
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
    trace_digest: Sha256Digest
    encrypted_trace_ref: Sha256Digest
    command_digest: Sha256Digest
    environment_digest: Sha256Digest
    fresh_ephemeral_session: Literal[True] = True
    tool_use_observed: Literal[False] = False
    model_reroute_observed: Literal[False] = False
    session_state_destroyed: Literal[True] = True
    saved_chatgpt_authentication: Literal[True] = True
    api_key_environment_present: Literal[False] = False
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def role_configuration_is_exact(self) -> Self:
        expected = {
            "semantic_sensor": ("gpt-5.6-luna", "medium"),
            "profile_author": ("gpt-5.6-sol", "xhigh"),
            "profile_reviewer": ("gpt-5.6-sol", "xhigh"),
        }[self.role]
        if (self.model, self.reasoning_effort) != expected:
            raise ValueError("v3.2 construction role configuration drifted")
        return self


class PersonaV32SensorResult(FrozenModel):
    result_version: Literal["1.0.0"] = "1.0.0"
    fixture_digest: Sha256Digest
    records: Annotated[tuple[PersonaSensorRecord, ...], Field(min_length=7, max_length=7)]
    execution_receipt: PersonaV32RoleReceipt

    @model_validator(mode="after")
    def result_is_exact(self) -> Self:
        if tuple(item.turn for item in self.records) != tuple(range(1, 8)):
            raise ValueError("v3.2 sensor result requires turns one through seven")
        if self.execution_receipt.role != "semantic_sensor":
            raise ValueError("v3.2 sensor result has the wrong role receipt")
        return self


class PersonaV32ConstructionReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    protocol_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    freeze_digest: Sha256Digest
    role_receipts: Annotated[tuple[PersonaV32RoleReceipt, ...], Field(min_length=3, max_length=3)]
    compiled_material: PersonaMaterialSnapshot
    static_material: PersonaMaterialSnapshot
    compiled_score: PersonaObjectiveScore
    static_score: PersonaObjectiveScore
    compiled_material_bytes: int = Field(ge=1, le=3000)
    static_material_bytes: int = Field(ge=1, le=3000)
    exact_target_gate_passed: bool
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def report_is_fail_closed(self) -> Self:
        if tuple(item.role for item in self.role_receipts) != (
            "semantic_sensor",
            "profile_author",
            "profile_reviewer",
        ):
            raise ValueError("v3.2 requires the ordered construction receipt set")
        if self.exact_target_gate_passed is not (
            self.compiled_score.exact and self.static_score.exact
        ):
            raise ValueError("v3.2 construction gate drifted from objective evidence")
        sizes = (
            len(self.compiled_material.target_guidance.encode("utf-8")),
            len(self.static_material.target_guidance.encode("utf-8")),
        )
        if sizes != (self.compiled_material_bytes, self.static_material_bytes):
            raise ValueError("v3.2 material measurements drifted")
        return self


class PersonaV32MaterialsFreeze(FrozenModel):
    freeze_version: Literal["1.0.0"] = "1.0.0"
    construction_report_digest: Sha256Digest
    compiled_material_digest: Sha256Digest
    static_material_digest: Sha256Digest
    compiled_material_bytes: int = Field(ge=1, le=3000)
    static_material_bytes: int = Field(ge=1, le=3000)
    target_runner_digest: Sha256Digest
    target_sessions_started: Literal[False] = False
    construction_exact: Literal[True] = True
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False


class PersonaV32TrialReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = "1.0.0"
    observation: CodexDevelopmentRunObservation
    delivery: TaskMaterialDeliveryReceipt
    integrity_valid: bool
    integrity_failures: tuple[NonEmptyStr, ...] = ()
    behavior_conformant: bool
    behavior_failures: tuple[NonEmptyStr, ...] = ()
    visible_tests_executed: Annotated[int, Field(ge=0)]
    encrypted_trace_ref: Sha256Digest

    @field_validator("integrity_failures", "behavior_failures")
    @classmethod
    def failures_are_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("v3.2 trial failures must be sorted and unique")
        return value

    @model_validator(mode="after")
    def states_are_coherent(self) -> Self:
        if self.integrity_valid != (not self.integrity_failures):
            raise ValueError("v3.2 integrity state does not match failures")
        if self.behavior_conformant != (not self.behavior_failures):
            raise ValueError("v3.2 behavior state does not match failures")
        return self


class PersonaV32JudgeDecision(FrozenModel):
    decision_version: Literal["1.0.0"] = "1.0.0"
    rating: CompactJudgePair
    evaluator_limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]


class PersonaV32TaskOutcome(FrozenModel):
    task_id: Identifier
    applicable_adaptation: bool
    compiled_output_id: Identifier
    static_output_id: Identifier
    compiled_behavior_conformant: bool
    static_behavior_conformant: bool
    compiled_checks_passed: int = Field(ge=0)
    static_checks_passed: int = Field(ge=0)
    checks_total: int = Field(ge=1)
    automated_winner: Literal["compiled_adaptation", "strong_static_profile", "tie"]
    judge_winner: Literal["compiled_adaptation", "strong_static_profile", "tie"]


class PersonaV32FinalReport(FrozenModel):
    report_version: Literal["1.0.0"] = "1.0.0"
    protocol_digest: Sha256Digest
    fixture_digest: Sha256Digest
    oracle_digest: Sha256Digest
    construction_report_digest: Sha256Digest
    materials_freeze_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    target_blind_report_digest: Sha256Digest
    judge_receipt_digests: tuple[Sha256Digest, Sha256Digest]
    task_outcomes: Annotated[tuple[PersonaV32TaskOutcome, ...], Field(min_length=2, max_length=2)]
    instrument_valid: bool
    construction_exact: bool
    compiled_false_activation_count: int = Field(ge=0)
    static_false_activation_count: int = Field(ge=0)
    behavioral_gate_passed: bool
    permitted_claim: Literal[
        "fresh_canary_compiled_outperformed",
        "fresh_canary_compiled_matched_static",
        "product_gate_failed",
        "instrumentation_failure",
    ]
    counts_toward_effectiveness_evidence: Literal[True] = True
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def final_claim_is_bounded(self) -> Self:
        if not self.instrument_valid and self.permitted_claim != "instrumentation_failure":
            raise ValueError("invalid v3.2 instrumentation permits no behavioral claim")
        if self.behavioral_gate_passed and self.permitted_claim not in {
            "fresh_canary_compiled_outperformed",
            "fresh_canary_compiled_matched_static",
        }:
            raise ValueError("passing v3.2 gate requires a bounded positive claim")
        if (
            not self.behavioral_gate_passed
            and self.instrument_valid
            and self.permitted_claim != "product_gate_failed"
        ):
            raise ValueError("failed valid v3.2 gate requires the product failure claim")
        return self


def seed_commitment(seed: bytes) -> Sha256Digest:
    return f"sha256:{hashlib.sha256(b'temper/persona-v32/seed/v1\x00' + seed).hexdigest()}"


def _blind_id(seed: bytes, *, label: str, prefix: str) -> Identifier:
    value = hmac.new(seed, label.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{prefix}-{value}"


def build_v32_plan(
    *, fixture: PersonaV32Fixture, seed: bytes
) -> tuple[PersonaV32PublicPlan, dict[str, object]]:
    conditions = ("compiled_adaptation", "strong_static_profile")
    assignments = {
        condition: _blind_id(seed, label=f"condition:{condition}", prefix="condition")
        for condition in conditions
    }
    ordered: list[tuple[str, str]] = []
    for task in fixture.tasks:
        conditions_for_task = sorted(
            conditions,
            key=lambda condition: hmac.new(
                seed,
                f"order:{task.task_id}:{condition}".encode(),
                hashlib.sha256,
            ).digest(),
        )
        ordered.extend((task.task_id, condition) for condition in conditions_for_task)
    cells = tuple(
        PersonaV32PlanCell(
            sequence=index,
            run_id=_blind_id(seed, label=f"run:{task_id}:{condition}", prefix="run"),
            task_id=task_id,
            blind_condition_id=assignments[condition],
            blind_output_id=_blind_id(seed, label=f"output:{task_id}:{condition}", prefix="output"),
        )
        for index, (task_id, condition) in enumerate(ordered, start=1)
    )
    sorted_ids = sorted(assignments.values())
    public = PersonaV32PublicPlan(
        seed_commitment=seed_commitment(seed),
        blind_condition_ids=(sorted_ids[0], sorted_ids[1]),
        run_order=cells,
    )
    private: dict[str, object] = {
        "plan_version": "1.0.0",
        "seed_commitment": public.seed_commitment,
        "condition_assignments": [
            {"condition": condition, "blind_condition_id": assignments[condition]}
            for condition in conditions
        ],
        "run_order": [
            {**cell.model_dump(mode="json", round_trip=True), "condition": condition}
            for cell, (_, condition) in zip(cells, ordered, strict=True)
        ],
        "external_validation_accessed": False,
    }
    return public, private


def build_v32_fixture() -> PersonaV32Fixture:
    """Return the fresh evidence and task descriptors frozen before execution."""

    broad = Scope(subject_ids=("maren",), project_ids=("tide-ledger",))
    incident = Scope(
        subject_ids=("maren",),
        project_ids=("tide-ledger",),
        activation_conditions=("production_incident",),
    )
    messages = (
        PersonaEvidenceMessage(turn=1, message="Summarize the Tide Ledger status."),
        PersonaEvidenceMessage(
            turn=2,
            message=(
                "For Tide Ledger work, I prefer every action plan to end with an explicit "
                "confirmation step; keep that as my default here."
            ),
        ),
        PersonaEvidenceMessage(turn=3, message="Use two bullets for this answer."),
        PersonaEvidenceMessage(
            turn=4,
            message="Tide Ledger has a production incident during a retained-tree rollout.",
        ),
        PersonaEvidenceMessage(
            turn=5,
            message="Tell me what the on-call engineer should inspect.",
        ),
        PersonaEvidenceMessage(
            turn=6,
            message=(
                "For future Tide Ledger production incidents, inspect API health, then the "
                "deployed revision, then backlog pressure before taking replacement action."
            ),
        ),
        PersonaEvidenceMessage(turn=7, message="Do not edit files in this response."),
    )
    evidence = PersonaStageEvidence(
        persona_id="maren",
        stage=2,
        checkpoint_turn=7,
        messages=messages,
    )
    registry = PersonaHostScopeRegistry(
        persona_id="maren",
        stage=2,
        bindings=tuple(
            PersonaHostScopeBinding(
                binding_id=f"scope-maren-turn-{message.turn}",
                source_turn=message.turn,
                scope=broad if message.turn <= 3 else incident,
            )
            for message in messages
        ),
    )
    case = PersonaPublicCase(
        case_id="maren-v32-tide-ledger-stage-2",
        persona_id="maren",
        stage=2,
        checkpoint_turn=7,
        current_scope=incident,
        context_label="project:tide-ledger:production-incident",
        scenario="Prepare a Tide Ledger retained-tree incident transfer plan.",
    )
    applicable_prompt = (
        "Implement Tide Ledger's production-incident transfer planner in "
        "`src/transfer_policy.py`. Preserve `plan_transfer(destination_exists, "
        "retention_class, recovery_requested=False) -> tuple[str, ...]`. The retention "
        "classes are `retained_user_tree` and `rebuildable_cache`. The only action strings "
        "are `begin_capture`, `save_recovery_point`, `inspect_api_health`, "
        "`inspect_deployed_revision`, `inspect_backlog_pressure`, `replace_retained_tree`, "
        "`rebuild_cache`, and `confirm_result`. A missing destination begins capture. An "
        "existing rebuildable cache is rebuilt directly. An existing retained tree is "
        "replaced after any requested recovery point and the current approved incident "
        "checks. Apply the current approved Tide Ledger behavior supplied with this task, "
        "reject unknown retention classes with `ValueError`, change only "
        "`src/transfer_policy.py`, and run `python3 -m unittest discover -v`."
    )
    neutral_prompt = (
        "Implement Ember Quay's thumbnail-cache transfer planner in "
        "`src/transfer_policy.py`. Preserve `plan_transfer(destination_exists, "
        "retention_class, recovery_requested=False) -> tuple[str, ...]`. The retention "
        "classes are `retained_user_tree` and `rebuildable_cache`. The only action strings "
        "are `create_thumbnail_cache`, `snapshot_layout`, `replace_layout`, "
        "`swap_thumbnail_cache`, `verify_layout`, `verify_cache`, and `decline`. A missing "
        "destination returns only `create_thumbnail_cache`. An existing rebuildable cache "
        "returns `swap_thumbnail_cache`, then `verify_cache`. For an existing retained tree, "
        "return `snapshot_layout`, `replace_layout`, then `verify_layout` when recovery is "
        "requested; otherwise return only `decline`. Reject unknown retention classes with "
        "`ValueError`, change only `src/transfer_policy.py`, and run "
        "`python3 -m unittest discover -v`."
    )
    return PersonaV32Fixture(
        case=case,
        evidence=evidence,
        scope_registry=registry,
        tasks=(
            PersonaV32TaskCase(
                task_id="ember-quay-thumbnail-control",
                project_id="ember-quay",
                context_label="project:ember-quay:thumbnail-cache",
                applicable_adaptation=False,
                fixture_directory=(
                    "development_benchmark_persona_v32/tasks/ember-quay-thumbnail-control/fixture"
                ),
                prompt=neutral_prompt,
            ),
            PersonaV32TaskCase(
                task_id="tide-ledger-incident-transfer",
                project_id="tide-ledger",
                context_label="project:tide-ledger:production-incident",
                applicable_adaptation=True,
                fixture_directory=(
                    "development_benchmark_persona_v32/tasks/tide-ledger-incident-transfer/fixture"
                ),
                prompt=applicable_prompt,
            ),
        ),
    )


def _scenario_id(destination: bool, storage: str, recovery: bool) -> str:
    return (
        f"{'existing' if destination else 'missing'}-"
        f"{'persistent' if storage == 'durable_release' else 'generated'}-"
        f"{'requested' if recovery else 'unrequested'}"
    )


def build_v32_oracle(fixture: PersonaV32Fixture) -> PersonaV32Oracle:
    """Return material and behavior answers kept out of all agent packets."""

    material = PersonaHiddenOracle(
        case_id=fixture.case.case_id,
        persona_id=fixture.case.persona_id,
        sentinel=False,
        active_claims=(
            PersonaExpectedClaim(
                source_turn=2,
                route=ArtifactRoute.PREFERENCE,
                scope=fixture.scope_registry.binding_for_turn(2).scope,
            ),
            PersonaExpectedClaim(
                source_turn=6,
                route=ArtifactRoute.PROCEDURE,
                scope=fixture.scope_registry.binding_for_turn(6).scope,
            ),
        ),
        forbidden_source_turns=(1, 3, 4, 5, 7),
    )
    tide: list[PersonaV32TaskScenario] = []
    ember: list[PersonaV32TaskScenario] = []
    for destination in (False, True):
        for storage in ("durable_release", "ephemeral_build_cache"):
            for recovery in (False, True):
                scenario_id = _scenario_id(destination, storage, recovery)
                tide_plan: tuple[str, ...]
                ember_plan: tuple[str, ...]
                metric: Literal["objective", "diagnostic", "neutral"]
                if not destination:
                    tide_plan = ("begin_capture", "confirm_result")
                    ember_plan = ("create_thumbnail_cache",)
                    metric = "objective"
                elif storage == "ephemeral_build_cache":
                    tide_plan = ("rebuild_cache", "confirm_result")
                    ember_plan = ("swap_thumbnail_cache", "verify_cache")
                    metric = "neutral"
                else:
                    tide_plan = (
                        *(("save_recovery_point",) if recovery else ()),
                        "inspect_api_health",
                        "inspect_deployed_revision",
                        "inspect_backlog_pressure",
                        "replace_retained_tree",
                        "confirm_result",
                    )
                    ember_plan = (
                        ("snapshot_layout", "replace_layout", "verify_layout")
                        if recovery
                        else ("decline",)
                    )
                    metric = "diagnostic"
                for collection, plan in ((tide, tide_plan), (ember, ember_plan)):
                    collection.append(
                        PersonaV32TaskScenario(
                            scenario_id=scenario_id,
                            destination_exists=destination,
                            storage_class=storage,
                            recovery_copy_approved=recovery,
                            expected_plan=plan,
                            metric=metric,
                        )
                    )
    return PersonaV32Oracle(
        material=material,
        tasks=(
            PersonaV32TaskOracle(
                task_id="ember-quay-thumbnail-control",
                scenarios=tuple(sorted(ember, key=lambda item: item.scenario_id)),
            ),
            PersonaV32TaskOracle(
                task_id="tide-ledger-incident-transfer",
                scenarios=tuple(sorted(tide, key=lambda item: item.scenario_id)),
            ),
        ),
    )


def build_v32_observations(fixture: PersonaV32Fixture) -> tuple[InteractionObservation, ...]:
    observed_at = datetime(2026, 8, 17, 22, 0, tzinfo=UTC)
    schema_digest = canonical_digest(PersonaV32Fixture.model_json_schema())
    return tuple(
        InteractionObservation(
            observation_id=f"v32-maren-turn-{message.turn}",
            subject_id=fixture.case.persona_id,
            task_ref=TaskRecordRef(
                record_id="persona-v32-maren-stage-2",
                record_version="1.0.0",
            ),
            turn_id=f"turn-{message.turn}",
            actor=ActorRef(actor_id=fixture.case.persona_id, kind=ActorKind.USER),
            source_class=SourceClass.EXPLICIT_USER_FEEDBACK,
            text=message.message,
            scope=fixture.scope_registry.binding_for_turn(message.turn).scope,
            observed_at=observed_at + timedelta(minutes=message.turn),
            source_system="local_interaction_runtime",
            source_version="1.0.0",
            source_schema_digest=schema_digest,
        )
        for message in fixture.evidence.messages
    )


def build_v32_author_packet(
    protocol: PersonaV32Protocol, fixture: PersonaV32Fixture
) -> PersonaV3ProfileAuthorPacket:
    return PersonaV3ProfileAuthorPacket(
        protocol_digest=canonical_digest(protocol),
        persona_id=fixture.case.persona_id,
        evidence=fixture.evidence,
        scope_registry_digest=canonical_digest(fixture.scope_registry),
    )


def bind_v32_profile_material(
    *, fixture: PersonaV32Fixture, reviewed: PersonaV3ProfileOutput
) -> PersonaMaterialSnapshot:
    visible = {item.turn: item for item in fixture.evidence.messages}
    claims: list[PersonaMaterialClaim] = []
    for proposal in reviewed.snapshot.claims:
        if any(turn not in visible for turn in proposal.source_turns):
            raise ValueError("v3.2 profile cited hidden or future evidence")
        binding = fixture.scope_registry.binding_for_turn(proposal.source_turns[-1])
        claim_digest = canonical_digest(
            {
                "persona_id": fixture.case.persona_id,
                "proposal": proposal.model_dump(mode="json", round_trip=True),
                "scope_binding_id": binding.binding_id,
            }
        ).removeprefix("sha256:")
        claims.append(
            PersonaMaterialClaim(
                claim_id=f"claim-{claim_digest[:24]}",
                statement=proposal.statement,
                route=proposal.route,
                scope=binding.scope,
                source_turns=proposal.source_turns,
                evidence_digests=tuple(
                    canonical_digest(visible[turn]) for turn in proposal.source_turns
                ),
            )
        )
    applicable = tuple(
        claim for claim in claims if scope_is_within(fixture.case.current_scope, claim.scope)
    )
    return PersonaMaterialSnapshot(
        case_id=fixture.case.case_id,
        persona_id=fixture.case.persona_id,
        source=PersonaMaterialSource.STATIC,
        claims=applicable,
        target_guidance=render_neutral_guidance(applicable),
        evidence_checkpoint_digest=fixture.evidence.content_digest,
        independently_reviewed=True,
    )


def bind_v32_compiled_material(
    *, fixture: PersonaV32Fixture, records: tuple[PersonaSensorRecord, ...]
) -> PersonaMaterialSnapshot:
    return compile_host_scoped_sensor_material(
        case=fixture.case,
        evidence=fixture.evidence,
        records=records,
        registry=fixture.scope_registry,
    )


def score_v32_material(
    fixture: PersonaV32Fixture,
    oracle: PersonaV32Oracle,
    material: PersonaMaterialSnapshot,
) -> PersonaObjectiveScore:
    if fixture.case.case_id != oracle.material.case_id:
        raise ValueError("v3.2 material oracle crossed fixtures")
    return score_objective_state(material, oracle.material)


def persona_v32_schemas() -> dict[str, dict[str, object]]:
    return {
        "persona-v32-protocol.schema.json": PersonaV32Protocol.model_json_schema(),
        "persona-v32-fixture.schema.json": PersonaV32Fixture.model_json_schema(),
        "persona-v32-oracle.schema.json": PersonaV32Oracle.model_json_schema(),
        "persona-v32-freeze.schema.json": PersonaV32Freeze.model_json_schema(),
        "persona-v32-construction-report.schema.json": (
            PersonaV32ConstructionReport.model_json_schema()
        ),
        "persona-v32-materials-freeze.schema.json": PersonaV32MaterialsFreeze.model_json_schema(),
        "persona-v32-public-plan.schema.json": PersonaV32PublicPlan.model_json_schema(),
        "persona-v32-trial-receipt.schema.json": PersonaV32TrialReceipt.model_json_schema(),
        "persona-v32-judge-decision.schema.json": PersonaV32JudgeDecision.model_json_schema(),
        "persona-v32-final-report.schema.json": PersonaV32FinalReport.model_json_schema(),
    }
