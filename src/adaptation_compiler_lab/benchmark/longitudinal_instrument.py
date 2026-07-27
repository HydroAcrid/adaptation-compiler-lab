"""Fail-closed helpers for future longitudinal benchmark coordination."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import Field

from adaptation_compiler_lab.benchmark.longitudinal import LongitudinalDevelopmentTask
from adaptation_compiler_lab.benchmark.longitudinal_scoring import (
    LongitudinalScenarioResult,
    LongitudinalTaskScore,
)
from adaptation_compiler_lab.domain import FrozenModel, NonEmptyStr, Sha256Digest


def sha256_path(path: Path) -> Sha256Digest:
    """Hash exact file bytes without parsing or normalizing them."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def verify_private_plan_digest(path: Path, expected_digest: str) -> Sha256Digest:
    """Fail closed unless the frozen private plan matches its exact stored digest."""

    actual = sha256_path(path)
    if actual != expected_digest:
        raise ValueError(
            f"frozen private-plan digest mismatch: expected {expected_digest}, observed {actual}"
        )
    return actual


def normalize_target_material(value: str) -> str:
    """Return the exact newline-normalized text written to target-visible files."""

    return value.rstrip() + "\n"


def normalized_utf8_size(value: str) -> int:
    """Measure the exact normalized UTF-8 bytes that will be written."""

    return len(normalize_target_material(value).encode("utf-8"))


def _normalized_words(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(re.findall(r"[\w]+(?:[-'][\w]+)*", normalized))


class ConditionLeakageMatch(FrozenModel):
    """One normalized excerpt copied from target-visible condition material."""

    material_index: int = Field(ge=0)
    word_offset: int = Field(ge=0)
    excerpt_digest: Sha256Digest
    excerpt_word_count: int = Field(ge=1)


def condition_leakage_matches(
    output: str,
    materials: tuple[str, ...],
    *,
    window_words: int = 12,
    minimum_excerpt_characters: int = 48,
) -> tuple[ConditionLeakageMatch, ...]:
    """Find normalized material excerpts without exposing their text in receipts."""

    if window_words < 2:
        raise ValueError("condition leakage window must contain at least two words")
    output_words = _normalized_words(output)
    if not output_words:
        return ()
    normalized_output = " ".join(output_words)
    matches: list[ConditionLeakageMatch] = []
    seen: set[tuple[int, str]] = set()
    for material_index, material in enumerate(materials):
        words = _normalized_words(material)
        if not words:
            continue
        width = min(window_words, len(words))
        for offset in range(len(words) - width + 1):
            excerpt = " ".join(words[offset : offset + width])
            if len(excerpt) < minimum_excerpt_characters or excerpt not in normalized_output:
                continue
            digest = f"sha256:{hashlib.sha256(excerpt.encode('utf-8')).hexdigest()}"
            key = (material_index, digest)
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                ConditionLeakageMatch(
                    material_index=material_index,
                    word_offset=offset,
                    excerpt_digest=digest,
                    excerpt_word_count=width,
                )
            )
    return tuple(matches)


_LONGITUDINAL_CONDITION_IDENTITY_MARKERS = (
    "compiled adaptation",
    "disposable-atomic-replace@",
    "persistent-backup@",
    "persistent-refuse-default@",
    "dogfood-evidence-",
    "strong static profile",
    "experimental condition",
)


def condition_identity_leaked(output: str) -> bool:
    """Detect short condition/provenance markers that excerpt windows cannot catch."""

    normalized = unicodedata.normalize("NFKC", output).casefold()
    return any(marker in normalized for marker in _LONGITUDINAL_CONDITION_IDENTITY_MARKERS)


type GitStatus = Literal[" ", "M", "T", "A", "D", "R", "C", "U", "?", "!"]
_GIT_STATUSES = frozenset({" ", "M", "T", "A", "D", "R", "C", "U", "?", "!"})


class PorcelainChange(FrozenModel):
    """One NUL-delimited Git porcelain-v1 change."""

    index_status: GitStatus
    worktree_status: GitStatus
    path: NonEmptyStr
    original_path: NonEmptyStr | None = None


