from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.autonomy.project_registry import (
    LearningProjectRegistry,
    LearningProjectV1,
)
from adaptation_compiler_lab.autonomy.protocol import AutonomyProtocol
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError
from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_codex_source import fixture as fixture


def registry_for(service, clock):
    return LearningProjectRegistry(
        service.store,
        tuple(
            LearningProjectV1(
                project_id=key,
                root=str(path.resolve()),
                source_roots=(str(path.resolve()),),
                capture_after_epoch_seconds=int(clock().timestamp()),
            )
            for key, path in service.projects.items()
        ),
        clock=clock,
    )


def repo(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    return root


def test_registered_projects_survive_restart_without_enabling_observation_or_research(
    app, tmp_path
):
    service, clock = app
    grant = service.grant()
    registry = registry_for(service, clock)
    path = repo(tmp_path, "second")
    preview = registry.preview([{"project_id": "second", "path": str(path)}])
    registry.register(preview["preview_token"], confirmed=True, key="register-second")
    restarted = registry_for(service, clock)
    assert set(restarted.projects()) == {"project", "second"}
    assert service.grant() == grant
    assert grant.project_ids == ("project",)
    assert not service.switch("personalization")
    assert not service.episodes()
    assert restarted.projects()["second"].capture_after_epoch_seconds == int(clock().timestamp())
    # Registration has no legacy policy dependency or consent-renewal operation.
    assert not any("policy" in e["type"] or "research" in e["type"] for e in service.store.events())


def test_registration_rechecks_confirmation_head_and_repository_identity(app, tmp_path):
    service, clock = app
    registry = registry_for(service, clock)
    root = repo(tmp_path, "second")
    preview = registry.preview([{"project_id": "second", "path": str(root)}])
    with pytest.raises(AutonomyIntegrityError, match="confirmed"):
        registry.register(preview["preview_token"], confirmed=False, key="no")
    (root / ".git").rmdir()
    with pytest.raises(AutonomyIntegrityError, match="changed after preview"):
        registry.register(preview["preview_token"], confirmed=True, key="missing")
    (root / ".git").mkdir()
    service.store.append("concurrent", "test", {}, at=clock())
    with pytest.raises(AutonomyIntegrityError, match="current confirmed"):
        registry.register(preview["preview_token"], confirmed=True, key="stale")
    assert "second" not in registry.projects()


def test_registration_expiry_and_duplicate_roots_are_rejected(app, tmp_path):
    service, clock = app
    registry = registry_for(service, clock)
    root = repo(tmp_path, "second")
    with pytest.raises(AutonomyIntegrityError, match="two projects"):
        registry.preview(
            [{"project_id": "a", "path": str(root)}, {"project_id": "b", "path": str(root)}]
        )
    preview = registry.preview([{"project_id": "second", "path": str(root)}])
    clock.value += timedelta(minutes=16)
    with pytest.raises(AutonomyIntegrityError, match="current confirmed"):
        registry.register(preview["preview_token"], confirmed=True, key="expired")


def test_unrelated_repository_cannot_be_disguised_as_a_source_alias(app, tmp_path):
    service, clock = app
    registry = registry_for(service, clock)
    root, other = repo(tmp_path, "first"), repo(tmp_path, "other")
    with pytest.raises(AutonomyIntegrityError, match="same repository directory"):
        registry.preview(
            [{"project_id": "first", "path": str(root), "source_roots": [str(root), str(other)]}]
        )


def test_protocol_registration_is_digest_bound_and_recovers_interrupted_receipt(app, tmp_path):
    service, clock = app
    registry = registry_for(service, clock)
    service.background_worker = BackgroundHabitWorker(service, project_registry=registry)
    protocol = AutonomyProtocol(service)
    root = repo(tmp_path, "second")
    preview = protocol.dispatch(
        "autonomy.projects.preview",
        {"projects": [{"project_id": "second", "path": str(root)}]},
        expected_digest=None,
        idempotency_key=None,
    )
    params = {"preview_token": preview["preview_token"], "confirmed": True}
    with pytest.raises(AutonomyIntegrityError, match="state changed"):
        protocol.dispatch(
            "autonomy.projects.register", params, expected_digest="bad", idempotency_key="second"
        )
    registry.register(preview["preview_token"], confirmed=True, key="learning-projects-second")
    protocol.dispatch(
        "autonomy.projects.register",
        params,
        expected_digest=service.snapshot_digest,
        idempotency_key="second",
    )
    protocol.dispatch(
        "autonomy.projects.register", params, expected_digest="old", idempotency_key="second"
    )
    assert "second" in service.projects
    assert sum(e["type"] == "learning_projects_registered" for e in service.store.events()) == 1
    assert service.grant().project_ids == ("project",)


def test_cached_protocol_refreshes_projects_registered_by_another_instance(app, tmp_path):
    service, clock = app
    registry = registry_for(service, clock)
    service.background_worker = BackgroundHabitWorker(service, project_registry=registry)
    protocol = AutonomyProtocol(service)
    protocol.dispatch("autonomy.status", {}, expected_digest=None, idempotency_key=None)
    other = registry_for(service, clock)
    root = repo(tmp_path, "second")
    preview = other.preview([{"project_id": "second", "path": str(root)}])
    other.register(preview["preview_token"], confirmed=True, key="other")
    protocol.dispatch("autonomy.status", {}, expected_digest=None, idempotency_key=None)
    assert "second" in service.projects


def test_nested_repository_uses_specific_scope_and_cannot_leak_to_granted_parent(fixture):
    f = fixture
    source = f["source"]
    parent = f["project"].parent
    source.projects = {"parent": (parent,), "project": (f["project"],)}
    source.most_specific_registered_root = True
    assert (
        source._eligible_project(f["thread"], source.grant.issued_at, source.clock()) == "project"
    )
    source.grant = source.grant.model_copy(update={"project_ids": ("parent",)})
    assert source._eligible_project(f["thread"], source.grant.issued_at, source.clock()) is None


def test_nested_scope_still_rejects_ambiguous_equal_roots(fixture):
    source = fixture["source"]
    source.projects = {"project": (fixture["project"],), "other": (fixture["project"],)}
    source.most_specific_registered_root = True
    with pytest.raises(AutonomyIntegrityError, match="overlapping"):
        source._eligible_project(fixture["thread"], source.grant.issued_at, source.clock())
