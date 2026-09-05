"""Explicit user authorization for projecting exact artifacts to another target."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from adaptation_compiler_lab.domain import (
    ArtifactRef,
    FrozenModel,
    Identifier,
    NonEmptyStr,
    Sha256Digest,
    UtcDateTime,
)
from adaptation_compiler_lab.governance import (
    SignatureEnvelope,
    SignerIdentity,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
    verify_signed_governance,
)
from adaptation_compiler_lab.runtime.models import ExternalGovernedRelease
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.models import ArtifactRenderProjection

_AUTHORIZATION_WINDOW = timedelta(days=30)
_PREVIEW_WINDOW = timedelta(minutes=10)


class RuntimeTargetAuthorizationError(ValueError):
    """A portable target authorization was missing, stale, or incoherent."""


class RuntimeTargetAuthorizationItemV1(FrozenModel):
    """One approved artifact considered for an exact target extension."""

    artifact_ref: ArtifactRef
    behavior_summary: NonEmptyStr
    scope_summary: NonEmptyStr
    already_compatible: bool


class RuntimeTargetAuthorizationPreviewV1(FrozenModel):
    """Raw-free exact review of what a new target may receive."""

    preview_version: Literal["1.0.0"] = "1.0.0"
    preview_token: Identifier
    subject_id: Identifier
    project_id: Identifier
    target_family: Identifier
    source_release_digest: Sha256Digest
    current_authorization_digest: Sha256Digest | None = None
    items: tuple[RuntimeTargetAuthorizationItemV1, ...]
    currently_authorized_artifact_refs: tuple[ArtifactRef, ...] = ()
    expires_at: UtcDateTime
    provider_call_required: Literal[False] = False
    raw_paths_exposed: Literal[False] = False

    @field_validator("items")
    @classmethod
    def items_are_sorted_unique(
        cls, value: tuple[RuntimeTargetAuthorizationItemV1, ...]
    ) -> tuple[RuntimeTargetAuthorizationItemV1, ...]:
        keys = tuple(_ref_key(item.artifact_ref) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("target authorization items must be sorted and unique")
        return value

    @field_validator("currently_authorized_artifact_refs")
    @classmethod
    def current_refs_are_sorted_unique(
        cls, value: tuple[ArtifactRef, ...]
    ) -> tuple[ArtifactRef, ...]:
        if tuple(_ref_key(item) for item in value) != tuple(
            sorted({_ref_key(item) for item in value})
        ):
            raise ValueError("current target authorizations must be sorted and unique")
        return value


class RuntimeTargetAuthorizationReceiptV1(FrozenModel):
    """Signed replacement set for one project's target-specific artifact authority."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    subject_id: Identifier
    project_id: Identifier
    target_family: Identifier
    decision: Literal["authorize", "revoke"]
    source_release_digest: Sha256Digest
    authorized_artifact_refs: tuple[ArtifactRef, ...]
    previous_authorization_digest: Sha256Digest | None = None
    decided_at: UtcDateTime
    expires_at: UtcDateTime
    signature: SignatureEnvelope
    raw_paths_exposed: Literal[False] = False

    @field_validator("authorized_artifact_refs")
    @classmethod
    def refs_are_sorted_unique(cls, value: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
        if tuple(_ref_key(item) for item in value) != tuple(
            sorted({_ref_key(item) for item in value})
        ):
            raise ValueError("authorized artifact refs must be sorted and unique")
        return value

    @model_validator(mode="after")
    def decision_and_signature_are_exact(self) -> Self:
        if (self.decision == "authorize") != bool(self.authorized_artifact_refs):
            raise ValueError("target authorization decision does not match its artifact set")
        if self.expires_at <= self.decided_at:
            raise ValueError("target authorization expiry must follow its decision")
        if (
            self.signature.purpose != "runtime_target_authorization"
            or self.signature.signed_at != self.decided_at
        ):
            raise ValueError("target authorization signature metadata is inconsistent")
        return self

    @property
    def unsigned_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"signature"})

    @property
    def content_digest(self) -> Sha256Digest:
        return canonical_digest(self)


