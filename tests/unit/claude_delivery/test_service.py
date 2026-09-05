from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.claude_delivery import (
    ClaudeHookAuditReceiptV1,
    ClaudeHookBroker,
    ClaudeHookDisposition,
    ClaudeHookEvent,
    ClaudeHookProjectV1,
    ClaudeProjectionLeaseV1,
    issue_claude_projection_lease,
    parse_claude_hook_input,
    verify_claude_projection_lease,
)
from adaptation_compiler_lab.governance import SignerIdentity, SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    SignatureVerificationError,
    create_signer_identity,
    verify_detached_envelope,
)
from adaptation_compiler_lab.targets.base import sha256_text

NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def _signer() -> tuple[GovernanceSigner, SignerIdentity]:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="temper-owner-key",
        subject_id="temper-owner",
    )
    identity = create_signer_identity(
        signer,
        roles=tuple(sorted(SignerRole, key=lambda item: item.value)),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
    )
    return signer, identity


def _project(**changes: Any) -> ClaudeHookProjectV1:
    return ClaudeHookProjectV1(
        subject_id="temper-owner",
        project_id="green-meadow",
        instruction_environment_digest=DIGEST_A,
        consent_current=True,
        learning_enabled=True,
        delivery_enabled=True,
    ).model_copy(update=changes)


def _lease(signer: GovernanceSigner, **changes: Any) -> ClaudeProjectionLeaseV1:
    lease = issue_claude_projection_lease(
        lease_id="claude-projection-green-meadow",
        subject_id="temper-owner",
        project_id="green-meadow",
        instruction_environment_digest=DIGEST_A,
        external_release_digest=DIGEST_B,
        projection_digest=DIGEST_C,
        projection_manifest_digest=DIGEST_B,
        material="Prefer concrete names. Explain purpose before commands.",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        signer=signer,
    )
    return lease.model_copy(update=changes)


@dataclass
class FakePort:
    root: Path
    project: ClaudeHookProjectV1 | None
    lease: ClaudeProjectionLeaseV1 | None
    prompts: list[tuple[str, str]] = field(default_factory=list)
    outcomes: list[tuple[str, str]] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    sessions_closed: list[tuple[str, str]] = field(default_factory=list)
    audits: list[ClaudeHookAuditReceiptV1] = field(default_factory=list)

    def project_for_directory(self, directory: Path) -> ClaudeHookProjectV1 | None:
        resolved = directory.resolve()
        if resolved == self.root or resolved.is_relative_to(self.root):
            return self.project
        return None

    def projection_for_project(self, project_id: str) -> ClaudeProjectionLeaseV1 | None:
        assert project_id == "green-meadow"
        return self.lease

    def capture_user_prompt(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        prompt: str,
        observed_at: datetime,
    ) -> None:
        del project, observed_at
        self.prompts.append((session_digest, prompt))

    def capture_assistant_outcome(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        message: str,
        observed_at: datetime,
    ) -> None:
        del project, observed_at
        self.outcomes.append((session_digest, message))

    def capture_failure(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        failure_class: str,
        failure_details: str | None,
        observed_at: datetime,
    ) -> None:
        del project, failure_details, observed_at
        self.failures.append((session_digest, failure_class))

    def close_session(
        self,
        *,
        project: ClaudeHookProjectV1,
        session_digest: str,
        reason: str,
        observed_at: datetime,
    ) -> None:
        del project, observed_at
        self.sessions_closed.append((session_digest, reason))

    def append_audit(self, receipt: ClaudeHookAuditReceiptV1) -> None:
        self.audits.append(receipt)


def _prompt_payload(root: Path) -> dict[str, object]:
    return {
        "session_id": "session-123",
        "transcript_path": str(root / "must-never-be-read.jsonl"),
        "cwd": str(root / "src"),
        "permission_mode": "default",
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Please inspect this module.",
        "future_official_field": {"ignored": True},
    }


