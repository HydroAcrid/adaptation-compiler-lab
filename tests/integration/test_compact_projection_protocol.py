from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.compact_execution import (
    load_compact_execution_contract,
)
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
)
from adaptation_compiler_lab.targets.codex_runtime_v2 import (
    build_runtime_projection_manifest_v2,
    render_codex_runtime_projection_v2,
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
        'return ("replace_target",)'
        if stage == 1
        else 'return ("write_temporary_tree", "atomically_replace_target")'
    )
    retained = (
        'return ("make_recovery_copy", "replace_target")'
        if stage < 3
        else (
            'return ("make_recovery_copy", "replace_target") '
            'if recovery_copy_requested else ("refuse_transfer",)'
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


def test_fresh_protocol_is_hash_frozen_and_unexecuted() -> None:
    root = _root()
    design = load_compact_projection_design(root)
    expected = (root / "PREREGISTRATION-v1.18.sha256").read_text(encoding="ascii").split()[0]

    assert sha256_file(root / "PREREGISTRATION-v1.18.json") == f"sha256:{expected}"
    assert design.design_version == "1.18.0"
    assert design.amendment_reason == "ephemeral_unified_exec_workspace_mount"
    assert design.prior_failed_profile_receipt_digest
    assert design.prior_failed_target_receipt_digest
    assert design.prior_failed_smoke_receipt_digest
    assert design.supersedes_design_digest
    assert design.superseded_scorer_digest
    assert design.policy_observer_digest
    assert design.scorer_sandbox_digest
    assert design.planned_target_sessions == 6
    assert design.maximum_subscription_sessions == 8
    assert design.profile_author_sessions == 0
    assert design.profile_review_sessions == 0
    assert design.instrument_smoke_sessions == 1
    assert not design.target_sessions_started
    assert not design.profile_sessions_started
    assert not design.judge_sessions_started
    assert design.provider_billed_calls == 0
    assert not design.api_keys_allowed
    assert not design.sealed_external_validation_accessed


def test_shared_envelope_path_matches_every_registered_task() -> None:
    root = _root()
    design = load_compact_projection_design(root)
    envelope = (root / "runtime-fixture-v1.12" / "shared-execution-envelope.md").read_text(
        encoding="utf-8"
    )

    assert "Allowed paths: src/transfer_policy.py." in envelope
    assert "Allowed paths: policy.py." not in envelope
    assert {path for task in design.tasks for path in task.allowed_change_paths} == {
        "src/transfer_policy.py"
    }


def test_execution_contract_freezes_luna_and_eight_subscription_sessions() -> None:
    root = _root()
    design = load_compact_projection_design(root)
    contract = load_compact_execution_contract(root, design=design)

    assert contract.model == "gpt-5.6-luna"
    assert contract.reasoning_effort == "medium"
    assert contract.authentication == "saved_chatgpt"
    assert contract.maximum_subscription_sessions == 8
    assert contract.profile_author_sessions == 0
    assert contract.profile_review_sessions == 0
    assert contract.instrument_smoke_sessions == 1
    assert contract.target_sessions == 6
    assert contract.judge_sessions == 1
    assert contract.target_outer_sandbox_digest == contract.role_outer_sandbox_digest
    assert contract.target_runner_source_digest
    assert contract.instrument_smoke_source_digest
    assert contract.inherited_profile_receipt_digest
    assert contract.target_workspace_policy == "workspace-read-only-except-registered-source-file"
    assert not contract.api_keys_allowed


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

    assert not checks["compact-v2-s3-diagnostic-retained-unrequested"]


def test_scorer_detects_missed_exception(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[1]
    source = _reference(1)

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-v2-s2-diagnostic-cache-unrequested"]


def test_scorer_detects_scope_leak(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[1]
    source = _reference(2).replace(
        'if retention_class == "rebuildable_cache":\n'
        '        return ("write_temporary_tree", "atomically_replace_target")\n'
        '    return ("make_recovery_copy", "replace_target")',
        'return ("write_temporary_tree", "atomically_replace_target")',
    )

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-v2-s2-neutral-retained"]


def test_scorer_detects_unnecessary_change(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[0]
    source = _reference(1).replace(
        'return ("create_target",)',
        'return ("refuse_transfer",)',
        1,
    )

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-v2-s1-objective-new-retained"]


@pytest.mark.parametrize(
    "replacement",
    (
        '"refuse_transfer"',
        '["refuse_transfer"]',
    ),
)
def test_scorer_rejects_non_tuple_return_contract(
    tmp_path: Path,
    replacement: str,
) -> None:
    task = load_compact_projection_design(_root()).tasks[2]
    source = _reference(3).replace('else ("refuse_transfer",)', f"else {replacement}")

    checks = _all_checks(_score(task, _workspace(tmp_path, task, source)))

    assert not checks["compact-v2-s3-diagnostic-retained-unrequested"]


def test_policy_cannot_forge_worker_observation_output(tmp_path: Path) -> None:
    task = load_compact_projection_design(_root()).tasks[2]
    fabricated = {
        "detail": None,
        "status": "returned",
        "value": ["refuse_transfer"],
        "worker_version": "1.0.0",
    }
    source = f"import json, os\nprint(json.dumps({fabricated!r}))\nos._exit(0)\n"

    result = _score(task, _workspace(tmp_path, task, source))

    assert not any(_all_checks(result).values())
    receipts = result["receipts"]
    assert isinstance(receipts, dict)
    assert {receipt["status"] for receipt in receipts.values() if isinstance(receipt, dict)} == {
        "succeeded"
    }


def test_validity_gate_detects_forbidden_path_defect() -> None:
    changes = parse_porcelain_v1_z(" M deployment_policy.py\0?? notes.md\0")

    assert unexpected_changed_paths(
        changes,
        frozenset({"deployment_policy.py"}),
    ) == ("notes.md",)


def test_runtime_fixture_manifests_bind_every_exact_rendered_clause() -> None:
    root = _root() / "runtime-fixture-v1.12"
    measurements = json.loads((root / "MEASUREMENTS-v1.1.json").read_text(encoding="utf-8"))
    assert measurements["shared_execution_envelope_bytes"] == 375

    for expected, stage in zip((163, 297, 304), (1, 2, 3), strict=True):
        release = ExternalGovernedRelease.model_validate_json(
            (root / f"external-governed-release-stage-{stage}.json").read_bytes()
        )
        projection = CanonicalRuntimeProjection.model_validate_json(
            (root / f"canonical-runtime-projection-stage-{stage}.json").read_bytes()
        )
        rendered_text = (root / f"codex-runtime-stage-{stage}.md").read_text(encoding="utf-8")
        rendered = RenderedRuntimeProjection(
            renderer_version="1.1.0",
            content=rendered_text,
            content_digest=sha256_file(root / f"codex-runtime-stage-{stage}.md"),
            utf8_bytes=len(rendered_text.encode("utf-8")),
            clause_digests=tuple(item.content_digest for item in projection.clauses),
        )
        manifest = RuntimeProjectionManifest.model_validate_json(
            (root / f"clause-binding-manifest-stage-{stage}.json").read_bytes()
        )

        assert rendered == render_codex_runtime_projection_v2(projection)
        assert rendered.utf8_bytes == expected
        assert (
            build_runtime_projection_manifest_v2(
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
    renderer = copied_repo / "src/adaptation_compiler_lab/targets/codex_runtime_v2.py"
    renderer.parent.mkdir(parents=True)
    shutil.copy2(
        _repo() / "src/adaptation_compiler_lab/targets/codex_runtime_v2.py",
        renderer,
    )
    runtime = copied / "runtime-fixture-v1.12" / "codex-runtime-stage-1.md"
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
    assert completed.stderr
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
    assert completed.stderr
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
    assert completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.2.json").read_bytes(),
        (root / "PREREGISTRATION-v1.2.sha256").read_bytes(),
    )


def test_preexec_amendment_generator_cannot_replace_frozen_v1_3() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.3.json").read_bytes(),
        (root / "PREREGISTRATION-v1.3.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_3.py"),
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
    assert completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.3.json").read_bytes(),
        (root / "PREREGISTRATION-v1.3.sha256").read_bytes(),
    )


def test_trusted_observation_amendment_generator_cannot_replace_frozen_v1_4() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.4.json").read_bytes(),
        (root / "PREREGISTRATION-v1.4.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_4.py"),
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
        (root / "PREREGISTRATION-v1.4.json").read_bytes(),
        (root / "PREREGISTRATION-v1.4.sha256").read_bytes(),
    )


def test_restricted_policy_amendment_generator_cannot_replace_frozen_v1_5() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.5.json").read_bytes(),
        (root / "PREREGISTRATION-v1.5.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_5.py"),
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
        (root / "PREREGISTRATION-v1.5.json").read_bytes(),
        (root / "PREREGISTRATION-v1.5.sha256").read_bytes(),
    )


def test_observer_format_amendment_generator_cannot_replace_frozen_v1_6() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.6.json").read_bytes(),
        (root / "PREREGISTRATION-v1.6.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_6.py"),
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
        (root / "PREREGISTRATION-v1.6.json").read_bytes(),
        (root / "PREREGISTRATION-v1.6.sha256").read_bytes(),
    )


def test_codex_target_amendment_generator_cannot_replace_frozen_v1_7() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.7.json").read_bytes(),
        (root / "PREREGISTRATION-v1.7.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_7.py"),
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
    assert completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.7.json").read_bytes(),
        (root / "PREREGISTRATION-v1.7.sha256").read_bytes(),
    )


def test_path_validation_amendment_generator_cannot_replace_frozen_v1_8() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.8.json").read_bytes(),
        (root / "PREREGISTRATION-v1.8.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_8.py"),
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
    assert completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.8.json").read_bytes(),
        (root / "PREREGISTRATION-v1.8.sha256").read_bytes(),
    )


