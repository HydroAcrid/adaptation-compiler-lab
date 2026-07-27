"""Independent objective scoring for public longitudinal task workspaces."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Literal

from pydantic import Field

from adaptation_compiler_lab.benchmark.longitudinal import LongitudinalDevelopmentTask
from adaptation_compiler_lab.domain import FrozenModel, Identifier


class LongitudinalScenarioResult(FrozenModel):
    scenario_id: Identifier
    metric: Literal["objective", "diagnostic", "neutral"]
    passed: bool
    observed: str
    expected: str


class LongitudinalTaskScore(FrozenModel):
    task_id: Identifier
    scenario_results: tuple[LongitudinalScenarioResult, ...]
    objective_passed: int = Field(ge=0)
    objective_total: int = Field(ge=1)
    diagnostic_passed: int = Field(ge=0)
    diagnostic_total: int = Field(ge=1)
    neutral_passed: int = Field(ge=0)
    neutral_total: int = Field(ge=1)


def _load_policy(workspace: Path, task_id: str) -> ModuleType:
    path = workspace / "policy.py"
    if not path.is_file():
        raise ValueError("longitudinal workspace is missing policy.py")
    module_name = "_acl_longitudinal_" + task_id.replace("-", "_")
    specification = importlib.util.spec_from_file_location(module_name, path)
    if specification is None or specification.loader is None:
        raise ValueError("longitudinal policy module could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    prior_bytecode_policy = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        specification.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior_bytecode_policy
        sys.modules.pop(module_name, None)
    return module


def score_longitudinal_task(
    task: LongitudinalDevelopmentTask,
    workspace: Path,
) -> LongitudinalTaskScore:
    """Score all frozen scenarios without exposing condition identity."""

    try:
        module = _load_policy(workspace.resolve(), task.task_id)
    except Exception as error:
        return _failed_score(task, f"{type(error).__name__}: {error}")
    results: list[LongitudinalScenarioResult] = []
    for scenario in task.scenarios:
        try:
            expected: str
            if task.task_kind == "action":
                function = getattr(module, "choose_publish_action", None)
                if not callable(function):
                    raise ValueError("action task is missing choose_publish_action")
                value = function(scenario.destination_exists, scenario.backup_requested)
                observed = str(value)
                expected = scenario.expected_action
                passed = value == expected
            else:
                function = getattr(module, "build_publish_plan", None)
                if not callable(function):
                    raise ValueError("plan task is missing build_publish_plan")
                raw_value = function(scenario.destination_exists, scenario.backup_requested)
                value = (
                    tuple(raw_value) if isinstance(raw_value, (list, tuple)) else (str(raw_value),)
                )
                observed = repr(value)
                expected = repr(scenario.expected_plan)
                passed = value == scenario.expected_plan
        except Exception as error:
            observed = f"{type(error).__name__}: {error}"
            expected = (
                scenario.expected_action
                if task.task_kind == "action"
                else repr(scenario.expected_plan)
            )
            passed = False
        results.append(
            LongitudinalScenarioResult(
                scenario_id=scenario.scenario_id,
                metric=scenario.metric,
                passed=passed,
                observed=observed,
                expected=expected,
            )
        )

    def counts(metric: str) -> tuple[int, int]:
        selected = [item for item in results if item.metric == metric]
        return sum(item.passed for item in selected), len(selected)

    objective = counts("objective")
    diagnostic = counts("diagnostic")
    neutral = counts("neutral")
    return LongitudinalTaskScore(
        task_id=task.task_id,
        scenario_results=tuple(results),
        objective_passed=objective[0],
        objective_total=objective[1],
        diagnostic_passed=diagnostic[0],
        diagnostic_total=diagnostic[1],
        neutral_passed=neutral[0],
        neutral_total=neutral[1],
    )


def _failed_score(task: LongitudinalDevelopmentTask, observed: str) -> LongitudinalTaskScore:
    results = tuple(
        LongitudinalScenarioResult(
            scenario_id=scenario.scenario_id,
            metric=scenario.metric,
            passed=False,
            observed=observed,
            expected=(
                scenario.expected_action
                if task.task_kind == "action"
                else repr(scenario.expected_plan)
            ),
        )
        for scenario in task.scenarios
    )

    def total(metric: str) -> int:
        return sum(item.metric == metric for item in results)

    return LongitudinalTaskScore(
        task_id=task.task_id,
        scenario_results=results,
        objective_passed=0,
        objective_total=total("objective"),
        diagnostic_passed=0,
        diagnostic_total=total("diagnostic"),
        neutral_passed=0,
        neutral_total=total("neutral"),
    )
