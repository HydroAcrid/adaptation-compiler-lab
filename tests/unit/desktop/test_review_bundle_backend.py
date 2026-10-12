"""Regression for JSON timestamps in encrypted review bundles."""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptation_compiler_lab.automatic_runtime.gateway_models import ChangeApplicationReceipt
from adaptation_compiler_lab.automatic_runtime.workspace_gateway import (
    CapturedChangeBundle,
    EncryptedChangeBundleStore,
    GitWorktreeProvider,
)
from adaptation_compiler_lab.desktop import service as desktop_service
from adaptation_compiler_lab.desktop.service import CodexDogfoodDesktopBackend
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from tests.unit.automatic_runtime.test_writable_gateway import DIGEST, _repository


def test_encrypted_json_bundle_can_be_reviewed_and_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    original = (root / "kept.txt").read_bytes()
    provider = GitWorktreeProvider(tmp_path / "workspaces")
    workspace = provider.create(canonical_root=root, project_id="fixture", session_id="fictional")
    raw = LocalRawPayloadStore(tmp_path / "raw", encryption_key=RawEncryptionKey(b"k" * 32))
    try:
        (workspace.root / "kept.txt").write_bytes(b"after\n")
        bundle = EncryptedChangeBundleStore(raw).capture(
            session_id="fictional",
            subject_id="fixture",
            workspace=workspace.root,
            baseline=workspace.baseline,
            release_digest=DIGEST,
            projection_digest=DIGEST,
            verification_receipts=(),
        )
    finally:
        provider.teardown(canonical_root=root, workspace=workspace.root)
    decisions: list[ChangeApplicationReceipt] = []

    class BundleLedger:
        def change_bundle(self, session_id: str) -> CapturedChangeBundle:
            assert session_id == "fictional"
            return bundle

        def application(self, session_id: str) -> None:
            assert session_id == "fictional"

        def append_application_outcome(
            self, receipt: ChangeApplicationReceipt, verifications: tuple[object, ...]
        ) -> None:
            assert verifications == ()
            decisions.append(receipt)

    monkeypatch.setattr(desktop_service, "_load_config", lambda path: object())
    monkeypatch.setattr(desktop_service, "_gateway_ledger", lambda config: BundleLedger())
    monkeypatch.setattr(desktop_service, "_raw_store", lambda config: raw)
    backend = CodexDogfoodDesktopBackend(tmp_path / "fictional.json")
    review = backend.change_review(session_id="fictional")
    assert review.expected_head == workspace.baseline.commit_sha
    assert review.changed_files == ("kept.txt",)
    assert "-before" in review.diff_text and "+after" in review.diff_text
    backend.discard_changes(session_id="fictional")
    assert decisions[0].status.value == "discarded"
    assert decisions[0].expected_head == review.expected_head
    assert (root / "kept.txt").read_bytes() == original