def test_schema_alignment_amendment_generator_cannot_replace_frozen_v1_9() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.9.json").read_bytes(),
        (root / "PREREGISTRATION-v1.9.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_9.py"),
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
    assert completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.9.json").read_bytes(),
        (root / "PREREGISTRATION-v1.9.sha256").read_bytes(),
    )


def test_lifecycle_envelope_amendment_generator_cannot_replace_frozen_v1_10() -> None:
    root = _root()
    before = (
        (root / "PREREGISTRATION-v1.10.json").read_bytes(),
        (root / "PREREGISTRATION-v1.10.sha256").read_bytes(),
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_10.py"),
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
    assert completed.stderr
    assert before == (
        (root / "PREREGISTRATION-v1.10.json").read_bytes(),
        (root / "PREREGISTRATION-v1.10.sha256").read_bytes(),
    )


def test_lifecycle_envelope_amendment_rejects_drifted_unchanged_fixture(
    tmp_path: Path,
) -> None:
    copied_repo = tmp_path / "repo"
    copied = copied_repo / "development_benchmark_compact_projection"
    shutil.copytree(_root(), copied)
    for relative in (
        "scripts/score_compact_projection_task.py",
        "scripts/observe_compact_projection_policy.py",
        "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
        "src/adaptation_compiler_lab/targets/codex_runtime.py",
    ):
        destination = copied_repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_repo() / relative, destination)
    (copied / "PREREGISTRATION-v1.10.json").unlink()
    (copied / "PREREGISTRATION-v1.10.sha256").unlink()
    envelope = copied / "runtime-fixture-v1.5" / "shared-execution-envelope.md"
    envelope.write_text(
        envelope.read_text(encoding="utf-8").replace("Allowed paths", "Permitted paths"),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_10.py"),
            "--repo",
            str(copied_repo),
            "--benchmark-root",
            str(copied),
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
    assert "drifted since v1.9" in completed.stderr
    assert not (copied / "PREREGISTRATION-v1.10.json").exists()
    assert not (copied / "PREREGISTRATION-v1.10.sha256").exists()


def test_schema_alignment_amendment_rejects_drifted_unchanged_fixture(
    tmp_path: Path,
) -> None:
    copied_repo = tmp_path / "repo"
    copied = copied_repo / "development_benchmark_compact_projection"
    shutil.copytree(_root(), copied)
    for relative in (
        "scripts/score_compact_projection_task.py",
        "scripts/observe_compact_projection_policy.py",
        "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
        "src/adaptation_compiler_lab/targets/codex_runtime.py",
    ):
        destination = copied_repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_repo() / relative, destination)
    (copied / "PREREGISTRATION-v1.9.json").unlink()
    (copied / "PREREGISTRATION-v1.9.sha256").unlink()
    runtime = copied / "runtime-fixture-v1.5" / "codex-runtime-stage-1.md"
    runtime.write_text(
        runtime.read_text(encoding="utf-8").replace("recoverable", "forgettable"),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_9.py"),
            "--repo",
            str(copied_repo),
            "--benchmark-root",
            str(copied),
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
    assert "drifted since v1.8" in completed.stderr
    assert not (copied / "PREREGISTRATION-v1.9.json").exists()
    assert not (copied / "PREREGISTRATION-v1.9.sha256").exists()


def test_path_validation_amendment_rejects_drifted_unchanged_fixture(
    tmp_path: Path,
) -> None:
    copied_repo = tmp_path / "repo"
    copied = copied_repo / "development_benchmark_compact_projection"
    shutil.copytree(_root(), copied)
    for relative in (
        "scripts/score_compact_projection_task.py",
        "scripts/observe_compact_projection_policy.py",
        "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
        "src/adaptation_compiler_lab/targets/codex_runtime.py",
    ):
        destination = copied_repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_repo() / relative, destination)
    (copied / "PREREGISTRATION-v1.8.json").unlink()
    (copied / "PREREGISTRATION-v1.8.sha256").unlink()
    envelope = copied / "runtime-fixture-v1.5" / "shared-execution-envelope.md"
    envelope.write_text(
        envelope.read_text(encoding="utf-8").replace("Allowed paths", "Permitted paths"),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_8.py"),
            "--repo",
            str(copied_repo),
            "--benchmark-root",
            str(copied),
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
    assert "drifted since v1.7" in completed.stderr
    assert not (copied / "PREREGISTRATION-v1.8.json").exists()
    assert not (copied / "PREREGISTRATION-v1.8.sha256").exists()


def test_codex_target_amendment_rejects_drifted_unchanged_fixture(
    tmp_path: Path,
) -> None:
    copied_repo = tmp_path / "repo"
    copied = copied_repo / "development_benchmark_compact_projection"
    shutil.copytree(_root(), copied)
    for relative in (
        "scripts/score_compact_projection_task.py",
        "scripts/observe_compact_projection_policy.py",
        "src/adaptation_compiler_lab/benchmark/longitudinal_instrument.py",
        "src/adaptation_compiler_lab/targets/codex_runtime.py",
    ):
        destination = copied_repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_repo() / relative, destination)
    (copied / "PREREGISTRATION-v1.7.json").unlink()
    (copied / "PREREGISTRATION-v1.7.sha256").unlink()
    runtime = copied / "runtime-fixture-v1.5" / "codex-runtime-stage-1.md"
    runtime.write_text(
        runtime.read_text(encoding="utf-8").replace("recoverable", "forgettable"),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_repo() / "scripts" / "supersede_compact_projection_protocol_v1_7.py"),
            "--repo",
            str(copied_repo),
            "--benchmark-root",
            str(copied),
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
    assert "drifted since v1.6" in completed.stderr
    assert not (copied / "PREREGISTRATION-v1.7.json").exists()
    assert not (copied / "PREREGISTRATION-v1.7.sha256").exists()