def parse_porcelain_v1_z(payload: str) -> tuple[PorcelainChange, ...]:
    """Parse both status columns and rename records from ``git status -z``."""

    if not payload:
        return ()
    fields = payload.split("\0")
    if fields[-1] != "":
        raise ValueError("NUL-delimited Git status is missing its final terminator")
    fields.pop()
    changes: list[PorcelainChange] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4 or entry[2] != " ":
            raise ValueError("malformed NUL-delimited Git porcelain entry")
        index_status, worktree_status = entry[0], entry[1]
        if index_status not in _GIT_STATUSES or worktree_status not in _GIT_STATUSES:
            raise ValueError("Git porcelain entry contains an unknown status code")
        path = entry[3:]
        if index_status == " " and worktree_status == " ":
            raise ValueError("Git porcelain entry has no changed status column")
        original_path: str | None = None
        if index_status in {"R", "C"}:
            if index >= len(fields):
                raise ValueError("Git rename or copy entry omitted its original path")
            original_path = fields[index]
            index += 1
        changes.append(
            PorcelainChange(
                index_status=cast(GitStatus, index_status),
                worktree_status=cast(GitStatus, worktree_status),
                path=path,
                original_path=original_path,
            )
        )
    return tuple(changes)


def unexpected_changed_paths(
    changes: tuple[PorcelainChange, ...],
    allowed_paths: frozenset[str],
) -> tuple[str, ...]:
    """Return changed paths outside the exact allowlist."""

    observed = {
        path
        for change in changes
        for path in (change.path, change.original_path)
        if path is not None and path not in allowed_paths
    }
    return tuple(sorted(observed))


