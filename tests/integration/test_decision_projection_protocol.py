from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from adaptation_compiler_lab.benchmark.compact_execution import (
    load_compact_execution_contract,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionTask,
    load_compact_projection_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.runtime import (
    CanonicalRuntimeProjection,
    ExternalDecisionRelease,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.codex_runtime_v3 import (
    RenderedDecisionProjection,
    build_runtime_projection_manifest_v3,
    render_codex_runtime_projection_v3,
)
from adaptation_compiler_lab.targets.codex_runtime_v4 import (
    RenderedDecisionTableProjection,
    build_runtime_projection_manifest_v4,
    render_codex_runtime_projection_v4,
)
from scripts import run_compact_projection_comparison as comparison
from scripts import run_durable_progress_comparison as durable_comparison


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_compact_projection"


def _reference(stage: int) -> str:
    cache = 'return ("publish_tree",)' if stage == 1 else 'return ("stage_tree", "swap_target")'
    retained = (
        'return ("snapshot_target", "publish_tree")'
        if stage < 3
        else (
            'return ("snapshot_target", "publish_tree") '
            'if recovery_copy_requested else ("refuse_publish",)'
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
        '        return ("create_target",)\n'
        '    if retention_class == "rebuildable_cache":\n'
        f"        {cache}\n"
        f"    {retained}\n"
    )


def _workspace(tmp_path: Path, task: CompactProjectionTask, source: str) -> Path:
    workspace = tmp_path / task.task_id
    shutil.copytree(_root() / task.fixture_directory, workspace)
    (workspace / "src" / "transfer_policy.py").write_text(source, encoding="utf-8")
    return workspace


def _reference_v21(stage: int) -> str:
    preview = (
        'return ("install_tree",)' if stage == 1 else 'return ("prepare_tree", "promote_tree")'
    )
    retained = (
        'return ("save_restore_point", "install_tree")'
        if stage < 3
        else (
            'return ("save_restore_point", "install_tree") '
            'if recovery_copy_requested else ("deny_promotion",)'
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
        '        return ("init_target",)\n'
        '    if retention_class == "rebuildable_cache":\n'
        f"        {preview}\n"
        f"    {retained}\n"
    )


def _reference_v22(stage: int) -> str:
    preview = (
        'return ("apply_payload",)'
        if stage == 1
        else 'return ("assemble_preview", "activate_preview")'
    )
    retained = (
        'return ("record_rollback", "apply_payload")'
        if stage < 3
        else (
            'return ("record_rollback", "apply_payload") '
            'if recovery_copy_requested else ("reject_apply",)'
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
        '        return ("open_target",)\n'
        '    if retention_class == "rebuildable_cache":\n'
        f"        {preview}\n"
        f"    {retained}\n"
    )


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


def test_v2_design_contract_and_fresh_materials_are_frozen() -> None:
    design = load_compact_projection_design(_root(), version="2.0")
    contract = load_compact_execution_contract(_root(), design=design)
    checksum = (_root() / "PREREGISTRATION-v2.0.sha256").read_text(encoding="ascii").split()[0]

    assert sha256_file(_root() / "PREREGISTRATION-v2.0.json") == f"sha256:{checksum}"
    assert design.design_version == "2.0.0"
    assert design.amendment_reason == "typed_decision_projection_and_fresh_tasks"
    assert design.renderer_id == "codex-decision-runtime"
    assert design.renderer_version == "2.0.0"
    assert contract.contract_version == "1.8.0"
    assert design.maximum_subscription_sessions == 8
    assert design.instrument_smoke_sessions == 1
    assert not design.target_sessions_started
    assert not design.judge_sessions_started
    assert not design.sealed_external_validation_accessed


def test_v2_decision_manifests_and_size_gate_validate() -> None:
    root = _root() / "runtime-fixture-v2.0"
    profile_root = _root() / "condition-materials-v1.14"

    for stage in (1, 2, 3):
        release = ExternalDecisionRelease.model_validate_json(
            (root / f"external-decision-release-stage-{stage}.json").read_bytes()
        )
        projection = CanonicalRuntimeProjection.model_validate_json(
            (root / f"canonical-runtime-projection-stage-{stage}.json").read_bytes()
        )
        rendered_text = (root / f"codex-runtime-stage-{stage}.md").read_text(encoding="utf-8")
        rendered = RenderedDecisionProjection(
            content=rendered_text,
            content_digest=sha256_file(root / f"codex-runtime-stage-{stage}.md"),
            utf8_bytes=len(rendered_text.encode("utf-8")),
            clause_digests=tuple(item.content_digest for item in projection.clauses),
        )
        manifest = RuntimeProjectionManifest.model_validate_json(
            (root / f"clause-binding-manifest-stage-{stage}.json").read_bytes()
        )

        assert rendered == render_codex_runtime_projection_v3(projection)
        assert (
            build_runtime_projection_manifest_v3(
                release=release,
                projection=projection,
                rendered=rendered,
            )
            == manifest
        )
        assert (
            rendered.utf8_bytes
            <= (profile_root / f"strong-profile-stage-{stage}.md").stat().st_size
        )


def test_v2_reference_passes_every_frozen_scenario(tmp_path: Path) -> None:
    design = load_compact_projection_design(_root(), version="2.0")

    for task in design.tasks:
        result = _score(task, _workspace(tmp_path, task, _reference(task.stage)))
        assert all(_checks(result).values())


def test_v2_scorer_detects_missed_branch_scope_leak_and_stale_rule(
    tmp_path: Path,
) -> None:
    design = load_compact_projection_design(_root(), version="2.0")
    stage_1, stage_2, stage_3 = design.tasks

    missed = _checks(_score(stage_1, _workspace(tmp_path, stage_1, _reference(3))))
    assert not missed["decision-s1-diagnostic-retained-unrequested"]

    leaked_source = _reference(2).replace(
        'if retention_class == "rebuildable_cache":\n'
        '        return ("stage_tree", "swap_target")\n'
        '    return ("snapshot_target", "publish_tree")',
        'return ("stage_tree", "swap_target")',
    )
    leaked = _checks(_score(stage_2, _workspace(tmp_path, stage_2, leaked_source)))
    assert not leaked["decision-s2-neutral-retained"]

    stale = _checks(_score(stage_3, _workspace(tmp_path, stage_3, _reference(2))))
    assert not stale["decision-s3-diagnostic-retained-unrequested"]


def test_command_audit_distinguishes_virtual_workspace_from_host_paths() -> None:
    def result(command: str) -> Any:
        return SimpleNamespace(
            events=(
                {
                    "item": {
                        "command": command,
                        "type": "command_execution",
                    }
                },
            )
        )

    assert comparison._command_audit(result("find /workspace -maxdepth 3 -type f"))[1] == ()
    assert comparison._command_audit(result("find / -maxdepth 3 -type f"))[1] == (
        "host or parent path access",
    )
    assert comparison._command_audit(result("cat /home/user/.config"))[1] == (
        "host or parent path access",
    )
    assert comparison._command_audit(result("find /workspace/.codex -type f"))[1] == (
        "ephemeral control surface inspection",
    )


def test_v21_reference_passes_every_fresh_scenario(tmp_path: Path) -> None:
    design = load_compact_projection_design(_root(), version="2.1")

    for task in design.tasks:
        result = _score(task, _workspace(tmp_path, task, _reference_v21(task.stage)))
        assert all(_checks(result).values())


def test_v21_design_and_bound_execution_contract_are_frozen() -> None:
    design = load_compact_projection_design(_root(), version="2.1")
    contract = load_compact_execution_contract(_root(), design=design)
    checksum = (_root() / "PREREGISTRATION-v2.1.sha256").read_text(encoding="ascii").split()[0]

    assert sha256_file(_root() / "PREREGISTRATION-v2.1.json") == f"sha256:{checksum}"
    assert design.design_version == "2.1.0"
    assert design.amendment_reason == "complete_decision_table_and_path_audit_fix"
    assert design.renderer_id == "codex-decision-table-runtime"
    assert design.renderer_version == "2.1.0"
    assert contract.contract_version == "1.9.0"
    assert contract.target_orchestrator_source_digest == sha256_file(
        _repo() / "scripts/run_compact_projection_comparison.py"
    )
    assert design.maximum_subscription_sessions == 8
    assert design.instrument_smoke_sessions == 1
    assert not design.target_sessions_started
    assert not design.judge_sessions_started
    assert not design.sealed_external_validation_accessed


def test_v21_complete_manifests_and_size_gate_validate() -> None:
    root = _root() / "runtime-fixture-v2.1"
    profile_root = _root() / "condition-materials-v1.14"

    for stage in (1, 2, 3):
        release = ExternalDecisionRelease.model_validate_json(
            (root / f"external-decision-release-stage-{stage}.json").read_bytes()
        )
        projection = CanonicalRuntimeProjection.model_validate_json(
            (root / f"canonical-runtime-projection-stage-{stage}.json").read_bytes()
        )
        rendered_text = (root / f"codex-runtime-stage-{stage}.md").read_text(encoding="utf-8")
        rendered = RenderedDecisionTableProjection(
            content=rendered_text,
            content_digest=sha256_file(root / f"codex-runtime-stage-{stage}.md"),
            utf8_bytes=len(rendered_text.encode("utf-8")),
            clause_digests=tuple(item.content_digest for item in projection.clauses),
        )
        manifest = RuntimeProjectionManifest.model_validate_json(
            (root / f"clause-binding-manifest-stage-{stage}.json").read_bytes()
        )

        assert rendered == render_codex_runtime_projection_v4(projection)
        assert (
            build_runtime_projection_manifest_v4(
                release=release,
                projection=projection,
                rendered=rendered,
            )
            == manifest
        )
        assert (
            rendered.utf8_bytes
            <= (profile_root / f"strong-profile-stage-{stage}.md").stat().st_size
        )


def test_v21_scorer_detects_stale_scope_and_supersession_errors(tmp_path: Path) -> None:
    design = load_compact_projection_design(_root(), version="2.1")
    stage_1, stage_2, stage_3 = design.tasks

    stale_stage_1 = _checks(_score(stage_1, _workspace(tmp_path, stage_1, _reference_v21(3))))
    assert not stale_stage_1["decision2-s1-diagnostic-retained-unrequested"]

    scope_leak = _reference_v21(2).replace(
        'if retention_class == "rebuildable_cache":\n'
        '        return ("prepare_tree", "promote_tree")\n'
        '    return ("save_restore_point", "install_tree")',
        'return ("prepare_tree", "promote_tree")',
    )
    leaked = _checks(_score(stage_2, _workspace(tmp_path, stage_2, scope_leak)))
    assert not leaked["decision2-s2-neutral-retained"]

    stale_stage_3 = _checks(_score(stage_3, _workspace(tmp_path, stage_3, _reference_v21(2))))
    assert not stale_stage_3["decision2-s3-diagnostic-retained-unrequested"]


def test_v22_reference_passes_every_fresh_scenario(tmp_path: Path) -> None:
    design = load_compact_projection_design(_root(), version="2.2")

    for task in design.tasks:
        result = _score(task, _workspace(tmp_path, task, _reference_v22(task.stage)))
        assert all(_checks(result).values())


def test_v22_design_and_durable_execution_contract_are_frozen() -> None:
    design = load_compact_projection_design(_root(), version="2.2")
    contract = load_compact_execution_contract(_root(), design=design)
    checksum = (_root() / "PREREGISTRATION-v2.2.sha256").read_text(encoding="ascii").split()[0]

    assert sha256_file(_root() / "PREREGISTRATION-v2.2.json") == f"sha256:{checksum}"
    assert design.design_version == "2.2.0"
    assert design.amendment_reason == "broken_pipe_resilience_and_fresh_tasks"
    assert design.maximum_subscription_sessions == 7
    assert design.instrument_smoke_sessions is None
    assert contract.contract_version == "1.10.0"
    assert contract.target_orchestrator_source_digest == sha256_file(
        _repo() / "scripts/run_durable_progress_comparison.py"
    )
    assert contract.inherited_smoke_receipt_digest == sha256_file(
        _root() / "INSTRUMENT_SMOKE-v2.1.json"
    )
    assert not design.target_sessions_started
    assert not design.judge_sessions_started
    assert not design.sealed_external_validation_accessed


def test_v22_scorer_detects_stale_scope_and_supersession_errors(tmp_path: Path) -> None:
    design = load_compact_projection_design(_root(), version="2.2")
    stage_1, stage_2, stage_3 = design.tasks

    stale_stage_1 = _checks(_score(stage_1, _workspace(tmp_path, stage_1, _reference_v22(3))))
    assert not stale_stage_1["decision3-s1-diagnostic-retained-unrequested"]

    scope_leak = _reference_v22(2).replace(
        'if retention_class == "rebuildable_cache":\n'
        '        return ("assemble_preview", "activate_preview")\n'
        '    return ("record_rollback", "apply_payload")',
        'return ("assemble_preview", "activate_preview")',
    )
    leaked = _checks(_score(stage_2, _workspace(tmp_path, stage_2, scope_leak)))
    assert not leaked["decision3-s2-neutral-retained"]

    stale_stage_3 = _checks(_score(stage_3, _workspace(tmp_path, stage_3, _reference_v22(2))))
    assert not stale_stage_3["decision3-s3-diagnostic-retained-unrequested"]


def test_progress_output_cannot_abort_execution(monkeypatch: Any) -> None:
    def closed_stream(*_args: object, **_kwargs: object) -> None:
        raise BrokenPipeError

    monkeypatch.setattr("builtins.print", closed_stream)
    durable_comparison._progress("diagnostic only")
