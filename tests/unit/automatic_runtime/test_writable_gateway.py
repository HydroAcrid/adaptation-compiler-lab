from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    ChangeApplicationStatus,
    VerificationCommandSpec,
)
from adaptation_compiler_lab.automatic_runtime.workspace_gateway import (
    CapturedChangeBundle,
    EncryptedChangeBundleStore,
    GitWorktreeProvider,
    IndependentVerifier,
    RecoverableChangeApplier,
    WorkspaceGatewayError,
    require_protected_paths_unchanged,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey

DIGEST = f"sha256:{'a' * 64}"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path, *, autocrlf: bool | None = None) -> Path:
    root = tmp_path / "canonical"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    if autocrlf is not None:
        _git(root, "config", "core.autocrlf", "true" if autocrlf else "false")
    (root / "kept.txt").write_text("before\n")
    (root / "deleted.txt").write_text("delete me\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return root


def _spec(expected: str = "after\n") -> tuple[VerificationCommandSpec, ...]:
    return (
        VerificationCommandSpec(
            command_id="focused-test",
            argv=(
                sys.executable,
                "-c",
                f"from pathlib import Path; assert Path('kept.txt').read_text() == {expected!r}",
            ),
            timeout_seconds=10,
        ),
    )


def test_verification_commands_are_explicitly_phase_scoped() -> None:
    postflight = VerificationCommandSpec(
        command_id="created-output",
        argv=(sys.executable, "-c", "raise SystemExit(0)"),
        applies_to="postflight",
    )
    shared = VerificationCommandSpec(
        command_id="shared",
        argv=(sys.executable, "-c", "raise SystemExit(0)"),
    )

    assert postflight.runs_during("preflight") is False
    assert postflight.runs_during("postflight") is True
    assert shared.runs_during("preflight") is True
    assert shared.runs_during("postflight") is True


@pytest.mark.parametrize("autocrlf", [False, True])
def test_capture_apply_and_independent_verification(tmp_path: Path, autocrlf: bool) -> None:
    canonical = _repository(tmp_path, autocrlf=autocrlf)
    (canonical / "kept.txt").unlink()
    (canonical / "deleted.txt").unlink()
    _git(canonical, "checkout-index", "--all", "--force")
    _git(canonical, "add", "--renormalize", ".")
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    workspace = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-1",
    )
    (workspace.root / "kept.txt").write_text("after\n")
    (workspace.root / "deleted.txt").unlink()
    (workspace.root / "added.txt").write_text("new\n")
    store = EncryptedChangeBundleStore(
        LocalRawPayloadStore(
            tmp_path / "raw",
            encryption_key=RawEncryptionKey(b"k" * 32),
        )
    )
    verification = IndependentVerifier().run(
        session_id="session-1",
        workspace=workspace.root,
        specs=_spec(),
    )
    bundle = store.capture(
        session_id="session-1",
        subject_id="kevin",
        workspace=workspace.root,
        baseline=workspace.baseline,
        release_digest=DIGEST,
        projection_digest=DIGEST,
        verification_receipts=verification,
    )
    provider.teardown(canonical_root=canonical, workspace=workspace.root)

    receipt, applied_verification = RecoverableChangeApplier(store).apply(
        bundle,
        canonical_root=canonical,
        expected_head=workspace.baseline.commit_sha,
        verification_specs=_spec(),
        verifier=IndependentVerifier(),
    )

    assert receipt.status is ChangeApplicationStatus.APPLIED
    assert all(item.exit_code == 0 for item in applied_verification)
    assert (canonical / "kept.txt").read_text() == "after\n"
    assert (canonical / "added.txt").read_text() == "new\n"
    assert not (canonical / "deleted.txt").exists()


