"""Freeze exact fixtures and runtime pins for the eight-cell debugger screen."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.modes import render_mode_material
from adaptation_compiler_lab.modes.curated_catalog import (
    CURATED_CATALOG,
    SYSTEMATIC_DEBUGGER_MODE,
)
from adaptation_compiler_lab.modes.evaluation import (
    ModeEvaluationFixtureV1,
    ModeEvaluationScenarioV1,
)
from adaptation_compiler_lab.modes.foundry_execution import FoundryExecutionContractV1
from adaptation_compiler_lab.modes.foundry_screening import FOUNDRY_SCREENING_DESIGN
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json


def _bundle_digest(repo: Path, paths: tuple[str, ...]) -> str:
    return canonical_digest({path: sha256_file(repo / path) for path in paths})


def _write_new(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _fixture(
    *,
    benchmark: Path,
    task_id: str,
    kind: Literal["diagnostic", "neutral_control"],
    title: str,
    prompt: str,
    function_name: str,
    fixture_directory: str,
    scenarios: tuple[ModeEvaluationScenarioV1, ...],
) -> ModeEvaluationFixtureV1:
    return ModeEvaluationFixtureV1(
        task_id=task_id,
        mode_id=SYSTEMATIC_DEBUGGER_MODE.mode_id,
        kind=kind,
        title=title,
        prompt=prompt,
        function_name=function_name,
        fixture_directory=fixture_directory,
        fixture_digest=development_tree_digest(benchmark / fixture_directory),
        allowed_change_paths=("src/solution.py",),
        visible_test_command=("python3", "-m", "unittest", "discover", "-v"),
        scenarios=scenarios,
    )


def build_contract(repo: Path) -> FoundryExecutionContractV1:
    benchmark = repo / "development_benchmark_curated_modes"
    fixtures = (
        _fixture(
            benchmark=benchmark,
            task_id="foundry-debug-01-shared-state",
            kind="diagnostic",
            title="Intermittent shared-state leak",
            prompt=(
                "Investigate a production report in `src/solution.py`: after one request has "
                "labels, the next request in the same worker batch sometimes inherits them. The "
                "small visible suite passes and therefore does not establish the reported "
                "behavior. "
                "Reproduce the incident locally, identify the first incorrect state, make one "
                "root-cause repair, rerun the focused reproduction, then run "
                "`python3 -m unittest discover -v`. Change only `src/solution.py` and report only "
                "checks you actually ran."
            ),
            function_name="render_request_pair",
            fixture_directory="fixtures/systematic-debugger/shared-state",
            scenarios=(
                ModeEvaluationScenarioV1(
                    scenario_id="shared-01-labeled-then-empty",
                    arguments=("ada", ["urgent"], "grace", []),
                    expected=[
                        {"labels": ["urgent"], "locale": "en-US", "user_id": "ada"},
                        {"labels": [], "locale": "en-US", "user_id": "grace"},
                    ],
                    metric="diagnostic",
                ),
                ModeEvaluationScenarioV1(
                    scenario_id="shared-02-empty-then-labeled",
                    arguments=("ada", [], "grace", ["review"]),
                    expected=[
                        {"labels": [], "locale": "en-US", "user_id": "ada"},
                        {"labels": ["review"], "locale": "en-US", "user_id": "grace"},
                    ],
                    metric="diagnostic",
                ),
                ModeEvaluationScenarioV1(
                    scenario_id="shared-03-distinct-labels",
                    arguments=("ada", ["one", "two"], "grace", ["three"]),
                    expected=[
                        {"labels": ["one", "two"], "locale": "en-US", "user_id": "ada"},
                        {"labels": ["three"], "locale": "en-US", "user_id": "grace"},
                    ],
                    metric="diagnostic",
                ),
            ),
        ),
        _fixture(
            benchmark=benchmark,
            task_id="foundry-debug-02-failed-fix",
            kind="diagnostic",
            title="Misleading previous repair",
            prompt=(
                "A previous repair note says that changing `policy = template` to "
                "`policy = template.copy()` fixed cross-job leakage in `src/solution.py`. The live "
                "report says the second policy still inherits the first policy's `X-Trace` header "
                "and retry delay. Do not trust the stale repair note. Reproduce the current "
                "failure, "
                "re-diagnose it from the live code, make one focused root-cause repair, rerun the "
                "reproduction, and run `python3 -m unittest discover -v`. Change only "
                "`src/solution.py` and report verification accurately."
            ),
            function_name="build_policy_pair",
            fixture_directory="fixtures/systematic-debugger/failed-fix",
            scenarios=(
                ModeEvaluationScenarioV1(
                    scenario_id="failed-fix-01-first-mutates",
                    arguments=("one", {"X-Trace": "yes"}, 2, "two", {}, None),
                    expected=[
                        {
                            "headers": {"Accept": "application/json", "X-Trace": "yes"},
                            "job_id": "one",
                            "retry_delays": [2],
                        },
                        {
                            "headers": {"Accept": "application/json"},
                            "job_id": "two",
                            "retry_delays": [],
                        },
                    ],
                    metric="diagnostic",
                ),
                ModeEvaluationScenarioV1(
                    scenario_id="failed-fix-02-independent-headers",
                    arguments=(
                        "one",
                        {"Accept": "text/plain"},
                        None,
                        "two",
                        {"X-Mode": "safe"},
                        None,
                    ),
                    expected=[
                        {
                            "headers": {"Accept": "text/plain"},
                            "job_id": "one",
                            "retry_delays": [],
                        },
                        {
                            "headers": {"Accept": "application/json", "X-Mode": "safe"},
                            "job_id": "two",
                            "retry_delays": [],
                        },
                    ],
                    metric="diagnostic",
                ),
                ModeEvaluationScenarioV1(
                    scenario_id="failed-fix-03-second-retry-only",
                    arguments=("one", {}, None, "two", {}, 5),
                    expected=[
                        {
                            "headers": {"Accept": "application/json"},
                            "job_id": "one",
                            "retry_delays": [],
                        },
                        {
                            "headers": {"Accept": "application/json"},
                            "job_id": "two",
                            "retry_delays": [5],
                        },
                    ],
                    metric="diagnostic",
                ),
            ),
        ),
        _fixture(
            benchmark=benchmark,
            task_id="foundry-debug-04-neutral-copy",
            kind="neutral_control",
            title="Release-status copy",
            prompt=(
                "Repair `release_status` in `src/solution.py` so surrounding whitespace is removed "
                "from both the component and version in its returned sentence. Preserve its "
                "validation and ready/not-ready wording. This is a narrow copy correction, not a "
                "debugging investigation. Change only `src/solution.py` and run "
                "`python3 -m unittest discover -v`."
            ),
            function_name="release_status",
            fixture_directory="fixtures/systematic-debugger/neutral-copy",
            scenarios=(
                ModeEvaluationScenarioV1(
                    scenario_id="neutral-01-ready-trimmed",
                    arguments=(" Desktop ", " 1.2 ", True),
                    expected="Desktop 1.2 is ready.",
                    metric="neutral",
                ),
                ModeEvaluationScenarioV1(
                    scenario_id="neutral-02-not-ready-trimmed",
                    arguments=(" Engine ", " 0.4-beta ", False),
                    expected="Engine 0.4-beta is not ready.",
                    metric="neutral",
                ),
                ModeEvaluationScenarioV1(
                    scenario_id="neutral-03-stable",
                    arguments=("CLI", "2", True),
                    expected="CLI 2 is ready.",
                    metric="neutral",
                ),
            ),
        ),
    )
    compiled = render_mode_material(SYSTEMATIC_DEBUGGER_MODE)
    upstream = (benchmark / "upstream/systematic-debugging-safe.md").read_bytes()
    return FoundryExecutionContractV1(
        design_digest=FOUNDRY_SCREENING_DESIGN.content_digest,
        catalog_digest=CURATED_CATALOG.content_digest,
        release_digest=next(
            item.content_digest
            for item in CURATED_CATALOG.releases
            if item.mode.mode_id == SYSTEMATIC_DEBUGGER_MODE.mode_id
        ),
        fixtures=tuple(sorted(fixtures, key=lambda item: item.task_id)),
        upstream_material_digest=sha256_bytes(upstream),
        compiled_material_digest=sha256_bytes(compiled.encode("utf-8")),
        compiled_material_utf8_bytes=len(compiled.encode("utf-8")),
        runner_source_digest=_bundle_digest(
            repo,
            (
                "scripts/run_foundry_systematic_debugger.py",
                "scripts/run_durable_progress_comparison.py",
                "src/adaptation_compiler_lab/runners/codex_mode_target.py",
                "src/adaptation_compiler_lab/runners/codex_subscription.py",
            ),
        ),
        scorer_source_digest=_bundle_digest(
            repo,
            (
                "scripts/score_foundry_screening_task.py",
                "scripts/observe_foundry_debug_policy.py",
                "src/adaptation_compiler_lab/modes/evaluation.py",
                "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
                "uv.lock",
            ),
        ),
        observer_source_digest=sha256_file(repo / "scripts/observe_foundry_debug_policy.py"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.expanduser().resolve()
    benchmark = repo / "development_benchmark_curated_modes"
    contract = build_contract(repo)
    (benchmark / "tasks").mkdir(parents=True, exist_ok=True)
    _write_new(
        benchmark / "EXECUTION_CONTRACT-systematic-debugger-v1.json",
        (canonical_json(contract) + "\n").encode("utf-8"),
    )
    for fixture in contract.fixtures:
        _write_new(
            benchmark / "tasks" / f"{fixture.task_id}.json",
            (canonical_json(fixture) + "\n").encode("utf-8"),
        )
    _write_new(
        benchmark / "PREREGISTRATION-systematic-debugger-v1.sha256",
        (contract.content_digest + "\n").encode("ascii"),
    )
    print(
        canonical_json(
            {
                "contract_digest": contract.content_digest,
                "mode_id": contract.mode_id,
                "target_runs": contract.target_runs,
            }
        )
    )


if __name__ == "__main__":
    main()
