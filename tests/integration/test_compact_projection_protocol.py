from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionTask,
    load_compact_projection_design,
)
from adaptation_compiler_lab.benchmark.longitudinal_instrument import (
    parse_porcelain_v1_z,
    unexpected_changed_paths,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.runtime import (
    CanonicalRuntimeProjection,
    ExternalGovernedRelease,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.codex_runtime import (
    RenderedRuntimeProjection,
    build_runtime_projection_manifest,
    render_codex_runtime_projection,
)


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_compact_projection"


def _score(task: CompactProjectionTask, workspace: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "score_compact_projection_task.py"),
            "--task-manifest",
            str(_root() / task.fixture_directory).replace("/fixture", "/task.json"),
            "--workspace",
            str(workspace),
        ],
        cwd=workspace,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


def _all_checks(value: dict[str, object]) -> dict[str, bool]:
    groups = value["checks"]
    assert isinstance(groups, dict)
    return {
        name: passed
        for group in groups.values()
        if isinstance(group, dict)
        for name, passed in group.items()
        if isinstance(name, str) and isinstance(passed, bool)
    }


def _reference(stage: int) -> str:
    cache = (
        'return ("replace_destination",)'
        if stage == 1
        else 'return ("write_temporary_tree", "atomically_replace_destination")'
    )
    durable = (
        'return ("create_recovery_copy", "replace_destination")'
        if stage < 3
        else (
            'return ("create_recovery_copy", "replace_destination") '
            'if recovery_copy_approved else ("refuse_replacement",)'
        )
    )
    return (
        "def plan_delivery(\n"
        "    destination_exists: bool,\n"
        "    storage_class: str,\n"
        "    recovery_copy_approved: bool = False,\n"
        ") -> tuple[str, ...]:\n"
        '    if storage_class not in {"durable_release", "ephemeral_build_cache"}:\n'
        '        raise ValueError(f"unsupported storage class: {storage_class}")\n'
        "    if not destination_exists:\n"
        '        return ("create_destination",)\n'
        '    if storage_class == "ephemeral_build_cache":\n'
        f"        {cache}\n"
        f"    {durable}\n"
    )


def _workspace(tmp_path: Path, task: CompactProjectionTask, source: str) -> Path:
    workspace = tmp_path / task.task_id
    shutil.copytree(_root() / task.fixture_directory, workspace)
    (workspace / "deployment_policy.py").write_text(source, encoding="utf-8")
    return workspace


def test_fresh_protocol_is_hash_frozen_and_unexecuted() -> None:
    root = _root()
    design = load_compact_projection_design(root)
    expected = (root / "PREREGISTRATION-v1.2.sha256").read_text(encoding="ascii").split()[0]

    assert sha256_file(root / "PREREGISTRATION-v1.2.json") == f"sha256:{expected}"
    assert design.design_version == "1.2.0"
    assert design.amendment_reason == "isolated_policy_observation"
    assert design.supersedes_design_digest
    assert design.superseded_scorer_digest
    assert design.policy_observer_digest
    assert design.scorer_sandbox_digest
    assert design.planned_target_sessions == 6
    assert design.maximum_subscription_sessions == 9
    assert not design.target_sessions_started
    assert not design.profile_sessions_started
    assert not design.judge_sessions_started
    assert design.provider_billed_calls == 0
    assert not design.api_keys_allowed
    assert not design.sealed_external_validation_accessed


def test_task_prompts_are_natural_and_do_not_disclose_expected_implementation() -> None:
    design = load_compact_projection_design(_root())

    for task in design.tasks:
        lowered = task.task_prompt.casefold()
        assert "create_recovery_copy" not in lowered
        assert "atomically_replace_destination" not in lowered
        assert "refuse_replacement" not in lowered
        assert "compiled" not in lowered
        assert "static profile" not in lowered


def test_visible_tests_pass_in_all_fresh_fixtures() -> None:
    design = load_compact_projection_design(_root())

    for task in design.tasks:
        completed = subprocess.run(
            list(task.visible_test_command),
            cwd=_root() / task.fixture_directory,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert completed.returncode == 0, (task.task_id, completed.stdout, completed.stderr)


def test_reference_implementations_pass_every_frozen_scenario(tmp_path: Path) -> None:
    design = load_compact_projection_design(_root())

    for task in design.tasks:
        result = _score(task, _workspace(tmp_path, task, _reference(task.stage)))
        assert all(_all_checks(result).values())


def test_scorer_detects_stale_rule(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[2]
    source = _reference(2)

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-s3-diagnostic-durable-default"]


def test_scorer_detects_missed_exception(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[1]
    source = _reference(1)

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-s2-diagnostic-cache-default"]


def test_scorer_detects_scope_leak(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[1]
    source = _reference(2).replace(
        'if storage_class == "ephemeral_build_cache":\n'
        '        return ("write_temporary_tree", "atomically_replace_destination")\n'
        '    return ("create_recovery_copy", "replace_destination")',
        'return ("write_temporary_tree", "atomically_replace_destination")',
    )

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-s2-neutral-durable-default"]


def test_scorer_detects_unnecessary_change(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[0]
    source = _reference(1).replace(
        'return ("create_destination",)',
        'return ("refuse_replacement",)',
        1,
    )

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-s1-objective-new-durable"]


@pytest.mark.parametrize(
    "replacement",
    (
        '"refuse_replacement"',
        '["refuse_replacement"]',
    ),
)
def test_scorer_rejects_non_tuple_return_contract(
    tmp_path: Path,
    replacement: str,
) -> None:
    task = load_compact_projection_design(_root()).tasks[2]
    source = _reference(3).replace('else ("refuse_replacement",)', f"else {replacement}")

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-s3-diagnostic-durable-default"]


def test_policy_cannot_forge_trusted_score_output(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[2]
    fabricated = {
        "checks": {
            "diagnostic": {
                scenario.scenario_id: True
                for scenario in task.scenarios
                if scenario.metric == "diagnostic"
            },
            "neutral": {
                scenario.scenario_id: True
                for scenario in task.scenarios
                if scenario.metric == "neutral"
            },
            "objective": {
                scenario.scenario_id: True
                for scenario in task.scenarios
                if scenario.metric == "objective"
            },
        },
        "observed": {},
        "task_id": task.task_id,
    }
    source = f"import json, os\nprint(json.dumps({fabricated!r}))\nos._exit(0)\n"

    result = _score(task, _workspace(tmp_path, task, source))

    assert not any(_all_checks(result).values())
    receipts = result["receipts"]
    assert isinstance(receipts, dict)
    assert {receipt["status"] for receipt in receipts.values() if isinstance(receipt, dict)} == {
        "malformed_output"
    }


def test_validity_gate_detects_forbidden_path_defect() -> None:
    changes = parse_porcelain_v1_z(" M deployment_policy.py\0?? notes.md\0")

    assert unexpected_changed_paths(
        changes,
        frozenset({"deployment_policy.py"}),
    ) == ("notes.md",)


def test_runtime_fixture_manifests_bind_every_exact_rendered_clause() -> None:
    root = _root() / "runtime-fixture"
    measurements = json.loads((root / "MEASUREMENTS-v1.0.json").read_text(encoding="utf-8"))
    assert measurements["shared_execution_envelope_bytes"] == 362

    for expected, stage in zip((163, 371, 378), (1, 2, 3), strict=True):
        release = ExternalGovernedRelease.model_validate_json(
            (root / f"external-governed-release-stage-{stage}.json").read_bytes()
        )
        projection = CanonicalRuntimeProjection.model_validate_json(
            (root / f"canonical-runtime-projection-stage-{stage}.json").read_bytes()
        )
        rendered_text = (root / f"codex-runtime-stage-{stage}.md").read_text(encoding="utf-8")
        rendered = RenderedRuntimeProjection(
            content=rendered_text,
            content_digest=sha256_file(root / f"codex-runtime-stage-{stage}.md"),
            utf8_bytes=len(rendered_text.encode("utf-8")),
            clause_digests=tuple(item.content_digest for item in projection.clauses),
        )
        manifest = RuntimeProjectionManifest.model_validate_json(
            (root / f"clause-binding-manifest-stage-{stage}.json").read_bytes()
        )

        assert rendered == render_codex_runtime_projection(projection)
        assert rendered.utf8_bytes == expected
        assert (
            build_runtime_projection_manifest(
                release=release,
                projection=projection,
                rendered=rendered,
            )
            == manifest
        )


def test_preregistration_rejects_same_length_runtime_fixture_substitution(
    tmp_path: Path,
) -> None:
    copied_repo = tmp_path / "repo"
    copied = copied_repo / "development_benchmark_compact_projection"
    shutil.copytree(_root(), copied)
    scorer = copied_repo / "scripts" / "score_compact_projection_task.py"
    scorer.parent.mkdir(parents=True)
    shutil.copy2(_repo() / "scripts" / scorer.name, scorer)
    observer = copied_repo / "scripts" / "observe_compact_projection_policy.py"
    shutil.copy2(_repo() / "scripts" / observer.name, observer)
    sandbox = copied_repo / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py"
    sandbox.parent.mkdir(parents=True)
    shutil.copy2(
        _repo() / "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
        sandbox,
    )
    renderer = copied_repo / "src/adaptation_compiler_lab/targets/codex_runtime.py"
    renderer.parent.mkdir(parents=True)
    shutil.copy2(
        _repo() / "src/adaptation_compiler_lab/targets/codex_runtime.py",
        renderer,
    )
    runtime = copied / "runtime-fixture" / "codex-runtime-stage-1.md"
    original = runtime.read_text(encoding="utf-8")
    runtime.write_text(original.replace("recoverable", "forgettable"), encoding="utf-8")
    assert len(runtime.read_bytes()) == len(original.encode("utf-8"))

    with pytest.raises(ValueError, match="runtime fixture tree digest drifted"):
        load_compact_projection_design(copied)


def test_frozen_protocol_generator_cannot_refresh_existing_design() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.0.json").read_bytes(),
        (root / "PREREGISTRATION-v1.0.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "freeze_compact_projection_protocol.py"),
            "--repo",
            str(_repo()),
            "--benchmark-root",
            str(root),
        ],
        cwd=_repo(),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode != 0
    assert "already frozen" in completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.0.json").read_bytes(),
        (root / "PREREGISTRATION-v1.0.sha256").read_bytes(),
    )


def test_scorer_amendment_generator_cannot_replace_frozen_v1_1() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.1.json").read_bytes(),
        (root / "PREREGISTRATION-v1.1.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol.py"),
            "--repo",
            str(_repo()),
            "--benchmark-root",
            str(root),
        ],
        cwd=_repo(),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode != 0
    assert "already frozen" in completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.1.json").read_bytes(),
        (root / "PREREGISTRATION-v1.1.sha256").read_bytes(),
    )


def test_isolation_amendment_generator_cannot_replace_frozen_v1_2() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.2.json").read_bytes(),
        (root / "PREREGISTRATION-v1.2.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_2.py"),
            "--repo",
            str(_repo()),
            "--benchmark-root",
            str(root),
        ],
        cwd=_repo(),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode != 0
    assert "already frozen" in completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.2.json").read_bytes(),
        (root / "PREREGISTRATION-v1.2.sha256").read_bytes(),
    )