class BoundedScorerReceipt(FrozenModel):
    """Durable coordinator evidence for one isolated scorer subprocess."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["succeeded", "timed_out", "crashed", "malformed_output"]
    exit_code: int | None
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    stdout_digest: Sha256Digest
    stderr_digest: Sha256Digest
    failure_reason: str | None = None
    timeout_seconds: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    sandbox_mode: Literal["linux-user-mount-network-pid-chroot-v1"] = (
        "linux-user-mount-network-pid-chroot-v1"
    )


class BoundedScorerResult(FrozenModel):
    score: LongitudinalTaskScore
    receipt: BoundedScorerReceipt


class CompactPolicyObservation(FrozenModel):
    """One untrusted-policy observation without hidden expected outcomes."""

    observation_version: Literal["1.0.0"] = "1.0.0"
    scenario_id: NonEmptyStr
    status: Literal["returned", "invalid_return", "raised"]
    value: tuple[str, ...] | None = None
    detail: str | None = None


class BoundedCompactPolicyObservationResult(FrozenModel):
    observation: CompactPolicyObservation | None
    receipt: BoundedScorerReceipt


def _bytes_digest(value: bytes) -> Sha256Digest:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _failed_score(
    task: LongitudinalDevelopmentTask,
    *,
    status: str,
    reason: str,
) -> LongitudinalTaskScore:
    observed = f"bounded scorer {status}: {reason}"
    results = tuple(
        LongitudinalScenarioResult(
            scenario_id=scenario.scenario_id,
            metric=scenario.metric,
            passed=False,
            observed=observed,
            expected=(
                scenario.expected_action
                if task.task_kind == "action"
                else repr(scenario.expected_plan)
            ),
        )
        for scenario in task.scenarios
    )

    def count(metric: str) -> int:
        return sum(item.metric == metric for item in results)

    return LongitudinalTaskScore(
        task_id=task.task_id,
        scenario_results=results,
        objective_passed=0,
        objective_total=count("objective"),
        diagnostic_passed=0,
        diagnostic_total=count("diagnostic"),
        neutral_passed=0,
        neutral_total=count("neutral"),
    )


def _current_uid_process_count() -> int:
    """Count existing host tasks so RLIMIT_NPROC leaves only bounded headroom."""

    uid = os.getuid()
    count = 0
    for status_path in Path("/proc").glob("[0-9]*/status"):
        try:
            uid_line = next(
                line
                for line in status_path.read_text(encoding="ascii").splitlines()
                if line.startswith("Uid:")
            )
        except (OSError, StopIteration, UnicodeDecodeError):
            continue
        if int(uid_line.split()[1]) == uid:
            try:
                count += sum(1 for _ in (status_path.parent / "task").iterdir())
            except OSError:
                count += 1
    return count


_SCORER_OUTPUT_LIMIT_BYTES = 1024 * 1024


def _scorer_resource_limits(timeout_seconds: float, process_limit: int) -> None:
    """Apply Linux child-only resource ceilings before generated policy import."""

    import resource

    cpu_soft = max(1, math.ceil(timeout_seconds))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft, cpu_soft + 1))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (_SCORER_OUTPUT_LIMIT_BYTES, _SCORER_OUTPUT_LIMIT_BYTES),
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (process_limit, process_limit))


@dataclass(frozen=True)
class _BoundedProcessOutcome:
    status: Literal["succeeded", "timed_out", "crashed"]
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    reason: str | None
    duration_seconds: float


def _run_bounded_sandbox_command(
    *,
    command: list[str],
    cwd: Path,
    sandbox_root: Path,
    timeout_seconds: float,
    process_limit: int,
    started: float,
) -> _BoundedProcessOutcome:
    """Run one already-constructed sandbox command with bounded file-backed output."""

    stdout = b""
    stderr = b""
    exit_code: int | None = None
    status: Literal["succeeded", "timed_out", "crashed"] = "crashed"
    reason: str | None = None
    process: subprocess.Popen[bytes] | None = None
    try:
        stdout_path = sandbox_root / "stdout.bin"
        stderr_path = sandbox_root / "stderr.bin"
        with (
            stdout_path.open("w+b") as stdout_stream,
            stderr_path.open("w+b") as stderr_stream,
        ):
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=stdout_stream,
                stderr=stderr_stream,
                start_new_session=True,
                preexec_fn=lambda: _scorer_resource_limits(
                    timeout_seconds,
                    process_limit,
                ),
                env={
                    "HOME": "/workspace",
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "PATH": "/usr/bin:/bin",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": (
                        f"/venv/lib/python{sys.version_info.major}."
                        f"{sys.version_info.minor}/site-packages:/app-src"
                    ),
                    "TMPDIR": "/tmp",
                },
            )
            try:
                exit_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                exit_code = process.wait()
                status = "timed_out"
                reason = f"exceeded {timeout_seconds:g} seconds"
            stdout_stream.seek(0)
            stderr_stream.seek(0)
            stdout = stdout_stream.read(_SCORER_OUTPUT_LIMIT_BYTES + 1)
            stderr = stderr_stream.read(_SCORER_OUTPUT_LIMIT_BYTES + 1)
    except (OSError, subprocess.SubprocessError) as error:
        if process is not None and process.poll() is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        reason = f"scorer sandbox could not start or complete: {error}"
    if reason is None:
        if len(stdout) > _SCORER_OUTPUT_LIMIT_BYTES or len(stderr) > _SCORER_OUTPUT_LIMIT_BYTES:
            status = "crashed"
            reason = (
                f"scorer output exceeded the {_SCORER_OUTPUT_LIMIT_BYTES}-byte per-stream ceiling"
            )
        elif exit_code != 0:
            status = "crashed"
            reason = f"scorer subprocess exited with code {exit_code}"
        else:
            status = "succeeded"
    return _BoundedProcessOutcome(
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        reason=reason,
        duration_seconds=time.monotonic() - started,
    )


_SCORER_SANDBOX_SCRIPT = r"""
set -eu
root=$1
venv=$2
python_runtime=$3
python_binary=$4
source_root=$5
scorer=$6
benchmark=$7
workspace=$8
task_id=$9

mount --make-rprivate /

mount_read_only_directory() {
    source=$1
    target=$2
    mkdir -p "$target"
    mount --rbind "$source" "$target"
    mount --make-rslave "$target"
    mount -o remount,ro,bind "$target"
}

mount_read_only_file() {
    source=$1
    target=$2
    : > "$target"
    mount --bind "$source" "$target"
    mount -o remount,ro,bind "$target"
}

mount_read_only_directory /usr "$root/usr"
if [ -e /lib ]; then
    mount_read_only_directory /lib "$root/lib"
