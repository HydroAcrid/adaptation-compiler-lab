from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from adaptation_compiler_lab.automatic_runtime import dogfood_cli
from adaptation_compiler_lab.desktop import runtime_migration
from adaptation_compiler_lab.domain import Scope
from adaptation_compiler_lab.governance.signing import sign_governance_event
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from tests.unit.automatic_runtime.test_runtime import _runtime


def config_fixture(tmp_path: Path) -> dogfood_cli.CodexDogfoodLocalConfig:
    runtime, policy = _runtime(tmp_path)
    policy = policy.model_copy(
        update={"scope": policy.scope.model_copy(update={"project_ids": ("project",)})}
    )
    authorization = runtime._authorization.model_dump(mode="json", exclude={"signature"})
    authorization["target_digest"] = policy.content_digest
    return dogfood_cli.CodexDogfoodLocalConfig(
        subject_id="kevin",
        repository_root=tmp_path / "project",
        state_root=tmp_path / "state",
        database_path=tmp_path / "state" / "runtime.sqlite3",
        raw_store_path=tmp_path / "state" / "raw",
        source_codex_home=tmp_path / "codex",
        codex_executable=tmp_path / "old-codex",
        runtime_pin_path=tmp_path / "old-pin",
        capture_after_epoch_seconds=100,
        policy=policy,
        policy_authorization=sign_governance_event(authorization, runtime._signer),
        signer_identity=runtime._identity,
        projects=(
            dogfood_cli.CodexDogfoodProjectConfig(
                project_id="project",
                root=tmp_path / "project",
                scope=Scope(
                    subject_ids=("kevin",), project_ids=("project",), target_families=("codex",)
                ),
            ),
        ),
    )


def test_endpoint_repair_preserves_identity_policy_and_cutoffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = config_fixture(tmp_path)
    executable, pin = tmp_path / "new-codex", tmp_path / "new-pin"
    executable.write_bytes(b"binary")
    pin.write_bytes(b"verified pin")
    path = tmp_path / "config.json"
    path.write_text(canonical_json(current))
    monkeypatch.setattr(runtime_migration, "_admit_legacy_binding", lambda path: False)
    monkeypatch.setattr(runtime_migration, "_registration_signer", lambda config: None)
    monkeypatch.setattr(runtime_migration, "select_product_codex_runtime_lock", lambda *args: pin)
    monkeypatch.setattr(runtime_migration, "persist_codex_runtime_lock", lambda *args: pin)
    migrated = []
    monkeypatch.setattr(
        runtime_migration,
        "_replace_config_with_credential_rebind",
        lambda path, before, after, **kwargs: migrated.append(after),
    )
    preview = runtime_migration.preview_runtime_endpoint_migration(path, executable)
    runtime_migration.apply_runtime_endpoint_migration(path, preview)
    updated = migrated[0]
    assert updated.codex_executable == executable.resolve()
    assert updated.runtime_pin_path == pin
    assert updated.policy == current.policy  # Expiry is not silently renewed.
    assert updated.policy_authorization == current.policy_authorization
    assert updated.signer_identity == current.signer_identity
    assert updated.subject_id == current.subject_id
    assert updated.projects == current.projects
    assert updated.capture_after_epoch_seconds == current.capture_after_epoch_seconds
    executable.write_bytes(b"different")
    with pytest.raises(ValueError, match="preview changed"):
        runtime_migration.apply_runtime_endpoint_migration(path, preview)


def test_verified_serialized_legacy_binding_and_rebind_failure_restore_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = config_fixture(tmp_path)
    path = tmp_path / "config.json"
    legacy = current.model_dump(mode="json")
    del legacy["watcher_idle_seconds"]
    path.write_text(json.dumps(legacy))
    expected = canonical_digest(legacy)

    class Store:
        def status(self):
            return SimpleNamespace(config_digest=expected)

        def rebind(self, **kwargs):
            assert kwargs["current_config_digest"] == expected
            raise OSError("secure store unavailable")

    monkeypatch.setattr(dogfood_cli, "platform_credential_store", lambda root: Store())
    updated = current.model_copy(update={"codex_executable": tmp_path / "new-codex"})
    with pytest.raises(OSError, match="secure store"):
        dogfood_cli._replace_config_with_credential_rebind(
            path, current, updated, serialized_legacy_binding=True
        )
    assert dogfood_cli._load_config(path) == current
    # A mismatched file is never rebound using an arbitrary envelope's advertised digest.
    path.write_text(canonical_json(current.model_copy(update={"capture_after_epoch_seconds": 999})))
    with pytest.raises(ValueError, match="configuration changed"):
        dogfood_cli._replace_config_with_credential_rebind(
            path, current, updated, serialized_legacy_binding=True
        )