def test_failed_post_apply_verification_rolls_back(tmp_path: Path) -> None:
    canonical = _repository(tmp_path)
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    workspace = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-2",
    )
    (workspace.root / "kept.txt").write_text("after\n")
    store = EncryptedChangeBundleStore(
        LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"z" * 32))
    )
    bundle = store.capture(
        session_id="session-2",
        subject_id="kevin",
        workspace=workspace.root,
        baseline=workspace.baseline,
        release_digest=DIGEST,
        projection_digest=DIGEST,
        verification_receipts=(),
    )
    provider.teardown(canonical_root=canonical, workspace=workspace.root)

    receipt, _ = RecoverableChangeApplier(store).apply(
        bundle,
        canonical_root=canonical,
        expected_head=workspace.baseline.commit_sha,
        verification_specs=_spec("impossible\n"),
        verifier=IndependentVerifier(),
    )

    assert receipt.status is ChangeApplicationStatus.ROLLED_BACK
    assert (canonical / "kept.txt").read_text() == "before\n"
    assert _git(canonical, "status", "--porcelain") == ""


def test_failed_application_recording_rolls_back_verified_changes(tmp_path: Path) -> None:
    canonical = _repository(tmp_path)
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    workspace = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-recording-failure",
    )
    (workspace.root / "kept.txt").write_text("after\n")
    store = EncryptedChangeBundleStore(
        LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"r" * 32))
    )
    bundle = store.capture(
        session_id="session-recording-failure",
        subject_id="kevin",
        workspace=workspace.root,
        baseline=workspace.baseline,
        release_digest=DIGEST,
        projection_digest=DIGEST,
        verification_receipts=(),
    )
    provider.teardown(canonical_root=canonical, workspace=workspace.root)

    def reject_recording(*_args: object) -> None:
        raise RuntimeError("ledger unavailable")

    receipt, verification = RecoverableChangeApplier(store).apply(
        bundle,
        canonical_root=canonical,
        expected_head=workspace.baseline.commit_sha,
        verification_specs=_spec(),
        verifier=IndependentVerifier(),
        verification_session_id="application-session-recording-failure",
        on_applied=reject_recording,
    )

    assert receipt.status is ChangeApplicationStatus.ROLLED_BACK
    assert receipt.failure_class == "RuntimeError"
    assert verification[0].session_id == "application-session-recording-failure"
    assert (canonical / "kept.txt").read_text() == "before\n"
    assert _git(canonical, "status", "--porcelain") == ""


def test_dirty_canonical_and_symlink_changes_fail_closed(tmp_path: Path) -> None:
    canonical = _repository(tmp_path)
    (canonical / "dirty.txt").write_text("uncommitted")
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    with pytest.raises(WorkspaceGatewayError, match="clean"):
        provider.create(
            canonical_root=canonical,
            project_id="fixture",
            session_id="session-3",
        )

    (canonical / "dirty.txt").unlink()
    workspace = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-4",
    )
    try:
        (workspace.root / "escape").symlink_to(tmp_path / "outside")
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    store = EncryptedChangeBundleStore(
        LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"x" * 32))
    )
    with pytest.raises(WorkspaceGatewayError, match="symlink"):
        store.capture(
            session_id="session-4",
            subject_id="kevin",
            workspace=workspace.root,
            baseline=workspace.baseline,
            release_digest=DIGEST,
            projection_digest=DIGEST,
            verification_receipts=(),
        )
    provider.teardown(canonical_root=canonical, workspace=workspace.root)


def test_agent_cannot_replace_independent_tests(tmp_path: Path) -> None:
    canonical = _repository(tmp_path)
    (canonical / "tests").mkdir()
    (canonical / "tests" / "test_trusted.py").write_text("assert True\n")
    _git(canonical, "add", ".")
    _git(canonical, "commit", "-m", "trusted tests")
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    workspace = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-5",
    )
    (workspace.root / "tests" / "test_trusted.py").write_text("assert False\n")
    store = EncryptedChangeBundleStore(
        LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"q" * 32))
    )
    bundle = store.capture(
        session_id="session-5",
        subject_id="kevin",
        workspace=workspace.root,
        baseline=workspace.baseline,
        release_digest=DIGEST,
        projection_digest=DIGEST,
        verification_receipts=(),
    )

    with pytest.raises(WorkspaceGatewayError, match="protected"):
        require_protected_paths_unchanged(bundle.receipt, protected_paths=("tests",))

    provider.teardown(canonical_root=canonical, workspace=workspace.root)


