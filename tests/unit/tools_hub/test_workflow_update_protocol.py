"""Exercise owner-reviewed repository workflow updates through the desktop protocol."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from adaptation_compiler_lab.serialization.canonical import canonical_bytes
from adaptation_compiler_lab.tools_hub.portable_setup import SetupError
from adaptation_compiler_lab.tools_hub.protocol import HubProtocol
from adaptation_compiler_lab.tools_hub.service import HubService, project_key
from adaptation_compiler_lab.tools_hub.workflow_update import CANDIDATE_NAME

from .test_portable_setup import approve, connect, desktop, review
from .test_workflow_evaluation import Replay, publisher, signed_setup


class Workflow:
    def __init__(self, service: HubService, root: Path) -> None:
        self.replay = Replay(root)
        self.protocol = HubProtocol(service)
        connect(service)
        approve(self.protocol, review(self.protocol, self.replay.baseline_path))
        self.catalog = root / "private-catalog"
        self.catalog.mkdir()
        self.candidate = self.catalog / CANDIDATE_NAME
        self.package = signed_setup(self.candidate, self.replay.signer, draft=self.replay.draft)
        self.replay.save_manifest()

    def connect(self) -> dict[str, Any]:
        return self.call(
            "source", directory=str(self.catalog), replay=str(self.replay.manifest_path)
        )

    def call(self, operation: str, **params: Any) -> dict[str, Any]:
        return desktop(self.protocol, f"update.{operation}", project_id="repo", **params)

    def active(self) -> dict[str, Any]:
        return cast(dict[str, Any], desktop(self.protocol, "status", project_id="repo")["active"])


@pytest.fixture
def workflow(service: HubService, tmp_path: Path) -> Workflow:
    return Workflow(service, tmp_path)


def test_review_and_approve_update_then_restore_offline(
    workflow: Workflow, service: HubService
) -> None:
    store_path = service.portable_setups.path(project_key("repo"))
    assert "version" not in service.seals.read(store_path, "portable_setup")
    before = workflow.call("status")
    assert before == {"connected": False, "can_rollback": False, "available": False}
    active_revision = service.setup_status("repo")[2]
    assert workflow.connect() == {"connected": True}
    assert service.setup_status("repo")[2] == active_revision
    assert workflow.call("status") == {"connected": True, "can_rollback": False, "available": True}
    preview = workflow.call("preview")
    assert preview["active_digest"] == workflow.replay.baseline.digest
    assert preview["digest"] == workflow.package.digest
    assert preview["source_name"] == CANDIDATE_NAME
    assert preview["direction"] == "update"
    assert [preview[k] for k in ("baseline_passed", "candidate_passed", "assertion_count")] == [
        4,
        5,
        5,
    ]

    def apply(key: str | None) -> dict[str, Any]:
        return workflow.protocol.dispatch(
            "portable_setup.update.approve",
            {"project_id": "repo", "review_id": preview["review_id"]},
            idempotency_key=key,
        )

    with pytest.raises(SetupError, match="fresh approval"):
        apply(None)
    assert workflow.active()["digest"] == workflow.replay.baseline.digest
    key = uuid4().hex
    assert apply(key)["digest"] == workflow.package.digest
    assert apply(key)["digest"] == workflow.package.digest
    with pytest.raises(SetupError, match="Review this exact"):
        apply(uuid4().hex)

    assert service.seals.read(store_path, "portable_setup")["version"] == 2
    record = store_path.read_text(encoding="utf-8")
    assert "v1-marker" not in record
    assert "v2-marker" not in record
    assert str(workflow.catalog) not in record
    assert workflow.call("status") == {"connected": True, "can_rollback": True, "available": False}

    workflow.candidate.unlink()
    workflow.replay.manifest_path.unlink()
    workflow.catalog.rmdir()
    workflow.protocol = HubProtocol(service)
    assert workflow.call("status")["can_rollback"] is True
    rollback = workflow.call("rollback_preview")
    assert rollback["direction"] == "rollback"
    assert rollback["active_digest"] == workflow.package.digest
    assert rollback["digest"] == workflow.replay.baseline.digest
    assert workflow.call("approve", review_id=rollback["review_id"])["digest"] == (
        workflow.replay.baseline.digest
    )
    assert workflow.call("disconnect") == {"connected": False}
    assert workflow.call("status") == {
        "connected": False,
        "can_rollback": False,
        "available": False,
    }
    assert "version" not in service.seals.read(store_path, "portable_setup")


@pytest.mark.parametrize("changed", ["candidate", "replay", "directory", "source", "active"])
def test_review_goes_stale_without_overwriting_active(
    workflow: Workflow, service: HubService, changed: str
) -> None:
    workflow.connect()
    preview = workflow.call("preview")
    if changed == "candidate":
        workflow.candidate.unlink()
        signed_setup(workflow.candidate, workflow.replay.signer, draft=workflow.replay.draft)
    elif changed == "replay":
        manifest = workflow.replay.manifest_path
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    elif changed == "directory":
        workflow.catalog.rename(workflow.catalog.with_name("moved"))
        workflow.catalog.mkdir()
    elif changed == "source":
        desktop(HubProtocol(service), "update.disconnect", project_id="repo")
        workflow.connect()
    elif changed == "active":
        other = HubProtocol(service)
        approve(other, review(other, workflow.replay.baseline_path))

    with pytest.raises(SetupError, match=r"[Cc]hanged|unavailable") as error:
        workflow.call("approve", review_id=preview["review_id"])
    assert str(workflow.catalog) not in str(error.value)
    assert workflow.active()["digest"] == workflow.replay.baseline.digest
    with pytest.raises(SetupError, match="Review this exact"):
        workflow.call("approve", review_id=preview["review_id"])


def test_rejects_regression_and_untrusted_publisher(workflow: Workflow) -> None:
    workflow.connect()
    workflow.candidate.unlink()
    workflow.replay.draft["items"][1]["text"] = "marker"
    signed_setup(workflow.candidate, workflow.replay.signer, draft=workflow.replay.draft)
    with pytest.raises(SetupError, match="did not improve the trusted replay"):
        workflow.call("preview")

    workflow.candidate.unlink()
    signed_setup(workflow.candidate, publisher(), draft=workflow.replay.draft)
    status = workflow.call("status")
    assert status["available"] is False
    assert "different publisher" in status["issue"]
    with pytest.raises(SetupError, match="different publisher"):
        workflow.call("preview")
    assert workflow.active()["digest"] == workflow.replay.baseline.digest
    assert workflow.call("status")["can_rollback"] is False


def test_requires_independent_trusted_replay_and_desktop_approval(workflow: Workflow) -> None:
    in_catalog = workflow.catalog / "fixture.json"
    in_catalog.write_bytes(workflow.replay.manifest_path.read_bytes())
    with pytest.raises(SetupError, match="outside the workflow source folder"):
        workflow.call("source", directory=str(workflow.catalog), replay=str(in_catalog))
    assert workflow.call("status")["connected"] is False
    with pytest.raises(ValueError, match="Unsupported"):
        workflow.protocol.dispatch(
            "portable_setup.update.source",
            {"project_id": "repo", "directory": str(workflow.catalog), "replay": str(in_catalog)},
            agent=True,
        )


def test_legacy_record_supports_update(workflow: Workflow, service: HubService) -> None:
    grant, project, revision, package = service.setup_status("repo")
    assert package is not None
    key = project_key("repo")
    store = service.portable_setups
    state = {"grant_id": grant["grant_id"], "project": project, "revision": revision}
    nonce = os.urandom(12)
    ciphertext = store.cipher().encrypt(nonce, canonical_bytes(package), canonical_bytes(state))
    service.seals.write(
        store.path(key),
        {**state, "encrypted": base64.b64encode(nonce + ciphertext).decode("ascii")},
        "portable_setup",
    )

    assert workflow.connect() == {"connected": True}
    preview = workflow.call("preview")
    assert workflow.call("approve", review_id=preview["review_id"])["digest"] == (
        workflow.package.digest
    )
    assert workflow.call("rollback_preview")["digest"] == package.digest


def test_failed_atomic_publish_leaves_active_and_rollback_intact(
    workflow: Workflow, service: HubService, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow.connect()
    preview = workflow.call("preview")
    store_file = service.portable_setups.path(project_key("repo"))
    before = store_file.read_bytes()

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("write failed")

    with monkeypatch.context() as patch:
        patch.setattr(service.seals, "write", fail)
        with pytest.raises(OSError, match="write failed"):
            workflow.call("approve", review_id=preview["review_id"])
    assert store_file.read_bytes() == before
    assert workflow.active()["digest"] == workflow.replay.baseline.digest
    assert workflow.call("status")["can_rollback"] is False


def test_source_status_omits_paths_and_replay_data(workflow: Workflow) -> None:
    workflow.connect()
    workflow.replay.manifest_path.unlink()

    status = workflow.call("status")

    assert status["available"] is False
    assert "replay file is unavailable" in status["issue"]
    serialized = json.dumps(status)
    assert str(workflow.catalog) not in serialized
    assert workflow.replay.manifest_path.name not in serialized


def test_disconnect_preserves_rollback_and_stales_outstanding_review(workflow: Workflow) -> None:
    workflow.connect()
    preview = workflow.call("preview")
    workflow.call("approve", review_id=preview["review_id"])
    rollback = workflow.call("rollback_preview")

    assert workflow.call("disconnect") == {"connected": False}
    assert workflow.call("status")["can_rollback"] is True
    with pytest.raises(SetupError, match="source changed"):
        workflow.call("approve", review_id=rollback["review_id"])
    new_review = workflow.call("rollback_preview")
    result = workflow.call("approve", review_id=new_review["review_id"])
    assert result["digest"] == workflow.replay.baseline.digest


@pytest.mark.parametrize("direction", ["update", "rollback"])
def test_approval_rechecks_active_grant(
    workflow: Workflow, service: HubService, direction: str
) -> None:
    workflow.connect()
    preview = workflow.call("preview")
    if direction == "rollback":
        workflow.call("approve", review_id=preview["review_id"])
        preview = workflow.call("rollback_preview")
    current = workflow.active()["digest"]
    grant = service.grant(active=True)
    assert grant is not None
    service.seals.write(service.home / "permission.json", {**grant, "paused": True}, "permission")

    with pytest.raises(ValueError, match="not enabled"):
        workflow.call("approve", review_id=preview["review_id"])
    assert workflow.active()["digest"] == current


def test_replay_source_separation_is_case_insensitive(workflow: Workflow) -> None:
    alias = workflow.catalog.with_name(workflow.catalog.name.upper()) / "fixture.json"
    with pytest.raises(SetupError, match="outside the workflow source folder"):
        workflow.call("source", directory=str(workflow.catalog), replay=str(alias))