fi
if [ -e /lib64 ]; then
    mount_read_only_directory /lib64 "$root/lib64"
fi
mount_read_only_directory "$venv" "$root/venv"
mount_read_only_directory "$python_runtime" "$root/python-runtime"
mount_read_only_directory "$source_root" "$root/app-src"
mount_read_only_directory "$benchmark" "$root/benchmark"
mount_read_only_directory "$workspace" "$root/workspace"
mkdir -p "$root/dev" "$root/proc" "$root/tmp"
chmod 1777 "$root/tmp"
mount_read_only_file /dev/null "$root/dev/null"
mount_read_only_file /dev/urandom "$root/dev/urandom"
mount -t proc -o nosuid,nodev,noexec,hidepid=2 proc "$root/proc"
mount -t tmpfs -o nodev,nosuid,noexec,size=16m tmpfs "$root/tmp"
mount_read_only_file "$scorer" "$root/scorer.py"

exec /usr/sbin/chroot "$root" /usr/bin/setpriv \
    --bounding-set=-all \
    --inh-caps=-all \
    --ambient-caps=-all \
    --no-new-privs \
    "/python-runtime/bin/$python_binary" /scorer.py \
    --benchmark-root /benchmark \
    --task-id "$task_id" \
    --workspace /workspace
"""


def _scorer_sandbox_command(
    *,
    sandbox_root: Path,
    scorer_script: Path,
    benchmark_root: Path,
    workspace: Path,
    task_id: str,
) -> list[str]:
    """Build a fail-closed Linux namespace/chroot command for untrusted policy code."""

    if sys.platform != "linux" or os.name != "posix":
        raise OSError("the scorer sandbox requires Linux")
    if os.getuid() == 0:
        raise OSError(
            "the scorer sandbox requires a non-root outer coordinator so RLIMIT_NPROC "
            "is enforceable"
        )
    required_commands = ("unshare", "sh", "mount", "chroot", "setpriv")
    resolved = {name: shutil.which(name) for name in required_commands}
    missing = tuple(name for name, path in resolved.items() if path is None)
    if missing:
        raise OSError(f"missing scorer sandbox commands: {', '.join(missing)}")
    venv = Path(sys.prefix).resolve()
    python_executable = Path(sys.executable).resolve()
    python_runtime = python_executable.parents[1]
    source_root = Path(__file__).resolve().parents[2]
    for label, path in (
        ("virtual environment", venv),
        ("Python runtime", python_runtime),
        ("package source", source_root),
        ("benchmark root", benchmark_root.resolve()),
        ("workspace", workspace.resolve()),
    ):
        if not path.is_dir():
            raise OSError(f"scorer sandbox {label} is not a directory: {path}")
    if not scorer_script.resolve().is_file():
        raise OSError(f"scorer script is not a file: {scorer_script}")
    sandbox_root.chmod(0o755)
    return [
        cast(str, resolved["unshare"]),
        "--user",
        "--map-user=65534",
        "--map-group=65534",
        "--keep-caps",
        "--mount",
        "--net",
        "--pid",
        "--fork",
        "--kill-child",
        cast(str, resolved["sh"]),
        "-ceu",
        _SCORER_SANDBOX_SCRIPT,
        "scorer-sandbox",
        str(sandbox_root),
        str(venv),
        str(python_runtime),
        python_executable.name,
        str(source_root),
        str(scorer_script.resolve()),
        str(benchmark_root.resolve()),
        str(workspace.resolve()),
        task_id,
    ]


_POLICY_OBSERVER_SANDBOX_SCRIPT = r"""
set -eu
root=$1
python_runtime=$2
python_binary=$3
observer=$4
workspace=$5
scenario_json=$6

mount --make-rprivate /

mount_read_only_directory() {
    source=$1
    target=$2
    mkdir -p "$target"
    mount --rbind "$source" "$target"
    mount --make-rslave "$target"
    mount -o remount,ro,bind "$target"
}

mount_read_only_file() {
    source=$1
    target=$2
    : > "$target"
    mount --bind "$source" "$target"
    mount -o remount,ro,bind "$target"
}

mount_read_only_directory /usr "$root/usr"
if [ -e /lib ]; then
    mount_read_only_directory /lib "$root/lib"