def test_change_receipt_cannot_be_substituted_onto_another_raw_bundle(tmp_path: Path) -> None:
    canonical = _repository(tmp_path)
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    store = EncryptedChangeBundleStore(
        LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"r" * 32))
    )
    first = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-6",
    )
    (first.root / "kept.txt").write_text("first\n")
    first_bundle = store.capture(
        session_id="session-6",
        subject_id="kevin",
        workspace=first.root,
        baseline=first.baseline,
        release_digest=DIGEST,
        projection_digest=DIGEST,
        verification_receipts=(),
    )
    second = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-7",
    )
    (second.root / "kept.txt").write_text("second\n")
    second_bundle = store.capture(
        session_id="session-7",
        subject_id="kevin",
        workspace=second.root,
        baseline=second.baseline,
        release_digest=DIGEST,
        projection_digest=DIGEST,
        verification_receipts=(),
    )

    with pytest.raises(WorkspaceGatewayError, match="binding"):
        store.load(
            CapturedChangeBundle(
                receipt=first_bundle.receipt,
                raw_reference=second_bundle.raw_reference,
            )
        )

    provider.teardown(canonical_root=canonical, workspace=first.root)
    provider.teardown(canonical_root=canonical, workspace=second.root)


def test_independent_verifier_scrubs_keys_and_times_out_process_group(tmp_path: Path) -> None:
    verifier = IndependentVerifier(
        base_environment={"PATH": str(Path(sys.executable).parent), "OPENAI_API_KEY": "secret"}
    )
    specs = (
        VerificationCommandSpec(
            command_id="secret-check",
            argv=(
                sys.executable,
                "-c",
                "import os; assert 'OPENAI_API_KEY' not in os.environ",
            ),
            timeout_seconds=5,
        ),
        VerificationCommandSpec(
            command_id="timeout-check",
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            timeout_seconds=1,
        ),
    )

    receipts = verifier.run(session_id="limits", workspace=tmp_path, specs=specs)

    assert receipts[0].exit_code == 0
    assert receipts[0].timed_out is False
    assert receipts[1].timed_out is True


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object coverage")
def test_windows_verifier_uses_bounded_job_object(tmp_path: Path) -> None:
    specs = (
        VerificationCommandSpec(
            command_id="windows-pass",
            argv=(sys.executable, "-c", "print('ok')"),
            timeout_seconds=5,
        ),
        VerificationCommandSpec(
            command_id="windows-timeout",
            argv=(sys.executable, "-c", "import time; time.sleep(10)"),
            timeout_seconds=1,
        ),
    )

    receipts = IndependentVerifier().run(
        session_id="windows-job-object",
        workspace=tmp_path,
        specs=specs,
    )

    assert receipts[0].exit_code == 0
    assert receipts[0].timed_out is False
    assert receipts[1].timed_out is True


@pytest.mark.parametrize(
    ("path", "content"),
    [
        (".env", "SAFE_VALUE=ordinary\n"),
        ("notes.txt", "token = ghp_123456789012345678901234567890123456\n"),
    ],
)
def test_private_paths_and_secret_like_content_are_not_bundled(
    tmp_path: Path, path: str, content: str
) -> None:
    canonical = _repository(tmp_path)
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    workspace = provider.create(
        canonical_root=canonical,
        project_id="fixture",
        session_id="session-secret",
    )
    (workspace.root / path).write_text(content)
    store = EncryptedChangeBundleStore(
        LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"s" * 32))
    )

    with pytest.raises(WorkspaceGatewayError):
        store.capture(
            session_id="session-secret",
            subject_id="kevin",
            workspace=workspace.root,
            baseline=workspace.baseline,
            release_digest=DIGEST,
            projection_digest=DIGEST,
            verification_receipts=(),
        )

    provider.teardown(canonical_root=canonical, workspace=workspace.root)