class RuntimeTargetAuthorizationStatusV1(FrozenModel):
    """Raw-free current target-extension status for product presentation."""

    status_version: Literal["1.0.0"] = "1.0.0"
    project_id: Identifier
    target_family: Identifier
    state: Literal["not_authorized", "authorized", "expired", "stale"]
    authorized_artifact_count: int = Field(ge=0)
    available_artifact_count: int = Field(ge=0)
    authorization_digest: Sha256Digest | None = None
    expires_at: UtcDateTime | None = None


class RuntimeTargetAuthorizationMutationV1(FrozenModel):
    """Raw-free renderer result for one signed target-authorization decision."""

    mutation_version: Literal["1.0.0"] = "1.0.0"
    receipt_id: Identifier
    decision: Literal["authorize", "revoke"]
    authorization_digest: Sha256Digest
    authorized_artifact_count: int = Field(ge=0)
    expires_at: UtcDateTime
    provider_call_required: Literal[False] = False
    raw_paths_exposed: Literal[False] = False


class RuntimeTargetAuthorizationService:
    """Persist exact reviewed target extensions without mutating source artifacts."""

    def __init__(
        self,
        *,
        subject_id: str,
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
        state_root: Path,
        now: Callable[[], datetime],
    ) -> None:
        if (
            signer.subject_id != subject_id
            or signer_identity.subject_id != subject_id
            or signer.identity_id != signer_identity.identity_id
            or signer.fingerprint != signer_identity.key_fingerprint
        ):
            raise RuntimeTargetAuthorizationError("target authorization signer changed")
        verify_signed_governance(signer_identity)
        if not {SignerRole.ACTIVATION, SignerRole.REVIEW} <= set(signer_identity.roles):
            raise RuntimeTargetAuthorizationError(
                "target authorization requires review and activation authority"
            )
        self._subject_id = subject_id
        self._signer = signer
        self._identity = signer_identity
        self._state_root = state_root.expanduser().resolve()
        self._now = now
        self._previews: dict[str, RuntimeTargetAuthorizationPreviewV1] = {}
        self._receipts: list[RuntimeTargetAuthorizationReceiptV1] = []
        self._idempotency: dict[str, tuple[Sha256Digest, RuntimeTargetAuthorizationReceiptV1]] = {}
        self._load()

    def preview(
        self,
        *,
        release: ExternalGovernedRelease,
        project_id: str,
        target_family: str,
    ) -> RuntimeTargetAuthorizationPreviewV1:
        now = self._now()
        current = self._current(project_id, target_family)
        current_refs = (
            ()
            if current is None or current.expires_at <= now
            else self._active_refs(release, current.authorized_artifact_refs)
        )
        items = tuple(
            sorted(
                (
                    RuntimeTargetAuthorizationItemV1(
                        artifact_ref=artifact.artifact_ref,
                        behavior_summary=artifact.behavioral_contract.intent,
                        scope_summary=_scope_summary(artifact.scope.project_ids),
                        already_compatible=_already_compatible(artifact, target_family),
                    )
                    for artifact in release.active_artifacts
                    if _applies_to_subject_project(
                        artifact,
                        subject_id=self._subject_id,
                        project_id=project_id,
                    )
                ),
                key=lambda item: _ref_key(item.artifact_ref),
            )
        )
        token = f"target-authorization-{secrets.token_hex(12)}"
        preview = RuntimeTargetAuthorizationPreviewV1(
            preview_token=token,
            subject_id=self._subject_id,
            project_id=project_id,
            target_family=target_family,
            source_release_digest=release.content_digest,
            current_authorization_digest=(None if current is None else current.content_digest),
            items=items,
            currently_authorized_artifact_refs=current_refs,
            expires_at=now + _PREVIEW_WINDOW,
        )
        self._previews[token] = preview
        return preview

    def apply(
        self,
        *,
        preview_token: str,
        release: ExternalGovernedRelease,
        selected_artifact_refs: tuple[ArtifactRef, ...],
        confirmed: bool,
        idempotency_key: str,
    ) -> RuntimeTargetAuthorizationReceiptV1:
        fingerprint = canonical_digest(
            {
                "action": "replace_runtime_target_authorization",
                "confirmed": confirmed,
                "preview_token": preview_token,
                "selected_artifact_refs": [
                    item.model_dump(mode="json") for item in selected_artifact_refs
                ],
            }
        )
        prior = self._idempotency.get(idempotency_key)
        if prior is not None:
            if prior[0] != fingerprint:
                raise RuntimeTargetAuthorizationError(
                    "idempotency key was reused for another target authorization"
                )
            return prior[1]
        if not confirmed:
            raise RuntimeTargetAuthorizationError("explicit target authorization is required")
        preview = self._previews.get(preview_token)
        now = self._now()
        verify_signed_governance(self._identity, effective_at=now)
        if preview is None or preview.expires_at <= now:
            raise RuntimeTargetAuthorizationError("target authorization preview expired")
        if release.content_digest != preview.source_release_digest:
            raise RuntimeTargetAuthorizationError("approved release changed after preview")
        current = self._current(preview.project_id, preview.target_family)
        current_digest = None if current is None else current.content_digest
        if current_digest != preview.current_authorization_digest:
            raise RuntimeTargetAuthorizationError("target authorization changed after preview")
        selected = tuple(sorted(selected_artifact_refs, key=_ref_key))
        if selected != tuple(sorted(set(selected), key=_ref_key)):
            raise RuntimeTargetAuthorizationError("target authorization selection is duplicated")
        selectable = {item.artifact_ref for item in preview.items if not item.already_compatible}
        if not set(selected) <= selectable:
            raise RuntimeTargetAuthorizationError(
                "target authorization selected an unavailable artifact"
            )
        previous = self._receipts[-1].content_digest if self._receipts else None
        placeholder = self._signer.envelope(
            {}, purpose="runtime_target_authorization", signed_at=now
        )
        draft = RuntimeTargetAuthorizationReceiptV1(
            receipt_id=f"target-authorization-{secrets.token_hex(12)}",
            subject_id=self._subject_id,
            project_id=preview.project_id,
            target_family=preview.target_family,
            decision="authorize" if selected else "revoke",
            source_release_digest=release.content_digest,
            authorized_artifact_refs=selected,
            previous_authorization_digest=previous,
            decided_at=now,
            expires_at=now + _AUTHORIZATION_WINDOW,
            signature=placeholder,
        )
        receipt = draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="runtime_target_authorization",
                    signed_at=now,
                )
            }
        )
        self._append(receipt, idempotency_key=idempotency_key, fingerprint=fingerprint)
        self._receipts.append(receipt)
        self._idempotency[idempotency_key] = (fingerprint, receipt)
        return receipt

    def authorized_refs(
        self,
        *,
        release: ExternalGovernedRelease,
        project_id: str,
        target_family: str,
        effective_at: datetime | None = None,
    ) -> tuple[ArtifactRef, ...]:
        current = self._current(project_id, target_family)
        at = effective_at or self._now()
        if current is None or current.decision != "authorize" or current.expires_at <= at:
            return ()
        return self._active_refs(release, current.authorized_artifact_refs)

    def authorization_digest(
        self,
        *,
        project_id: str,
        target_family: str,
        effective_at: datetime | None = None,
    ) -> Sha256Digest | None:
        current = self._current(project_id, target_family)
        at = effective_at or self._now()
        if current is None or current.decision != "authorize" or current.expires_at <= at:
            return None
        return current.content_digest

    def status(
        self,
        *,
        release: ExternalGovernedRelease,
        project_id: str,
        target_family: str,
    ) -> RuntimeTargetAuthorizationStatusV1:
        current = self._current(project_id, target_family)
        now = self._now()
        items = tuple(
            artifact
            for artifact in release.active_artifacts
            if _applies_to_subject_project(
                artifact,
                subject_id=self._subject_id,
                project_id=project_id,
            )
            and not _already_compatible(artifact, target_family)
        )
        refs = (
            () if current is None else self._active_refs(release, current.authorized_artifact_refs)
        )
        state: Literal["not_authorized", "authorized", "expired", "stale"]
        if current is None or current.decision == "revoke":
            state = "not_authorized"
        elif current.expires_at <= now:
            state = "expired"
        elif len(refs) != len(current.authorized_artifact_refs):
            state = "stale"
        else:
            state = "authorized"
        return RuntimeTargetAuthorizationStatusV1(
            project_id=project_id,
            target_family=target_family,
            state=state,
            authorized_artifact_count=len(refs) if state == "authorized" else 0,
            available_artifact_count=len(items),
            authorization_digest=(
                current.content_digest
                if current is not None and state != "not_authorized"
                else None
            ),
            expires_at=(None if current is None else current.expires_at),
        )

    def _current(
        self, project_id: str, target_family: str
    ) -> RuntimeTargetAuthorizationReceiptV1 | None:
        return next(
            (
                item
                for item in reversed(self._receipts)
                if item.project_id == project_id and item.target_family == target_family
            ),
            None,
        )

    @staticmethod
    def _active_refs(
        release: ExternalGovernedRelease,
        refs: tuple[ArtifactRef, ...],
    ) -> tuple[ArtifactRef, ...]:
        active = {item.artifact_ref for item in release.active_artifacts}
        return tuple(item for item in refs if item in active)

    @property
    def _path(self) -> Path:
        return self._state_root / "runtime" / "target-authorizations.json"

    def _append(
        self,
        receipt: RuntimeTargetAuthorizationReceiptV1,
        *,
        idempotency_key: str,
        fingerprint: Sha256Digest,
    ) -> None:
        value = self._read()
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise RuntimeTargetAuthorizationError("target authorization index is invalid")
        entries.append(
            {
                "idempotency_key": idempotency_key,
                "fingerprint": fingerprint,
                "receipt": receipt.model_dump(mode="json"),
            }
        )
        _atomic_replace(self._path, (canonical_json(value) + "\n").encode("utf-8"))

    def _load(self) -> None:
        value = self._read()
        entries = value.get("entries")
        if not isinstance(entries, list):
            raise RuntimeTargetAuthorizationError("target authorization index is invalid")
        previous: Sha256Digest | None = None
        for raw in entries:
            try:
                if not isinstance(raw, dict):
                    raise ValueError
                receipt = RuntimeTargetAuthorizationReceiptV1.model_validate_json(
                    canonical_json(raw["receipt"]), strict=True
                )
                key = str(raw["idempotency_key"])
                fingerprint = str(raw["fingerprint"])
                if (
                    receipt.subject_id != self._subject_id
                    or receipt.previous_authorization_digest != previous
                ):
                    raise ValueError
                verify_detached_envelope(
                    receipt.unsigned_payload,
                    receipt.signature,
                    public_key_base64=self._identity.public_key_base64,
                    expected_purpose="runtime_target_authorization",
                )
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeTargetAuthorizationError(
                    "target authorization index failed verification"
                ) from error
            self._receipts.append(receipt)
            self._idempotency[key] = (fingerprint, receipt)
            previous = receipt.content_digest

    def _read(self) -> dict[str, object]:
        if not self._path.exists():
            return {"entries": [], "version": 1}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeTargetAuthorizationError(
                "target authorization index is invalid"
            ) from error
        if not isinstance(value, dict) or value.get("version") != 1:
            raise RuntimeTargetAuthorizationError("target authorization index is invalid")
        return value


def _ref_key(value: ArtifactRef) -> tuple[str, str, str]:
    return value.record_id, value.record_version, value.content_digest


def _applies_to_subject_project(
    artifact: ArtifactRenderProjection,
    *,
    subject_id: str,
    project_id: str,
) -> bool:
    scope = artifact.scope
    return (
        (not scope.subject_ids or subject_id in scope.subject_ids)
        and (not scope.project_ids or project_id in scope.project_ids)
        and not artifact.revoked
    )


def _already_compatible(artifact: ArtifactRenderProjection, target_family: str) -> bool:
    return (
        not artifact.target_compatibility or target_family in artifact.target_compatibility
    ) and (not artifact.scope.target_families or target_family in artifact.scope.target_families)


def _scope_summary(project_ids: tuple[str, ...]) -> str:
    return (
        "Project-scoped behavior"
        if project_ids
        else "Core-wide behavior · this authorization applies only here"
    )


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise
