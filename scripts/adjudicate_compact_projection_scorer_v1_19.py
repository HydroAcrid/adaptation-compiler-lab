"""Blindly rescore the immutable v1.19 patches after the trusted PATH failure."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.benchmark.compact_execution import (
    CompactProjectionBlindReport,
    load_compact_execution_contract,
)
from adaptation_compiler_lab.benchmark.compact_projection import (
    CompactProjectionTask,
    load_compact_projection_design,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.persistence.raw import (
    LocalRawPayloadStore,
    RawEncryptionKey,
    RawPayloadRef,
)
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

_TRUSTED_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
_MEDIA_TYPE = "application/vnd.adaptation-compiler-lab.compact-target-run+json"


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _environment(*, home: Path, repo_source: Path | None = None) -> dict[str, str]:
    value = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": _TRUSTED_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if repo_source is not None:
        value["PYTHONPATH"] = str(repo_source)
    return value


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 30,
    stdin: str | None = None,
    repo_source: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=stdin,
        env=_environment(home=cwd, repo_source=repo_source),
        timeout=timeout,
    )


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} is not a JSON object")
    return value


def _raw_reference(root: Path, digest: str) -> RawPayloadRef:
    path = root / "sha256" / digest[:2] / digest
    envelope = json.loads(path.read_bytes().split(b"\n", 1)[1])
    size = envelope.get("plaintext_size")
    if not isinstance(size, int) or size < 1:
        raise RuntimeError("encrypted target trace has invalid size metadata")
    return RawPayloadRef(
        sha256=digest,
        size_bytes=size,
        media_type=_MEDIA_TYPE,
        relative_path=f"sha256/{digest[:2]}/{digest}",
    )


def _progress_by_run(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if not isinstance(item, dict):
            raise RuntimeError("target progress entry is not an object")
        run_id = item.get("run_id")
        digest = item.get("raw_trace_ref_digest")
        if (
            not isinstance(run_id, str)
            or not isinstance(digest, str)
            or not digest.startswith("sha256:")
            or run_id in values
        ):
            raise RuntimeError("target progress entry is malformed")
        values[run_id] = digest.removeprefix("sha256:")
    if len(values) != 6:
        raise RuntimeError("target progress does not cover six unique runs")
    return values


def _initialize_workspace(fixture: Path, workspace: Path) -> None:
    shutil.copytree(
        fixture,
        workspace,
        ignore=shutil.ignore_patterns(
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            "*.pyc",
            "*.pyo",
        ),
    )
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.name", "Adaptation Compiler Lab"],
        ["git", "config", "user.email", "scorer-adjudication@invalid.local"],
        ["git", "add", "--all"],
        ["git", "commit", "--quiet", "-m", "frozen adjudication fixture"],
    ):
        completed = _run(command, cwd=workspace)
        if completed.returncode != 0:
            raise RuntimeError("unable to initialize adjudication workspace")


def _counts(score: dict[str, Any], group: str) -> tuple[int, int]:
    groups = score.get("checks")
    values = groups.get(group) if isinstance(groups, dict) else None
    if (
        not isinstance(values, dict)
        or not values
        or not all(isinstance(value, bool) for value in values.values())
    ):
        raise RuntimeError(f"corrected scorer returned malformed {group} checks")
    return (sum(bool(value) for value in values.values()), len(values))


def _receipts_succeeded(score: dict[str, Any]) -> bool:
    receipts = score.get("receipts")
    return (
        isinstance(receipts, dict)
        and bool(receipts)
        and all(
            isinstance(value, dict) and value.get("status") == "succeeded"
            for value in receipts.values()
        )
    )


def _score(
    *,
    python: Path,
    scorer: Path,
    manifest: Path,
    workspace: Path,
    repo_source: Path,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str]]:
    process = _run(
        [
            str(python),
            str(scorer),
            "--task-manifest",
            str(manifest),
            "--workspace",
            str(workspace),
        ],
        cwd=workspace,
        repo_source=repo_source,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "corrected trusted scorer process failed: " + process.stderr.strip()
        )
    value = json.loads(process.stdout)
    if not isinstance(value, dict) or not _receipts_succeeded(value):
        raise RuntimeError("corrected trusted scorer did not produce successful receipts")
    return value, process


def _raw_bundle(
    *,
    store: LocalRawPayloadStore,
    root: Path,
    digest: str,
) -> dict[str, Any]:
    value = json.loads(store.read(_raw_reference(root, digest)))
    if not isinstance(value, dict):
        raise RuntimeError("decrypted target bundle is not an object")
    return value


def _assert_original_failure_is_scorer_only(
    observation: Any,
    raw: dict[str, Any],
) -> None:
    reasons = (observation.invalid_reason or "").split("; ")
    if (
        observation.valid
        or not reasons
        or any(not reason.startswith("independent scorer failed safely for ") for reason in reasons)
    ):
        raise RuntimeError("original invalid record was not a scorer-only failure")
    diff = raw.get("diff")
    trace = base64.b64decode(str(raw.get("trace_base64")), validate=True)
    visible = raw.get("visible_test")
    if (
        raw.get("run_id") != observation.run_id
        or not isinstance(diff, str)
        or sha256_bytes(diff.encode("utf-8")) != observation.diff_digest
        or sha256_bytes(trace) != observation.trace_digest
        or raw.get("exit_code") != 0
        or raw.get("timed_out") is not False
        or raw.get("trace_validation_error") is not None
        or not isinstance(visible, dict)
        or visible.get("returncode") != 0
    ):
        raise RuntimeError("original target evidence drifted before adjudication")


def _adjudicate_one(
    *,
    observation: Any,
    task: CompactProjectionTask,
    raw: dict[str, Any],
    benchmark: Path,
    python: Path,
    scorer: Path,
    repo_source: Path,
) -> tuple[Any, dict[str, Any]]:
    _assert_original_failure_is_scorer_only(observation, raw)
    diff = str(raw["diff"])
    with tempfile.TemporaryDirectory(prefix="acl-compact-scorer-adjudication-") as temporary:
        workspace = Path(temporary) / "task"
        _initialize_workspace(benchmark / task.fixture_directory, workspace)
        applied = _run(["git", "apply", "--binary", "-"], cwd=workspace, stdin=diff)
        if applied.returncode != 0:
            raise RuntimeError("unable to reconstruct exact target patch")
        status = _run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=workspace,
        )
        changed = tuple(line[3:] for line in status.stdout.splitlines() if len(line) >= 4)
        if status.returncode != 0 or changed != task.allowed_change_paths:
            raise RuntimeError("reconstructed target patch changed an unexpected path")
        visible = _run(list(task.visible_test_command), cwd=workspace)
        if visible.returncode != 0:
            raise RuntimeError("reconstructed patch failed its visible test")
        score, scorer_process = _score(
            python=python,
            scorer=scorer,
            manifest=benchmark / task.fixture_directory.replace("/fixture", "/task.json"),
            workspace=workspace,
            repo_source=repo_source,
        )
    objective = _counts(score, "objective")
    diagnostic = _counts(score, "diagnostic")
    neutral = _counts(score, "neutral")
    corrected = observation.model_copy(
        update={
            "diagnostic_checks_passed": diagnostic[0],
            "diagnostic_checks_total": diagnostic[1],
            "invalid_reason": None,
            "neutral_checks_passed": neutral[0],
            "neutral_checks_total": neutral[1],
            "objective_checks_passed": objective[0],
            "objective_checks_total": objective[1],
            "scorer_output_digest": canonical_digest(score),
            "valid": True,
        }
    )
    return corrected, {
        "blind_output_id": observation.blind_output_id,
        "corrected_scorer_output_digest": corrected.scorer_output_digest,
        "diagnostic": {"passed": diagnostic[0], "total": diagnostic[1]},
        "neutral": {"passed": neutral[0], "total": neutral[1]},
        "objective": {"passed": objective[0], "total": objective[1]},
        "original_diff_digest": observation.diff_digest,
        "original_trace_digest": observation.trace_digest,
        "scorer_process_stdout_digest": sha256_bytes(scorer_process.stdout.encode("utf-8")),
        "task_id": observation.task_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target-output-root", type=Path, required=True)
    parser.add_argument("--target-config-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    benchmark = repo / "development_benchmark_compact_projection"
    results = benchmark / "results-v1.19"
    design = load_compact_projection_design(benchmark, version="1.19")
    contract = load_compact_execution_contract(benchmark, design=design)
    if _run(["git", "status", "--porcelain"], cwd=repo).stdout:
        raise RuntimeError("scorer adjudication requires a clean repository")
    failure = _load_object(benchmark / "TARGET_EXECUTION_FAILURE-v1.19.json")
    if (
        failure.get("failure_class") != "post_action_scorer_instrument"
        or failure.get("scorer_adjudication_permitted") is not True
    ):
        raise RuntimeError("v1.19 scorer adjudication is not authorized")
    original = CompactProjectionBlindReport.model_validate_json(
        (results / "blind-report.json").read_bytes()
    )
    original_completion = _load_object(results / "completion.json")
    if original_completion.get("blind_report_digest") != original.content_digest:
        raise RuntimeError("original completion no longer binds the blind report")

    output_root = arguments.target_output_root.resolve()
    config_root = arguments.target_config_root.resolve()
    encrypted_root = output_root / "encrypted"
    progress = _progress_by_run(output_root / "progress.jsonl")
    store = LocalRawPayloadStore(
        encrypted_root,
        encryption_key=RawEncryptionKey.from_file(
            config_root / "trace-encryption.key",
            workspace_root=repo,
        ),
    )
    python = arguments.python.resolve()
    scorer = repo / "scripts/score_compact_projection_task.py"
    task_by_id = {task.task_id: task for task in design.tasks}
    corrected_observations = []
    corrections = []
    for observation in original.observations:
        raw = _raw_bundle(
            store=store,
            root=encrypted_root,
            digest=progress[observation.run_id],
        )
        corrected, correction = _adjudicate_one(
            observation=observation,
            task=task_by_id[observation.task_id],
            raw=raw,
            benchmark=benchmark,
            python=python,
            scorer=scorer,
            repo_source=repo / "src",
        )
        corrected_observations.append(corrected)
        corrections.append(correction)

    corrected_report = original.model_copy(update={"observations": tuple(corrected_observations)})
    corrected_path = results / "blind-report-adjudicated.json"
    receipt_path = results / "scorer-adjudication-receipt.json"
    completion_path = results / "completion-adjudicated.json"
    if corrected_path.exists() or receipt_path.exists() or completion_path.exists():
        raise RuntimeError("scorer adjudication outputs already exist; refusing to overwrite")
    _exclusive_write(corrected_path, _canonical_bytes(corrected_report.model_dump(mode="json")))
    receipt = {
        "adjudication_kind": "instrument_only_rescore",
        "adjudication_protocol_digest": sha256_file(
            benchmark / "SCORER_ADJUDICATION_PROTOCOL-v1.19.md"
        ),
        "adjudication_source_digest": sha256_file(Path(__file__)),
        "condition_mapping_access": False,
        "corrected_blind_report_digest": corrected_report.content_digest,
        "corrected_records_valid": sum(item.valid for item in corrected_report.observations),
        "corrections": corrections,
        "design_digest": design.content_digest,
        "execution_contract_digest": contract.content_digest,
        "external_validation_accessed": False,
        "new_target_sessions": 0,
        "original_blind_report_digest": original.content_digest,
        "original_blind_report_file_digest": sha256_file(results / "blind-report.json"),
        "original_completion_file_digest": sha256_file(results / "completion.json"),
        "provider_billed_calls": 0,
        "scorer_source_digest": sha256_file(scorer),
        "scorer_system_path": _TRUSTED_PATH,
        "sealed_condition_mapping_withheld": True,
    }
    _exclusive_write(receipt_path, _canonical_bytes(receipt))
    completion = {
        **original_completion,
        "adjudication_receipt_digest": sha256_file(receipt_path),
        "blind_report_digest": corrected_report.content_digest,
        "invalid_runs": sum(not item.valid for item in corrected_report.observations),
        "original_completion_digest": sha256_file(results / "completion.json"),
        "target_sessions_added_by_adjudication": 0,
    }
    _exclusive_write(completion_path, _canonical_bytes(completion))
    print(
        canonical_json(
            {
                "blind_report_digest": corrected_report.content_digest,
                "records_valid": sum(item.valid for item in corrected_report.observations),
                "receipt_digest": sha256_file(receipt_path),
                "target_sessions_added": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
