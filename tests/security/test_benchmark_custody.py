"""Property checks for benchmark signature tampering and held-out plaintext leakage."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from adaptation_compiler_lab.benchmark.custody import (
    CustodyEncryptionKey,
    ExternalCustodyStore,
)
from adaptation_compiler_lab.benchmark.models import FeasibilityDesign
from adaptation_compiler_lab.governance import (
    BlindedSplitManifest,
    BlindedTaskDescriptor,
    SignerRole,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    SignatureVerificationError,
    create_signer_identity,
    sign_custody_manifest,
    verify_signed_governance,
)
from adaptation_compiler_lab.serialization import canonical_digest

NOW = datetime(2026, 7, 22, 20, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def _split() -> BlindedSplitManifest:
    return BlindedSplitManifest(
        benchmark_id="benchmark-security-fixture",
        held_out_tasks=tuple(
            BlindedTaskDescriptor(
                blind_task_id=f"task-{index:012x}",
                blind_family_id=f"family-{index:012x}",
                stratum=stratum,
            )
            for index, stratum in enumerate(FeasibilityDesign().task_families, start=1)
        ),
    )


@settings(
    max_examples=16,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@given(secret=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=32, max_size=64))
def test_external_seal_never_persists_heldout_plaintext(tmp_path: Path, secret: str) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    store = ExternalCustodyStore(
        tmp_path / "external-custody",
        workspace_root=workspace,
        encryption_key=CustodyEncryptionKey(b"h" * 32),
    )
    payload = f"HELDOUT-SECRET-{secret}".encode()
    reference = store.seal(
        payload,
        benchmark_id="benchmark-security-fixture",
        split_manifest_digest=DIGEST,
    )

    assert payload not in store.location(reference).read_bytes()
    verification = store.verify(
        reference,
        benchmark_id="benchmark-security-fixture",
        split_manifest_digest=DIGEST,
    )
    assert verification.plaintext_digest == reference.plaintext_digest


@settings(max_examples=32)
@given(index=st.integers(min_value=0, max_value=63), bit=st.integers(min_value=0, max_value=7))
def test_any_custody_manifest_signature_bit_tamper_fails(index: int, bit: int) -> None:
    signer = GovernanceSigner(
        Ed25519PrivateKey.generate(),
        identity_id="custody-security-identity",
        subject_id="user-kevin",
    )
    identity = create_signer_identity(
        signer,
        roles=(SignerRole.CUSTODY,),
        created_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
    )
    split = _split()
    manifest = sign_custody_manifest(
        {
            "governance_type": "custody_manifest",
            "manifest_id": "custody-security-manifest",
            "schema_version": "1.0",
            "subject_id": "user-kevin",
            "benchmark_id": split.benchmark_id,
            "blinded_split": split.model_dump(mode="json"),
            "split_manifest_digest": canonical_digest(split),
            "sealed_bundle_digest": "sha256:" + "b" * 64,
            "sealed_plaintext_digest": "sha256:" + "c" * 64,
            "sealed_plaintext_bytes": 100,
            "encryption_algorithm": "AES-256-GCM",
            "storage_boundary": "outside_compiler_workspace",
            "policy_version": "1.0.0",
            "sealed_at": NOW.isoformat(),
        },
        signer,
    )
    signature = bytearray(base64.b64decode(manifest.signature.signature_base64))
    signature[index] ^= 1 << bit
    tampered = manifest.model_copy(
        update={
            "signature": manifest.signature.model_copy(
                update={"signature_base64": base64.b64encode(signature).decode("ascii")}
            )
        }
    )

    with pytest.raises(SignatureVerificationError):
        verify_signed_governance(tampered, identity)
