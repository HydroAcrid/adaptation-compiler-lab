"""Ed25519 key custody, canonical signing, and verification."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast, overload

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from adaptation_compiler_lab.domain.base import UtcDateTime
from adaptation_compiler_lab.domain.references import CaptureReceiptRef, ConsentReceiptRef
from adaptation_compiler_lab.governance.models import (
    CaptureReceipt,
    ConsentReceipt,
    GovernanceEvent,
    GovernanceEventType,
    SignatureEnvelope,
    SignedGovernanceObject,
    SignerIdentity,
    SignerRole,
)
from adaptation_compiler_lab.serialization.canonical import canonical_bytes, canonical_digest

SIGNING_KEY_FILE_ENV: Final = "ACLAB_SIGNING_KEY_FILE"
SIGNING_KEY_PASSPHRASE_ENV: Final = "ACLAB_SIGNING_KEY_PASSPHRASE"


class GovernanceKeyError(ValueError):
    """Raised when a key is absent, unsafe, incompatible, or cannot be decrypted."""


class SignatureVerificationError(ValueError):
    """Raised when signed governance content cannot be authenticated."""


def _fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _public_key_base64(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _outside(path: Path, forbidden_root: Path) -> bool:
    return not path.is_relative_to(forbidden_root)


def require_external_key_path(path: Path, *, workspace_root: Path) -> Path:
    """Resolve a key path and reject any path inside the workspace/repository root."""

    resolved = path.expanduser().resolve()
    root = workspace_root.expanduser().resolve()
    if not _outside(resolved, root):
        raise GovernanceKeyError("key files must remain outside the workspace")
    for parent in (resolved.parent, *resolved.parents):
        if (parent / ".git").exists():
            raise GovernanceKeyError("key files must remain outside every Git repository")
    return resolved


def write_new_private_key(
    path: Path,
    *,
    passphrase: str,
    workspace_root: Path,
) -> Ed25519PrivateKey:
    """Create one encrypted PKCS8 Ed25519 key without overwriting an existing file."""

    if not passphrase:
        raise GovernanceKeyError("signing-key passphrase is unavailable")
    resolved = require_external_key_path(path, workspace_root=workspace_root)
    if resolved.exists():
        raise GovernanceKeyError(f"refusing to overwrite signing key: {resolved}")
    if not resolved.parent.is_dir():
        raise GovernanceKeyError(f"signing-key parent does not exist: {resolved.parent}")
    private_key = Ed25519PrivateKey.generate()
    encoded = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase.encode("utf-8")),
    )
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        with suppress(OSError):
            resolved.chmod(0o600)
    except BaseException:
        resolved.unlink(missing_ok=True)
        raise
    return private_key


def load_private_key(
    path: Path,
    *,
    passphrase: str,
    workspace_root: Path,
) -> Ed25519PrivateKey:
    if not passphrase:
        raise GovernanceKeyError("signing-key passphrase is unavailable")
    resolved = require_external_key_path(path, workspace_root=workspace_root)
    try:
        encoded = resolved.read_bytes()
    except FileNotFoundError as error:
        raise GovernanceKeyError(f"signing key is unavailable: {resolved}") from error
    try:
        key = serialization.load_pem_private_key(encoded, password=passphrase.encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise GovernanceKeyError("signing key cannot be decrypted") from error
    if not isinstance(key, Ed25519PrivateKey):
        raise GovernanceKeyError("signing key is not Ed25519")
    return key


def load_private_key_from_environment(
    *, workspace_root: Path, environ: Mapping[str, str] | None = None
) -> Ed25519PrivateKey:
    environment = os.environ if environ is None else environ
    path = environment.get(SIGNING_KEY_FILE_ENV)
    passphrase = environment.get(SIGNING_KEY_PASSPHRASE_ENV)
    if not path or not passphrase:
        raise GovernanceKeyError(
            f"{SIGNING_KEY_FILE_ENV} and {SIGNING_KEY_PASSPHRASE_ENV} are required"
        )
    return load_private_key(Path(path), passphrase=passphrase, workspace_root=workspace_root)


def _unsigned_payload(value: SignedGovernanceObject) -> dict[str, object]:
    return cast(
        dict[str, object],
        value.model_dump(mode="json", round_trip=True, exclude={"signature"}),
    )


def _message(payload: Mapping[str, object], envelope: SignatureEnvelope) -> bytes:
    return canonical_bytes(
        {
            "canonicalization_version": envelope.canonicalization_version,
            "payload": dict(payload),
            "purpose": envelope.purpose,
            "signed_at": envelope.signed_at.isoformat(),
            "signer_identity_id": envelope.signer_identity_id,
        }
    )


@dataclass(frozen=True, slots=True)
class GovernanceSigner:
    """Dedicated key plus public identity metadata used to issue signed objects."""

    private_key: Ed25519PrivateKey
    identity_id: str
    subject_id: str

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.private_key.public_key())

    def envelope(
        self, payload: Mapping[str, object], *, purpose: str, signed_at: UtcDateTime
    ) -> SignatureEnvelope:
        unsigned = SignatureEnvelope(
            signer_identity_id=self.identity_id,
            key_fingerprint=self.fingerprint,
            purpose=purpose,
            signed_at=signed_at,
            signature_base64=base64.b64encode(b"\x00" * 64).decode("ascii"),
        )
        signature = self.private_key.sign(_message(payload, unsigned))
        return unsigned.model_copy(
            update={"signature_base64": base64.b64encode(signature).decode("ascii")}
        )


def create_signer_identity(
    signer: GovernanceSigner,
    *,
    roles: tuple[SignerRole, ...],
    created_at: UtcDateTime,
    expires_at: UtcDateTime | None = None,
) -> SignerIdentity:
    unsigned: dict[str, object] = {
        "governance_type": "signer_identity",
        "identity_id": signer.identity_id,
        "schema_version": "1.0",
        "subject_id": signer.subject_id,
        "public_key_base64": _public_key_base64(signer.private_key.public_key()),
        "key_fingerprint": signer.fingerprint,
        "roles": [role.value for role in roles],
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at is not None else None,
    }
    placeholder = signer.envelope(unsigned, purpose="signer_identity", signed_at=created_at)
    draft = SignerIdentity.model_validate_json(
        json.dumps({**unsigned, "signature": placeholder.model_dump(mode="json")})
    )
    normalized = _unsigned_payload(draft)
    envelope = signer.envelope(normalized, purpose="signer_identity", signed_at=created_at)
    return draft.model_copy(update={"signature": envelope})


def sign_consent(unsigned: Mapping[str, object], signer: GovernanceSigner) -> ConsentReceipt:
    issued_at = _timestamp(unsigned, "issued_at")
    placeholder = signer.envelope(unsigned, purpose="consent_receipt", signed_at=issued_at)
    draft = ConsentReceipt.model_validate_json(
        json.dumps({**unsigned, "signature": placeholder.model_dump(mode="json")})
    )
    normalized = _unsigned_payload(draft)
    envelope = signer.envelope(normalized, purpose="consent_receipt", signed_at=issued_at)
    return draft.model_copy(update={"signature": envelope})


def sign_capture(unsigned: Mapping[str, object], signer: GovernanceSigner) -> CaptureReceipt:
    captured_at = _timestamp(unsigned, "captured_at")
    placeholder = signer.envelope(unsigned, purpose="capture_receipt", signed_at=captured_at)
    draft = CaptureReceipt.model_validate_json(
        json.dumps({**unsigned, "signature": placeholder.model_dump(mode="json")})
    )
    normalized = _unsigned_payload(draft)
    envelope = signer.envelope(normalized, purpose="capture_receipt", signed_at=captured_at)
    return draft.model_copy(update={"signature": envelope})


def sign_governance_event(
    unsigned: Mapping[str, object], signer: GovernanceSigner
) -> GovernanceEvent:
    event_type = GovernanceEventType(str(unsigned.get("event_type")))
    purpose = {
        GovernanceEventType.REVIEW_DECISION: "review",
        GovernanceEventType.RELEASE_DECISION: "release",
        GovernanceEventType.ACTIVATION_DECISION: "activation",
        GovernanceEventType.CUSTODY_ACTION: "custody",
    }[event_type]
    occurred_at = _timestamp(unsigned, "occurred_at")
    placeholder = signer.envelope(unsigned, purpose=purpose, signed_at=occurred_at)
    draft = GovernanceEvent.model_validate_json(
        json.dumps({**unsigned, "signature": placeholder.model_dump(mode="json")})
    )
    normalized = _unsigned_payload(draft)
    envelope = signer.envelope(normalized, purpose=purpose, signed_at=occurred_at)
    return draft.model_copy(update={"signature": envelope})


def _timestamp(payload: Mapping[str, object], field: str) -> datetime:
    value = payload.get(field)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise GovernanceKeyError(f"{field} is required before signing")


def verify_signed_governance(
    value: SignedGovernanceObject,
    identity: SignerIdentity | None = None,
    *,
    effective_at: datetime | None = None,
) -> None:
    """Authenticate canonical bytes, signer binding, role, subject, and validity window."""

    signer_identity = value if isinstance(value, SignerIdentity) else identity
    if signer_identity is None:
        raise SignatureVerificationError("signer identity is required")
    envelope = value.signature
    if envelope.signer_identity_id != signer_identity.identity_id:
        raise SignatureVerificationError("signature identity does not match the supplied signer")
    if envelope.key_fingerprint != signer_identity.key_fingerprint:
        raise SignatureVerificationError("signature fingerprint does not match the supplied signer")
    if not isinstance(value, SignerIdentity) and value.subject_id != signer_identity.subject_id:
        raise SignatureVerificationError("signed object crossed its signer subject boundary")
    expected_role = _required_role(value)
    if expected_role is not None and expected_role not in signer_identity.roles:
        raise SignatureVerificationError(f"signer lacks required {expected_role.value} role")
    when = envelope.signed_at if effective_at is None else effective_at
    if when < signer_identity.created_at:
        raise SignatureVerificationError("signature predates signer identity")
    if signer_identity.expires_at is not None and when > signer_identity.expires_at:
        raise SignatureVerificationError("signer identity is expired")
    public_bytes = base64.b64decode(signer_identity.public_key_base64, validate=True)
    public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
    try:
        public_key.verify(
            base64.b64decode(envelope.signature_base64, validate=True),
            _message(_unsigned_payload(value), envelope),
        )
    except InvalidSignature as error:
        raise SignatureVerificationError("Ed25519 signature verification failed") from error


def _required_role(value: SignedGovernanceObject) -> SignerRole | None:
    if isinstance(value, ConsentReceipt):
        return SignerRole.CONSENT
    if isinstance(value, CaptureReceipt):
        return SignerRole.CONSENT
    if isinstance(value, GovernanceEvent):
        return {
            GovernanceEventType.REVIEW_DECISION: SignerRole.REVIEW,
            GovernanceEventType.RELEASE_DECISION: SignerRole.RELEASE,
            GovernanceEventType.ACTIVATION_DECISION: SignerRole.ACTIVATION,
            GovernanceEventType.CUSTODY_ACTION: SignerRole.CUSTODY,
        }[value.event_type]
    return None


@overload
def governance_ref(value: ConsentReceipt) -> ConsentReceiptRef: ...


@overload
def governance_ref(value: CaptureReceipt) -> CaptureReceiptRef: ...


def governance_ref(value: ConsentReceipt | CaptureReceipt) -> ConsentReceiptRef | CaptureReceiptRef:
    """Return an exact typed reference without exposing signed contents."""

    digest = canonical_digest(value)
    if isinstance(value, ConsentReceipt):
        return ConsentReceiptRef(object_id=value.receipt_id, content_digest=digest)
    return CaptureReceiptRef(object_id=value.receipt_id, content_digest=digest)
