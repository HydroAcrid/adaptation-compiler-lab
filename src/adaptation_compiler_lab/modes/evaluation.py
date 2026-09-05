"""Frozen same-agent effectiveness instrument for built-in capability Modes."""

from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import time
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
)
from adaptation_compiler_lab.domain.values import strings_are_sorted_unique
from adaptation_compiler_lab.serialization import canonical_digest

if TYPE_CHECKING:
    from adaptation_compiler_lab.benchmark.longitudinal_instrument import BoundedScorerReceipt

ModeEvaluationCondition = Literal["core-only", "core-plus-mode"]
ModeEvaluationMetric = Literal["diagnostic", "neutral"]


class ModeEvaluationScenarioV1(FrozenModel):
    """One answer-bearing scorer case that never enters a target workspace."""

    scenario_id: Identifier
    arguments: tuple[object, ...]
    expected: object
    metric: ModeEvaluationMetric


class ModePolicyObservationV1(FrozenModel):
    """Answer-blind return from one capability-free generated policy."""

    observation_version: Literal["1.0.0"] = "1.0.0"
    scenario_id: Identifier
    status: Literal["returned", "raised", "invalid_return"]
    value: object | None = None
    detail: NonEmptyStr | None = None

    @model_validator(mode="after")
    def state_is_coherent(self) -> Self:
        if self.status == "returned" and self.detail is not None:
            raise ValueError("returned Mode observation cannot contain an error detail")
        if self.status != "returned" and self.detail is None:
            raise ValueError("failed Mode observation requires an error detail")
        return self


