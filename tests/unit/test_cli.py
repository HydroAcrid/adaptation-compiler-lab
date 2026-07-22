"""Focused tests for the explicit local-only CLI boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from adaptation_compiler_lab.cli import app
from adaptation_compiler_lab.domain import (
    ActorKind,
    ActorRef,
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
    ):
        assert command in result.output


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


def test_bundle_import_list_and_show_is_a_local_auditable_workflow(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)
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
    assert any(path.is_file() and path.read_text(encoding="utf-8") == text for path in raw_files)


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