fi
if [ -e /lib64 ]; then
    mount_read_only_directory /lib64 "$root/lib64"
fi
mount_read_only_directory "$python_runtime" "$root/python-runtime"
mount_read_only_directory "$workspace" "$root/workspace"
mkdir -p "$root/dev" "$root/proc" "$root/tmp"
chmod 1777 "$root/tmp"
mount_read_only_file /dev/null "$root/dev/null"
mount_read_only_file /dev/urandom "$root/dev/urandom"
mount -t proc -o nosuid,nodev,noexec,hidepid=2 proc "$root/proc"
mount -t tmpfs -o nodev,nosuid,noexec,size=16m tmpfs "$root/tmp"
mount_read_only_file "$observer" "$root/observer.py"

exec /usr/sbin/chroot "$root" /usr/bin/setpriv \
    --bounding-set=-all \
    --inh-caps=-all \
    --ambient-caps=-all \
    --no-new-privs \
    "/python-runtime/bin/$python_binary" /observer.py \
    --workspace /workspace \
    --scenario-json "$scenario_json"
"""


def _policy_observer_sandbox_command(
    *,
    sandbox_root: Path,
    observer_script: Path,
    workspace: Path,
    scenario_json: str,
) -> list[str]:
    """Build an answer-blind sandbox for one generated-policy observation."""

    if sys.platform != "linux" or os.name != "posix":
        raise OSError("the policy observer sandbox requires Linux")
    if os.getuid() == 0:
        raise OSError(
            "the policy observer sandbox requires a non-root outer coordinator so "
            "RLIMIT_NPROC is enforceable"
        )
    required_commands = ("unshare", "sh", "mount", "chroot", "setpriv")
    resolved = {name: shutil.which(name) for name in required_commands}
    missing = tuple(name for name, path in resolved.items() if path is None)
    if missing:
        raise OSError(f"missing policy observer sandbox commands: {', '.join(missing)}")
    python_executable = Path(sys.executable).resolve()
    python_runtime = python_executable.parents[1]
    for label, path in (
        ("Python runtime", python_runtime),
        ("workspace", workspace.resolve()),
    ):
        if not path.is_dir():
            raise OSError(f"policy observer sandbox {label} is not a directory: {path}")
    if not observer_script.resolve().is_file():
        raise OSError(f"policy observer script is not a file: {observer_script}")
    sandbox_root.chmod(0o755)
    return [
        cast(str, resolved["unshare"]),
        "--user",
        "--map-user=65534",
        "--map-group=65534",
        "--keep-caps",
        "--mount",
        "--net",
        "--pid",
        "--fork",
        "--kill-child",
        cast(str, resolved["sh"]),
        "-ceu",
        _POLICY_OBSERVER_SANDBOX_SCRIPT,
        "policy-observer-sandbox",
        str(sandbox_root),
        str(python_runtime),
        python_executable.name,
        str(observer_script.resolve()),
        str(workspace.resolve()),
        scenario_json,
    ]


def run_bounded_compact_policy_observation(
    *,
    observer_script: Path,
    workspace: Path,
    scenario_id: str,
    destination_exists: bool,
    storage_class: str,
    recovery_copy_approved: bool,
    timeout_seconds: float,
) -> BoundedCompactPolicyObservationResult:
    """Observe one policy call without exposing hidden expected outcomes to its sandbox."""

    started = time.monotonic()
    process_limit = max(_current_uid_process_count() + 16, 128)
    scenario_json = json.dumps(
        {
            "destination_exists": destination_exists,
            "recovery_copy_approved": recovery_copy_approved,
            "scenario_id": scenario_id,
            "storage_class": storage_class,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with tempfile.TemporaryDirectory(prefix="acl-policy-observer-sandbox-") as temporary:
        sandbox_root = Path(temporary)
        try:
            command = _policy_observer_sandbox_command(
                sandbox_root=sandbox_root,
                observer_script=observer_script,
                workspace=workspace,
                scenario_json=scenario_json,
            )
            outcome = _run_bounded_sandbox_command(
                command=command,
                cwd=workspace,
                sandbox_root=sandbox_root,
                timeout_seconds=timeout_seconds,
                process_limit=process_limit,
                started=started,
            )
        except OSError as error:
            outcome = _BoundedProcessOutcome(
                status="crashed",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                reason=f"policy observer sandbox could not start: {error}",
                duration_seconds=time.monotonic() - started,
            )
    status: Literal["succeeded", "timed_out", "crashed", "malformed_output"] = outcome.status
    reason = outcome.reason
    observation: CompactPolicyObservation | None = None
    if status == "succeeded":
        try:
            observation = CompactPolicyObservation.model_validate_json(
                outcome.stdout.decode("utf-8")
            )
            if observation.scenario_id != scenario_id:
                raise ValueError("policy observer returned a different scenario ID")
        except (UnicodeDecodeError, ValueError, TypeError) as error:
            status = "malformed_output"
            reason = f"{type(error).__name__}: {error}"
    return BoundedCompactPolicyObservationResult(
        observation=observation,
        receipt=BoundedScorerReceipt(
            status=status,
            exit_code=outcome.exit_code,
            duration_seconds=outcome.duration_seconds,
            stdout_digest=_bytes_digest(outcome.stdout),
            stderr_digest=_bytes_digest(outcome.stderr),
            failure_reason=reason,
            timeout_seconds=timeout_seconds,
        ),
    )


def run_bounded_longitudinal_scorer(
    *,
    scorer_script: Path,
    benchmark_root: Path,
    task: LongitudinalDevelopmentTask,
    workspace: Path,
    timeout_seconds: float,
) -> BoundedScorerResult:
    """Score inside a bounded Linux filesystem/network/PID sandbox."""

    started = time.monotonic()
    # WSL accounts some host tasks that are not visible in the distribution's
    # /proc mount. Keep a conservative absolute floor while still bounding forks.
    process_limit = max(_current_uid_process_count() + 16, 128)
    status: Literal["succeeded", "timed_out", "crashed", "malformed_output"]
    with tempfile.TemporaryDirectory(prefix="acl-scorer-sandbox-") as temporary:
        sandbox_root = Path(temporary)
        try:
            command = _scorer_sandbox_command(
                sandbox_root=sandbox_root,
                scorer_script=scorer_script,
                benchmark_root=benchmark_root,
                workspace=workspace,
                task_id=task.task_id,
            )
            outcome = _run_bounded_sandbox_command(
                command=command,
                cwd=workspace,
                sandbox_root=sandbox_root,
                timeout_seconds=timeout_seconds,
                process_limit=process_limit,
                started=started,
            )
        except OSError as error:
            outcome = _BoundedProcessOutcome(
                status="crashed",
                exit_code=None,
                stdout=b"",
                stderr=b"",
                reason=f"scorer sandbox could not start: {error}",
                duration_seconds=time.monotonic() - started,
            )
        status = outcome.status
        reason = outcome.reason
        if status == "succeeded":
            try:
                decoded_stdout = outcome.stdout.decode("utf-8")
                score = LongitudinalTaskScore.model_validate_json(decoded_stdout)
                if score.task_id != task.task_id:
                    raise ValueError("scorer returned a different task ID")
            except (UnicodeDecodeError, ValueError, TypeError) as error:
                status = "malformed_output"
                reason = f"{type(error).__name__}: {error}"
            else:
                return BoundedScorerResult(
                    score=score,
                    receipt=BoundedScorerReceipt(
                        status=status,
                        exit_code=outcome.exit_code,
                        duration_seconds=outcome.duration_seconds,
                        stdout_digest=_bytes_digest(outcome.stdout),
                        stderr_digest=_bytes_digest(outcome.stderr),
                        timeout_seconds=timeout_seconds,
                    ),
                )
    assert reason is not None
    return BoundedScorerResult(
        score=_failed_score(task, status=status, reason=reason),
        receipt=BoundedScorerReceipt(
            status=status,
            exit_code=outcome.exit_code,
            duration_seconds=outcome.duration_seconds,
            stdout_digest=_bytes_digest(outcome.stdout),
            stderr_digest=_bytes_digest(outcome.stderr),
            failure_reason=reason,
            timeout_seconds=timeout_seconds,
        ),
    )