class ModeEvaluationFixtureV1(FrozenModel):
    """One public task binding plus hidden independent scorer cases."""

    fixture_version: Literal["1.0.0"] = "1.0.0"
    task_id: Identifier
    mode_id: Identifier
    kind: Literal["diagnostic", "neutral_control"]
    title: NonEmptyStr
    prompt: NonEmptyStr
    function_name: Identifier
    fixture_directory: NonEmptyStr
    fixture_digest: Sha256Digest
    allowed_change_paths: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    visible_test_command: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    scenarios: Annotated[tuple[ModeEvaluationScenarioV1, ...], Field(min_length=3)]

    @field_validator("allowed_change_paths")
    @classmethod
    def paths_are_safe_sorted_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not strings_are_sorted_unique(value):
            raise ValueError("mode evaluation writable paths must be sorted and unique")
        for raw in value:
            path = PurePosixPath(raw)
            if path.is_absolute() or ".." in path.parts or raw != path.as_posix():
                raise ValueError("mode evaluation writable paths must be safe relative paths")
        return value

    @field_validator("visible_test_command")
    @classmethod
    def visible_command_is_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != ("python3", "-m", "unittest", "discover", "-v"):
            raise ValueError("mode evaluation visible command must use the frozen unittest form")
        return value

    @model_validator(mode="after")
    def task_and_scenarios_are_coherent(self) -> Self:
        ids = tuple(item.scenario_id for item in self.scenarios)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("mode evaluation scenarios must be sorted and unique")
        expected_metric: ModeEvaluationMetric = (
            "diagnostic" if self.kind == "diagnostic" else "neutral"
        )
        if any(item.metric != expected_metric for item in self.scenarios):
            raise ValueError("mode evaluation scenario metric does not match task kind")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeEvaluationExecutionContractV1(FrozenModel):
    """Exact zero-provider-billing runtime and scoring contract."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    catalog_design_digests: Annotated[tuple[Sha256Digest, ...], Field(min_length=3, max_length=3)]
    fixtures: Annotated[tuple[ModeEvaluationFixtureV1, ...], Field(min_length=15, max_length=15)]
    runner_source_digest: Sha256Digest
    scorer_source_digest: Sha256Digest
    observer_source_digest: Sha256Digest
    judge_role_runner_source_digest: Sha256Digest
    judge_source_digest: Sha256Digest
    unblind_source_digest: Sha256Digest
    target_cli_version: Literal["codex-cli 0.153.1"] = "codex-cli 0.153.1"
    target_cli_digest: Literal[
        "sha256:b9315df68cb0e2827c940ffacb66f7524e820d9744060c755fbf938724ad2b76"
    ] = "sha256:b9315df68cb0e2827c940ffacb66f7524e820d9744060c755fbf938724ad2b76"
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    target_reasoning_effort: Literal["medium"] = "medium"
    target_timeout_seconds: Literal[600] = 600
    target_runs: Literal[30] = 30
    blinded_judge_sessions: Literal[3] = 3
    judge_model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    judge_reasoning_effort: Literal["xhigh"] = "xhigh"
    judge_timeout_seconds: Literal[600] = 600
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    external_validation_accessed: Literal[False] = False
    tuning_after_first_target_run: Literal[False] = False

    @model_validator(mode="after")
    def catalog_is_complete(self) -> Self:
        task_ids = tuple(item.task_id for item in self.fixtures)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("mode evaluation fixtures must be sorted and unique")
        mode_counts = Counter(item.mode_id for item in self.fixtures)
        if sorted(mode_counts.values()) != [5, 5, 5]:
            raise ValueError("mode evaluation requires five tasks for each of three Modes")
        for mode_id in mode_counts:
            kinds = Counter(item.kind for item in self.fixtures if item.mode_id == mode_id)
            if kinds != Counter({"diagnostic": 3, "neutral_control": 2}):
                raise ValueError("each Mode requires three diagnostics and two controls")
        if self.catalog_design_digests != tuple(sorted(set(self.catalog_design_digests))):
            raise ValueError("catalog design digests must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeEvaluationRunCellV1(FrozenModel):
    sequence: Annotated[int, Field(ge=1, le=30)]
    run_id: Identifier
    task_id: Identifier
    blind_condition_id: Identifier
    blind_output_id: Identifier


class ModeEvaluationPublicPlanV1(FrozenModel):
    """Condition-blind target order safe to commit before execution."""

    plan_version: Literal["1.0.0"] = "1.0.0"
    contract_digest: Sha256Digest
    seed_commitment: Sha256Digest
    blind_condition_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    run_order: Annotated[tuple[ModeEvaluationRunCellV1, ...], Field(min_length=30, max_length=30)]
    condition_mapping_withheld: Literal[True] = True
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def order_is_complete(self) -> Self:
        if self.blind_condition_ids != tuple(sorted(set(self.blind_condition_ids))):
            raise ValueError("blind condition IDs must be sorted and unique")
        if tuple(item.sequence for item in self.run_order) != tuple(range(1, 31)):
            raise ValueError("mode evaluation run sequence must be contiguous")
        if len({item.run_id for item in self.run_order}) != 30:
            raise ValueError("mode evaluation run IDs must be unique")
        if len({item.blind_output_id for item in self.run_order}) != 30:
            raise ValueError("mode evaluation output IDs must be unique")
        if len({(item.task_id, item.blind_condition_id) for item in self.run_order}) != 30:
            raise ValueError("mode evaluation plan must contain each task-condition cell once")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeJudgePairDecisionV1(FrozenModel):
    """One condition-blind quality preference over an exact anonymous pair."""

    task_id: Identifier
    ordered_output_ids: Annotated[tuple[Identifier, ...], Field(min_length=2, max_length=2)]
    preferred_output_id: Identifier | None = None
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def preference_is_bound_to_the_pair(self) -> Self:
        if len(set(self.ordered_output_ids)) != 2:
            raise ValueError("Mode judge pair requires two distinct output IDs")
        if (
            self.preferred_output_id is not None
            and self.preferred_output_id not in self.ordered_output_ids
        ):
            raise ValueError("Mode judge preference must select an output in its pair")
        return self


class ModeJudgeDecisionV1(FrozenModel):
    """One fresh judge's five condition-blind decisions for a single Mode."""

    decision_version: Literal["1.0.0"] = "1.0.0"
    mode_id: Identifier
    pair_ratings: Annotated[tuple[ModeJudgePairDecisionV1, ...], Field(min_length=5, max_length=5)]
    overall_assessment: NonEmptyStr
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def ratings_are_complete_and_ordered(self) -> Self:
        task_ids = tuple(item.task_id for item in self.pair_ratings)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("Mode judge task ratings must be sorted and unique")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class ModeEvaluationTaskOutcomeV1(FrozenModel):
    """Unblinded objective and secondary result for one Mode task."""

    task_id: Identifier
    mode_id: Identifier
    kind: Literal["diagnostic", "neutral_control"]
    core_output_id: Identifier
    mode_output_id: Identifier
    core_checks_passed: int = Field(ge=0)
    core_checks_total: int = Field(ge=1)
    mode_checks_passed: int = Field(ge=0)
    mode_checks_total: int = Field(ge=1)
    automated_winner: Literal["core-only", "core-plus-mode", "tie"]
    judge_winner: Literal["core-only", "core-plus-mode", "tie"]
    core_behavior_conformant: bool
    mode_behavior_conformant: bool

    @model_validator(mode="after")
    def check_counts_are_valid(self) -> Self:
        if self.core_checks_passed > self.core_checks_total:
            raise ValueError("core check count exceeds its total")
        if self.mode_checks_passed > self.mode_checks_total:
            raise ValueError("Mode check count exceeds its total")
        return self


