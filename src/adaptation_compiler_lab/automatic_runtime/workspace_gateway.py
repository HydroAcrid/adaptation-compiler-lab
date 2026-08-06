"""Disposable Git workspaces, independent verification, and recoverable change application."""

from __future__ import annotations

import base64
import json
import os
import resource
import signal
import stat
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal

from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    ChangeApplicationReceipt,
    ChangeApplicationStatus,
    VerificationCommandSpec,
    VerificationReceipt,
    WorkspaceBaseline,
    WorkspaceChangeReceipt,
    WorkspaceFileChange,
    WorkspaceLease,
)
from adaptation_compiler_lab.domain import Sha256Digest
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from adaptation_compiler_lab.sanitization import scan_text
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json

MAXIMUM_FILE_BYTES: Final = 5_000_000
MAXIMUM_BUNDLE_BYTES: Final = 25_000_000
_FORBIDDEN_PARTS: Final = frozenset({".git"})


class WorkspaceGatewayError(ValueError):
    """Raised when a workspace cannot be proven isolated and recoverable."""


def require_protected_paths_unchanged(
    receipt: WorkspaceChangeReceipt, *, protected_paths: tuple[str, ...]
) -> None:
    """Prevent an agent from changing the independent verifier or its trusted inputs."""

    for change in receipt.changes:
        if any(
            change.path == protected or change.path.startswith(f"{protected}/")
            for protected in protected_paths
        ):
            raise WorkspaceGatewayError("agent changed a protected independent-verification path")


def _run_git(root: Path, argv: Sequence[str], *, timeout: int = 60) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise WorkspaceGatewayError("Git workspace operation failed closed")
    return completed.stdout.strip()


def _digest_bytes(value: bytes) -> Sha256Digest:
    return Sha256Digest(f"sha256:{sha256(value).hexdigest()}")


def _digest_path(path: Path) -> Sha256Digest:
    return _digest_bytes(str(path.expanduser().resolve()).encode("utf-8"))


def _safe_relative(path: str) -> str:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
        or any(part.lower() in _FORBIDDEN_PARTS for part in parts)
    ):
        raise WorkspaceGatewayError("change bundle contains a forbidden path")
    return normalized


def _require_change_path_allowed(path: str) -> None:
    parts = path.split("/")
    if any(
        part.lower().startswith(".env.")
        or part.lower()
        in {".aws", ".env", ".gnupg", ".npmrc", ".pypirc", ".ssh", "auth.json", "credentials"}
        for part in parts
    ):
        raise WorkspaceGatewayError(
            "credential and private-state paths cannot enter a change bundle"
        )


@dataclass(frozen=True, slots=True)
class DisposableWorkspace:
    baseline: WorkspaceBaseline
    lease: WorkspaceLease
    root: Path


