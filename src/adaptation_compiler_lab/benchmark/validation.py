"""Public validation entry points for benchmark configuration data."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from adaptation_compiler_lab.benchmark.models import (
    BenchmarkConfig,
    BenchmarkOutcomeRecord,
    FeasibilityDesign,
    InternalFeasibilityDesign,
)
from adaptation_compiler_lab.domain.enums import Partition


class BenchmarkConfigurationError(ValueError):
    """Stable wrapper for schema and cross-record benchmark violations."""

    def __init__(self, validation_error: ValidationError) -> None:
        self.validation_error = validation_error
        messages = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in validation_error.errors(include_url=False)
        )
        super().__init__(messages)


def validate_benchmark_config(value: BenchmarkConfig | dict[str, Any]) -> BenchmarkConfig:
    """Validate a config without reading held-out payloads or mutating state."""

    payload = value.model_dump(mode="python") if isinstance(value, BenchmarkConfig) else value
    try:
        return BenchmarkConfig.model_validate(payload)
    except ValidationError as error:
        raise BenchmarkConfigurationError(error) from error


def validate_feasibility_design(
    value: FeasibilityDesign | dict[str, Any],
) -> FeasibilityDesign:
    """Validate the exact machine-readable Milestone 3 preregistration."""

    payload = value.model_dump(mode="python") if isinstance(value, FeasibilityDesign) else value
    try:
        return FeasibilityDesign.model_validate(payload)
    except ValidationError as error:
        raise BenchmarkConfigurationError(error) from error


def validate_internal_feasibility_design(
    value: InternalFeasibilityDesign | dict[str, Any],
) -> InternalFeasibilityDesign:
    """Validate the exact machine-readable internal v1.1 preregistration."""

    payload = (
        value.model_dump(mode="python") if isinstance(value, InternalFeasibilityDesign) else value
    )
    try:
        return InternalFeasibilityDesign.model_validate(payload)
    except ValidationError as error:
        raise BenchmarkConfigurationError(error) from error


def validate_benchmark_outcomes(
    config: BenchmarkConfig, outcomes: tuple[BenchmarkOutcomeRecord, ...]
) -> tuple[BenchmarkOutcomeRecord, ...]:
    """Validate blinded result rows against registered held-out tasks and conditions."""

    task_by_id = {task.task_id: task for task in config.tasks}
    blind_ids = {bundle.blind_id for bundle in config.condition_bundles}
    if outcomes and (
        config.freeze.held_out_revealed_at is None or config.freeze.execution_started_at is None
    ):
        raise ValueError(
            "benchmark outcomes require registered held-out reveal and execution timestamps"
        )
    seen_run_ids: set[str] = set()
    seen_cells: set[tuple[str, str, int]] = set()
    for outcome in outcomes:
        if outcome.run_id in seen_run_ids:
            raise ValueError(f"duplicate benchmark run ID {outcome.run_id!r}")
        seen_run_ids.add(outcome.run_id)
        task = task_by_id.get(outcome.task_id)
        if task is None:
            raise ValueError(f"outcome references unknown task {outcome.task_id!r}")
        if task.partition is not Partition.HELD_OUT:
            raise ValueError("confirmatory outcome must reference a held-out task")
        if task.cluster_id != outcome.cluster_id:
            raise ValueError("outcome cluster must match its registered task")
        if outcome.blind_condition_id not in blind_ids:
            raise ValueError("outcome uses an unregistered blind condition ID")
        cell = (outcome.task_id, outcome.blind_condition_id, outcome.trial_index)
        if cell in seen_cells:
            raise ValueError("duplicate task-condition-trial outcome cell")
        seen_cells.add(cell)
    if outcomes:
        held_out_task_ids = {
            task.task_id for task in config.tasks if task.partition is Partition.HELD_OUT
        }
        expected_cells = {
            (task_id, blind_id, trial_index)
            for task_id in held_out_task_ids
            for blind_id in blind_ids
            for trial_index in range(1, config.planned_trials_per_cell + 1)
        }
        if seen_cells != expected_cells:
            missing_cells = len(expected_cells - seen_cells)
            unexpected_cells = len(seen_cells - expected_cells)
            raise ValueError(
                "outcomes must contain every planned held-out task-condition-trial cell "
                f"(missing={missing_cells}, unexpected={unexpected_cells})"
            )
    return outcomes