class ModeEvaluationModeOutcomeV1(FrozenModel):
    """Preregistered pass/fail result for one capability Mode."""

    mode_id: Identifier
    tasks: Annotated[tuple[ModeEvaluationTaskOutcomeV1, ...], Field(min_length=5, max_length=5)]
    instrument_valid: bool
    gate_passed: bool
    diagnostic_core_passed: int = Field(ge=0)
    diagnostic_mode_passed: int = Field(ge=0)
    neutral_core_passed: int = Field(ge=0)
    neutral_mode_passed: int = Field(ge=0)
    judge_core_wins: int = Field(ge=0)
    judge_mode_wins: int = Field(ge=0)
    judge_ties: int = Field(ge=0)
    projection_utf8_bytes: int = Field(ge=0, le=12000)
    failure_reasons: tuple[NonEmptyStr, ...] = ()
    permitted_claim: Literal[
        "bounded_same_agent_mode_evidence",
        "mode_gate_failed",
        "instrumentation_failure",
    ]

    @model_validator(mode="after")
    def outcome_is_coherent(self) -> Self:
        task_ids = tuple(item.task_id for item in self.tasks)
        if task_ids != tuple(sorted(set(task_ids))):
            raise ValueError("Mode outcome tasks must be sorted and unique")
        if any(item.mode_id != self.mode_id for item in self.tasks):
            raise ValueError("Mode outcome contains a task from another Mode")
        if self.judge_core_wins + self.judge_mode_wins + self.judge_ties != 5:
            raise ValueError("Mode outcome must account for five blind ratings")
        expected_claim = (
            "instrumentation_failure"
            if not self.instrument_valid
            else ("bounded_same_agent_mode_evidence" if self.gate_passed else "mode_gate_failed")
        )
        if self.permitted_claim != expected_claim:
            raise ValueError("Mode outcome claim does not match its gate state")
        if self.gate_passed and self.failure_reasons:
            raise ValueError("a passing Mode outcome cannot contain failure reasons")
        return self


class ModeEvaluationResultV1(FrozenModel):
    """Complete immutable unblinded result for the three-Mode instrument."""

    result_version: Literal["1.0.0"] = "1.0.0"
    contract_digest: Sha256Digest
    public_plan_digest: Sha256Digest
    source_commit: NonEmptyStr
    mode_outcomes: Annotated[
        tuple[ModeEvaluationModeOutcomeV1, ...], Field(min_length=3, max_length=3)
    ]
    all_instrument_valid: bool
    passed_mode_count: int = Field(ge=0, le=3)
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def aggregate_is_exact(self) -> Self:
        mode_ids = tuple(item.mode_id for item in self.mode_outcomes)
        if mode_ids != tuple(sorted(set(mode_ids))):
            raise ValueError("Mode results must be sorted and unique")
        if self.all_instrument_valid != all(item.instrument_valid for item in self.mode_outcomes):
            raise ValueError("aggregate instrument validity is inconsistent")
        if self.passed_mode_count != sum(item.gate_passed for item in self.mode_outcomes):
            raise ValueError("aggregate passing Mode count is inconsistent")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


