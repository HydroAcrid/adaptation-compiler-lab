from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from adaptation_compiler_lab.autonomy import project_registry as registry_module
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


@pytest.mark.parametrize("replace_git_only", [False, True])
def test_replaced_repository_or_git_marker_invalidates_preview(app, tmp_path, replace_git_only):
    service, clock = app
    registry = registry_for(service, clock)
    root = repo(tmp_path, "second")
    preview = registry.preview([{"project_id": "second", "path": str(root)}])
    target = root / ".git" if replace_git_only else root
    target.rename(tmp_path / "original")
    if replace_git_only:
        (root / ".git").mkdir()
    else:
        repo(tmp_path, "second")
    with pytest.raises(AutonomyIntegrityError, match="identity changed after preview"):
        registry.register(preview["preview_token"], confirmed=True, key="replaced")
    assert "second" not in registry.projects()


@pytest.mark.parametrize("previously_registered", [False, True])
def test_physical_alias_cannot_claim_a_second_scope(
    app, tmp_path, monkeypatch, previously_registered
):
    service, clock = app
    registry = registry_for(service, clock)
    first, alias = repo(tmp_path, "first"), repo(tmp_path, "alias")
    selections = [{"project_id": "first", "path": str(first)}]
    if previously_registered:
        preview = registry.preview(selections)
        registry.register(preview["preview_token"], confirmed=True, key="first")
        selections = []
    actual_identity = registry_module._path_identity
    monkeypatch.setattr(
        registry_module,
        "_path_identity",
        lambda path: actual_identity(first) if path == alias else actual_identity(path),
    )
    with pytest.raises(AutonomyIntegrityError, match="two projects"):
        registry.preview([*selections, {"project_id": "alias", "path": str(alias)}])


def test_reading_registry_rechecks_physical_scope_collisions(app, tmp_path, monkeypatch):
    service, clock = app
    registry = registry_for(service, clock)
    first, other = repo(tmp_path, "first"), repo(tmp_path, "other")
    preview = registry.preview(
        [
            {"project_id": "first", "path": str(first)},
            {"project_id": "other", "path": str(other)},
        ]
    )
    registry.register(preview["preview_token"], confirmed=True, key="both")
    actual_identity = registry_module._path_identity
    monkeypatch.setattr(
        registry_module,
        "_path_identity",
        lambda path: actual_identity(first) if path == other else actual_identity(path),
    )
    with pytest.raises(AutonomyIntegrityError, match="two projects"):
        registry.projects()


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


def test_omitted_child_alias_cannot_fall_through_to_parent_grant(fixture, monkeypatch):
    f = fixture
    source = f["source"]
    alias = f["project"].parent / "child-alias"
    alias.mkdir()
    source.projects = {"parent": (alias.parent,), "project": (f["project"],)}
    source.most_specific_registered_root = True
    f["thread"]["cwd"] = str(alias)
    actual_identity = registry_module._path_identity
    monkeypatch.setattr(
        registry_module,
        "_path_identity",
        lambda path: actual_identity(f["project"]) if path == alias else actual_identity(path),
    )
    assert (
        source._eligible_project(f["thread"], source.grant.issued_at, source.clock()) == "project"
    )
    source.grant = source.grant.model_copy(update={"project_ids": ("parent",)})
    assert source._eligible_project(f["thread"], source.grant.issued_at, source.clock()) is None
