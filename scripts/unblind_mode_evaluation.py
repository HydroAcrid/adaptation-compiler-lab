"""Unblind the frozen Mode comparison after all blind judges are recorded."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.connectors.models import JsonObject
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationFixtureV1,
    ModeEvaluationModeOutcomeV1,
    ModeEvaluationPublicPlanV1,
    ModeEvaluationResultV1,
    ModeEvaluationTaskOutcomeV1,
    ModeJudgeDecisionV1,
    build_mode_evaluation_plan,
    load_mode_evaluation_contract,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

Condition = Literal["core-only", "core-plus-mode"]


def _write_new(path: Path, value: object, *, mode: int = 0o644) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("Mode result must be a JSON object")
    payload = (canonical_json(value) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _load_object(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"invalid Mode evaluation file: {path.name}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"Mode evaluation file is not an object: {path.name}")
    return cast(JsonObject, value)


def _automated_winner(core: JsonObject, mode: JsonObject) -> Condition | Literal["tie"]:
    core_passed = cast(int, core["checks_passed"])
    mode_passed = cast(int, mode["checks_passed"])
    if mode_passed > core_passed:
        return "core-plus-mode"
    if core_passed > mode_passed:
        return "core-only"
    return "tie"


def _judge_winner(
    *,
    decision: ModeJudgeDecisionV1,
    task_id: str,
    output_conditions: dict[str, Condition],
) -> Condition | Literal["tie"]:
    rating = next((item for item in decision.pair_ratings if item.task_id == task_id), None)
    if rating is None:
        raise RuntimeError("Mode judge omitted a task")
    if rating.preferred_output_id is None:
        return "tie"
    try:
        return output_conditions[rating.preferred_output_id]
    except KeyError as error:
        raise RuntimeError("Mode judge selected an unknown output") from error


def build_mode_outcome(
    *,
    mode_id: str,
    fixtures: tuple[ModeEvaluationFixtureV1, ...],
    trials_by_task: dict[str, dict[Condition, JsonObject]],
    decision: ModeJudgeDecisionV1,
    output_conditions: dict[str, Condition],
) -> ModeEvaluationModeOutcomeV1:
    """Apply the frozen per-Mode gate without reading hidden condition material."""

    tasks: list[ModeEvaluationTaskOutcomeV1] = []
    relevant_trials: list[JsonObject] = []
    for fixture in sorted(fixtures, key=lambda item: item.task_id):
        task_id = fixture.task_id
        kind = fixture.kind
        pair = trials_by_task.get(task_id, {})
        if set(pair) != {"core-only", "core-plus-mode"}:
            raise RuntimeError("Mode result does not contain both conditions for a task")
        core = pair["core-only"]
        mode = pair["core-plus-mode"]
        relevant_trials.extend((core, mode))
        tasks.append(
            ModeEvaluationTaskOutcomeV1(
                task_id=task_id,
                mode_id=mode_id,
                kind=kind,
                core_output_id=cast(str, core["blind_output_id"]),
                mode_output_id=cast(str, mode["blind_output_id"]),
                core_checks_passed=cast(int, core["checks_passed"]),
                core_checks_total=cast(int, core["checks_total"]),
                mode_checks_passed=cast(int, mode["checks_passed"]),
                mode_checks_total=cast(int, mode["checks_total"]),
                automated_winner=_automated_winner(core, mode),
                judge_winner=_judge_winner(
                    decision=decision,
                    task_id=task_id,
                    output_conditions=output_conditions,
                ),
                core_behavior_conformant=cast(bool, core["behavior_conformant"]),
                mode_behavior_conformant=cast(bool, mode["behavior_conformant"]),
            )
        )
    instrument_valid = len(relevant_trials) == 10 and all(
        item.get("integrity_valid") is True for item in relevant_trials
    )
    diagnostics = tuple(item for item in tasks if item.kind == "diagnostic")
    neutral = tuple(item for item in tasks if item.kind == "neutral_control")
    diagnostic_core = sum(item.core_checks_passed for item in diagnostics)
    diagnostic_mode = sum(item.mode_checks_passed for item in diagnostics)
    neutral_core = sum(item.core_checks_passed for item in neutral)
    neutral_mode = sum(item.mode_checks_passed for item in neutral)
    winners = Counter(item.judge_winner for item in tasks)
    projection_sizes = {
        cast(int, item["mode_projection_utf8_bytes"])
        for item in relevant_trials
        if output_conditions[cast(str, item["blind_output_id"])] == "core-plus-mode"
    }
    projection_bytes = max(projection_sizes, default=0)
    protocol_failures = tuple(
        reason
        for item in relevant_trials
        if output_conditions[cast(str, item["blind_output_id"])] == "core-plus-mode"
        for reason in cast(list[str], item.get("behavior_failures", []))
        if any(
            marker in reason.casefold()
            for marker in ("forbidden", "scope", "leak", "outside", "unexpected path")
        )
    )
    failures: list[str] = []
    if not instrument_valid:
        failures.append("one or more target records failed instrument integrity")
    if diagnostic_mode < diagnostic_core:
        failures.append("Mode regressed aggregate diagnostic correctness")
    if neutral_mode < neutral_core:
        failures.append("Mode regressed a neutral-control aggregate")
    if not (diagnostic_mode > diagnostic_core or winners["core-plus-mode"] > winners["core-only"]):
        failures.append("Mode did not improve a diagnostic or blinded-quality measure")
    if protocol_failures:
        failures.append("Mode condition recorded a forbidden operation or scope-leakage signal")
    if len(projection_sizes) != 1 or projection_bytes <= 0:
        failures.append("Mode projection size was not stable and positive")
    if projection_bytes > 12000 or (projection_bytes + 3) // 4 > 3000:
        failures.append("Mode projection exceeded the frozen size ceiling")
    if not all(item.get("activation_exact") is True for item in relevant_trials):
        failures.append("a target did not receive its exact assigned activation")
    if not all(item.get("deactivation_exact") is True for item in relevant_trials):
        failures.append("a target workspace or Mode activation was not fully removed")
    gate_passed = instrument_valid and not failures
    permitted_claim: Literal[
        "bounded_same_agent_mode_evidence",
        "mode_gate_failed",
        "instrumentation_failure",
    ] = (
        "instrumentation_failure"
        if not instrument_valid
        else ("bounded_same_agent_mode_evidence" if gate_passed else "mode_gate_failed")
    )
    return ModeEvaluationModeOutcomeV1(
        mode_id=mode_id,
        tasks=tuple(tasks),
        instrument_valid=instrument_valid,
        gate_passed=gate_passed,
        diagnostic_core_passed=diagnostic_core,
        diagnostic_mode_passed=diagnostic_mode,
        neutral_core_passed=neutral_core,
        neutral_mode_passed=neutral_mode,
        judge_core_wins=winners["core-only"],
        judge_mode_wins=winners["core-plus-mode"],
        judge_ties=winners["tie"],
        projection_utf8_bytes=projection_bytes,
        failure_reasons=tuple(sorted(set(failures))),
        permitted_claim=permitted_claim,
    )


def _markdown(result: ModeEvaluationResultV1) -> str:
    lines = [
        "# Temper Capability Mode Evaluation",
        "",
        "This is a bounded same-agent development comparison, not a general product or "
        "cross-model claim.",
        "",
        "| Mode | Gate | Diagnostics (Core → Mode) | Neutral (Core → Mode) | Blind quality "
        "(Core / Mode / Tie) | Projection bytes |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for outcome in result.mode_outcomes:
        lines.append(
            f"| {outcome.mode_id} | {'PASS' if outcome.gate_passed else 'FAIL'} | "
            f"{outcome.diagnostic_core_passed} → {outcome.diagnostic_mode_passed} | "
            f"{outcome.neutral_core_passed} → {outcome.neutral_mode_passed} | "
            f"{outcome.judge_core_wins} / {outcome.judge_mode_wins} / "
            f"{outcome.judge_ties} | {outcome.projection_utf8_bytes} |"
        )
    lines.extend(["", "## Task-level matrix", ""])
    lines.extend(
        [
            "| Mode | Task | Kind | Automated | Blind quality | Core | Mode |",
            "| --- | --- | --- | --- | --- | ---: | ---: |",
        ]
    )
    for outcome in result.mode_outcomes:
        for task in outcome.tasks:
            lines.append(
                f"| {outcome.mode_id} | {task.task_id} | {task.kind} | "
                f"{task.automated_winner} | {task.judge_winner} | "
                f"{task.core_checks_passed}/{task.core_checks_total} | "
                f"{task.mode_checks_passed}/{task.mode_checks_total} |"
            )
    lines.extend(
        [
            "",
            "All target and judge sessions used saved ChatGPT authentication. Provider-billed "
            "calls: 0. The deferred external-validation study remained sealed and unaccessed.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_mode_evaluation"
    results = benchmark / "results-v1"
    result_path = results / "unblinded-result.json"
    markdown_path = results / "MODE_EVALUATION_RESULT.md"
    if result_path.exists() or markdown_path.exists():
        raise RuntimeError("Mode evaluation has already been unblinded")
    contract = load_mode_evaluation_contract(benchmark / "EXECUTION_CONTRACT-v1.json")
    if contract.unblind_source_digest != sha256_file(repo / "scripts/unblind_mode_evaluation.py"):
        raise RuntimeError("Mode evaluation unblinder drifted")
    seed_path = arguments.seed_file.expanduser().resolve()
    if seed_path.is_relative_to(repo) or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("Mode evaluation seed boundary is invalid")
    public, private = build_mode_evaluation_plan(contract, seed=seed_path.read_bytes())
    frozen_public = ModeEvaluationPublicPlanV1.model_validate_json(
        (benchmark / "PUBLIC_PLAN-v1.json").read_text(encoding="utf-8"), strict=True
    )
    if public != frozen_public:
        raise RuntimeError("Mode evaluation seed does not reproduce the public plan")
    report = _load_object(results / "blind-trial-report.json")
    completion = _load_object(results / "completion.json")
    raw_trials = report.get("trials")
    if (
        report.get("contract_digest") != contract.content_digest
        or report.get("public_plan_digest") != public.content_digest
        or report.get("unblinded") is not False
        or not isinstance(raw_trials, list)
        or len(raw_trials) != 30
        or completion.get("report_digest") != canonical_digest(report)
    ):
        raise RuntimeError("Mode evaluation blind report is incomplete or drifted")
    public_cells = {item.run_id: item for item in public.run_order}
    if {cast(str, item.get("run_id")) for item in raw_trials if isinstance(item, dict)} != set(
        public_cells
    ):
        raise RuntimeError("Mode evaluation trial coverage does not match its public plan")
    assignments = cast(list[dict[str, object]], private["condition_assignments"])
    condition_by_blind = {
        str(item["blind_condition_id"]): cast(Condition, item["condition"]) for item in assignments
    }
    trials_by_task: dict[str, dict[Condition, JsonObject]] = defaultdict(dict)
    output_conditions: dict[str, Condition] = {}
    for raw in raw_trials:
        if not isinstance(raw, dict):
            raise RuntimeError("Mode evaluation trial is not an object")
        trial = raw
        run_id = cast(str, trial["run_id"])
        cell = public_cells[run_id]
        if (
            trial.get("task_id") != cell.task_id
            or trial.get("blind_condition_id") != cell.blind_condition_id
            or trial.get("blind_output_id") != cell.blind_output_id
        ):
            raise RuntimeError("Mode evaluation trial changed its public binding")
        condition = condition_by_blind[cell.blind_condition_id]
        if condition in trials_by_task[cell.task_id]:
            raise RuntimeError("Mode evaluation repeated a task-condition cell")
        trials_by_task[cell.task_id][condition] = trial
        output_conditions[cell.blind_output_id] = condition
    judge_completion = _load_object(results / "judges/completion.json")
    receipt_digests = judge_completion.get("judge_receipt_digests")
    if not isinstance(receipt_digests, dict) or judge_completion.get("session_count") != 3:
        raise RuntimeError("Mode judge completion receipt is invalid")
    decisions: dict[str, ModeJudgeDecisionV1] = {}
    for mode_id in sorted({item.mode_id for item in contract.fixtures}):
        receipt = _load_object(results / "judges" / f"{mode_id}.json")
        if (
            receipt_digests.get(mode_id) != canonical_digest(receipt)
            or receipt.get("blind_report_digest") != canonical_digest(report)
            or receipt.get("condition_mapping_access") is not False
            or receipt.get("provider_billed_calls") != 0
            or receipt.get("model") != contract.judge_model
            or receipt.get("reasoning_effort") != contract.judge_reasoning_effort
        ):
            raise RuntimeError("Mode judge receipt is invalid or unblinded")
        decision = ModeJudgeDecisionV1.model_validate(receipt.get("decision"), strict=True)
        if decision.mode_id != mode_id or receipt.get("decision_digest") != decision.content_digest:
            raise RuntimeError("Mode judge decision binding drifted")
        decisions[mode_id] = decision
    outcomes = tuple(
        build_mode_outcome(
            mode_id=mode_id,
            fixtures=tuple(item for item in contract.fixtures if item.mode_id == mode_id),
            trials_by_task=trials_by_task,
            decision=decisions[mode_id],
            output_conditions=output_conditions,
        )
        for mode_id in sorted(decisions)
    )
    result = ModeEvaluationResultV1(
        contract_digest=contract.content_digest,
        public_plan_digest=public.content_digest,
        source_commit=cast(str, report["source_commit"]),
        mode_outcomes=outcomes,
        all_instrument_valid=all(item.instrument_valid for item in outcomes),
        passed_mode_count=sum(item.gate_passed for item in outcomes),
    )
    _write_new(result_path, result)
    descriptor = os.open(markdown_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(_markdown(result))


if __name__ == "__main__":
    main()
