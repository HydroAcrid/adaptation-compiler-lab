"""Uniform, explicitly supplemental audit; never rewrites frozen trial receipts."""

from __future__ import annotations

import argparse
import json
import shlex
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config, _runtime_secrets
from adaptation_compiler_lab.benchmark.repo_extension_screen import (
    RepoShell,
    parse_grade,
    selected_text,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from scripts.run_repo_extension_screen import (
    BENCH,
    EXPECTED_CHECKS,
    extended,
    extract,
    new_json,
    put,
    remove_tree,
    runtime_for,
)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_one(
    receipt: dict[str, Any],
    *,
    run: Path,
    fixtures: Path,
    output: Path,
    raw: LocalRawPayloadStore,
    cases: dict[str, Any],
    sources: list[dict[str, Any]],
) -> None:
    start = time.monotonic()
    name = f"{receipt['task_id']}-{receipt['arm']}-{receipt['repeat']}"
    folder, case = output / name, cases[receipt["task_id"]]
    folder.mkdir()
    patch = json.loads(raw.read(RawPayloadRef(**receipt["patch_ref"])))
    candidate = folder / "candidate"
    extract(case, fixtures, candidate)
    put(candidate, patch)
    shell = RepoShell(candidate, runtime_for(case))
    build = shell.run(case["typecheck"], limit=100_000) if case.get("typecheck") else None
    test_paths = [p for p in patch if p.startswith("tests/") and p.endswith((".py", ".test.ts"))]
    sensitivity, before_result, after_result = "no_changed_tests", None, None
    if test_paths:
        before = folder / "original-with-candidate-tests"
        extract(case, fixtures, before)
        put(before, {p: text for p, text in patch.items() if p.startswith("tests/")})
        command = (
            "python -m pytest -q -p no:cacheprovider "
            if case["kind"] == "python"
            else "node node_modules/vitest/vitest.mjs run "
        )
        command += " ".join(shlex.quote(p) for p in test_paths)
        if case["kind"] == "node":
            command += " --maxWorkers=1 --no-file-parallelism --reporter=json"
        before_raw = RepoShell(before, runtime_for(case)).run(command, limit=2_000_000)
        after_raw = shell.run(command, limit=2_000_000)
        before_result = parse_grade(case["kind"], before_raw["output"], before_raw["returncode"])
        after_result = parse_grade(case["kind"], after_raw["output"], after_raw["returncode"])
        sensitivity = (
            "failing_before_passing_after"
            if before_result["failed"] > 0
            and before_result["errors"] == 0
            and after_result["complete"]
            else "intended_failure_not_established"
        )
    else:
        before_raw, after_raw = None, None
    model = json.loads(raw.read(RawPayloadRef(**receipt["raw_ref"])))["model"]
    observed = "\n".join(t.get("output", "") for t in model["tool_calls"])
    exposure: dict[str, bool] = {}
    if receipt["arm"] == "direct_skills":
        exposure = {s["id"]: s["text"].strip() in observed for s in sources}
    elif receipt["arm"] == "temper_selected":
        selector = read(run / "selectors" / (case["id"] + ".json"))
        material = selected_text(sources, selector["clause_ids"])
        exposure = {"selected_material": not material or material.strip() in observed}
    authoritative = receipt["authoritative"]
    runtime_passed = (
        authoritative["passed"] == EXPECTED_CHECKS[case["id"]]
        and authoritative["failed"] == 0
        and authoritative["errors"] == 0
    )
    build_passed = None if build is None else build["returncode"] == 0
    instrument = all(c["instrument_valid"] for c in shell.calls) and (
        before_raw is None or before_raw["instrument_valid"]
    )
    ref = raw.put(
        json.dumps(
            {
                "build": build,
                "candidate_tests_before": before_raw,
                "candidate_tests_after": after_raw,
            }
        ).encode(),
        media_type="application/json",
    )
    for path in (candidate, folder / "original-with-candidate-tests"):
        if path.exists():
            remove_tree(path, output)
    result = {
        "task_id": case["id"],
        "arm": receipt["arm"],
        "repeat": receipt["repeat"],
        "frozen_complete": receipt["complete"],
        "locked_runtime_checks_passed": runtime_passed,
        "actual_candidate_typecheck_passed": build_passed,
        "instrument_valid": instrument,
        "diagnostic_complete": bool(
            runtime_passed
            and (build is None or build["instrument_valid"])
            and build_passed is not False
            and receipt["model_status"] == "completed"
            and not receipt["scope_failures"]
            and not receipt["deleted_paths"]
        ),
        "candidate_tests": {
            "state": sensitivity,
            "test_paths": test_paths,
            "before": before_result,
            "after": after_result,
        },
        "full_guidance_observed_in_tool_output": exposure,
        "validation_error_tool_calls": sum(
            bool(t.get("validation_error")) for t in model["tool_calls"]
        ),
        "audit_seconds": time.monotonic() - start,
        "raw_ref": asdict(ref),
        "interpretation": "Diagnostic audit of the exact unchanged candidate; "
        "not a replacement frozen score or prospective promotion.",
    }
    new_json(folder / "audit.json", result)
    print(
        json.dumps(
            {
                "audited": name,
                "actual_build": build_passed,
                "runtime_checks": runtime_passed,
                "diagnostic_complete": result["diagnostic_complete"],
                "test_sensitivity": sensitivity,
            }
        ),
        flush=True,
    )


def main(config_path: Path, run: Path, fixtures: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    config = _load_config(config_path)
    raw = LocalRawPayloadStore(
        run / "encrypted-raw",
        encryption_key=_runtime_secrets(config).raw_encryption_key(
            workspace_root=config.repository_root
        ),
    )
    cases = {c["id"]: c for c in read(BENCH / "cases.json")}
    sources = read(BENCH / "sources.json")
    seen: set[str] = set()
    while len(seen) < 12:
        for path in sorted((run / "trials").glob("*/receipt.json")):
            if path.parent.name in seen:
                continue
            try:
                receipt = read(path)
            except json.JSONDecodeError:
                continue
            audit_one(
                receipt,
                run=run,
                fixtures=fixtures,
                output=output,
                raw=raw,
                cases=cases,
                sources=sources,
            )
            seen.add(path.parent.name)
        if len(seen) < 12:
            time.sleep(5)
    new_json(output / "complete.json", {"audited_trials": len(seen), "additional_model_turns": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "run", "fixtures", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    main(args.config, extended(args.run), extended(args.fixtures), extended(args.output))
