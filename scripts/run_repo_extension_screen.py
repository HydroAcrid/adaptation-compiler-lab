"""Run a frozen full-repository comparison using native skills and offline shell tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import statistics
import subprocess
import tarfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config, _runtime_secrets
from adaptation_compiler_lab.autonomy import codex_transport
from adaptation_compiler_lab.autonomy.codex_transport import (
    configured_analysis_session,
    read_capacity,
    verify_model,
)
from adaptation_compiler_lab.benchmark.extension_screen import clauses
from adaptation_compiler_lab.benchmark.repo_extension_screen import (
    ARMS,
    SELECTOR_SCHEMA,
    RepoShell,
    changed_paths,
    parse_grade,
    run_tool_turn,
    scope_failures,
    selected_text,
    summarize,
    tree,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "development_benchmark_extensions/real-repo-v1"
RUNTIME = {
    "python_runtime": "/home/kevin_dotel/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu",
    "python_runtime_alias": "/home/kevin_dotel/.local/share/uv/python/cpython-3.12-linux-x86_6"
    "4-gnu",
    "python_venv": "/home/kevin_dotel/projects/adaptation-compiler-lab/.venv",
    "node_runtime": "/home/kevin_dotel/.nvm/versions/node/v24.18.0",
}
MODULE = ROOT / "src/adaptation_compiler_lab/benchmark/repo_extension_screen.py"
ACTIVE_PROTOCOL = BENCH / "protocol-validated-v2.json"
ACTIVE_ADMISSION = BENCH / "instrument-admission-v2.json"
EXPECTED_CHECKS = {"temper-live-policy": 55, "kairn-runtime-cache": 98}


def extended(path: Path) -> Path:
    resolved = path.resolve()
    value = str(resolved)
    return resolved if value.startswith("\\\\?\\") else Path("\\\\?\\" + value)


def remove_tree(path: Path, run_root: Path) -> None:
    target, boundary = path.resolve(), run_root.resolve()
    if target == boundary or not target.is_relative_to(boundary):
        raise ValueError("cleanup target is outside the verified experiment directory")

    def writable_retry(function: Any, name: str, error: BaseException) -> None:
        if not Path(name).resolve().is_relative_to(boundary):
            raise ValueError("cleanup callback escaped experiment") from error
        os.chmod(name, stat.S_IWRITE)
        function(name)

    shutil.rmtree(target, onexc=writable_retry)


@contextmanager
def benchmark_session(config_path: Path) -> Iterator[Any]:
    # Scoped to this serial benchmark process. Product sensor restrictions and
    # installed config remain unchanged. Native dynamic tools require this host.
    original = codex_transport.analysis_profile
    codex_transport.analysis_profile = lambda: original().replace(
        "code_mode_host = false", "code_mode_host = true"
    )
    try:
        with configured_analysis_session(config_path) as session:
            yield session
    finally:
        codex_transport.analysis_profile = original


def new_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_for(case: dict[str, Any]) -> dict[str, str]:
    return {
        **RUNTIME,
        **(
            {"node_modules": "/home/kevin_dotel/projects/kairn/node_modules"}
            if case["kind"] == "node"
            else {}
        ),
    }


def extract(
    case: dict[str, Any], fixtures: Path, destination: Path, *, git_init: bool = True
) -> None:
    archive = fixtures / case["id"] / "base.tar"
    if file_hash(archive) != case["archive_sha256"]:
        raise ValueError("historical source archive changed")
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as tar:
        if any(m.issym() or m.islnk() for m in tar.getmembers()):
            raise ValueError("unsafe historical source archive")
        tar.extractall(destination, filter="data")
    if case["kind"] == "node":
        # A read-only workspace cannot create this dependency mountpoint later.
        (destination / "node_modules").mkdir(exist_ok=True)
    if git_init:

        def git(*args: str) -> None:
            subprocess.run(
                ["git", "-c", "core.hooksPath=" + str(destination / ".git/empty-hooks"), *args],
                cwd=destination,
                capture_output=True,
                check=True,
            )

        git("init", "-q", "-b", "codex/swe-replay")
        git("config", "core.autocrlf", "false")
        git("config", "core.longpaths", "true")
        git("config", "user.name", "Local SWE Replay")
        git("config", "user.email", "replay@example.invalid")
        git("add", ".")
        git("commit", "-q", "-m", "Historical task starting tree")


def mapping(case: dict[str, Any], fixtures: Path, category: str) -> dict[str, str]:
    data: dict[str, str] = json.loads(
        (fixtures / case["id"] / (category + ".json")).read_text(encoding="utf-8")
    )
    if {p: "sha256:" + hashlib.sha256(c.encode()).hexdigest() for p, c in data.items()} != case[
        category + "_file_sha256"
    ]:
        raise ValueError("hidden reference material changed")
    return data


def put(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("reference file escaped workspace")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def grade(
    case: dict[str, Any], workspace: Path, *, admitted: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    shell = RepoShell(workspace, runtime_for(case))
    outcome = shell.run(case["grade_check"], limit=2_000_000)
    result = parse_grade(case["kind"], outcome["output"], outcome["returncode"])
    typecheck = shell.run(case["typecheck"], limit=100_000) if case.get("typecheck") else None
    result.update(
        instrument_valid=outcome["instrument_valid"]
        and (result["receipt_present"] or admitted)
        and (typecheck is None or typecheck["instrument_valid"]),
        typecheck_passed=None if typecheck is None else typecheck["returncode"] == 0,
        elapsed_seconds=sum(c["elapsed_seconds"] for c in shell.calls),
    )
    result["complete"] &= typecheck is None or typecheck["returncode"] == 0
    result["complete"] &= result["passed"] == EXPECTED_CHECKS[case["id"]]
    result["candidate_execution_failed"] = admitted and not result["receipt_present"]
    return result, {"unit": outcome, "typecheck": typecheck}


def copy_candidate_production(
    project: Path, graded: Path, modified: list[str], scope: list[str]
) -> None:
    for relative in modified:
        # Candidate tests are evaluated separately. They cannot weaken the
        # independent original and withheld acceptance suite, or inflate counts.
        if relative.startswith("tests/") or relative in scope:
            continue
        source = project / relative
        if source.is_file():
            (graded / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, graded / relative)


def controls(fixtures: Path, output: Path) -> None:
    cases = json.loads((BENCH / "cases.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    for case in cases:
        before, after = output / (case["id"] + "-original"), output / (case["id"] + "-reference")
        extract(case, fixtures, before)
        put(before, mapping(case, fixtures, "grading"))
        original, raw_before = grade(case, before)
        extract(case, fixtures, after)
        put(after, mapping(case, fixtures, "oracle"))
        put(after, mapping(case, fixtures, "grading"))
        repaired, raw_after = grade(case, after)
        receipt = {"task_id": case["id"], "original": original, "reference": repaired}
        receipts.append(receipt)
        new_json(
            output / (case["id"] + "-control-detail.json"),
            {"original": raw_before, "reference": raw_after},
        )
        print(json.dumps(receipt), flush=True)
        if (
            not original["instrument_valid"]
            or original["complete"]
            or not original["failed"]
            or original["errors"]
            or not repaired["complete"]
        ):
            new_json(output / "failed-control.json", receipt)
            raise ValueError("real-repository control failed; do not run targets")
    new_json(output / "controls.json", receipts)


def freeze() -> None:
    bound = {
        str(p.relative_to(ROOT)).replace("\\", "/"): file_hash(p)
        for p in [
            Path(__file__).resolve(),
            MODULE,
            ROOT / "scripts/prepare_repo_extension_screen.py",
            ROOT / "src/adaptation_compiler_lab/benchmark/extension_screen.py",
            ROOT / "src/adaptation_compiler_lab/autonomy/codex_transport.py",
            ROOT / "src/adaptation_compiler_lab/connectors/codex_app_server.py",
            BENCH / "sources.json",
            BENCH / "cases.json",
            ACTIVE_ADMISSION,
        ]
    }
    new_json(
        ACTIVE_PROTOCOL,
        {
            "created_at": datetime.now(UTC).isoformat(),
            "bound_files": bound,
            "purpose": "development_only_historical_real_repository_replay",
            "instrument_version": 2,
            "repair": "Precreate the read-only Node dependency mountpoint; "
            "reject selector infrastructure failures; preserve all "
            "authoritative tests and fixed expected counts. Task "
            "inputs, source catalog, model, budgets and selection "
            "contract are unchanged.",
            "authoritative_test_counts": EXPECTED_CHECKS,
            "arms": list(ARMS),
            "repeats": 2,
            "maximum_model_turns": 14,
            "additional_transport_probe_turns": 3,
            "solver_seconds": 480,
            "selector_seconds": 150,
            "tool_seconds": 45,
            "max_executed_solver_tools": 60,
            "model_policy": "configured_verified_model_and_effort_no_fallback_minimum_20_perce"
            "nt_known_capacity",
            "native_skill_delivery": "explicit skill input items and a read-only "
            "/skills mirror for "
            "full upstream files or exact selected paragraphs; actual source "
            "loading is verified by a probe",
            "rule": "A completion advantage over direct skills must repeat on the "
            "same task, with no baseline/direct completion regression. "
            "Otherwise no repeated completion advantage. Failures and scope "
            "violations remain failures; instrument failures invalidate "
            "conclusions.",
            "secondary_measures": [
                "authoritative checks",
                "candidate test sensitivity before/after",
                "actual tools",
                "changed paths",
                "wall time",
                "all reported model tokens",
                "mechanical skill setup",
            ],
            "performance_rule": "Two repeats only: descriptive usage and timings; no general "
            "efficiency claim.",
            "overhead": "Include both task selectors, skill publication, fresh native "
            "auth/context/catalog, all tool calls, workspace creation, "
            "authoritative grading, candidate-test counterfactuals and "
            "cleanup. Account shared source acquisition separately. Do not "
            "represent unknown human research, integration, maintenance or "
            "prototype development effort as zero.",
            "shared_preexisting_setup": "Already installed local Python and Node dependencies. No "
            "fresh-machine install or model download measured.",
            "not_claimed": [
                "new product router",
                "full pstack suite",
                "Pi runtime",
                "market demand",
                "independent unseen tasks",
                "native GUI workflows",
                "private-alpha release gate",
            ],
        },
    )
    print("Frozen " + file_hash(ACTIVE_PROTOCOL))


def install_skills(
    workspace: Path, sources: list[dict[str, Any]], material: str | None
) -> list[dict[str, str]]:
    entries = (
        sources
        if material is None
        else [
            {
                "id": "temper-selected",
                "text": "---\nname: temper-selected\ndescription: Task-scoped selected "
                "source guidance.\n---\n\n" + material,
            }
        ]
    )
    result = []
    for source in entries:
        name = (
            "ponytail"
            if source["id"] == "ponytail"
            else "tdd"
            if source["id"] == "pstack-tdd"
            else source["id"]
        )
        path = workspace / ".agents/skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(source["text"], encoding="utf-8", newline="\n")
        result.append({"type": "skill", "name": name, "path": str(path)})
    return result


def model_call(
    config_path: Path,
    prompt: str,
    shell: RepoShell,
    sources: list[dict[str, Any]],
    *,
    material: str | None = None,
    direct: bool = False,
    selector: bool = False,
    expected_model: tuple[str, str] | None = None,
) -> dict[str, Any]:
    start = time.monotonic()
    with benchmark_session(config_path) as (
        config,
        schemas,
        contract,
        rpc,
        native_workspace,
    ):
        if (
            expected_model is not None
            and (config.semantic_model, config.semantic_reasoning_effort) != expected_model
        ):
            raise ValueError("configured model or effort changed during the comparison")
        remaining = read_capacity(rpc, contract)
        if remaining is None or remaining < 20:
            raise ValueError("subscription capacity unknown or below threshold")
        verify_model(
            rpc, contract, model=config.semantic_model, effort=config.semantic_reasoning_effort
        )
        setup_start = time.monotonic()
        skills = (
            install_skills(native_workspace, sources, None if direct else material)
            if direct or material
            else []
        )
        setup_seconds = time.monotonic() - setup_start
        # Explicit skill input is native delivery, avoiding a source-dump comparator.
        if skills:
            shell.skills_root = native_workspace / ".agents/skills"
            prompt += (
                "\n\nUse "
                + " and ".join("$" + s["name"] for s in skills)
                + " for this task. The exact skill files are available to repo_shell read-only "
                "at /skills/<skill-name>/SKILL.md. Read them there before applying the guidance; "
                "native Windows paths in input metadata are not Bash paths."
            )
        value = run_tool_turn(
            rpc,
            schemas,
            workspace=native_workspace,
            model=config.semantic_model,
            effort=config.semantic_reasoning_effort,
            prompt=prompt,
            shell=shell,
            skills=skills,
            selector=selector,
            output_schema=SELECTOR_SCHEMA if selector else None,
            timeout=150 if selector else 480,
            max_tools=12 if selector else 60,
        )
    return {
        **value,
        "model": config.semantic_model,
        "effort": config.semantic_reasoning_effort,
        "elapsed_seconds": time.monotonic() - start,
        "skill_setup_seconds": setup_seconds,
        "native_skill_inputs": len(skills),
        "remaining_capacity_before": remaining,
    }


def transport_probe(config: Path, fixtures: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    project = output / "project"
    project.mkdir()
    (project / "input.txt").write_text("actual-tool-workspace-7139\n")
    source = [
        {
            "id": "ponytail",
            "text": "---\nname: ponytail\ndescription: Native skill delivery transport "
            "probe.\n---\nAfter completing the requested file check, include "
            "NATIVE_SKILL_TRANSPORT_OK in your final message.\n",
        }
    ]
    value = model_call(
        config,
        "Use repo_shell to read input.txt, write its exact contents into "
        "proof.txt, and run a Python assertion that they match. Finish "
        "with a short status.",
        RepoShell(project, RUNTIME),
        source,
        direct=True,
    )
    config_value = _load_config(config)
    raw = LocalRawPayloadStore(
        output / "encrypted-raw",
        encryption_key=_runtime_secrets(config_value).raw_encryption_key(
            workspace_root=config_value.repository_root
        ),
    )
    reference = raw.put(json.dumps(value).encode(), media_type="application/json")
    passed = (
        value["status"] == "completed"
        and len(value["tool_calls"]) > 0
        and (project / "proof.txt").read_text() == (project / "input.txt").read_text()
        and "NATIVE_SKILL_TRANSPORT_OK" in "\n".join(value["messages"])
    )
    new_json(
        output / "probe.json",
        {
            "passed": passed,
            "usage": value["usage"],
            "elapsed_seconds": value["elapsed_seconds"],
            "native_skill_inputs": value["native_skill_inputs"],
            "tool_calls": len(value["tool_calls"]),
            "raw_ref": asdict(reference),
        },
    )
    print(json.dumps({"native_skill_and_real_tool_probe": passed}), flush=True)
    if not passed:
        raise ValueError("native skill/tool transport did not execute correctly")


def candidate_test_sensitivity(
    case: dict[str, Any], fixtures: Path, output: Path, candidate: Path, changed: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    tests = [
        p
        for p in changed
        if p.startswith("tests/") and p.endswith((".py", ".test.ts")) and (candidate / p).is_file()
    ]
    if not tests:
        return {"state": "no_changed_tests", "test_paths": []}, {}
    before, after = output / "test-before", output / "test-after"
    extract(case, fixtures, before)
    # Preserve candidate production state and original/added candidate checks.
    shutil.copytree(
        candidate, after, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")
    )
    for p in changed:
        if not p.startswith("tests/") or not (candidate / p).is_file():
            continue
        (before / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / p, before / p)
    command = (
        "python -m pytest -q -p no:cacheprovider "
        if case["kind"] == "python"
        else "node node_modules/vitest/vitest.mjs run "
    )
    command += " ".join(__import__("shlex").quote(p) for p in tests)
    if case["kind"] == "node":
        command += " --maxWorkers=1 --no-file-parallelism --reporter=json"
    outcomes = [
        RepoShell(p, runtime_for(case)).run(command, limit=2_000_000) for p in (before, after)
    ]
    grades = [parse_grade(case["kind"], r["output"], r["returncode"]) for r in outcomes]
    sensitivity = grades[0]["failed"] > 0 and grades[0]["errors"] == 0 and grades[1]["complete"]
    return {
        "state": "failing_before_passing_after"
        if sensitivity
        else "intended_failure_not_established",
        "test_paths": tests,
        "before": grades[0],
        "after": grades[1],
        "elapsed_seconds": sum(o["elapsed_seconds"] for o in outcomes),
    }, {"before": outcomes[0], "after": outcomes[1]}


def run(config_path: Path, fixtures: Path, output: Path) -> None:
    protocol = json.loads(ACTIVE_PROTOCOL.read_text(encoding="utf-8"))
    for relative, expected in protocol["bound_files"].items():
        if file_hash(ROOT / relative) != expected:
            raise ValueError("frozen implementation or input changed")
    admission = json.loads(ACTIVE_ADMISSION.read_text(encoding="utf-8"))
    if not admission["native_skill_and_tool_probe_passed"] or not admission["all_controls_passed"]:
        raise ValueError("instrument has not passed its real execution controls")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True):
        raise ValueError("target execution requires a clean committed source candidate")
    if any((p / ".git").exists() for p in (output, *output.parents)):
        raise ValueError("model traces must stay outside Git")
    output.mkdir(parents=True, exist_ok=False)
    config = _load_config(config_path)
    raw = LocalRawPayloadStore(
        output / "encrypted-raw",
        encryption_key=_runtime_secrets(config).raw_encryption_key(
            workspace_root=config.repository_root
        ),
    )
    cases = json.loads((BENCH / "cases.json").read_text(encoding="utf-8"))
    sources = json.loads((BENCH / "sources.json").read_text(encoding="utf-8"))
    if any(
        "sha256:" + hashlib.sha256(s["text"].encode()).hexdigest() != s["source_sha256"]
        for s in sources
    ):
        raise ValueError("loaded upstream source text does not match its pinned digest")
    started = time.monotonic()
    new_json(
        output / "execution.json",
        {
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "protocol_sha256": file_hash(ACTIVE_PROTOCOL),
            "model": config.semantic_model,
            "effort": config.semantic_reasoning_effort,
            "started_at": datetime.now(UTC).isoformat(),
            "github_ci_used": False,
            "personal_runtime_modified": False,
            "runtime": RUNTIME,
            "native_executable_sha256": file_hash(config.codex_executable),
            "native_pin_sha256": file_hash(config.runtime_pin_path),
        },
    )
    # Cheap file publication only; not represented as human onboarding time.
    mechanical = {}
    for arm in ("direct_skills", "temper_selected"):
        values = []
        for i in range(5):
            destination = output / "setup-measurements" / f"{arm}-{i}"
            t = time.monotonic()
            install_skills(
                destination,
                sources,
                None
                if arm == "direct_skills"
                else "Representative bounded guidance for a filesystem-only setup measurement.",
            )
            remove_tree(destination, output)
            values.append(time.monotonic() - t)
        mechanical[arm] = {
            "seconds": values,
            "median_seconds": statistics.median(values),
            "scope": "local skill file creation and removal only; placeholder selected "
            "text, no inference",
        }
    new_json(output / "mechanical-setup.json", mechanical)
    selectors = []
    plans = {}
    for case in cases:
        print(json.dumps({"selector_started": case["id"]}), flush=True)
        project = output / "selection-workspaces" / case["id"]
        setup_start = time.monotonic()
        extract(case, fixtures, project)
        before = tree(project)
        selection = model_call(
            config_path,
            json.dumps(
                {
                    "task": case["task"],
                    "visible_verification": case["visible_check"],
                    "catalog": clauses(sources),
                }
            ),
            RepoShell(project, runtime_for(case), readonly=True),
            [],
            selector=True,
            expected_model=(config.semantic_model, config.semantic_reasoning_effort),
        )
        raw_ref = raw.put(json.dumps(selection).encode(), media_type="application/json")
        if (
            selection["status"] != "completed"
            or tree(project) != before
            or not all(t["instrument_valid"] for t in selection["tool_calls"])
        ):
            new_json(
                output / "selectors" / (case["id"] + "-failed.json"),
                {
                    "task_id": case["id"],
                    "instrument_valid": False,
                    "usage": selection["usage"],
                    "elapsed_seconds": selection["elapsed_seconds"],
                    "raw_ref": asdict(raw_ref),
                },
            )
            raise ValueError("selector failed its admitted read-only tool environment")
        ids = json.loads(selection["messages"][-1])["clause_ids"]
        plans[case["id"]] = selected_text(sources, ids)
        receipt = {
            "task_id": case["id"],
            "clause_ids": ids,
            "usage": selection["usage"],
            "model_call_seconds": selection["elapsed_seconds"],
            "total_seconds": time.monotonic() - setup_start,
            "native_skill_inputs": 0,
            "tool_count": len(selection["tool_calls"]),
            "raw_ref": asdict(raw_ref),
        }
        selectors.append(receipt)
        new_json(output / "selectors" / (case["id"] + ".json"), receipt)
        print(
            json.dumps(
                {"selected": case["id"], "paragraphs": len(ids), "tools": receipt["tool_count"]}
            ),
            flush=True,
        )
    trials = []
    for repeat in (0, 1):
        for index, case in enumerate(cases):
            order = list(ARMS)
            rotation = (index + repeat) % 3
            order = order[rotation:] + order[:rotation]
            for arm in order:
                start = time.monotonic()
                name = f"{case['id']}-{arm}-{repeat}"
                print(json.dumps({"trial_started": name}), flush=True)
                folder = output / "trials" / name
                project = folder / "project"
                extract(case, fixtures, project, git_init=True)
                before = tree(project)
                setup_seconds = time.monotonic() - start
                value = model_call(
                    config_path,
                    case["task"] + "\n\nExisting focused test command:\n" + case["visible_check"],
                    RepoShell(project, runtime_for(case)),
                    sources,
                    direct=arm == "direct_skills",
                    material=plans[case["id"]] if arm == "temper_selected" else None,
                    expected_model=(config.semantic_model, config.semantic_reasoning_effort),
                )
                modified = changed_paths(before, tree(project))
                scope = scope_failures(modified, case["allowed_prefixes"])
                deleted = [p for p in modified if not (project / p).is_file()]
                grade_start = time.monotonic()
                graded = folder / "authoritative-grade"
                extract(case, fixtures, graded)
                copy_candidate_production(project, graded, modified, scope)
                # Restore historical reference tests, so candidate test weakening cannot pass.
                put(graded, mapping(case, fixtures, "grading"))
                result, grade_raw = grade(case, graded, admitted=True)
                sensitivity, sensitivity_raw = candidate_test_sensitivity(
                    case, fixtures, folder, project, modified
                )
                grading_seconds = time.monotonic() - grade_start
                raw_ref = raw.put(
                    json.dumps(
                        {
                            "model": value,
                            "authoritative": grade_raw,
                            "candidate_test_sensitivity": sensitivity_raw,
                        }
                    ).encode(),
                    media_type="application/json",
                )
                instrument = result["instrument_valid"] and all(
                    t["instrument_valid"] for t in value["tool_calls"]
                )
                # Preserve encrypted patches, then remove disposable source copies.
                patch_ref = raw.put(
                    json.dumps(
                        {
                            p: (project / p).read_text(encoding="utf-8", errors="strict")
                            for p in modified
                            if (project / p).is_file()
                        }
                    ).encode(),
                    media_type="application/json",
                )
                cleanup_start = time.monotonic()
                for directory in (project, graded, folder / "test-before", folder / "test-after"):
                    if directory.exists():
                        remove_tree(directory, output)
                cleanup_seconds = time.monotonic() - cleanup_start
                receipt = {
                    "task_id": case["id"],
                    "arm": arm,
                    "repeat": repeat,
                    "model_status": value["status"],
                    "model": value["model"],
                    "effort": value["effort"],
                    "complete": bool(
                        result["complete"]
                        and value["status"] == "completed"
                        and not scope
                        and not deleted
                    ),
                    "instrument_valid": instrument,
                    "authoritative": result,
                    "scope_failures": scope,
                    "deleted_paths": deleted,
                    "changed_paths": modified,
                    "candidate_tests": sensitivity,
                    "usage": value["usage"],
                    "tool_count": len(value["tool_calls"]),
                    "failed_tool_calls": sum(t["returncode"] != 0 for t in value["tool_calls"]),
                    "tool_seconds": sum(t.get("elapsed_seconds", 0) for t in value["tool_calls"]),
                    "native_skill_inputs": value["native_skill_inputs"],
                    "workspace_setup_seconds": setup_seconds,
                    "model_call_seconds": value["elapsed_seconds"],
                    "skill_setup_seconds": value["skill_setup_seconds"],
                    "grading_and_counterfactual_seconds": grading_seconds,
                    "cleanup_seconds": cleanup_seconds,
                    "total_seconds": time.monotonic() - start,
                    "raw_ref": asdict(raw_ref),
                    "patch_ref": asdict(patch_ref),
                }
                new_json(folder / "receipt.json", receipt)
                trials.append(receipt)
                print(
                    json.dumps(
                        {
                            "trial": name,
                            "complete": receipt["complete"],
                            "checks": result["passed"],
                            "failed": result["failed"],
                            "tools": receipt["tool_count"],
                            "seconds": round(receipt["total_seconds"], 1),
                        }
                    ),
                    flush=True,
                )
                if not instrument:
                    raise ValueError(
                        "instrument failed; preserve this attempted cell and do not claim "
                        "a comparison"
                    )
    summary = summarize(trials)
    summary.update(model_calls=14, selectors=selectors, wall_seconds=time.monotonic() - started)
    new_json(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    args.fixtures = extended(args.fixtures)
    if args.output is not None:
        args.output = extended(args.output)
    if args.freeze:
        freeze()
    elif args.controls:
        if args.output is None:
            parser.error("--controls requires --output")
        controls(args.fixtures, args.output)
    elif args.probe:
        if args.output is None or args.config is None:
            parser.error("--probe requires --output and --config")
        transport_probe(args.config, args.fixtures, args.output)
    elif args.config and args.output:
        run(args.config, args.fixtures, args.output)
    else:
        parser.error("choose --controls, --probe, --freeze or --config with --output")