def _blind_id(seed: bytes, label: str, prefix: str) -> str:
    value = hmac.new(seed, label.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{prefix}-{value}"


def build_mode_evaluation_plan(
    contract: ModeEvaluationExecutionContractV1,
    *,
    seed: bytes,
) -> tuple[ModeEvaluationPublicPlanV1, dict[str, object]]:
    """Create a deterministic blocked order and separately held condition mapping."""

    if len(seed) < 32:
        raise ValueError("mode evaluation randomization seed requires at least 256 bits")
    conditions: tuple[ModeEvaluationCondition, ...] = ("core-only", "core-plus-mode")
    condition_ids = {
        condition: _blind_id(seed, f"condition:{condition}", "condition")
        for condition in conditions
    }
    cells: list[dict[str, object]] = []
    sequence = 1
    for fixture in sorted(
        contract.fixtures,
        key=lambda item: hmac.new(
            seed,
            f"task:{item.task_id}".encode(),
            hashlib.sha256,
        ).digest(),
    ):
        ordered_conditions = sorted(
            conditions,
            key=lambda condition: hmac.new(
                seed,
                f"cell:{fixture.task_id}:{condition}".encode(),
                hashlib.sha256,
            ).digest(),
        )
        for condition in ordered_conditions:
            cells.append(
                {
                    "sequence": sequence,
                    "run_id": _blind_id(seed, f"run:{fixture.task_id}:{condition}", "run"),
                    "task_id": fixture.task_id,
                    "blind_condition_id": condition_ids[condition],
                    "blind_output_id": _blind_id(
                        seed,
                        f"output:{fixture.task_id}:{condition}",
                        "output",
                    ),
                    "condition": condition,
                }
            )
            sequence += 1
    commitment = (
        "sha256:" + hashlib.sha256(b"temper/mode-evaluation/seed/v1\x00" + seed).hexdigest()
    )
    public = ModeEvaluationPublicPlanV1(
        contract_digest=contract.content_digest,
        seed_commitment=commitment,
        blind_condition_ids=tuple(sorted(condition_ids.values())),
        run_order=tuple(
            ModeEvaluationRunCellV1.model_validate(
                {key: value for key, value in cell.items() if key != "condition"}
            )
            for cell in cells
        ),
    )
    private = {
        "plan_version": "1.0.0",
        "contract_digest": contract.content_digest,
        "seed_commitment": commitment,
        "condition_assignments": [
            {"condition": condition, "blind_condition_id": condition_ids[condition]}
            for condition in conditions
        ],
        "run_order": cells,
        "external_validation_accessed": False,
    }
    return public, private


def load_mode_evaluation_contract(path: Path) -> ModeEvaluationExecutionContractV1:
    try:
        return ModeEvaluationExecutionContractV1.model_validate_json(
            path.read_text(encoding="utf-8"),
            strict=True,
        )
    except (OSError, ValueError, TypeError) as error:
        raise ValueError(f"invalid Mode evaluation contract: {path}") from error


def load_mode_evaluation_fixture(path: Path) -> ModeEvaluationFixtureV1:
    try:
        return ModeEvaluationFixtureV1.model_validate_json(
            path.read_text(encoding="utf-8"),
            strict=True,
        )
    except (OSError, ValueError, TypeError) as error:
        raise ValueError(f"invalid Mode evaluation fixture: {path}") from error


def run_bounded_mode_policy_observation(
    *,
    observer_script: Path,
    workspace: Path,
    scenario: ModeEvaluationScenarioV1,
    function_name: str,
    timeout_seconds: float = 2.0,
) -> tuple[ModePolicyObservationV1 | None, BoundedScorerReceipt]:
    """Execute one hidden call in the existing answer-blind Linux scorer sandbox."""

    from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
        BoundedScorerReceipt,
        _BoundedProcessOutcome,
        _bytes_digest,
        _current_uid_process_count,
        _policy_observer_sandbox_command,
        _run_bounded_sandbox_command,
    )

    started = time.monotonic()
    process_limit = max(_current_uid_process_count() + 16, 128)
    scenario_json = json.dumps(
        {
            "arguments": scenario.arguments,
            "function_name": function_name,
            "scenario_id": scenario.scenario_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with tempfile.TemporaryDirectory(prefix="temper-mode-observer-sandbox-") as temporary:
        sandbox_root = Path(temporary)
        try:
            command = _policy_observer_sandbox_command(
                sandbox_root=sandbox_root,
                observer_script=observer_script,
                workspace=workspace,
                scenario_json=scenario_json,
            )
            outcome = _run_bounded_sandbox_command(
                command=command,
                cwd=workspace,
                sandbox_root=sandbox_root,
                timeout_seconds=timeout_seconds,
                process_limit=process_limit,
                started=started,
            )
        except OSError as error:
            outcome = _BoundedProcessOutcome(
                status="crashed",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                reason=f"Mode observer sandbox could not start: {error}",
                duration_seconds=time.monotonic() - started,
            )
    status: Literal["succeeded", "timed_out", "crashed", "malformed_output"] = outcome.status
    reason = outcome.reason
    observation: ModePolicyObservationV1 | None = None
    if status == "succeeded":
        try:
            observation = ModePolicyObservationV1.model_validate_json(
                outcome.stdout.decode("utf-8")
            )
            if observation.scenario_id != scenario.scenario_id:
                raise ValueError("Mode observer returned a different scenario ID")
        except (UnicodeDecodeError, ValueError, TypeError) as error:
            status = "malformed_output"
            reason = f"{type(error).__name__}: {error}"
    receipt = BoundedScorerReceipt(
        status=status,
        exit_code=outcome.exit_code,
        duration_seconds=outcome.duration_seconds,
        stdout_digest=_bytes_digest(outcome.stdout),
        stderr_digest=_bytes_digest(outcome.stderr),
        failure_reason=reason,
        timeout_seconds=timeout_seconds,
    )
    return observation, receipt
