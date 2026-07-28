from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from adaptation_compiler_lab.benchmark.compact_projection import CompactProjectionTask
from adaptation_compiler_lab.benchmark.semantic_remediation import (
    load_semantic_remediation_contract,
    load_semantic_remediation_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.runtime import (
    CanonicalRuntimeProjection,
    ExternalSemanticDecisionRelease,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.codex_runtime_v5 import (
    RenderedSemanticDecisionProjection,
    build_runtime_projection_manifest_v5,
    render_codex_runtime_projection_v5,
)


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_compact_projection"


def _reference(stage: int) -> str:
    preview = (
        'return ("deploy_payload",)' if stage == 1 else 'return ("compose_preview", "flip_preview")'
    )
    persistent = (
        'return ("capture_restore", "deploy_payload")'
        if stage < 3
        else (
            'return ("capture_restore", "deploy_payload") '
            'if recovery_copy_requested else ("decline_deploy",)'
        )
    )
    return (
        "def plan_transfer(\n"
        "    destination_exists: bool,\n"
        "    retention_class: str,\n"
        "    recovery_copy_requested: bool = False,\n"
        ") -> tuple[str, ...]:\n"
        '    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:\n'
        '        raise ValueError(f"unsupported retention class: {retention_class}")\n'
        "    if not destination_exists:\n"
        '        return ("seed_destination",)\n'
        '    if retention_class == "rebuildable_cache":\n'
        f"        {preview}\n"
        f"    {persistent}\n"
    )


def _workspace(tmp_path: Path, task: CompactProjectionTask, source: str) -> Path:
    workspace = tmp_path / task.task_id
    shutil.copytree(_root() / task.fixture_directory, workspace)
    (workspace / "src" / "transfer_policy.py").write_text(source, encoding="utf-8")
    return workspace


def _score(task: CompactProjectionTask, workspace: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts/score_compact_projection_task.py"),
            "--task-manifest",
            str((_root() / task.fixture_directory).parent / "task.json"),
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


def _checks(value: dict[str, object]) -> dict[str, bool]:
    groups = value["checks"]
    assert isinstance(groups, dict)
    return {
        name: passed
        for group in groups.values()
        if isinstance(group, dict)
        for name, passed in group.items()
        if isinstance(name, str) and isinstance(passed, bool)
    }


def test_semantic_runtime_manifests_and_size_gate_validate() -> None:
    runtime = _root() / "runtime-fixture-v2.3"
    profile = _root() / "condition-materials-v1.14"

    for stage in (1, 2, 3):
        release = ExternalSemanticDecisionRelease.model_validate_json(
            (runtime / f"external-semantic-decision-release-stage-{stage}.json").read_bytes()
        )
        projection = CanonicalRuntimeProjection.model_validate_json(
            (runtime / f"canonical-runtime-projection-stage-{stage}.json").read_bytes()
        )
        text = (runtime / f"codex-runtime-stage-{stage}.md").read_text(encoding="utf-8")
        rendered = RenderedSemanticDecisionProjection(
            content=text,
            content_digest=sha256_file(runtime / f"codex-runtime-stage-{stage}.md"),
            utf8_bytes=len(text.encode("utf-8")),
            clause_digests=tuple(item.content_digest for item in projection.clauses),
        )
        manifest = RuntimeProjectionManifest.model_validate_json(
            (runtime / f"clause-binding-manifest-stage-{stage}.json").read_bytes()
        )

        assert rendered == render_codex_runtime_projection_v5(projection)
        assert (
            build_runtime_projection_manifest_v5(
                release=release,
                projection=projection,
                rendered=rendered,
            )
            == manifest
        )
        assert rendered.utf8_bytes <= (profile / f"strong-profile-stage-{stage}.md").stat().st_size


def test_semantic_reference_passes_every_fresh_scenario(tmp_path: Path) -> None:
    design = load_semantic_remediation_design(_root())

    for task in design.tasks:
        result = _score(task, _workspace(tmp_path, task, _reference(task.stage)))
        assert all(_checks(result).values())


def test_semantic_visible_suites_execute_tests_in_every_fixture() -> None:
    design = load_semantic_remediation_design(_root())

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
        assert completed.returncode == 0, completed.stderr
        assert "Ran 2 tests" in completed.stderr


def test_semantic_scorer_detects_stale_scope_and_supersession_errors(
    tmp_path: Path,
) -> None:
    stage_1, stage_2, stage_3 = load_semantic_remediation_design(_root()).tasks

    stale_stage_1 = _checks(_score(stage_1, _workspace(tmp_path, stage_1, _reference(3))))
    assert not stale_stage_1["decision4-s1-diagnostic-retained-unrequested"]

    scope_leak = _reference(2).replace(
        'if retention_class == "rebuildable_cache":\n'
        '        return ("compose_preview", "flip_preview")\n'
        '    return ("capture_restore", "deploy_payload")',
        'return ("compose_preview", "flip_preview")',
    )
    leaked = _checks(_score(stage_2, _workspace(tmp_path, stage_2, scope_leak)))
    assert not leaked["decision4-s2-neutral-retained"]

    stale_stage_3 = _checks(_score(stage_3, _workspace(tmp_path, stage_3, _reference(2))))
    assert not stale_stage_3["decision4-s3-diagnostic-retained-unrequested"]


def test_semantic_design_and_execution_contract_are_frozen() -> None:
    design = load_semantic_remediation_design(_root())
    contract = load_semantic_remediation_contract(_root(), design=design)
    checksum = (
        (_root() / "SEMANTIC_REMEDIATION_PREREGISTRATION-v1.sha256")
        .read_text(encoding="ascii")
        .split()[0]
    )

    assert (
        sha256_file(_root() / "SEMANTIC_REMEDIATION_PREREGISTRATION-v1.json")
        == f"sha256:{checksum}"
    )
    assert design.renderer_version == "3.0.0"
    assert design.prior_target_sessions_completed == 9
    assert design.planned_target_sessions == 3
    assert design.cumulative_target_session_ceiling == 12
    assert not design.comparative_claims_allowed
    assert contract.target_sessions == 3
    assert contract.model == "gpt-5.6-luna"
    assert contract.authentication == "saved_chatgpt"
    assert contract.target_orchestrator_source_digest == sha256_file(
        _repo() / "scripts/run_semantic_remediation_gate.py"
    )
    assert not design.target_sessions_started
    assert not design.sealed_external_validation_accessed


def test_semantic_tasks_are_natural_and_do_not_disclose_expected_actions() -> None:
    design = load_semantic_remediation_design(_root())

    forbidden = {
        "capture_restore",
        "compose_preview",
        "decline_deploy",
        "compiled",
        "static profile",
    }
    for task in design.tasks:
        prompt = task.task_prompt.casefold()
        assert all(item not in prompt for item in forbidden)