class GitWorktreeProvider:
    """Create exact detached worktrees beneath one dedicated runtime root."""

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root.expanduser().resolve()

    def create(
        self,
        *,
        canonical_root: Path,
        project_id: str,
        session_id: str,
        created_at: datetime | None = None,
    ) -> DisposableWorkspace:
        canonical = canonical_root.expanduser().resolve()
        if not (canonical / ".git").exists():
            raise WorkspaceGatewayError("canonical project is not a Git worktree")
        if _run_git(canonical, ["status", "--porcelain=v1", "--untracked-files=all"]):
            raise WorkspaceGatewayError("canonical project must be clean before workspace creation")
        commit = _run_git(canonical, ["rev-parse", "HEAD"])
        tree = _run_git(canonical, ["rev-parse", "HEAD^{tree}"])
        now = created_at or datetime.now(UTC)
        self._root.mkdir(parents=True, exist_ok=True)
        root = (self._root / session_id).resolve()
        if root.parent != self._root or root.exists():
            raise WorkspaceGatewayError("workspace lease path is unsafe or already exists")
        subprocess_result = subprocess.run(
            ["git", "-C", str(canonical), "worktree", "add", "--detach", str(root), commit],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if subprocess_result.returncode != 0:
            raise WorkspaceGatewayError("detached writable worktree could not be created")
        if root.resolve().parent != self._root or _run_git(root, ["rev-parse", "HEAD"]) != commit:
            self.teardown(canonical_root=canonical, workspace=root)
            raise WorkspaceGatewayError("created worktree does not match the frozen baseline")
        baseline = WorkspaceBaseline(
            baseline_id=f"baseline-{session_id}",
            project_id=project_id,
            canonical_root_digest=_digest_path(canonical),
            commit_sha=commit,
            tree_sha=tree,
            workspace_root_digest=_digest_path(root),
            created_at=now,
        )
        lease = WorkspaceLease(
            lease_id=f"workspace-{session_id}",
            session_id=session_id,
            baseline_digest=canonical_digest(baseline),
            workspace_root_digest=baseline.workspace_root_digest,
            acquired_at=now,
            expires_at=now + timedelta(hours=1),
        )
        return DisposableWorkspace(baseline=baseline, lease=lease, root=root)

    def teardown(self, *, canonical_root: Path, workspace: Path) -> None:
        canonical = canonical_root.expanduser().resolve()
        resolved = workspace.expanduser().resolve()
        if resolved.parent != self._root or resolved == self._root:
            raise WorkspaceGatewayError("refusing to remove a workspace outside the runtime root")
        if resolved.exists():
            completed = subprocess.run(
                ["git", "-C", str(canonical), "worktree", "remove", "--force", str(resolved)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                raise WorkspaceGatewayError("disposable worktree teardown failed")
        _run_git(canonical, ["worktree", "prune"])


class IndependentVerifier:
    """Execute only registered argv commands with a scrubbed environment and hard timeouts."""

    _SECRET_NAMES: Final = (
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "CODEX_API_KEY",
        "OPENAI_API_KEY",
        "ACLAB_SIGNING_KEY_PASSPHRASE",
        "ACLAB_SIGNING_KEY_FILE",
        "ACLAB_RAW_KEY_FILE",
    )

    def __init__(self, *, base_environment: Mapping[str, str] | None = None) -> None:
        environment = dict(os.environ if base_environment is None else base_environment)
        for name in self._SECRET_NAMES:
            environment.pop(name, None)
        environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "NO_PROXY": "*",
                "no_proxy": "*",
            }
        )
        self._environment = environment

    def run(
        self,
        *,
        session_id: str,
        workspace: Path,
        specs: tuple[VerificationCommandSpec, ...],
        clock: Callable[[], datetime] | None = None,
    ) -> tuple[VerificationReceipt, ...]:
        now = clock or (lambda: datetime.now(UTC))
        root = workspace.expanduser().resolve()
        receipts: list[VerificationReceipt] = []
        for spec in specs:
            started = now()
            timed_out = False
            exit_code = -1
            output = b""
            process: subprocess.Popen[bytes] | None = None
            try:
                process = subprocess.Popen(
                    list(spec.argv),
                    cwd=root,
                    env=self._environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    preexec_fn=partial(self._set_resource_limits, spec.timeout_seconds),
                )
                stdout, _ = process.communicate(timeout=spec.timeout_seconds)
                exit_code = process.returncode
                output = stdout[: spec.maximum_output_bytes]
            except subprocess.TimeoutExpired:
                timed_out = True
                if process is not None:
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, _ = process.communicate()
                    output = stdout[: spec.maximum_output_bytes]
            completed_at = now()
            receipts.append(
                VerificationReceipt(
                    receipt_id=f"verify-{session_id}-{spec.command_id}",
                    session_id=session_id,
                    command_id=spec.command_id,
                    argv_digest=canonical_digest({"argv": spec.argv}),
                    exit_code=exit_code,
                    timed_out=timed_out,
                    output_digest=_digest_bytes(output),
                    output_bytes=len(output),
                    started_at=started,
                    completed_at=completed_at,
                )
            )
        return tuple(receipts)

    @staticmethod
    def _set_resource_limits(timeout_seconds: int) -> None:
        limits = (
            (resource.RLIMIT_CPU, timeout_seconds + 1),
            (resource.RLIMIT_AS, 2_000_000_000),
            (resource.RLIMIT_FSIZE, 100_000_000),
            (resource.RLIMIT_NPROC, 128),
        )
        for kind, target in limits:
            current_soft, current_hard = resource.getrlimit(kind)
            bounded = (
                target if current_hard == resource.RLIM_INFINITY else min(target, current_hard)
            )
            if current_soft != resource.RLIM_INFINITY:
                bounded = min(bounded, current_soft)
            resource.setrlimit(kind, (bounded, current_hard))


@dataclass(frozen=True, slots=True)
class CapturedChangeBundle:
    receipt: WorkspaceChangeReceipt
    raw_reference: RawPayloadRef


class EncryptedChangeBundleStore:
    """Capture complete file bytes while keeping only raw-free metadata in receipts."""

    def __init__(self, raw_store: LocalRawPayloadStore) -> None:
        self._raw_store = raw_store

    def capture(
        self,
        *,
        session_id: str,
        subject_id: str,
        workspace: Path,
        baseline: WorkspaceBaseline,
        release_digest: Sha256Digest,
        projection_digest: Sha256Digest,
        verification_receipts: tuple[VerificationReceipt, ...],
        captured_at: datetime | None = None,
    ) -> CapturedChangeBundle:
        root = workspace.expanduser().resolve()
        if _run_git(root, ["rev-parse", "HEAD"]) != baseline.commit_sha:
            raise WorkspaceGatewayError("agent changed the frozen workspace commit")
        baseline_paths = set(_run_git(root, ["ls-tree", "-r", "--name-only", "HEAD"]).splitlines())
        current_paths = self._current_paths(root)
        changes: list[WorkspaceFileChange] = []
        raw_changes: list[dict[str, object]] = []
        total = 0
        for candidate in sorted(baseline_paths | current_paths):
            relative = _safe_relative(candidate)
            before = self._git_bytes(root, relative) if relative in baseline_paths else None
            target = root / relative
            if target.is_symlink():
                link_value = os.readlink(target).encode("utf-8")
                if before == link_value and relative in baseline_paths:
                    continue
                raise WorkspaceGatewayError("symlink changes are not supported")
            after = target.read_bytes() if relative in current_paths else None
            before_mode = self._git_mode(root, relative) if before is not None else None
            after_mode = (
                self._current_mode(root, target, tracked=relative in baseline_paths)
                if after is not None
                else None
            )
            if before == after and before_mode == after_mode:
                continue
            _require_change_path_allowed(relative)
            size = 0 if after is None else len(after)
            if size > MAXIMUM_FILE_BYTES:
                raise WorkspaceGatewayError("change bundle exceeds the per-file size limit")
            if after is not None and b"\x00" not in after:
                try:
                    rendered_after = after.decode("utf-8")
                except UnicodeDecodeError:
                    rendered_after = ""
                if rendered_after and scan_text(rendered_after).findings:
                    raise WorkspaceGatewayError("secret-like content cannot enter a change bundle")
            total += size
            if total > MAXIMUM_BUNDLE_BYTES:
                raise WorkspaceGatewayError("change bundle exceeds the total size limit")
            operation: Literal["add", "modify", "delete"] = (
                "add" if before is None else "delete" if after is None else "modify"
            )
            changes.append(
                WorkspaceFileChange(
                    path=relative,
                    operation=operation,
                    before_digest=None if before is None else _digest_bytes(before),
                    after_digest=None if after is None else _digest_bytes(after),
                    before_mode=before_mode,
                    after_mode=after_mode,
                    size_bytes=size,
                    binary=(b"\x00" in (after if after is not None else before or b"")),
                )
            )
            raw_changes.append(
                {
                    "after": None if after is None else base64.b64encode(after).decode("ascii"),
                    "before": None if before is None else base64.b64encode(before).decode("ascii"),
                    "after_mode": after_mode,
                    "before_mode": before_mode,
                    "operation": operation,
                    "path": relative,
                }
            )
        raw_payload = canonical_json(
            {
                "baseline": baseline.model_dump(mode="json"),
                "changes": raw_changes,
                "session_id": session_id,
                "version": 1,
            }
        ).encode("utf-8")
        reference = self._raw_store.put(
            raw_payload,
            media_type="application/vnd.adaptation-compiler.change-bundle+json",
        )
        receipt = WorkspaceChangeReceipt(
            receipt_id=f"changes-{session_id}",
            session_id=session_id,
            subject_id=subject_id,
            baseline_digest=canonical_digest(baseline),
            release_digest=release_digest,
            projection_digest=projection_digest,
            encrypted_bundle_digest=Sha256Digest(f"sha256:{reference.sha256}"),
            changes=tuple(changes),
            total_bytes=total,
            verification_receipt_digests=tuple(
                canonical_digest(item) for item in verification_receipts
            ),
            captured_at=captured_at or datetime.now(UTC),
        )
        return CapturedChangeBundle(receipt=receipt, raw_reference=reference)

    @staticmethod
    def _current_paths(root: Path) -> set[str]:
        result: set[str] = set()
        for directory, names, files in os.walk(root, followlinks=False):
            current = Path(directory)
            names[:] = [name for name in names if name != ".git"]
            files = [name for name in files if name != ".git"]
            for name in names:
                candidate = current / name
                if candidate.is_symlink():
                    result.add(_safe_relative(candidate.relative_to(root).as_posix()))
            for name in files:
                relative = (current / name).relative_to(root).as_posix()
                result.add(_safe_relative(relative))
        return result

    @staticmethod
    def _git_bytes(root: Path, relative: str) -> bytes:
        completed = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{relative}"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise WorkspaceGatewayError("baseline file could not be read")
        return completed.stdout

    @staticmethod
    def _git_mode(root: Path, relative: str) -> int:
        rendered = _run_git(root, ["ls-tree", "HEAD", "--", relative])
        try:
            git_mode = rendered.split(maxsplit=1)[0]
        except IndexError as error:
            raise WorkspaceGatewayError("baseline file mode could not be read") from error
        return 0o755 if git_mode == "100755" else 0o644

    @classmethod
    def _current_mode(cls, root: Path, target: Path, *, tracked: bool) -> int:
        if _run_git(root, ["config", "--bool", "core.filemode"]) == "true":
            return stat.S_IMODE(target.stat().st_mode)
        if tracked:
            return cls._git_mode(root, target.relative_to(root).as_posix())
        return 0o644

    def load(self, bundle: CapturedChangeBundle) -> dict[str, object]:
        payload = self._raw_store.read(bundle.raw_reference)
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkspaceGatewayError("encrypted change bundle is invalid") from error
        if not isinstance(value, dict):
            raise WorkspaceGatewayError("encrypted change bundle is invalid")
        if (
            value.get("session_id") != bundle.receipt.session_id
            or Sha256Digest(f"sha256:{bundle.raw_reference.sha256}")
            != bundle.receipt.encrypted_bundle_digest
        ):
            raise WorkspaceGatewayError("encrypted change bundle receipt binding changed")
        try:
            baseline = WorkspaceBaseline.model_validate_json(
                canonical_json(value["baseline"]), strict=True
            )
        except (KeyError, ValueError) as error:
            raise WorkspaceGatewayError("encrypted change bundle baseline is invalid") from error
        if canonical_digest(baseline) != bundle.receipt.baseline_digest:
            raise WorkspaceGatewayError("encrypted change bundle baseline binding changed")
        raw_changes = value.get("changes")
        if not isinstance(raw_changes, list):
            raise WorkspaceGatewayError("encrypted change bundle lacks file entries")
        reconstructed: list[WorkspaceFileChange] = []
        for raw in raw_changes:
            if not isinstance(raw, dict):
                raise WorkspaceGatewayError("encrypted change bundle file entry is invalid")
            before = RecoverableChangeApplier._decode_optional(raw.get("before"))
            after = RecoverableChangeApplier._decode_optional(raw.get("after"))
            before_mode = RecoverableChangeApplier._decode_mode(raw.get("before_mode"))
            after_mode = RecoverableChangeApplier._decode_mode(raw.get("after_mode"))
            operation = raw.get("operation")
            if operation not in {"add", "modify", "delete"}:
                raise WorkspaceGatewayError("encrypted change bundle operation is invalid")
            reconstructed.append(
                WorkspaceFileChange(
                    path=_safe_relative(str(raw.get("path", ""))),
                    operation=operation,
                    before_digest=None if before is None else _digest_bytes(before),
                    after_digest=None if after is None else _digest_bytes(after),
                    before_mode=before_mode,
                    after_mode=after_mode,
                    size_bytes=0 if after is None else len(after),
                    binary=(b"\x00" in (after if after is not None else before or b"")),
                )
            )
        if (
            tuple(reconstructed) != bundle.receipt.changes
            or sum(item.size_bytes for item in reconstructed) != bundle.receipt.total_bytes
        ):
            raise WorkspaceGatewayError("encrypted change bundle file binding changed")
        return value


class RecoverableChangeApplier:
    """Apply one exact bundle to an unchanged canonical tree and roll back on failure."""

    def __init__(self, bundle_store: EncryptedChangeBundleStore) -> None:
        self._bundle_store = bundle_store

    def apply(
        self,
        bundle: CapturedChangeBundle,
        *,
        canonical_root: Path,
        expected_head: str,
        verification_specs: tuple[VerificationCommandSpec, ...],
        verifier: IndependentVerifier,
        recorded_at: datetime | None = None,
    ) -> tuple[ChangeApplicationReceipt, tuple[VerificationReceipt, ...]]:
        root = canonical_root.expanduser().resolve()
        now = recorded_at or datetime.now(UTC)
        if _run_git(root, ["rev-parse", "HEAD"]) != expected_head:
            return self._refused(bundle, expected_head, now, "stale_head"), ()
        if _run_git(root, ["status", "--porcelain=v1", "--untracked-files=all"]):
            return self._refused(bundle, expected_head, now, "dirty_worktree"), ()
        value = self._bundle_store.load(bundle)
        raw_changes = value.get("changes")
        if not isinstance(raw_changes, list):
            raise WorkspaceGatewayError("change bundle lacks its file payloads")
        backups: dict[Path, tuple[bytes | None, int | None]] = {}
        receipts: tuple[VerificationReceipt, ...] = ()
        try:
            for raw in raw_changes:
                if not isinstance(raw, dict):
                    raise WorkspaceGatewayError("change bundle contains an invalid file entry")
                relative = _safe_relative(str(raw.get("path", "")))
                target = (root / relative).resolve()
                if target != root / relative or not target.is_relative_to(root):
                    raise WorkspaceGatewayError("change path escaped the canonical repository")
                before = self._decode_optional(raw.get("before"))
                after = self._decode_optional(raw.get("after"))
                before_mode = self._decode_mode(raw.get("before_mode"))
                after_mode = self._decode_mode(raw.get("after_mode"))
                actual = target.read_bytes() if target.is_file() else None
                actual_mode = (
                    before_mode
                    if target.is_file()
                    and _run_git(root, ["config", "--bool", "core.filemode"]) != "true"
                    else stat.S_IMODE(target.stat().st_mode)
                    if target.is_file()
                    else None
                )
                if actual != before or actual_mode != before_mode:
                    raise WorkspaceGatewayError("canonical file changed after bundle capture")
                backups[target] = (actual, actual_mode)
                self._write_or_delete(target, after, mode=after_mode)
            receipts = verifier.run(
                session_id=f"apply-{bundle.receipt.session_id}",
                workspace=root,
                specs=verification_specs,
            )
            if any(item.exit_code != 0 or item.timed_out for item in receipts):
                raise WorkspaceGatewayError("independent post-apply verification failed")
        except BaseException as error:
            for target, (before, before_mode) in backups.items():
                self._write_or_delete(target, before, mode=before_mode)
            return (
                ChangeApplicationReceipt(
                    receipt_id=f"apply-{bundle.receipt.session_id}",
                    session_id=bundle.receipt.session_id,
                    change_receipt_digest=bundle.receipt.content_digest,
                    expected_head=expected_head,
                    status=ChangeApplicationStatus.ROLLED_BACK,
                    verification_receipt_digests=tuple(canonical_digest(item) for item in receipts),
                    recorded_at=now,
                    failure_class=type(error).__name__,
                ),
                receipts,
            )
        return (
            ChangeApplicationReceipt(
                receipt_id=f"apply-{bundle.receipt.session_id}",
                session_id=bundle.receipt.session_id,
                change_receipt_digest=bundle.receipt.content_digest,
                expected_head=expected_head,
                status=ChangeApplicationStatus.APPLIED,
                verification_receipt_digests=tuple(canonical_digest(item) for item in receipts),
                recorded_at=now,
            ),
            receipts,
        )

    @staticmethod
    def _decode_optional(value: object) -> bytes | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise WorkspaceGatewayError("change bundle file bytes are invalid")
        try:
            return base64.b64decode(value, validate=True)
        except ValueError as error:
            raise WorkspaceGatewayError("change bundle file bytes are invalid") from error

    @staticmethod
    def _decode_mode(value: object) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or not 0 <= value <= 0o777:
            raise WorkspaceGatewayError("change bundle file mode is invalid")
        return value

    @staticmethod
    def _write_or_delete(target: Path, value: bytes | None, *, mode: int | None) -> None:
        if value is None:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            if mode is not None:
                temporary.chmod(mode)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _refused(
        bundle: CapturedChangeBundle,
        expected_head: str,
        recorded_at: datetime,
        failure_class: str,
    ) -> ChangeApplicationReceipt:
        return ChangeApplicationReceipt(
            receipt_id=f"apply-{bundle.receipt.session_id}",
            session_id=bundle.receipt.session_id,
            change_receipt_digest=bundle.receipt.content_digest,
            expected_head=expected_head,
            status=ChangeApplicationStatus.REFUSED,
            verification_receipt_digests=(),
            recorded_at=recorded_at,
            failure_class=failure_class,
        )
