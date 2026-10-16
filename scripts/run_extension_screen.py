"""Freeze and run a rapid development-only extension composition comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config, _runtime_secrets
from adaptation_compiler_lab.autonomy.codex_transport import (
    configured_analysis_session,
    read_capacity,
    run_habit_turn,
    verify_model,
)
from adaptation_compiler_lab.benchmark.extension_screen import (
    COMMON,
    CONDITIONS,
    SELECTOR,
    SELECTOR_SCHEMA,
    SOLVER_SCHEMA,
    clauses,
    compile_selection,
    digest,
    prompt,
    score,
    summarize,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "development_benchmark_extensions" / "rapid-v1"
RUNNER = Path(__file__).resolve()
SCORER = ROOT / "src/adaptation_compiler_lab/benchmark/extension_screen.py"


def write_new(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str) -> bytes:
    with urlopen(
        Request(url, headers={"User-Agent": "Temper-development-screen"}), timeout=30
    ) as response:
        payload: bytes = response.read(256 * 1024)
        return payload


def prepare() -> None:
    sources = []
    for source_id, repository, path in (
        ("ponytail", "DietrichGebert/ponytail", "skills/ponytail/SKILL.md"),
        ("pstack-how", "backnotprop/pstack", "skills/how/SKILL.md"),
    ):
        commit = json.loads(fetch(f"https://api.github.com/repos/{repository}/commits/main"))["sha"]
        text = fetch(f"https://raw.githubusercontent.com/{repository}/{commit}/{path}").decode()
        license_text = fetch(
            f"https://raw.githubusercontent.com/{repository}/{commit}/LICENSE"
        ).decode()
        if "Permission is hereby granted" not in license_text:
            raise ValueError("source license requires further review")
        sources.append(
            {
                "id": source_id,
                "repository": "https://github.com/" + repository,
                "commit": commit,
                "path": path,
                "text": text,
                "source_sha256": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
                "license": license_text,
                "license_sha256": "sha256:" + hashlib.sha256(license_text.encode()).hexdigest(),
            }
        )
    write_new(BENCH / "sources.json", sources)
    freeze("protocol.json")


def freeze(filename: str = "protocol-validated.json") -> None:
    # Inputs and code are bound only before target execution; prior preparation is preserved.
    sources = json.loads((BENCH / "sources.json").read_text())
    cases = json.loads((BENCH / "cases.json").read_text())
    frozen = {
        "purpose": "development_screen_not_release_calibration",
        "created_at": datetime.now(UTC).isoformat(),
        "repeats": 2,
        "conditions": list(CONDITIONS),
        "cases_sha256": file_hash(BENCH / "cases.json"),
        "sources_sha256": file_hash(BENCH / "sources.json"),
        "runner_sha256": file_hash(RUNNER),
        "scorer_sha256": file_hash(SCORER),
        "model_policy": "configured_verified_model_no_fallback",
        "maximum_model_turns": 21,
        "turn_timeout_seconds": 120,
        "minimum_remaining_capacity": 20,
        "correctness_before_cost": True,
        "rule": (
            "Advance only on an objective gain over direct guidance repeated twice, with no "
            "baseline/direct regression and no neutral-task guidance; otherwise report no "
            "incremental quality signal, regression or instrument failure."
        ),
        "performance_rule": (
            "Two repetitions only; report median/range descriptively, "
            "no speed/token efficiency claim."
        ),
        "not_tested": [
            "native plugins/hooks",
            "Pi runtime",
            "persistent personal learning",
            "market demand",
            "general effectiveness",
        ],
        "task_ids": [case["id"] for case in cases],
    }
    write_new(BENCH / filename, frozen)
    print(
        json.dumps(
            {
                "prepared": True,
                "protocol_digest": digest(frozen),
                "sources": [{k: s[k] for k in ("id", "commit", "source_sha256")} for s in sources],
            }
        )
    )


class Tap:
    def __init__(self, rpc: Any) -> None:
        self.rpc = rpc
        self.events: list[dict[str, Any]] = []
        self.usage: dict[str, Any] | None = None

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = self.rpc.request(method, params)
        self.events.append({"method": method, "params": params, "result": result})
        return result

    def next_notification(self, **kwargs: Any) -> dict[str, Any]:
        event: dict[str, Any] = self.rpc.next_notification(**kwargs)
        self.events.append(event)
        if event.get("method") == "thread/tokenUsage/updated":
            self.usage = event.get("params", {}).get("tokenUsage", {}).get("total")
        return event


def run(config_path: Path, output: Path) -> None:
    protocol = json.loads((BENCH / "protocol-validated.json").read_text())
    for key, path in (
        ("cases_sha256", BENCH / "cases.json"),
        ("sources_sha256", BENCH / "sources.json"),
        ("runner_sha256", RUNNER),
        ("scorer_sha256", SCORER),
    ):
        if file_hash(path) != protocol[key]:
            raise ValueError("frozen inputs or implementation changed; do not resume this run")
    output.mkdir(parents=True, exist_ok=True)
    if any((parent / ".git").exists() for parent in (output, *output.parents)):
        raise ValueError("raw benchmark execution must stay outside Git")
    if (output / "summary.json").exists() or (output / "execution.json").exists():
        raise ValueError("execution already exists; preserve it rather than overwrite")
    cases = json.loads((BENCH / "cases.json").read_text())
    sources = json.loads((BENCH / "sources.json").read_text())
    catalog = clauses(sources)
    config = _load_config(config_path)
    raw = LocalRawPayloadStore(
        output / "encrypted-raw",
        encryption_key=_runtime_secrets(config).raw_encryption_key(
            workspace_root=config.repository_root
        ),
    )
    write_new(
        output / "execution.json",
        {
            "protocol_digest": digest(protocol),
            "model": config.semantic_model,
            "effort": config.semantic_reasoning_effort,
            "started_at": datetime.now(UTC).isoformat(),
            "source_commit": __import__("subprocess")
            .check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
            .strip(),
            "calls_limit": 21,
            "github_ci_used": False,
            "personal_runtime_modified": False,
        },
    )
    controls = []
    for case in cases:
        before = score(case, {"files": []}, output)
        oracle = score(
            case, {"files": [{"path": p, "content": c} for p, c in case["oracle"].items()]}, output
        )
        if not before["instrument_valid"] or before["complete"] or not oracle["complete"]:
            raise ValueError("baseline/oracle instrument checks failed before target execution")
        controls.append({"task_id": case["id"], "before": before, "oracle": oracle})
    write_new(output / "controls.json", controls)
    calls = 0

    def call(name: str, instructions: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        if calls >= 21:
            raise ValueError("foreground screen reached its frozen model-call budget")
        calls += 1
        started = time.monotonic()
        with configured_analysis_session(config_path) as (
            current,
            schemas,
            contract,
            rpc,
            workspace,
        ):
            if (current.semantic_model, current.semantic_reasoning_effort) != (
                config.semantic_model,
                config.semantic_reasoning_effort,
            ):
                raise ValueError("configured model changed during comparison")
            capacity = read_capacity(rpc, contract)
            if capacity is None or capacity < 20:
                raise ValueError("subscription capacity unknown or below threshold")
            verify_model(
                rpc, contract, model=config.semantic_model, effort=config.semantic_reasoning_effort
            )
            tap = Tap(rpc)
            result = run_habit_turn(
                tap,
                schemas,
                workspace=workspace,
                model=config.semantic_model,
                effort=config.semantic_reasoning_effort,
                contract=instructions,
                prompt=user,
                output_schema=schema,
                timeout=120,
            )
        elapsed = time.monotonic() - started
        raw_ref = raw.put(
            json.dumps({"events": tap.events, "result": result}).encode(),
            media_type="application/json",
        )
        record = {
            "name": name,
            "elapsed_seconds": elapsed,
            "usage": tap.usage,
            "instruction_utf8_bytes": len(instructions.encode()),
            "prompt_utf8_bytes": len(user.encode()),
            "raw_ref": asdict(raw_ref),
            "result_digest": digest(json.loads(result)),
        }
        write_new(output / "calls" / (name + ".json"), record)
        return {"record": record, "value": json.loads(result)}

    selectors = []
    selections = {}
    for case in cases:
        selected = call(
            case["id"] + "-selector",
            SELECTOR,
            json.dumps({"task": json.loads(prompt(case)), "catalog": catalog}),
            SELECTOR_SCHEMA,
        )
        ids = selected["value"]["clause_ids"]
        selections[case["id"]] = compile_selection(catalog, ids)
        selectors.append({"task_id": case["id"], "clause_ids": ids, **selected["record"]})
        print(json.dumps({"selected": case["id"], "clauses": len(ids)}), flush=True)
    write_new(output / "selectors.json", selectors)
    full = "\n\n".join(s["text"] for s in sources)
    trials = []
    # Counterbalance order across tasks/repetitions. Every trial starts a fresh context.
    for repeat in (0, 1):
        for case_index, case in enumerate(cases):
            order = list(CONDITIONS)
            rotation = (case_index + repeat) % 3
            order = order[rotation:] + order[:rotation]
            for condition in order:
                material = (
                    ""
                    if condition == "baseline"
                    else full
                    if condition == "direct_sources"
                    else selections[case["id"]]
                )
                instructions = COMMON + (
                    "\n\nAdvisory source material:\n" + material if material else ""
                )
                name = f"{case['id']}-{condition}-{repeat}"
                result = call(name, instructions, prompt(case), SOLVER_SCHEMA)
                try:
                    outcome = score(case, result["value"], output)
                except ValueError as error:
                    outcome = {
                        "instrument_valid": True,
                        "complete": False,
                        "passed": [],
                        "total": case["check_count"],
                        "scope_failure": str(error),
                    }
                trial = {
                    "task_id": case["id"],
                    "condition": condition,
                    "repeat": repeat,
                    "score": outcome,
                    **result["record"],
                }
                write_new(output / "trials" / (name + ".json"), trial)
                trials.append(trial)
                print(
                    json.dumps(
                        {
                            "trial": name,
                            "passed": len(outcome["passed"]),
                            "total": outcome["total"],
                            "complete": outcome["complete"],
                        }
                    ),
                    flush=True,
                )
    summary = summarize(trials, selectors)
    summary.update(
        protocol_digest=digest(protocol),
        model=config.semantic_model,
        model_turns=calls,
        upstream_source_commits={s["id"]: s["commit"] for s in sources},
    )
    write_new(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.freeze:
        freeze()
    elif args.config and args.output:
        run(args.config, args.output)
    else:
        parser.error("use --prepare or provide --config and --output")
