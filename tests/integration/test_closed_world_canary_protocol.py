from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from adaptation_compiler_lab.benchmark.closed_world_canary import (
    load_closed_world_canary_contract,
    load_closed_world_canary_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.runtime import (
    CanonicalRuntimeProjection,
    ExternalSemanticDecisionRelease,
    RuntimeProjectionManifest,
)
from adaptation_compiler_lab.targets.codex_runtime_v6 import (
    RenderedClosedWorldDecisionProjection,
    build_runtime_projection_manifest_v6,
    render_codex_runtime_projection_v6,
)


def _repo() -> Path:
    return Path(__file__).parents[2]


def _root() -> Path:
    return _repo() / "development_benchmark_compact_projection"


def _reference() -> str:
    return (
        "def plan_transfer(\n"
        "    destination_exists: bool,\n"
        "    retention_class: str,\n"
        "    recovery_copy_requested: bool = False,\n"
        ") -> tuple[str, ...]:\n"
        '    if retention_class not in {"retained_user_tree", "rebuildable_cache"}:\n'
        '        raise ValueError(f"unsupported retention class: {retention_class}")\n'
        "    if not destination_exists:\n"
        '        return ("initialize_site",)\n'
        '    if retention_class == "retained_user_tree":\n'
        '        return ("save_checkpoint", "publish_release")\n'
        '    return ("publish_release",)\n'
    )


def _workspace(tmp_path: Path, source: str) -> Path:
    task = load_closed_world_canary_design(_root()).task
    workspace = tmp_path / task.task_id
    shutil.copytree(_root() / task.fixture_directory, workspace)
    (workspace / "src/transfer_policy.py").write_text(source, encoding="utf-8")
    return workspace


def _score(workspace: Path) -> dict[str, object]:
    task = load_closed_world_canary_design(_root()).task
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


def test_closed_world_runtime_manifests_and_size_gate_validate() -> None:
    runtime = _root() / "runtime-fixture-v2.4"
    profile = _root() / "condition-materials-v1.14"

    for stage in (1, 2, 3):
        release = ExternalSemanticDecisionRelease.model_validate_json(
            (runtime / f"external-semantic-decision-release-stage-{stage}.json").read_bytes()
        )
        projection = CanonicalRuntimeProjection.model_validate_json(
            (runtime / f"canonical-runtime-projection-stage-{stage}.json").read_bytes()
        )
        text = (runtime / f"codex-runtime-stage-{stage}.md").read_text(encoding="utf-8")
        rendered = RenderedClosedWorldDecisionProjection(
            content=text,
            content_digest=sha256_file(runtime / f"codex-runtime-stage-{stage}.md"),
            utf8_bytes=len(text.encode("utf-8")),
            clause_digests=tuple(item.content_digest for item in projection.clauses),
        )
        manifest = RuntimeProjectionManifest.model_validate_json(
            (runtime / f"clause-binding-manifest-stage-{stage}.json").read_bytes()
        )

        assert rendered == render_codex_runtime_projection_v6(projection)
        assert (
            build_runtime_projection_manifest_v6(
                release=release,
                projection=projection,
                rendered=rendered,
            )
            == manifest
        )
        assert rendered.utf8_bytes <= (profile / f"strong-profile-stage-{stage}.md").stat().st_size


def test_closed_world_reference_passes_every_fresh_scenario(tmp_path: Path) -> None:
    assert all(_checks(_score(_workspace(tmp_path, _reference()))).values())


def test_closed_world_scorer_detects_the_exact_prior_failure(tmp_path: Path) -> None:
    prior_failure = _reference().replace(
        'if retention_class == "retained_user_tree":\n'
        '        return ("save_checkpoint", "publish_release")\n'
        '    return ("publish_release",)',
        'if retention_class == "rebuildable_cache":\n'
        '        return ("build_preview", "switch_preview")\n'
        "    if recovery_copy_requested:\n"
        '        return ("save_checkpoint", "publish_release")\n'
        '    return ("block_publish",)',
    )

    checks = _checks(_score(_workspace(tmp_path, prior_failure)))

    assert not checks["decision5-s1-diagnostic-persistent-unrequested"]
    assert not checks["decision5-s1-neutral-preview"]


def test_closed_world_visible_suite_executes_two_tests() -> None:
    task = load_closed_world_canary_design(_root()).task
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


def test_closed_world_design_and_contract_are_frozen() -> None:
    design = load_closed_world_canary_design(_root())
    contract = load_closed_world_canary_contract(_root(), design=design)
    checksum = (
        (_root() / "CLOSED_WORLD_CANARY_PREREGISTRATION-v1.sha256")
        .read_text(encoding="ascii")
        .split()[0]
    )

    assert (
        sha256_file(_root() / "CLOSED_WORLD_CANARY_PREREGISTRATION-v1.json") == f"sha256:{checksum}"
    )
    assert design.renderer_version == "3.1.0"
    assert design.prior_study_target_sessions == 12
    assert design.planned_target_sessions == 1
    assert not design.retries_allowed
    assert not design.comparative_claims_allowed
    assert contract.target_sessions == 1
    assert contract.model == "gpt-5.6-luna"
    assert contract.target_orchestrator_source_digest == sha256_file(
        _repo() / "scripts/run_closed_world_canary.py"
    )