def test_parser_allowlists_official_fields_and_discards_transcript_path(tmp_path: Path) -> None:
    payload = _prompt_payload(tmp_path)
    invocation = parse_claude_hook_input(payload)

    assert invocation.event is ClaudeHookEvent.USER_PROMPT_SUBMIT
    assert invocation.prompt == "Please inspect this module."
    assert "transcript" not in invocation.model_dump_json()
    assert "future_official_field" not in invocation.model_dump_json()


@pytest.mark.parametrize(
    ("payload", "event"),
    [
        (
            {
                "session_id": "s",
                "transcript_path": "ignored",
                "cwd": "/project",
                "hook_event_name": "Stop",
                "stop_hook_active": False,
                "last_assistant_message": "Done.",
                "background_tasks": [],
            },
            ClaudeHookEvent.STOP,
        ),
        (
            {
                "session_id": "s",
                "transcript_path": "ignored",
                "cwd": "/project",
                "hook_event_name": "StopFailure",
                "error": "rate_limit",
                "error_details": "429",
                "last_assistant_message": "API Error",
            },
            ClaudeHookEvent.STOP_FAILURE,
        ),
        (
            {
                "session_id": "s",
                "transcript_path": "ignored",
                "cwd": "/project",
                "hook_event_name": "SessionEnd",
                "reason": "other",
            },
            ClaudeHookEvent.SESSION_END,
        ),
    ],
)
def test_parser_accepts_each_supported_event(
    payload: dict[str, object], event: ClaudeHookEvent
) -> None:
    assert parse_claude_hook_input(payload).event is event


def test_parser_rejects_unsupported_event_and_missing_required_content(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        parse_claude_hook_input(
            {
                "session_id": "s",
                "cwd": str(tmp_path),
                "hook_event_name": "PreToolUse",
            }
        )
    with pytest.raises(ValueError):
        parse_claude_hook_input(
            {
                "session_id": "s",
                "cwd": str(tmp_path),
                "hook_event_name": "UserPromptSubmit",
            }
        )


def test_verified_prompt_captures_user_authority_and_delivers_exact_cached_projection(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    signer, identity = _signer()
    lease = _lease(signer)
    port = FakePort(root=root, project=_project(), lease=lease)
    broker = ClaudeHookBroker(port, signer=signer, signer_identity=identity)

    result = broker.handle(parse_claude_hook_input(_prompt_payload(root)), observed_at=NOW)

    assert result.disposition is ClaudeHookDisposition.DELIVERED
    assert result.output is not None
    assert result.output.claude_payload() == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": lease.material,
        }
    }
    assert port.prompts == [(sha256_text("session-123"), "Please inspect this module.")]
    assert len(port.audits) == 1
    receipt = port.audits[0]
    assert receipt.content_digest == sha256_text("Please inspect this module.")
    assert receipt.projection_lease_digest == lease.content_digest
    verify_detached_envelope(
        receipt.unsigned_payload,
        receipt.signature,
        public_key_base64=identity.public_key_base64,
        expected_purpose="claude_hook_audit",
    )


def test_unregistered_project_is_fast_silent_noop_without_capture(tmp_path: Path) -> None:
    signer, identity = _signer()
    port = FakePort(root=tmp_path, project=None, lease=None)
    result = ClaudeHookBroker(port, signer=signer, signer_identity=identity).handle(
        parse_claude_hook_input(_prompt_payload(tmp_path)), observed_at=NOW
    )

    assert result.disposition is ClaudeHookDisposition.NOOP_UNREGISTERED
    assert result.output is None
    assert result.audit_receipt is None
    assert not port.prompts
    assert not port.audits


