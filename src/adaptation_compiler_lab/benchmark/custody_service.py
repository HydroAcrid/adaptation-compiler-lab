"""High-level sealing and verification with mandatory signed access logging."""

from __future__ import annotations

from datetime import datetime

from adaptation_compiler_lab.benchmark.custody import (
    CustodyKeyError,
    ExternalCustodyStore,
    SealedBundleRef,
    SealVerification,
)
from adaptation_compiler_lab.benchmark.registry import BenchmarkRegistry
from adaptation_compiler_lab.governance import (
    BlindedSplitManifest,
    CustodyAccessEvent,
    CustodyAccessOutcome,
    CustodyManifest,
)
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    sign_custody_manifest,
)
from adaptation_compiler_lab.persistence.errors import IntegrityError, RecordNotFoundError
from adaptation_compiler_lab.serialization import canonical_digest


class CustodyCoordinatorError(ValueError):
    """The custody coordinator could not safely complete and log an operation."""


class CustodyCoordinator:
    """Bind opaque bytes to signed metadata while never returning held-out plaintext."""

    def __init__(self, store: ExternalCustodyStore, registry: BenchmarkRegistry) -> None:
        self._store = store
        self._registry = registry

    def seal(
        self,
        payload: bytes,
        *,
        manifest_id: str,
        blinded_split: BlindedSplitManifest,
        subject_id: str,
        policy_version: str,
        sealed_at: datetime,
        access_event_id: str,
        actor_identity: str,
        reason: str,
        signer: GovernanceSigner,
    ) -> tuple[CustodyManifest, CustodyAccessEvent]:
        """Seal an external bundle and atomically register its signed metadata/access entry."""

        if not payload:
            raise CustodyCoordinatorError("held-out bundle must not be empty")
        split_digest = canonical_digest(blinded_split)
        reference = self._store.seal(
            payload,
            benchmark_id=blinded_split.benchmark_id,
            split_manifest_digest=split_digest,
        )
        manifest = sign_custody_manifest(
            {
                "governance_type": "custody_manifest",
                "manifest_id": manifest_id,
                "schema_version": "1.0",
                "subject_id": subject_id,
                "benchmark_id": blinded_split.benchmark_id,
                "blinded_split": blinded_split.model_dump(mode="json"),
                "split_manifest_digest": split_digest,
                "sealed_bundle_digest": reference.sealed_bundle_digest,
                "sealed_plaintext_digest": reference.plaintext_digest,
                "sealed_plaintext_bytes": reference.plaintext_bytes,
                "encryption_algorithm": "AES-256-GCM",
                "storage_boundary": "outside_compiler_workspace",
                "policy_version": policy_version,
                "sealed_at": sealed_at.isoformat(),
            },
            signer,
        )
        event = self._registry.register_manifest(
            manifest,
            access_event_id=access_event_id,
            actor_identity=actor_identity,
            reason=reason,
            signer=signer,
        )
        return manifest, event

    def verify(
        self,
        manifest_id: str,
        *,
        access_event_id: str,
        actor_identity: str,
        occurred_at: datetime,
        signer: GovernanceSigner,
    ) -> SealVerification:
        """Authenticate a seal and always append an allowed/denied signed access entry."""

        manifest = self._registry.custody_manifest(manifest_id)
        reference = SealedBundleRef(
            sealed_bundle_digest=manifest.sealed_bundle_digest,
            plaintext_digest=manifest.sealed_plaintext_digest,
            plaintext_bytes=manifest.sealed_plaintext_bytes,
        )
        try:
            verification = self._store.verify(
                reference,
                benchmark_id=manifest.benchmark_id,
                split_manifest_digest=manifest.split_manifest_digest,
            )
        except (CustodyKeyError, IntegrityError, RecordNotFoundError) as error:
            self._registry.record_verification(
                manifest_id,
                event_id=access_event_id,
                outcome=CustodyAccessOutcome.DENIED,
                actor_identity=actor_identity,
                reason="Sealed-bundle verification failed without revealing payload content.",
                occurred_at=occurred_at,
                signer=signer,
            )
            raise CustodyCoordinatorError("sealed-bundle verification failed") from error
        self._registry.record_verification(
            manifest_id,
            event_id=access_event_id,
            outcome=CustodyAccessOutcome.ALLOWED,
            actor_identity=actor_identity,
            reason=(
                "Encrypted seal and split-manifest binding verified; plaintext was not returned."
            ),
            occurred_at=occurred_at,
            signer=signer,
        )
        return verification
