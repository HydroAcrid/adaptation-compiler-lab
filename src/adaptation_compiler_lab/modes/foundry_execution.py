"""Frozen execution and result records for one bounded curated-Mode screen."""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.domain import FrozenModel, Identifier, Sha256Digest
from adaptation_compiler_lab.modes.evaluation import ModeEvaluationFixtureV1
from adaptation_compiler_lab.serialization import canonical_digest

FoundryCondition = Literal["compiled_mode", "core_only", "upstream_safe"]


class FoundryExecutionContractV1(FrozenModel):
    """Exact eight-cell Systematic Debugger execution contract."""

    contract_version: Literal["1.0.0"] = "1.0.0"
    design_digest: Sha256Digest
    catalog_digest: Sha256Digest
    release_digest: Sha256Digest
    mode_id: Literal["curated-systematic-debugger"] = "curated-systematic-debugger"
    fixtures: Annotated[tuple[ModeEvaluationFixtureV1, ...], Field(min_length=3, max_length=3)]
    upstream_material_digest: Sha256Digest
    compiled_material_digest: Sha256Digest
    compiled_material_utf8_bytes: Annotated[int, Field(ge=1, le=12_000)]
    runner_source_digest: Sha256Digest
    scorer_source_digest: Sha256Digest
    observer_source_digest: Sha256Digest
    target_cli_version: Literal["codex-cli 0.153.1"] = "codex-cli 0.153.1"
    target_cli_digest: Literal[
        "sha256:b9315df68cb0e2827c940ffacb66f7524e820d9744060c755fbf938724ad2b76"
    ] = "sha256:b9315df68cb0e2827c940ffacb66f7524e820d9744060c755fbf938724ad2b76"
    code_mode_host_digest: Literal[
        "sha256:c215117917037afd6b7621ba11ca18054ebdb890c314454f485b27574a73e1b7"
    ] = "sha256:c215117917037afd6b7621ba11ca18054ebdb890c314454f485b27574a73e1b7"
    bubblewrap_digest: Literal[
        "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    ] = "sha256:d78807229d616606e339c5988392b9e0ab4a6a6998fa51e4590837f426a12fca"
    target_model: Literal["gpt-5.6-luna"] = "gpt-5.6-luna"
    target_reasoning_effort: Literal["medium"] = "medium"
    target_timeout_seconds: Literal[600] = 600
    target_runs: Literal[8] = 8
    authentication: Literal["saved_chatgpt"] = "saved_chatgpt"
    provider_billed_calls: Literal[0] = 0
    api_keys_allowed: Literal[False] = False
    external_validation_accessed: Literal[False] = False
    tuning_after_first_run: Literal[False] = False

    @model_validator(mode="after")
    def fixture_set_is_exact(self) -> Self:
        ids = tuple(item.task_id for item in self.fixtures)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("Foundry fixtures must be sorted and unique")
        if Counter(item.kind for item in self.fixtures) != Counter(
            {"diagnostic": 2, "neutral_control": 1}
        ):
            raise ValueError("Foundry screen requires two diagnostics and one neutral control")
        if any(item.mode_id != self.mode_id for item in self.fixtures):
            raise ValueError("Foundry fixture references another Mode")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class FoundryTrialResultV1(FrozenModel):
    """Immutable public outcome for one condition/task cell."""

    trial_version: Literal["1.0.0"] = "1.0.0"
    run_id: Identifier
    task_id: Identifier
    task_kind: Literal["diagnostic", "neutral_control"]
    condition: FoundryCondition
    contract_digest: Sha256Digest
    source_commit: str
    trace_digest: Sha256Digest
    diff_digest: Sha256Digest
    final_response_digest: Sha256Digest
    command_digest: Sha256Digest
    environment_digest: Sha256Digest
    encrypted_trace_ref: Sha256Digest
    hidden_checks_passed: int = Field(ge=0)
    hidden_checks_total: int = Field(ge=1)
    visible_tests_passed: bool
    focused_reproduction_observed: bool | None
    regression_command_observed: bool
    behavior_conformant: bool
    integrity_valid: bool
    behavior_failures: tuple[str, ...] = ()
    integrity_failures: tuple[str, ...] = ()
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_output_tokens: int = Field(ge=0)
    workspace_destroyed: bool
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False

    @model_validator(mode="after")
    def counts_and_states_are_coherent(self) -> Self:
        if self.hidden_checks_passed > self.hidden_checks_total:
            raise ValueError("Foundry passed checks exceed total checks")
        if self.integrity_valid != (not self.integrity_failures):
            raise ValueError("Foundry integrity state is inconsistent")
        if self.behavior_conformant != (not self.behavior_failures):
            raise ValueError("Foundry behavior state is inconsistent")
        if self.task_kind == "neutral_control" and self.focused_reproduction_observed is not None:
            raise ValueError("neutral control cannot require a debugging reproduction")
        return self


class FoundryScreeningResultV1(FrozenModel):
    """Deterministic eight-cell screen with deliberately bounded claims."""

    result_version: Literal["1.0.0"] = "1.0.0"
    contract_digest: Sha256Digest
    source_commit: str
    trials: Annotated[tuple[FoundryTrialResultV1, ...], Field(min_length=8, max_length=8)]
    instrument_valid: bool
    disposition: Literal[
        "advance_to_blinded_comparison",
        "compiler_regression",
        "no_specialty_signal",
        "instrumentation_failure",
    ]
    reason: str
    provider_billed_calls: Literal[0] = 0
    external_validation_accessed: Literal[False] = False
    product_evaluated: Literal[False] = False

    @model_validator(mode="after")
    def aggregate_is_coherent(self) -> Self:
        if len({item.run_id for item in self.trials}) != 8:
            raise ValueError("Foundry result contains duplicate runs")
        if len({item.contract_digest for item in self.trials}) != 1 or any(
            item.contract_digest != self.contract_digest for item in self.trials
        ):
            raise ValueError("Foundry result mixes execution contracts")
        if len({item.source_commit for item in self.trials}) != 1 or any(
            item.source_commit != self.source_commit for item in self.trials
        ):
            raise ValueError("Foundry result mixes source commits")
        task_conditions = Counter((item.task_id, item.condition) for item in self.trials)
        if set(task_conditions.values()) != {1}:
            raise ValueError("Foundry result contains duplicate task-condition cells")
        diagnostic_conditions = Counter(
            item.condition for item in self.trials if item.task_kind == "diagnostic"
        )
        neutral_conditions = Counter(
            item.condition for item in self.trials if item.task_kind == "neutral_control"
        )
        if diagnostic_conditions != Counter(
            {"compiled_mode": 2, "core_only": 2, "upstream_safe": 2}
        ) or neutral_conditions != Counter({"compiled_mode": 1, "core_only": 1}):
            raise ValueError("Foundry result does not contain the frozen eight-cell design")
        if len({item.task_id for item in self.trials if item.task_kind == "diagnostic"}) != 2:
            raise ValueError("Foundry result requires two diagnostic tasks")
        if len({item.task_id for item in self.trials if item.task_kind == "neutral_control"}) != 1:
            raise ValueError("Foundry result requires one neutral-control task")
        if not all(item.workspace_destroyed for item in self.trials):
            raise ValueError("Foundry result requires destroyed disposable workspaces")
        if self.instrument_valid != all(item.integrity_valid for item in self.trials):
            raise ValueError("Foundry aggregate integrity is inconsistent")
        if not self.instrument_valid and self.disposition != "instrumentation_failure":
            raise ValueError("invalid Foundry instrument must report instrumentation failure")
        return self

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)
