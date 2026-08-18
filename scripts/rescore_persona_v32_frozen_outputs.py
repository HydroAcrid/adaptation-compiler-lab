"""Rescore exact frozen v3.2 diffs with the amended capability-free observer."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.persona_v32_adjudication import (
    PersonaV32FinalReportV11,
    PersonaV32FrozenRescoreReport,
    PersonaV32FrozenRescoreTrial,
    PersonaV32ScoringAmendment,
    strict_v32_scorer_failures,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_DIFF_PATH = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)


def _group_counts(score: dict[str, object], group: str) -> tuple[int, int]:
    groups = score.get("checks")
    if not isinstance(groups, dict):
        return (0, 1)
    values = groups.get(group)
    if not isinstance(values, dict) or not values:
        return (0, 1)
    checks = tuple(item for item in values.values() if isinstance(item, bool))
    if len(checks) != len(values):
        return (0, max(1, len(values)))
    return (sum(checks), len(checks))


def _write_new(path: Path, value: Mapping[str, object]) -> None:
    payload = (canonical_json(value) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _score_frozen_output(
    *,
    repo: Path,
    task_id: str,
    output: dict[str, object],
) -> dict[str, object]:
    diff = cast(str, output["diff"])
    allowed = set(cast(list[str], output["allowed_change_paths"]))
    paths = {path for pair in _DIFF_PATH.findall(diff) for path in pair}
    if paths != allowed:
        raise RuntimeError("frozen diff paths do not match their exact allowlist")
    task_root = repo / "development_benchmark_persona_v32/tasks" / task_id
    with tempfile.TemporaryDirectory(prefix="temper-v32-frozen-rescore-") as temporary:
        workspace = Path(temporary) / "workspace"
        shutil.copytree(task_root / "fixture", workspace)
        patch_path = Path(temporary) / "frozen.patch"
        patch_path.write_text(diff, encoding="utf-8")
        applied = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if applied.returncode != 0:
            raise RuntimeError(f"frozen diff failed validation: {applied.stderr}")
        subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        environment = dict(os.environ)
        environment.pop("CODEX_API_KEY", None)
        environment.pop("OPENAI_API_KEY", None)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(repo / "scripts/score_compact_projection_task_v12.py"),
                "--task-manifest",
                str(task_root / "task.json"),
                "--workspace",
                str(workspace),
            ],
            cwd=repo,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"amended scorer failed: {completed.stderr}")
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise RuntimeError("amended scorer returned a non-object")
        return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / "development_benchmark_persona_v32"
    amendment_path = root / "SCORING-AMENDMENT-v1.4.json"
    amendment = PersonaV32ScoringAmendment.model_validate_json(amendment_path.read_bytes())
    if amendment.frozen_rescorer_digest != sha256_file(Path(__file__)):
        raise RuntimeError("v3.2 frozen rescorer drifted after amendment")
    original_path = root / "FINAL-REPORT-v1.json"
    original = PersonaV32FinalReportV11.model_validate_json(original_path.read_bytes())
    if amendment.invalidated_final_report_digest != canonical_digest(original):
        raise RuntimeError("v3.2 invalidated final report drifted")
    blind_path = root / "target-results-v1/BLIND-REPORT-v1.json"
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    by_output = {item["observation"]["blind_output_id"]: item for item in blind["trials"]}
    trials = []
    all_receipts = True
    output_root = root / "target-results-v1/anonymous-outputs"
    for output_id in sorted(by_output):
        receipt = by_output[output_id]
        output_path = output_root / f"{output_id}.json"
        output = json.loads(output_path.read_text(encoding="utf-8"))
        diff = cast(str, output["diff"])
        raw_diff_digest = sha256_bytes(diff.encode())
        if raw_diff_digest != receipt["observation"]["diff_digest"]:
            raise RuntimeError("v3.2 frozen anonymous diff drifted")
        score = _score_frozen_output(
            repo=repo,
            task_id=cast(str, output["task_id"]),
            output=output,
        )
        failures = strict_v32_scorer_failures(score)
        receipts = score.get("receipts")
        receipt_success = isinstance(receipts, dict) and all(
            isinstance(item, dict) and item.get("status") == "succeeded"
            for item in receipts.values()
        )
        all_receipts = all_receipts and receipt_success
        objective = _group_counts(score, "objective")
        diagnostic = _group_counts(score, "diagnostic")
        neutral = _group_counts(score, "neutral")
        trials.append(
            PersonaV32FrozenRescoreTrial(
                blind_output_id=output_id,
                task_id=cast(str, output["task_id"]),
                original_diff_digest=raw_diff_digest,
                original_scorer_output_digest=receipt["observation"]["scorer_output_digest"],
                corrected_scorer_output_digest=canonical_digest(score),
                objective_checks_passed=objective[0],
                objective_checks_total=objective[1],
                diagnostic_checks_passed=diagnostic[0],
                diagnostic_checks_total=diagnostic[1],
                neutral_checks_passed=neutral[0],
                neutral_checks_total=neutral[1],
                behavior_failures=failures,
                behavior_conformant=not failures,
            )
        )
    report = PersonaV32FrozenRescoreReport(
        scoring_amendment_digest=canonical_digest(amendment),
        invalidated_final_report_digest=canonical_digest(original),
        target_blind_report_digest=sha256_file(blind_path),
        corrected_observer_digest=sha256_file(
            repo / "scripts/observe_compact_projection_policy_v12.py"
        ),
        corrected_scorer_digest=sha256_file(repo / "scripts/score_compact_projection_task_v12.py"),
        trials=tuple(trials),
        all_observer_receipts_succeeded=all_receipts,
        all_check_totals_passed=all(item.behavior_conformant for item in trials),
    )
    _write_new(
        root / "FROZEN-RESCORE-v1.4.json",
        report.model_dump(mode="json", round_trip=True),
    )
    print(canonical_json(report.model_dump(mode="json", round_trip=True)))


if __name__ == "__main__":
    main()