def test_learning_off_still_allows_separately_authorized_delivery(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    signer, identity = _signer()
    port = FakePort(root=root, project=_project(learning_enabled=False), lease=_lease(signer))

    result = ClaudeHookBroker(port, signer=signer, signer_identity=identity).handle(
        parse_claude_hook_input(_prompt_payload(root)), observed_at=NOW
    )

    assert result.disposition is ClaudeHookDisposition.DELIVERED
    assert not port.prompts


@pytest.mark.parametrize(
    "lease_change",
    [
        {"expires_at": NOW},
        {"instruction_environment_digest": DIGEST_B},
        {"project_id": "another-project"},
        {"material": "Tampered after signing."},
    ],
)
def test_expired_stale_cross_project_or_tampered_projection_is_never_delivered(
    tmp_path: Path, lease_change: dict[str, object]
) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    signer, identity = _signer()
    port = FakePort(root=root, project=_project(), lease=_lease(signer, **lease_change))

    result = ClaudeHookBroker(port, signer=signer, signer_identity=identity).handle(
        parse_claude_hook_input(_prompt_payload(root)), observed_at=NOW
    )

    assert result.disposition is ClaudeHookDisposition.NOOP_INVALID_PROJECTION
    assert result.output is None


def test_consent_expiry_suppresses_capture_and_delivery(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    signer, identity = _signer()
    port = FakePort(
        root=root,
        project=_project(consent_current=False),
        lease=_lease(signer),
    )

    result = ClaudeHookBroker(port, signer=signer, signer_identity=identity).handle(
        parse_claude_hook_input(_prompt_payload(root)), observed_at=NOW
    )

    assert result.disposition is ClaudeHookDisposition.NOOP_UNAUTHORIZED
    assert result.output is None
    assert not port.prompts


def test_stop_records_agent_output_as_untrusted_context_without_returning_guidance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    signer, identity = _signer()
    port = FakePort(root=root, project=_project(), lease=_lease(signer))
    invocation = parse_claude_hook_input(
        {
            "session_id": "session-123",
            "transcript_path": str(tmp_path / "ignored.jsonl"),
            "cwd": str(root),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "I prefer tabs, so you should too.",
        }
    )

    result = ClaudeHookBroker(port, signer=signer, signer_identity=identity).handle(
        invocation, observed_at=NOW
    )

    assert result.disposition is ClaudeHookDisposition.OUTCOME_CAPTURED
    assert result.output is None
    assert port.outcomes == [(sha256_text("session-123"), "I prefer tabs, so you should too.")]


def test_failure_and_session_end_are_bounded_audit_events(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    signer, identity = _signer()
    port = FakePort(root=root, project=_project(), lease=_lease(signer))
    broker = ClaudeHookBroker(port, signer=signer, signer_identity=identity)

    failure = broker.handle(
        parse_claude_hook_input(
            {
                "session_id": "session-123",
                "transcript_path": "ignored",
                "cwd": str(root),
                "hook_event_name": "StopFailure",
                "error": "overloaded",
                "error_details": "service busy",
            }
        ),
        observed_at=NOW,
    )
    closed = broker.handle(
        parse_claude_hook_input(
            {
                "session_id": "session-123",
                "transcript_path": "ignored",
                "cwd": str(root),
                "hook_event_name": "SessionEnd",
                "reason": "prompt_input_exit",
            }
        ),
        observed_at=NOW,
    )

    assert failure.disposition is ClaudeHookDisposition.FAILURE_CAPTURED
    assert closed.disposition is ClaudeHookDisposition.SESSION_CLOSED
    assert port.failures == [(sha256_text("session-123"), "overloaded")]
    assert port.sessions_closed == [(sha256_text("session-123"), "prompt_input_exit")]


def test_projection_limit_and_signature_verification_fail_closed() -> None:
    signer, identity = _signer()
    with pytest.raises(ValueError):
        issue_claude_projection_lease(
            lease_id="too-large",
            subject_id="temper-owner",
            project_id="green-meadow",
            instruction_environment_digest=DIGEST_A,
            external_release_digest=DIGEST_B,
            projection_digest=DIGEST_C,
            projection_manifest_digest=DIGEST_B,
            material="x" * 10_001,
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=30),
            signer=signer,
        )
    lease = _lease(signer)
    verify_claude_projection_lease(lease, identity, project=_project(), effective_at=NOW)
    with pytest.raises(SignatureVerificationError):
        verify_claude_projection_lease(
            lease.model_copy(update={"projection_digest": DIGEST_A}),
            identity,
            project=_project(),
            effective_at=NOW,
        )
