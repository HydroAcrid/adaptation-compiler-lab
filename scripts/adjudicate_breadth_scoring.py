"""Replay immutable Milestone 6A.4 diffs through the direct scorer contract."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Literal, cast

from adaptation_compiler_lab.benchmark.breadth_adjudication import (
    BreadthScoringAdjudicationResult,
    BreadthScoringCorrection,
    direct_check_counts,
    load_breadth_adjudication_design,
    validate_direct_score,
)
from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthReplicationPublicPlan,
    BreadthReplicationResult,
    BreadthTaskPairOutcome,
    build_breadth_plan,
    load_breadth_contract,
    load_breadth_design,
)
from adaptation_compiler_lab.benchmark.models import BenchmarkCondition
from adaptation_compiler_lab.benchmark.role_packets import ApprovedSourceFamily
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_FORBIDDEN_ENV = frozenset({"CODEX_API_KEY", "OPENAI_API_KEY"})
_LEGACY_FAILURE = "independent scorer returned no receipts"


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", round_trip=True)
    if not isinstance(value, dict):
        raise TypeError("breadth adjudication artifact must be a JSON object")
    return (canonical_json(value) + "\n").encode("utf-8")


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def _git(arguments: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run(["git", *arguments], cwd=cwd, timeout=30)


def _initialize_workspace(fixture: Path, workspace: Path) -> None:
    shutil.copytree(
        fixture,
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    commands = (
        ["init", "-q"],
        ["config", "user.email", "benchmark@example.invalid"],
        ["config", "user.name", "Benchmark"],
        ["add", "-A"],
        ["commit", "-qm", "fixture"],
    )
    for command in commands:
        completed = _git(command, cwd=workspace)
        if completed.returncode != 0:
            raise RuntimeError(f"unable to initialize replay workspace: {completed.stderr}")


def _score(
    *,
    bubblewrap: Path,
    scorer: Path,
    task_id: str,
    workspace: Path,
) -> dict[str, dict[str, bool]]:
    command = [
        str(bubblewrap),
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--symlink",
        "usr/sbin",
        "/sbin",
        "--ro-bind",
        "/etc",
        "/etc",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/opt/acl",
        "--ro-bind",
        str(scorer),
        "/opt/acl/scorer.py",
        "--ro-bind",
        str(workspace),
        "/workspace",
        "--chdir",
        "/workspace",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--",
        "/usr/bin/python3",
        "/opt/acl/scorer.py",
        "--task-id",
        task_id,
        "--workspace",
        "/workspace",
    ]
    completed = _run(command, cwd=workspace, timeout=60)
    if completed.returncode != 0:
        raise RuntimeError(f"adjudication scorer failed: {completed.stderr}")
    try:
        value = json.loads(completed.stdout)
    except ValueError as error:
        raise RuntimeError("adjudication scorer returned malformed JSON") from error
    return validate_direct_score(value)


def _correction(
    *,
    root: Path,
    bubblewrap: Path,
    scorer: Path,
    task_id: str,
    output_id: str,
    original_trial: object,
    expected_input: object,
) -> BreadthScoringCorrection:
    from adaptation_compiler_lab.benchmark.breadth_adjudication import (
        BreadthAdjudicationInput,
    )
    from adaptation_compiler_lab.benchmark.task_channel_comparison import (
        FairComparisonTrialReceipt,
    )

    trial = cast(FairComparisonTrialReceipt, original_trial)
    bound = cast(BreadthAdjudicationInput, expected_input)
    if not trial.integrity_valid or trial.behavior_failures != (_LEGACY_FAILURE,):
        raise RuntimeError("adjudication accepts only the registered common adapter failure")
    if canonical_digest(trial) != bound.original_trial_digest:
        raise RuntimeError("original trial receipt drifted before adjudication")
    output_path = root / f"results-v1/anonymous-outputs/{output_id}.json"
    if sha256_file(output_path) != bound.public_output_digest:
        raise RuntimeError("anonymous output drifted before adjudication")
    public = json.loads(output_path.read_text(encoding="utf-8"))
    if (
        not isinstance(public, dict)
        or public.get("blind_output_id") != output_id
        or public.get("task_id") != task_id
        or not isinstance(public.get("diff"), str)
        or not isinstance(public.get("final_response"), str)
        or public.get("visible_test_executed") is not True
    ):
        raise RuntimeError("anonymous output is malformed")
    diff = str(public["diff"])
    final_response = str(public["final_response"])
    if sha256_bytes(diff.encode("utf-8")) != bound.diff_digest:
        raise RuntimeError("anonymous diff does not match its frozen observation")
    if sha256_bytes(final_response.encode("utf-8")) != bound.final_response_digest:
        raise RuntimeError("anonymous response does not match its frozen observation")
    fixture = root / f"tasks/{task_id}/fixture"
    with tempfile.TemporaryDirectory(prefix="acl-breadth-adjudication-") as temporary:
        workspace = Path(temporary) / "task"
        _initialize_workspace(fixture, workspace)
        applied = _run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=workspace,
            timeout=30,
            input_text=diff,
        )
        if applied.returncode != 0:
            raise RuntimeError(f"unable to replay anonymous diff: {applied.stderr}")
        score = _score(
            bubblewrap=bubblewrap,
            scorer=scorer,
            task_id=task_id,
            workspace=workspace,
        )
    failures = tuple(
        sorted(
            f"{group}.{name}"
            for group in ("diagnostic", "neutral", "objective")
            for name, passed in score[group].items()
            if not passed
        )
    )
    objective = score["objective"]
    diagnostic = score["diagnostic"]
    neutral = score["neutral"]
    objective_counts = direct_check_counts(objective)
    diagnostic_counts = direct_check_counts(diagnostic)
    neutral_counts = direct_check_counts(neutral)
    return BreadthScoringCorrection(
        task_id=task_id,
        blind_output_id=output_id,
        original_trial_digest=bound.original_trial_digest,
        public_output_digest=bound.public_output_digest,
        scorer_output_digest=canonical_digest(score),
        objective=objective,
        diagnostic=diagnostic,
        neutral=neutral,
        objective_passed=objective_counts[0],
        objective_total=objective_counts[1],
        diagnostic_passed=diagnostic_counts[0],
        diagnostic_total=diagnostic_counts[1],
        neutral_passed=neutral_counts[0],
        neutral_total=neutral_counts[1],
        behavior_conformant=not failures,
        behavior_failures=failures,
    )


def _winner(
    compiled: BreadthScoringCorrection,
    profile: BreadthScoringCorrection,
) -> Literal["compiled_adaptation", "strong_static_profile", "tie"]:
    if compiled.behavior_conformant != profile.behavior_conformant:
        return "compiled_adaptation" if compiled.behavior_conformant else "strong_static_profile"
    if compiled.total_passed > profile.total_passed:
        return "compiled_adaptation"
    if profile.total_passed > compiled.total_passed:
        return "strong_static_profile"
    return "tie"


def _family_totals(
    corrections: list[BreadthScoringCorrection],
    families: dict[str, ApprovedSourceFamily],
) -> dict[ApprovedSourceFamily, dict[str, int]]:
    totals: dict[ApprovedSourceFamily, dict[str, int]] = defaultdict(
        lambda: {
            "objective_passed": 0,
            "objective_total": 0,
            "diagnostic_passed": 0,
            "diagnostic_total": 0,
            "neutral_passed": 0,
            "neutral_total": 0,
            "behavior_conformant": 0,
            "records": 0,
        }
    )
    for correction in corrections:
        target = totals[families[correction.task_id]]
        for group in ("objective", "diagnostic", "neutral"):
            target[f"{group}_passed"] += getattr(correction, f"{group}_passed")
            target[f"{group}_total"] += getattr(correction, f"{group}_total")
        target["behavior_conformant"] += int(correction.behavior_conformant)
        target["records"] += 1
    return dict(totals)


def _markdown(
    *,
    result: BreadthScoringAdjudicationResult,
    family_summary: dict[str, dict[ApprovedSourceFamily, dict[str, int]]],
    compiled_bytes: tuple[int, int, int],
    profile_bytes: tuple[int, int, int],
) -> str:
    lines = [
        "# Milestone 6A.4 Scoring Adjudication",
        "",
        "The immutable v1 report remains a failed scoring-instrument result. This v1.1 "
        "adjudication replays its digest-bound target diffs through the frozen direct scorer.",
        "",
        f"Corrected primary gate: **{'PASS' if result.primary_gate_passed else 'FAIL'}**.",
        "",
        f"Permitted claim: `{result.permitted_claim}`.",
        "",
        "## Corrected task matrix",
        "",
        "| Task | Family | Stage | Winner | Compiled checks | Profile checks |",
        "| --- | --- | ---: | --- | ---: | ---: |",
    ]
    for pair in result.task_pairs:
        lines.append(
            f"| {pair.task_id} | {pair.family.value} | {pair.stage} | "
            f"{pair.automated_winner} | {pair.compiled_total_passed} | "
            f"{pair.profile_total_passed} |"
        )
    lines.extend(
        [
            "",
            "## Corrected family aggregates",
            "",
            "| Condition | Family | Objective | Diagnostic | Neutral | Conformant |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for condition in ("compiled_adaptation", "strong_static_profile"):
        for family in ApprovedSourceFamily:
            value = family_summary[condition][family]
            lines.append(
                f"| {condition} | {family.value} | "
                f"{value['objective_passed']}/{value['objective_total']} | "
                f"{value['diagnostic_passed']}/{value['diagnostic_total']} | "
                f"{value['neutral_passed']}/{value['neutral_total']} | "
                f"{value['behavior_conformant']}/{value['records']} |"
            )
    lines.extend(
        [
            "",
            "## Material size",
            "",
            "| Stage | Compiled bytes | Strong-profile bytes |",
            "| ---: | ---: | ---: |",
            *[
                f"| {stage} | {compiled_bytes[stage - 1]} | {profile_bytes[stage - 1]} |"
                for stage in range(1, 4)
            ],
            "",
            "## Secondary blind judge",
            "",
            f"- Compiled wins: {result.judge_compiled_wins}",
            f"- Strong-profile wins: {result.judge_profile_wins}",
            f"- Ties: {result.judge_ties}",
            "",
            "No target or judge session was rerun. No condition material, target output, or "
            "original receipt was modified. Provider-billed calls and external-validation "
            "access remained zero.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--seed-file", type=Path, required=True)
    parser.add_argument("--bubblewrap", type=Path, required=True)
    arguments = parser.parse_args()
    if any(os.environ.get(name) for name in _FORBIDDEN_ENV):
        raise RuntimeError("API keys are forbidden for breadth scoring adjudication")
    repo = arguments.repo.resolve()
    root = repo / "development_benchmark_breadth_replication"
    design = load_breadth_design(root)
    load_breadth_contract(root, design=design)
    adjudication = load_breadth_adjudication_design(root)
    original_path = root / "results-v1/unblinded-result.json"
    original = BreadthReplicationResult.model_validate_json(original_path.read_bytes())
    if sha256_file(original_path) != adjudication.original_result_file_digest:
        raise RuntimeError("original breadth result drifted before adjudication")
    if not original.instrument_valid or original.permitted_claim != "breadth_gate_failed":
        raise RuntimeError("original breadth result is outside the adjudication scope")
    if _git(["status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("breadth scoring adjudication requires a clean repository")
    seed_path = arguments.seed_file.expanduser().resolve()
    if repo == seed_path or repo in seed_path.parents or seed_path.stat().st_mode & 0o077:
        raise RuntimeError("breadth adjudication seed boundary is invalid")
    public, private = build_breadth_plan(
        design_digest=design.content_digest,
        tasks=design.tasks,
        seed=seed_path.read_bytes(),
    )
    frozen_public = BreadthReplicationPublicPlan.model_validate_json(
        (root / "PUBLIC_PLAN-v1.json").read_bytes()
    )
    if public != frozen_public:
        raise RuntimeError("breadth adjudication seed does not reproduce the frozen plan")
    assignments = cast(list[dict[str, object]], private["condition_assignments"])
    condition_by_blind = {
        str(item["blind_condition_id"]): BenchmarkCondition(str(item["condition"]))
        for item in assignments
    }
    input_by_output = {item.blind_output_id: item for item in adjudication.inputs}
    bubblewrap = arguments.bubblewrap.expanduser().resolve()
    scorer = repo / "scripts/score_breadth_replication_task.py"
    corrections = tuple(
        _correction(
            root=root,
            bubblewrap=bubblewrap,
            scorer=scorer,
            task_id=trial.observation.task_id,
            output_id=trial.observation.blind_output_id,
            original_trial=trial,
            expected_input=input_by_output[trial.observation.blind_output_id],
        )
        for trial in original.trials
    )
    trial_by_output = {item.observation.blind_output_id: item for item in original.trials}
    by_task: dict[str, dict[BenchmarkCondition, BreadthScoringCorrection]] = defaultdict(dict)
    for correction in corrections:
        trial = trial_by_output[correction.blind_output_id]
        condition = condition_by_blind[trial.observation.blind_condition_id]
        by_task[correction.task_id][condition] = correction
    metadata = {item.task_id: item for item in design.tasks}
    pairs: list[BreadthTaskPairOutcome] = []
    for wrapped in design.tasks:
        cells = by_task[wrapped.task_id]
        compiled = cells[BenchmarkCondition.COMPILED_ADAPTATION]
        profile = cells[BenchmarkCondition.STRONG_STATIC_PROFILE]
        pairs.append(
            BreadthTaskPairOutcome(
                task_id=wrapped.task_id,
                family=wrapped.task.family,
                stage=wrapped.stage,
                compiled_output_id=compiled.blind_output_id,
                profile_output_id=profile.blind_output_id,
                automated_winner=_winner(compiled, profile),
                compiled_total_passed=compiled.total_passed,
                profile_total_passed=profile.total_passed,
                compiled_behavior_conformant=compiled.behavior_conformant,
                profile_behavior_conformant=profile.behavior_conformant,
            )
        )
    compiled_corrections = [
        item
        for item in corrections
        if condition_by_blind[trial_by_output[item.blind_output_id].observation.blind_condition_id]
        is BenchmarkCondition.COMPILED_ADAPTATION
    ]
    profile_corrections = [
        item
        for item in corrections
        if condition_by_blind[trial_by_output[item.blind_output_id].observation.blind_condition_id]
        is BenchmarkCondition.STRONG_STATIC_PROFILE
    ]
    families = {task_id: wrapped.task.family for task_id, wrapped in metadata.items()}
    compiled_families = _family_totals(compiled_corrections, families)
    profile_families = _family_totals(profile_corrections, families)
    family_gates = 0
    for family in ApprovedSourceFamily:
        compiled_value = compiled_families[family]
        profile_value = profile_families[family]
        metrics_hold = all(
            compiled_value[metric] >= profile_value[metric]
            for metric in (
                "objective_passed",
                "diagnostic_passed",
                "neutral_passed",
                "behavior_conformant",
            )
        )
        compiled_perfect = (
            all(
                compiled_value[f"{group}_passed"] == compiled_value[f"{group}_total"]
                for group in ("objective", "diagnostic", "neutral")
            )
            and compiled_value["behavior_conformant"] == compiled_value["records"]
        )
        family_gates += int(metrics_hold and compiled_perfect)
    size_gate = all(
        compiled < profile
        for compiled, profile in zip(
            design.compiled_material_bytes,
            design.profile_material_bytes,
            strict=True,
        )
    )
    primary_gate = family_gates == 4 and size_gate
    compiled_total = sum(item.total_passed for item in compiled_corrections)
    profile_total = sum(item.total_passed for item in profile_corrections)
    claim: Literal[
        "compiled_outperformed_on_multifamily_suite_without_family_regression",
        "compiled_matched_profile_across_all_approved_families",
        "breadth_gate_failed_after_adjudication",
        "scoring_adjudication_instrument_failure",
    ]
    if not primary_gate:
        claim = "breadth_gate_failed_after_adjudication"
    elif compiled_total > profile_total:
        claim = "compiled_outperformed_on_multifamily_suite_without_family_regression"
    else:
        claim = "compiled_matched_profile_across_all_approved_families"
    result = BreadthScoringAdjudicationResult(
        design_digest=adjudication.content_digest,
        original_result_file_digest=adjudication.original_result_file_digest,
        source_commit=_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip(),
        corrections=corrections,
        task_pairs=tuple(pairs),
        replay_instrument_valid=True,
        primary_gate_passed=primary_gate,
        family_gates_passed=family_gates,
        judge_compiled_wins=original.judge_compiled_wins,
        judge_profile_wins=original.judge_profile_wins,
        judge_ties=original.judge_ties,
        permitted_claim=claim,
    )
    results = root / "results-v1.1"
    results.mkdir(parents=True, exist_ok=False)
    result_path = results / "SCORING_ADJUDICATION-v1.json"
    _exclusive_write(result_path, _canonical_bytes(result))
    summary = {
        "compiled_adaptation": compiled_families,
        "strong_static_profile": profile_families,
    }
    _exclusive_write(
        results / "MILESTONE_6A4_ADJUDICATED_RESULT.md",
        _markdown(
            result=result,
            family_summary=summary,
            compiled_bytes=design.compiled_material_bytes,
            profile_bytes=design.profile_material_bytes,
        ).encode("utf-8"),
    )
    _exclusive_write(
        results / "completion.json",
        _canonical_bytes(
            {
                "adjudication_result_digest": sha256_file(result_path),
                "external_validation_accessed": False,
                "original_result_preserved": True,
                "provider_billed_calls": 0,
                "replay_instrument_valid": True,
                "target_sessions_added": 0,
            }
        ),
    )


if __name__ == "__main__":
    main()
