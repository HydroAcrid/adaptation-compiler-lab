from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from adaptation_compiler_lab.dogfood import (
    PUBLIC_DOGFOOD_SUBJECT,
    LongitudinalDogfoodCompiler,
    public_dogfood_transitions,
)
from adaptation_compiler_lab.governance import SignerIdentity, SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
)
from adaptation_compiler_lab.runtime import (
    ExternalGovernedRelease,
    RuntimeTargetAuthorizationError,
    RuntimeTargetAuthorizationService,
    build_external_governed_releases,
)
from adaptation_compiler_lab.targets.models import TargetKind
from adaptation_compiler_lab.targets.profiles import default_target_profile

NOW = datetime(2026, 9, 5, 16, tzinfo=UTC)


def _release() -> ExternalGovernedRelease:
    transitions = public_dogfood_transitions()
    result = LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
        transitions
    )
    return cast(
        tuple[ExternalGovernedRelease, ExternalGovernedRelease, ExternalGovernedRelease],
        build_external_governed_releases(transitions, result),
    )[-1]


def _service(
    root: Path,
    *,
    now: datetime = NOW,
    signer: GovernanceSigner | None = None,
    identity: SignerIdentity | None = None,
) -> RuntimeTargetAuthorizationService:
    selected_signer = signer or GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="target-authorization-signer",
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
    )
    selected_identity = identity or create_signer_identity(
        selected_signer,
        roles=(SignerRole.ACTIVATION, SignerRole.REVIEW),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=365),
    )
    return RuntimeTargetAuthorizationService(
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
        signer=selected_signer,
        signer_identity=selected_identity,
        state_root=root,
        now=lambda: now,
    )


def test_target_extension_requires_an_exact_preview_and_explicit_confirmation(
    tmp_path: Path,
) -> None:
    release = _release()
    service = _service(tmp_path)
    preview = service.preview(
        release=release,
        project_id="generated-cache",
        target_family="claude-code",
    )
    selected = tuple(item.artifact_ref for item in preview.items if not item.already_compatible)

    with pytest.raises(RuntimeTargetAuthorizationError, match="explicit"):
        service.apply(
            preview_token=preview.preview_token,
            release=release,
            selected_artifact_refs=selected,
            confirmed=False,
            idempotency_key="target-decision",
        )
    receipt = service.apply(
        preview_token=preview.preview_token,
        release=release,
        selected_artifact_refs=selected,
        confirmed=True,
        idempotency_key="target-decision",
    )

    assert receipt.decision == "authorize"
    assert (
        service.authorized_refs(
            release=release,
            project_id="generated-cache",
            target_family="claude-code",
        )
        == selected
    )
    assert (
        service.status(
            release=release,
            project_id="generated-cache",
            target_family="claude-code",
        ).state
        == "authorized"
    )


def test_target_extension_is_restart_safe_reversible_and_tamper_evident(
    tmp_path: Path,
) -> None:
    release = _release()
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="restart-signer",
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
    )
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.ACTIVATION, SignerRole.REVIEW),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=365),
    )
    service = _service(tmp_path, signer=signer, identity=identity)
    preview = service.preview(
        release=release,
        project_id="generated-cache",
        target_family="claude-code",
    )
    selected = tuple(item.artifact_ref for item in preview.items if not item.already_compatible)
    receipt = service.apply(
        preview_token=preview.preview_token,
        release=release,
        selected_artifact_refs=selected,
        confirmed=True,
        idempotency_key="authorize",
    )
    replay = service.apply(
        preview_token=preview.preview_token,
        release=release,
        selected_artifact_refs=selected,
        confirmed=True,
        idempotency_key="authorize",
    )
    assert replay == receipt

    restarted = _service(tmp_path, signer=signer, identity=identity)
    assert (
        restarted.authorized_refs(
            release=release,
            project_id="generated-cache",
            target_family="claude-code",
        )
        == selected
    )

    revoke_preview = restarted.preview(
        release=release,
        project_id="generated-cache",
        target_family="claude-code",
    )
    revoked = restarted.apply(
        preview_token=revoke_preview.preview_token,
        release=release,
        selected_artifact_refs=(),
        confirmed=True,
        idempotency_key="revoke",
    )
    assert revoked.decision == "revoke"
    assert not restarted.authorized_refs(
        release=release,
        project_id="generated-cache",
        target_family="claude-code",
    )

    index = tmp_path / "runtime" / "target-authorizations.json"
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["entries"][0]["receipt"]["project_id"] = "another-project"
    index.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeTargetAuthorizationError, match="verification"):
        _service(tmp_path, signer=signer, identity=identity)


def test_new_release_artifacts_remain_unauthorized_until_reviewed(tmp_path: Path) -> None:
    first, second, _third = cast(
        tuple[ExternalGovernedRelease, ExternalGovernedRelease, ExternalGovernedRelease],
        build_external_governed_releases(
            public_dogfood_transitions(),
            LongitudinalDogfoodCompiler(default_target_profile(TargetKind.CODEX)).compile(
                public_dogfood_transitions()
            ),
        ),
    )
    service = _service(tmp_path)
    preview = service.preview(
        release=first,
        project_id="generated-cache",
        target_family="claude-code",
    )
    selected = tuple(item.artifact_ref for item in preview.items)
    service.apply(
        preview_token=preview.preview_token,
        release=first,
        selected_artifact_refs=selected,
        confirmed=True,
        idempotency_key="first-release",
    )

    authorized = service.authorized_refs(
        release=second,
        project_id="generated-cache",
        target_family="claude-code",
    )

    assert authorized == selected
    assert len(authorized) < len(second.active_artifacts)


def test_target_extension_rejects_a_stale_competing_preview(tmp_path: Path) -> None:
    release = _release()
    service = _service(tmp_path)
    stale_preview = service.preview(
        release=release,
        project_id="generated-cache",
        target_family="claude-code",
    )
    current_preview = service.preview(
        release=release,
        project_id="generated-cache",
        target_family="claude-code",
    )
    selected = tuple(
        item.artifact_ref for item in current_preview.items if not item.already_compatible
    )
    service.apply(
        preview_token=current_preview.preview_token,
        release=release,
        selected_artifact_refs=selected,
        confirmed=True,
        idempotency_key="current-preview",
    )

    with pytest.raises(RuntimeTargetAuthorizationError, match="changed after preview"):
        service.apply(
            preview_token=stale_preview.preview_token,
            release=release,
            selected_artifact_refs=(),
            confirmed=True,
            idempotency_key="stale-preview",
        )


def test_target_extension_requires_review_and_activation_signer_roles(
    tmp_path: Path,
) -> None:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="review-only-signer",
        subject_id=PUBLIC_DOGFOOD_SUBJECT,
    )
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.REVIEW,),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=365),
    )

    with pytest.raises(RuntimeTargetAuthorizationError, match="review and activation"):
        _service(tmp_path, signer=signer, identity=identity)
