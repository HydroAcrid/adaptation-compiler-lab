"""Focused tests for the explicit local-only CLI boundary."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from adaptation_compiler_lab.automatic_runtime import dogfood_cli
from adaptation_compiler_lab.automatic_runtime.gateway_models import (
    CredentialEnvelopeMetadata,
)
from adaptation_compiler_lab.automatic_runtime.service import AutomaticRuntimeError
from adaptation_compiler_lab.cli import app
from adaptation_compiler_lab.connectors.pins import DEFAULT_DOGFOOD_RUNTIME_LOCK
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
    ApprovalDecision,
    AuthorityClass,
    ClaimType,
    Evidence,
    EvidenceState,
    Partition,
    PayloadReference,
    PermittedUse,
    PrivacyContext,
    RedactionState,
    Scope,
    SensitivityClass,
    SourceClass,
    SyntheticOrigin,
)
from adaptation_compiler_lab.governance.signing import write_new_private_key

runner = CliRunner()
NOW = datetime(2026, 7, 22, 16, 0, tzinfo=UTC)


def _initialize(tmp_path: Path, *, subject_id: str = "synthetic-user") -> Path:
    workspace = tmp_path / "workspace"
    result = runner.invoke(
        app,
        ["workspace", "init", str(workspace), "--subject-id", subject_id],
    )
    assert result.exit_code == 0, result.output
    return workspace


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _evidence(text: str) -> Evidence:
    encoded = text.encode("utf-8")
    raw_digest = hashlib.sha256(encoded).hexdigest()
    actor = ActorRef(actor_id="fixture-system", kind=ActorKind.SYSTEM, version="1.0.0")
    return Evidence(
        record_id="evidence-cli-1",
        record_version="1.0.0",
        created_at=NOW,
        created_by=actor,
        policy_version="1.0.0",
        observed_at=NOW,
        producer=actor,
        source_class=SourceClass.SYNTHETIC,
        authority_class=AuthorityClass.SYNTHETIC_ONLY,
        authority_reason="Synthetic CLI fixture authority only.",
        allowed_claim_types=(ClaimType.SYNTHETIC_EXPECTATION,),
        state=EvidenceState.RAW,
        redaction_state=RedactionState.NONE,
        payload=PayloadReference(
            locator=f"sha256/{raw_digest[:2]}/{raw_digest}",
            content_digest=f"sha256:{raw_digest}",
            media_type="text/plain",
            byte_length=len(encoded),
        ),
        synthetic_origin=SyntheticOrigin(
            fixture_id="fixture-cli",
            description="Synthetic CLI integration fixture.",
        ),
        scope=Scope(subject_ids=("synthetic-user",)),
        privacy=PrivacyContext(
            sensitivity=SensitivityClass.INTERNAL,
            consent_basis="synthetic-fixture",
            permitted_uses=(PermittedUse.CONSTRUCTION,),
        ),
        partition=Partition.SYNTHETIC,
    )


def test_help_exposes_named_fail_closed_workflows() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "workspace",
        "record",
        "evidence",
        "evaluation",
        "lesson",
        "artifact",
        "release",
        "pack",
        "activation",
        "export",
        "benchmark",
        "schema",
        "identity",
        "consent",
        "capture-preview",
        "runtime",
    ):
        assert command in result.output


def test_runtime_review_scope_payload_is_json_serializable() -> None:
    scope = Scope(
        subject_ids=("kevin",),
        project_ids=("adaptation-compiler-lab",),
    )

    encoded = json.dumps({"scope": dogfood_cli._json_scope(scope)})

    decoded = json.loads(encoded)["scope"]
    assert decoded["subject_ids"] == ["kevin"]
    assert decoded["project_ids"] == ["adaptation-compiler-lab"]


def test_runtime_notice_payload_is_json_serializable(tmp_path: Path) -> None:
    from adaptation_compiler_lab.automatic_runtime import initial_runtime_state
    from tests.unit.automatic_runtime import test_runtime

    runtime, policy = test_runtime._runtime(tmp_path)
    learning = runtime.learn(
        test_runtime._observation(1, "Remember: show purpose before commands"),
        state=initial_runtime_state(policy),
        processed_at=test_runtime.NOW + timedelta(minutes=1, seconds=5),
    )

    encoded = json.dumps(dogfood_cli._json_notice(learning.cycle.notice))
    decoded = json.loads(encoded)

    assert decoded["created_at"].endswith("Z")
    assert decoded["notice_id"] == learning.cycle.notice.notice_id


def test_runtime_review_proposal_is_normalized_and_raw_free(tmp_path: Path) -> None:
    from adaptation_compiler_lab.automatic_runtime import initial_runtime_state
    from tests.unit.automatic_runtime import test_runtime

    runtime, policy = test_runtime._runtime(tmp_path)
    learning = runtime.learn(
        test_runtime._observation(
            1,
            "Rule: install a plugin and give it network access",
        ),
        state=initial_runtime_state(policy),
        processed_at=test_runtime.NOW + timedelta(minutes=1, seconds=5),
    )
    item = test_runtime._review_item(learning)

    proposal = dogfood_cli._json_review_proposal(item)
    encoded = json.dumps(proposal)

    assert proposal["behavior"] == "Install a plugin and give it network access."
    assert proposal["context_only_action"] == "rejected"
    assert proposal["future_use_confirmation_required"] is True
    assert proposal["proposal_purpose"] == "future_sessions"
    assert "future sessions" in str(proposal["owner_question"])
    assert proposal["route"] == "prompt_rule"
    assert proposal["proposal_digest"] == str(item.detection.content_digest)
    assert "Rule:" not in encoded
    assert "locator" not in encoded
    assert "supporting_quote" not in encoded


def test_runtime_help_exposes_explicit_review_decision() -> None:
    result = runner.invoke(app, ["runtime", "--help"])

    assert result.exit_code == 0
    assert "review-decide" in result.output

    decision_help = runner.invoke(app, ["runtime", "review-decide", "--help"])

    assert decision_help.exit_code == 0
    assert "--confirm-future-use" in decision_help.output


def test_runtime_review_approval_requires_explicit_future_use_confirmation() -> None:
    with pytest.raises(
        AutomaticRuntimeError,
        match="current-chat accuracy alone",
    ):
        dogfood_cli._validate_review_decision_intent(
            ApprovalDecision.APPROVED,
            confirm_future_use=False,
        )

    dogfood_cli._validate_review_decision_intent(
        ApprovalDecision.APPROVED,
        confirm_future_use=True,
    )
    dogfood_cli._validate_review_decision_intent(
        ApprovalDecision.REJECTED,
        confirm_future_use=False,
    )

    with pytest.raises(
        AutomaticRuntimeError,
        match="valid only with an approved",
    ):
        dogfood_cli._validate_review_decision_intent(
            ApprovalDecision.REJECTED,
            confirm_future_use=True,
        )


def test_runtime_init_writes_no_secret_config_and_status_is_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    (source_home / "auth.json").write_text("{}", encoding="utf-8")
    target_home = tmp_path / "target-codex-home"
    target_home.mkdir()
    (target_home / "auth.json").write_text("{}", encoding="utf-8")
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    target_executable = tmp_path / "target-codex"
    target_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    target_executable.chmod(0o700)
    desktop_source = tmp_path / "desktop-source"
    desktop_source.mkdir()
    key_path = tmp_path / "governance.pem"
    passphrase = "correct horse battery staple"
    write_new_private_key(
        key_path,
        passphrase=passphrase,
        workspace_root=repository,
    )
    raw_key_path = tmp_path / "raw.key"
    raw_key = base64.b64encode(b"r" * 32).decode("ascii")
    raw_key_path.write_text(raw_key, encoding="ascii")
    monkeypatch.setenv("ACLAB_SIGNING_KEY_FILE", str(key_path))
    monkeypatch.setenv("ACLAB_SIGNING_KEY_PASSPHRASE", passphrase)
    monkeypatch.setenv("ACLAB_RAW_KEY_FILE", str(raw_key_path))

    open_calls: list[dict[str, object]] = []

    @contextmanager
    def fake_open_codex_dogfood(**kwargs: object) -> Iterator[None]:
        open_calls.append(kwargs)
        yield None

    monkeypatch.setattr(
        dogfood_cli,
        "open_codex_dogfood",
        fake_open_codex_dogfood,
    )
    state = tmp_path / "dogfood-state"
    initialized = runner.invoke(
        app,
        [
            "runtime",
            "init",
            "--state-root",
            str(state),
            "--repository-root",
            str(repository),
            "--project-root",
            str(repository),
            "--source-root",
            str(repository),
            "--source-root",
            str(desktop_source),
            "--codex-executable",
            str(executable),
            "--source-codex-home",
            str(source_home),
            "--subject-id",
            "kevin",
            "--project-id",
            "dogfood-project",
            "--target-codex-executable",
            str(target_executable),
            "--target-codex-home",
            str(target_home),
            "--target-runtime-pin",
            str(DEFAULT_DOGFOOD_RUNTIME_LOCK),
        ],
    )

    assert initialized.exit_code == 0, initialized.output
    config_path = state / "config.json"
    text = config_path.read_text(encoding="utf-8")
    assert passphrase not in text
    assert raw_key not in text
    assert "PRIVATE KEY" not in text
    config = dogfood_cli.CodexDogfoodLocalConfig.model_validate_json(text)
    assert (
        config.credential_binding_digest
        != config.model_copy(update={"gateway_model": "different-model"}).credential_binding_digest
    )
    assert config.effective_target_codex_executable == target_executable
    assert config.effective_target_codex_home == target_home
    assert config.gateway_windows_sandbox == "elevated"
    assert set(config.projects[0].effective_source_roots) == {
        desktop_source,
        repository,
    }
    assert [call["executable"] for call in open_calls] == [
        executable,
        target_executable,
    ]
    with dogfood_cli._isolated_target_home(config) as isolated_home:
        isolated_config = (isolated_home / "config.toml").read_text(encoding="utf-8")
        assert 'sandbox_mode = "workspace-write"' in isolated_config
        assert 'sandbox = "elevated"' in isolated_config
        assert (isolated_home / "auth.json").is_file()

    status = runner.invoke(
        app,
        ["runtime", "status", "--config", str(config_path)],
    )
    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["generation"] == 0

    gate = runner.invoke(
        app,
        ["runtime", "gate-report", "--config", str(config_path)],
    )
    assert gate.exit_code == 0, gate.output
    gate_payload = json.loads(gate.stdout)
    assert gate_payload["evidence_ready"] is False
    assert gate_payload["remaining_interactions"] == 20

    metadata = CredentialEnvelopeMetadata(
        envelope_id="credentials-kevin",
        subject_id="kevin",
        config_digest=f"sha256:{'a' * 64}",
        signer_fingerprint=f"sha256:{'b' * 64}",
        protector="windows-dpapi-current-user",
        ciphertext_digest=f"sha256:{'c' * 64}",
        enrolled_at=NOW,
    )

    class FakeCredentialStore:
        def __init__(self, _state_root: Path) -> None:
            pass

        def status(self) -> CredentialEnvelopeMetadata:
            return metadata

    monkeypatch.setattr(dogfood_cli, "DpapiCredentialStore", FakeCredentialStore)
    credential_status = runner.invoke(
        app,
        ["runtime", "credentials", "status", "--config", str(config_path)],
    )
    assert credential_status.exit_code == 0, credential_status.output
    credential_payload = json.loads(credential_status.stdout)
    assert credential_payload["enrolled"] is True
    assert credential_payload["metadata"]["envelope_id"] == "credentials-kevin"


def test_synthetic_identity_consent_and_capture_preview_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _initialize(tmp_path, subject_id="kevin")
    key_file = tmp_path / "keys" / "governance.pem"
    key_file.parent.mkdir()
    identity_file = tmp_path / "identity.json"
    consent_file = tmp_path / "consent.json"
    capture_file = tmp_path / "capture.json"
    monkeypatch.setenv("TEST_SIGNING_PASSPHRASE", "correct horse battery staple")
    identity_request = _write_json(
        tmp_path / "identity-request.json",
        {
            "identity_id": "kevin-governance-1",
            "subject_id": "kevin",
            "roles": ["activation", "consent", "custody", "release", "review"],
            "created_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=365)).isoformat(),
        },
    )

    created = runner.invoke(
        app,
        [
            "identity",
            "create",
            str(identity_request),
            "--key-file",
            str(key_file),
            "--passphrase-env",
            "TEST_SIGNING_PASSPHRASE",
            "--output",
            str(identity_file),
            "--workspace",
            str(workspace),
        ],
    )
    assert created.exit_code == 0, created.output
    assert key_file.exists()
    assert "PRIVATE KEY" not in identity_file.read_text(encoding="utf-8")

    monkeypatch.setenv("ACLAB_SIGNING_KEY_FILE", str(key_file))
    monkeypatch.setenv("ACLAB_SIGNING_KEY_PASSPHRASE", "correct horse battery staple")
    consent_request = _write_json(
        tmp_path / "consent-request.json",
        {
            "receipt_id": "consent-synthetic-1",
            "subject_id": "kevin",
            "source_selector": {
                "source_system": "synthetic_fixture",
                "selection_method": "synthetic_fixture",
                "source_ids": ["fixture-1"],
            },
            "scope": {"subject_ids": ["kevin"]},
            "permitted_uses": ["construction"],
            "issued_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=1)).isoformat(),
            "retention_until": (NOW + timedelta(days=30)).isoformat(),
            "policy_version": "1.0.0",
        },
    )
    issued = runner.invoke(
        app,
        [
            "consent",
            "issue",
            str(consent_request),
            "--identity-id",
            "kevin-governance-1",
            "--output",
            str(consent_file),
            "--workspace",
            str(workspace),
        ],
    )
    assert issued.exit_code == 0, issued.output

    capture_request = _write_json(
        tmp_path / "capture-request.json",
        {
            "receipt_id": "capture-synthetic-1",
            "subject_id": "kevin",
            "consent_receipt_id": "consent-synthetic-1",
            "source_selector": {
                "source_system": "synthetic_fixture",
                "selection_method": "synthetic_fixture",
                "source_ids": ["fixture-1"],
            },
            "source_version": "synthetic-1.0",
            "source_schema_digest": "sha256:" + "a" * 64,
            "payload_digest": "sha256:" + "b" * 64,
            "captured_at": (NOW + timedelta(minutes=1)).isoformat(),
            "synthetic": True,
        },
    )
    previewed = runner.invoke(
        app,
        [
            "capture-preview",
            "create",
            str(capture_request),
            "--identity-id",
            "kevin-governance-1",
            "--output",
            str(capture_file),
            "--workspace",
            str(workspace),
        ],
    )
    verified = runner.invoke(
        app,
        [
            "capture-preview",
            "verify",
            str(capture_file),
            str(consent_file),
            str(identity_file),
        ],
    )

    assert previewed.exit_code == 0, previewed.output
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.stdout)["valid"] is True


def test_identity_command_fails_closed_without_passphrase_key_material(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path, subject_id="kevin")
    request = _write_json(
        tmp_path / "identity-request.json",
        {
            "identity_id": "kevin-governance-1",
            "subject_id": "kevin",
            "roles": ["consent"],
            "created_at": NOW.isoformat(),
        },
    )

    result = runner.invoke(
        app,
        [
            "identity",
            "create",
            str(request),
            "--key-file",
            str(tmp_path / "missing-passphrase.pem"),
            "--passphrase-env",
            "INTENTIONALLY_UNSET_ACLAB_TEST_VALUE",
            "--workspace",
            str(workspace),
        ],
    )

    assert result.exit_code == 1
    assert "passphrase environment variable is unavailable" in result.output


def test_workspace_init_status_and_duplicate_init_fail_closed(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)

    status = runner.invoke(app, ["workspace", "status", "--workspace", str(workspace)])
    duplicate = runner.invoke(
        app,
        ["workspace", "init", str(workspace), "--subject-id", "synthetic-user"],
    )

    assert status.exit_code == 0
    assert json.loads(status.stdout)["record_total"] == 0
    assert duplicate.exit_code == 1
    assert "workspace already exists" in duplicate.output


def test_invalid_record_returns_structured_error_without_traceback(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["record", "validate", str(invalid)])

    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["type"] == "ValueError"
    assert "Traceback" not in result.output


def test_bundle_import_list_and_show_is_a_local_auditable_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _initialize(tmp_path)
    key_file = tmp_path / "raw-payload.key"
    key_file.write_text(base64.b64encode(os.urandom(32)).decode("ascii"), encoding="ascii")
    monkeypatch.setenv("ACLAB_RAW_KEY_FILE", str(key_file))
    text = "Synthetic feedback payload with no credentials."
    evidence = _evidence(text)
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "bundle_version": "1.0",
                "subject_id": "synthetic-user",
                "records": [evidence.model_dump(mode="json")],
                "raw_payloads": [
                    {
                        "evidence_record_id": evidence.record_id,
                        "evidence_record_version": evidence.record_version,
                        "media_type": "text/plain",
                        "source_path": "synthetic/input.txt",
                        "text": text,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    imported = runner.invoke(
        app,
        ["record", "import-bundle", str(bundle), "--workspace", str(workspace)],
    )
    listed = runner.invoke(app, ["evidence", "list", "--workspace", str(workspace)])
    shown = runner.invoke(
        app,
        [
            "evidence",
            "show",
            evidence.record_id,
            evidence.record_version,
            "--workspace",
            str(workspace),
        ],
    )

    assert imported.exit_code == 0, imported.output
    assert listed.exit_code == 0, listed.output
    assert shown.exit_code == 0, shown.output
    assert json.loads(listed.stdout)["evidence"][0]["record_id"] == evidence.record_id
    shown_payload = json.loads(shown.stdout)
    assert shown_payload["record_id"] == evidence.record_id
    assert text not in shown.stdout
    raw_files = tuple((workspace / "raw-evidence" / "sha256").glob("**/*"))
    assert any(
        path.is_file() and text.encode("utf-8") not in path.read_bytes() for path in raw_files
    )


def test_release_candidate_snapshots_have_explicit_list_and_show(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)
    request = tmp_path / "candidate.json"
    request.write_text(
        json.dumps(
            {
                "candidate_id": "candidate-cli-1",
                "candidate_version": "1.0.0",
                "created_at": NOW.isoformat(),
                "created_by": {
                    "actor_id": "candidate-author",
                    "kind": "agent",
                    "version": "1.0.0",
                },
                "policy_version": "1.0.0",
                "artifact_refs": [],
                "schema_versions": ["1.0.0"],
                "policy_versions": ["1.0.0"],
                "construction_boundary": {
                    "construction_cutoff": NOW.isoformat(),
                    "split_manifest_digest": "sha256:" + "a" * 64,
                    "custody_policy_version": "1.0.0",
                    "held_out_sealed": True,
                },
                "proposal_disposition_id": "proposal-cli-1",
                "proposal_rationale": "Propose an explicit empty release.",
            }
        ),
        encoding="utf-8",
    )

    created = runner.invoke(
        app,
        ["release", "candidate", "create", str(request), "--workspace", str(workspace)],
    )
    listed = runner.invoke(app, ["release", "candidate", "list", "--workspace", str(workspace)])
    shown = runner.invoke(
        app,
        [
            "release",
            "candidate",
            "show",
            "candidate-cli-1",
            "1.0.0",
            "proposal-cli-1",
            "--workspace",
            str(workspace),
        ],
    )

    assert created.exit_code == 0, created.output
    assert listed.exit_code == 0, listed.output
    assert shown.exit_code == 0, shown.output
    assert json.loads(listed.stdout)["snapshots"][0]["state"] == "proposed"
    assert json.loads(shown.stdout)["candidate_id"] == "candidate-cli-1"

    expiry = _write_json(
        tmp_path / "expiry.json",
        {
            "expired_at": (NOW + timedelta(minutes=1)).isoformat(),
            "actor": {"actor_id": "reviewer-1", "kind": "human_reviewer"},
            "disposition_id": "expiry-cli-1",
            "rationale": "Expire the unused synthetic proposal.",
        },
    )
    expired = runner.invoke(
        app,
        [
            "release",
            "candidate",
            "expire",
            "candidate-cli-1",
            "1.0.0",
            "proposal-cli-1",
            str(expiry),
            "--workspace",
            str(workspace),
        ],
    )

    assert expired.exit_code == 0, expired.output
    assert json.loads(expired.stdout)["state"] == "expired"


@pytest.mark.parametrize("group", ["lesson", "artifact"])
def test_proposal_commands_refuse_wrong_record_types_without_persisting(
    tmp_path: Path, group: str
) -> None:
    workspace = _initialize(tmp_path)
    wrong_record = _write_json(
        tmp_path / f"wrong-{group}.json",
        _evidence("Synthetic non-secret text.").model_dump(mode="json"),
    )

    proposed = runner.invoke(
        app,
        [group, "propose", str(wrong_record), "--workspace", str(workspace)],
    )
    listed = runner.invoke(app, [group, "list", "--workspace", str(workspace)])

    assert proposed.exit_code == 1
    assert f"requires a {'LessonCandidate' if group == 'lesson' else 'Artifact'}" in proposed.output
    assert listed.exit_code == 0, listed.output
    values = next(iter(json.loads(listed.stdout).values()))
    assert values == []


def test_activate_requires_explicit_confirmation_before_workspace_access(tmp_path: Path) -> None:
    missing_workspace = tmp_path / "missing"
    approval = tmp_path / "approval.json"
    approval.write_text("{}", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "activation",
            "activate",
            "staging",
            str(approval),
            "--release-id",
            "release-1",
            "--release-version",
            "1.0.0",
            "--target-pack-id",
            "pack-1",
            "--target-pack-version",
            "1.0.0",
            "--workspace",
            str(missing_workspace),
        ],
    )

    assert result.exit_code == 1
    assert "requires --confirm" in result.output
    assert not missing_workspace.exists()


def test_empty_release_compile_canary_activate_and_export_workflow(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)
    author = {
        "actor_id": "candidate-author",
        "kind": "agent",
        "version": "1.0.0",
    }
    reviewer = {"actor_id": "reviewer-1", "kind": "human_reviewer"}
    candidate_request = _write_json(
        tmp_path / "candidate-flow.json",
        {
            "candidate_id": "candidate-flow",
            "candidate_version": "1.0.0",
            "created_at": NOW.isoformat(),
            "created_by": author,
            "policy_version": "1.0.0",
            "artifact_refs": [],
            "schema_versions": ["1.0.0"],
            "policy_versions": ["1.0.0"],
            "construction_boundary": {
                "construction_cutoff": NOW.isoformat(),
                "split_manifest_digest": "sha256:" + "a" * 64,
                "custody_policy_version": "1.0.0",
                "held_out_sealed": True,
            },
            "proposal_disposition_id": "proposal-flow",
            "proposal_rationale": "Propose an explicit empty release.",
        },
    )
    created = runner.invoke(
        app,
        [
            "release",
            "candidate",
            "create",
            str(candidate_request),
            "--workspace",
            str(workspace),
        ],
    )
    assert created.exit_code == 0, created.output

    evaluated_at = NOW + timedelta(minutes=1)
    evaluation_request = _write_json(
        tmp_path / "evaluate.json",
        {
            "evaluated_at": evaluated_at.isoformat(),
            "evaluator": reviewer,
            "disposition_id": "evaluation-flow",
            "rationale": "Empty release gates pass.",
        },
    )
    evaluation_output = tmp_path / "evaluation-result.json"
    evaluated = runner.invoke(
        app,
        [
            "release",
            "candidate",
            "evaluate",
            "candidate-flow",
            "1.0.0",
            "proposal-flow",
            str(evaluation_request),
            "--workspace",
            str(workspace),
            "--output",
            str(evaluation_output),
        ],
    )
    assert evaluated.exit_code == 0, evaluated.output
    assert json.loads(evaluation_output.read_text(encoding="utf-8"))["report"]["passed"]

    approved_at = NOW + timedelta(minutes=2)
    release_approval = _write_json(
        tmp_path / "release-approval.json",
        {
            "decision": "approved",
            "approver": reviewer,
            "decided_at": approved_at.isoformat(),
            "policy_version": "1.0.0",
            "rationale": "Approve the explicit empty release.",
        },
    )
    approved = runner.invoke(
        app,
        [
            "release",
            "candidate",
            "approve",
            str(evaluation_output),
            str(release_approval),
            "--disposition-id",
            "approval-flow",
            "--workspace",
            str(workspace),
        ],
    )
    assert approved.exit_code == 0, approved.output

    released_at = NOW + timedelta(minutes=3)
    freeze_request = _write_json(
        tmp_path / "freeze.json",
        {
            "release_id": "release-flow",
            "record_version": "1.0.0",
            "release_version": "1.0.0",
            "released_at": released_at.isoformat(),
            "created_by": author,
            "disposition_id": "freeze-flow",
            "rationale": "Freeze the approved empty release.",
        },
    )
    frozen = runner.invoke(
        app,
        [
            "release",
            "candidate",
            "freeze",
            "candidate-flow",
            "1.0.0",
            "approval-flow",
            str(freeze_request),
            "--workspace",
            str(workspace),
        ],
    )
    assert frozen.exit_code == 0, frozen.output

    compiled_at = NOW + timedelta(minutes=4)
    pack_context = _write_json(
        tmp_path / "pack-context.json",
        {
            "record_id": "pack-flow",
            "record_version": "1.0.0",
            "created_at": compiled_at.isoformat(),
            "created_by": author,
            "policy_version": "1.0.0",
            "privacy": {
                "sensitivity": "internal",
                "consent_basis": "synthetic-fixture",
                "permitted_uses": ["target_delivery"],
                "review_state": "approved",
                "reviewed_by": reviewer,
                "reviewed_at": compiled_at.isoformat(),
            },
        },
    )
    compiled = runner.invoke(
        app,
        [
            "pack",
            "compile",
            "generic-json",
            "release-flow",
            "1.0.0",
            str(pack_context),
            "--output-name",
            "pack-flow",
            "--workspace",
            str(workspace),
        ],
    )
    assert compiled.exit_code == 0, compiled.output
    assert json.loads(compiled.stdout)["activated"] is False
    assert (workspace / "packs" / "pack-flow" / "adaptation-pack.json").is_file()

    canary_approval = _write_json(
        tmp_path / "canary-approval.json",
        {
            "decision": "approved",
            "approver": reviewer,
            "decided_at": (NOW + timedelta(minutes=5)).isoformat(),
            "policy_version": "1.0.0",
            "rationale": "Approve a local canary pointer.",
        },
    )
    canary = runner.invoke(
        app,
        [
            "activation",
            "canary",
            "test-environment",
            str(canary_approval),
            "--release-id",
            "release-flow",
            "--release-version",
            "1.0.0",
            "--target-pack-id",
            "pack-flow",
            "--target-pack-version",
            "1.0.0",
            "--workspace",
            str(workspace),
        ],
    )
    assert canary.exit_code == 0, canary.output

    activation_approval = _write_json(
        tmp_path / "activation-approval.json",
        {
            "decision": "approved",
            "approver": reviewer,
            "decided_at": (NOW + timedelta(minutes=6)).isoformat(),
            "policy_version": "1.0.0",
            "rationale": "Approve activation after canary review.",
        },
    )
    activated = runner.invoke(
        app,
        [
            "activation",
            "activate",
            "test-environment",
            str(activation_approval),
            "--release-id",
            "release-flow",
            "--release-version",
            "1.0.0",
            "--target-pack-id",
            "pack-flow",
            "--target-pack-version",
            "1.0.0",
            "--workspace",
            str(workspace),
            "--confirm",
        ],
    )
    status = runner.invoke(
        app,
        ["activation", "status", "test-environment", "--workspace", str(workspace)],
    )
    exported = runner.invoke(
        app,
        [
            "export",
            "sanitized",
            "release-flow",
            "1.0.0",
            "--output-name",
            "export-flow",
            "--workspace",
            str(workspace),
        ],
    )

    assert activated.exit_code == 0, activated.output
    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["action"] == "activate"
    assert exported.exit_code == 0, exported.output
    assert (workspace / "exports" / "export-flow" / "manifest.json").is_file()


def test_schema_export_is_explicit_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "schemas"
    first = runner.invoke(app, ["schema", "export", str(output)])
    second = runner.invoke(app, ["schema", "export", str(output)])

    assert first.exit_code == 0, first.output
    assert len(tuple(output.glob("*.schema.json"))) == 8
    assert second.exit_code == 1
    assert "new or empty" in second.output


@pytest.mark.parametrize("command", [["record", "show"], ["pack", "compile"]])
def test_missing_required_arguments_do_not_mutate(command: list[str]) -> None:
    result = runner.invoke(app, command)

    assert result.exit_code != 0
