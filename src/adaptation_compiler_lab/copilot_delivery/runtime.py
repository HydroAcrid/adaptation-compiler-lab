"""No-model governed runtime for Copilot CLI prompt transformation."""

from __future__ import annotations

import base64
import os
import secrets
import tempfile
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.copilot_delivery.models import (
    CopilotDeliveryReceiptV1,
    CopilotHookAuthorizationV1,
    CopilotHookDisposition,
    CopilotHookInvocationV1,
    CopilotHookOutputV1,
    CopilotHookResultV1,
    CopilotProjectionLeaseV1,
    CopilotProjectionManifestV1,
)
from adaptation_compiler_lab.copilot_delivery.projection import (
    COPILOT_CLI_TARGET_FAMILY,
    build_copilot_projection_manifest,
    render_copilot_hook_projection,
)
from adaptation_compiler_lab.governance import SignerIdentity
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
    verify_signed_governance,
)
from adaptation_compiler_lab.instruction_environment import NativeTarget
from adaptation_compiler_lab.instruction_environment.resolver import (
    apply_instruction_environment,
    build_instruction_delta_plan,
)
from adaptation_compiler_lab.instruction_environment.service import InstructionEnvironmentService
from adaptation_compiler_lab.runtime.models import CanonicalRuntimeProjection
from adaptation_compiler_lab.serialization import canonical_digest, canonical_json
from adaptation_compiler_lab.targets.base import sha256_text
from adaptation_compiler_lab.targets.models import ScopeDimension

_LEASE_TTL = timedelta(minutes=15)
_TEMPER_MARKER = "<temper-approved-context>"


class CopilotHookRuntimeError(ValueError):
    """Raised for invalid runtime configuration; invocation failures no-op."""


class CopilotProjectionCandidate:
    """Projection plus exact reviewed cross-target authorization."""

    def __init__(
        self,
        projection: CanonicalRuntimeProjection,
        target_authorization_digest: str,
    ) -> None:
        self.projection = projection
        self.target_authorization_digest = target_authorization_digest


class LocalCopilotHookRuntime:
    """Prepare cached projections and serve them only to exact registered roots."""

    def __init__(
        self,
        *,
        projects: Mapping[str, Path],
        signer: GovernanceSigner,
        signer_identity: SignerIdentity,
        instruction_environment: InstructionEnvironmentService,
        authorization_provider: Callable[[str, datetime], CopilotHookAuthorizationV1 | None],
        projection_provider: Callable[
            [str, datetime], CanonicalRuntimeProjection | CopilotProjectionCandidate | None
        ],
        receipt_path: Path,
        clock: Callable[[], datetime],
    ) -> None:
        if (
            signer.subject_id != signer_identity.subject_id
            or signer.identity_id != signer_identity.identity_id
            or signer.fingerprint != signer_identity.key_fingerprint
        ):
            raise CopilotHookRuntimeError("Copilot runtime signer changed")
        verify_signed_governance(signer_identity)
        resolved = {
            project_id: root.expanduser().resolve(strict=True)
            for project_id, root in projects.items()
        }
        if not resolved:
            raise CopilotHookRuntimeError("Copilot runtime requires registered projects")
        roots = tuple(resolved.items())
        for index, (project_id, root) in enumerate(roots):
            if not root.is_dir():
                raise CopilotHookRuntimeError("Copilot project root is unavailable")
            for other_id, other in roots[index + 1 :]:
                if root.is_relative_to(other) or other.is_relative_to(root):
                    raise CopilotHookRuntimeError(
                        f"Copilot project roots overlap: {project_id} and {other_id}"
                    )
        self._projects = resolved
        self._signer = signer
        self._identity = signer_identity
        self._instruction_environment = instruction_environment
        self._authorization_provider = authorization_provider
        self._projection_provider = projection_provider
        self._receipt_path = receipt_path.expanduser().resolve(strict=False)
        self._clock = clock
        self._leases: dict[str, CopilotProjectionLeaseV1] = {}
        self._manifests: dict[str, CopilotProjectionManifestV1] = {}
        self._receipt_fingerprints = self._load_receipts()

    def prepare_projection(
        self, project_id: str, *, issued_at: datetime | None = None
    ) -> CopilotProjectionLeaseV1 | None:
        now = issued_at or self._clock()
        authorization = self._authorization_provider(project_id, now)
        if not self._authorization_is_current(authorization, project_id, now):
            self._clear(project_id)
            return None
        assert authorization is not None
        root = self._projects.get(project_id)
        if root is None:
            raise CopilotHookRuntimeError("Copilot projection names an unknown project")
        environment = self._instruction_environment.refresh(
            project_id=project_id,
            target=NativeTarget.COPILOT,
            working_directory=root,
        )
        if not environment.complete:
            self._clear(project_id)
            return None
        provided = self._projection_provider(project_id, now)
        if provided is None:
            self._clear(project_id)
            return None
        if isinstance(provided, CopilotProjectionCandidate):
            projection = provided.projection
            target_authorization_digest = provided.target_authorization_digest
        else:
            projection = provided
            target_authorization_digest = None
        self._validate_projection(projection, project_id)
        if not projection.clauses:
            self._clear(project_id)
            return None
        relations = self._instruction_environment.cached_relations(projection, environment)
        delta_plan = build_instruction_delta_plan(
            projection,
            environment,
            semantic_relations=relations,
        )
        delta = apply_instruction_environment(projection, delta_plan)
        if not delta.clauses:
            self._clear(project_id)
            return None
        rendered = render_copilot_hook_projection(delta)
        manifest = build_copilot_projection_manifest(
            subject_id=self._identity.subject_id,
            projection=projection,
            delta_plan=delta_plan,
            rendered=rendered,
            created_at=now,
            target_authorization_digest=target_authorization_digest,
        )
        expires_at = min(authorization.expires_at, now + _LEASE_TTL)
        if expires_at <= now:
            self._clear(project_id)
            return None
        placeholder = self._signer.envelope({}, purpose="copilot_projection_lease", signed_at=now)
        draft = CopilotProjectionLeaseV1(
            lease_id=f"copilot-projection-{project_id}-{secrets.token_hex(8)}",
            subject_id=self._identity.subject_id,
            project_id=project_id,
            instruction_environment_digest=environment.content_digest,
            external_release_digest=projection.external_release_digest,
            projection_digest=delta.content_digest,
            projection_manifest_digest=manifest.content_digest,
            material=rendered.content,
            material_digest=sha256_text(rendered.content),
            material_utf8_bytes=rendered.utf8_bytes,
            issued_at=now,
            expires_at=expires_at,
            signature=placeholder,
        )
        lease = draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="copilot_projection_lease",
                    signed_at=now,
                )
            }
        )
        self._leases[project_id] = lease
        self._manifests[project_id] = manifest
        return lease

    def prepare_all(self) -> tuple[CopilotProjectionLeaseV1, ...]:
        return tuple(
            lease
            for project_id in sorted(self._projects)
            if (lease := self.prepare_projection(project_id)) is not None
        )

    def handle(self, invocation: CopilotHookInvocationV1) -> CopilotHookResultV1:
        """Fail open for the agent while refusing stale or unauthorized projection."""

        now = self._clock()
        try:
            resolved = Path(invocation.working_directory).expanduser().resolve(strict=True)
        except OSError:
            return CopilotHookResultV1(disposition=CopilotHookDisposition.NOOP_UNREGISTERED)
        matches = tuple(
            project_id
            for project_id, root in self._projects.items()
            if resolved == root or resolved.is_relative_to(root)
        )
        if len(matches) != 1:
            return CopilotHookResultV1(disposition=CopilotHookDisposition.NOOP_UNREGISTERED)
        project_id = matches[0]
        authorization = self._authorization_provider(project_id, now)
        if not self._authorization_is_current(authorization, project_id, now):
            return CopilotHookResultV1(disposition=CopilotHookDisposition.NOOP_UNAUTHORIZED)
        lease = self._leases.get(project_id)
        if lease is None or not lease.issued_at <= now < lease.expires_at:
            return CopilotHookResultV1(disposition=CopilotHookDisposition.NOOP_NO_PROJECTION)
        try:
            self._verify_lease(lease)
            environment = self._instruction_environment.refresh(
                project_id=project_id,
                target=NativeTarget.COPILOT,
                working_directory=resolved,
            )
        except (OSError, TypeError, ValueError):
            return CopilotHookResultV1(disposition=CopilotHookDisposition.NOOP_STALE_ENVIRONMENT)
        if (
            not environment.complete
            or environment.content_digest != lease.instruction_environment_digest
        ):
            return CopilotHookResultV1(disposition=CopilotHookDisposition.NOOP_STALE_ENVIRONMENT)
        modified = (
            f"{invocation.transformed_prompt}\n\n{_TEMPER_MARKER}\n"
            f"{lease.material}</temper-approved-context>"
        )
        delivered_at = now
        placeholder = self._signer.envelope(
            {}, purpose="copilot_delivery_receipt", signed_at=delivered_at
        )
        draft = CopilotDeliveryReceiptV1(
            receipt_id=f"copilot-delivery-{secrets.token_hex(12)}",
            subject_id=self._identity.subject_id,
            project_id=project_id,
            session_digest=sha256_text(invocation.session_id),
            prompt_digest=sha256_text(invocation.prompt),
            transformed_prompt_digest=sha256_text(invocation.transformed_prompt),
            projection_lease_digest=lease.content_digest,
            instruction_environment_digest=environment.content_digest,
            delivered_at=delivered_at,
            signature=placeholder,
        )
        receipt = draft.model_copy(
            update={
                "signature": self._signer.envelope(
                    draft.unsigned_payload,
                    purpose="copilot_delivery_receipt",
                    signed_at=delivered_at,
                )
            }
        )
        self._append_receipt(receipt)
        return CopilotHookResultV1(
            disposition=CopilotHookDisposition.DELIVERED,
            receipt=receipt,
            output=CopilotHookOutputV1(modified_transformed_prompt=modified),
        )

    def projection_manifest(self, project_id: str) -> CopilotProjectionManifestV1 | None:
        return self._manifests.get(project_id)

    def _validate_projection(self, projection: CanonicalRuntimeProjection, project_id: str) -> None:
        if (
            projection.context.subject_id != self._identity.subject_id
            or projection.context.project_id != project_id
            or projection.context.target_family != COPILOT_CLI_TARGET_FAMILY
            or ScopeDimension.TARGET_FAMILIES not in projection.context.known_dimensions
        ):
            raise CopilotHookRuntimeError("Copilot projection context binding changed")

    def _authorization_is_current(
        self,
        authorization: CopilotHookAuthorizationV1 | None,
        project_id: str,
        now: datetime,
    ) -> bool:
        return bool(
            authorization is not None
            and authorization.subject_id == self._identity.subject_id
            and authorization.project_id == project_id
            and authorization.delivery_enabled
            and authorization.effective_at <= now < authorization.expires_at
        )

    def _verify_lease(self, lease: CopilotProjectionLeaseV1) -> None:
        if lease.subject_id != self._identity.subject_id:
            raise CopilotHookRuntimeError("Copilot lease crossed its owner")
        public_key = base64.b64encode(
            self._signer.private_key.public_key().public_bytes_raw()
        ).decode("ascii")
        verify_detached_envelope(
            lease.unsigned_payload,
            lease.signature,
            public_key_base64=public_key,
            expected_purpose="copilot_projection_lease",
        )

    def _clear(self, project_id: str) -> None:
        self._leases.pop(project_id, None)
        self._manifests.pop(project_id, None)
        return None

    def _load_receipts(self) -> set[str]:
        if not self._receipt_path.exists():
            return set()
        fingerprints: set[str] = set()
        try:
            lines = self._receipt_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                receipt = CopilotDeliveryReceiptV1.model_validate_json(line)
                if receipt.subject_id != self._identity.subject_id:
                    raise ValueError
                self._verify_delivery_receipt(receipt)
                fingerprints.add(_delivery_fingerprint(receipt))
        except (OSError, TypeError, ValueError) as error:
            raise CopilotHookRuntimeError("Copilot delivery ledger is invalid") from error
        return fingerprints

    def _append_receipt(self, receipt: CopilotDeliveryReceiptV1) -> None:
        fingerprint = _delivery_fingerprint(receipt)
        if fingerprint in self._receipt_fingerprints:
            return
        self._verify_delivery_receipt(receipt)
        self._receipt_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._receipt_path.read_bytes() if self._receipt_path.exists() else b""
        payload = existing + (canonical_json(receipt.model_dump(mode="json")) + "\n").encode()
        _atomic_replace(self._receipt_path, payload)
        self._receipt_fingerprints.add(fingerprint)

    def _verify_delivery_receipt(self, receipt: CopilotDeliveryReceiptV1) -> None:
        public_key = base64.b64encode(
            self._signer.private_key.public_key().public_bytes_raw()
        ).decode("ascii")
        verify_detached_envelope(
            receipt.unsigned_payload,
            receipt.signature,
            public_key_base64=public_key,
            expected_purpose="copilot_delivery_receipt",
        )


class CopilotHookHandler:
    """Strict official-payload adapter returning only ``modifiedTransformedPrompt``."""

    def __init__(self, runtime: LocalCopilotHookRuntime) -> None:
        self.runtime = runtime

    def __call__(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        invocation = parse_copilot_hook_input(payload)
        result = self.runtime.handle(invocation)
        return None if result.output is None else result.output.copilot_payload()


def parse_copilot_hook_input(payload: Mapping[str, Any]) -> CopilotHookInvocationV1:
    expected = {"sessionId", "timestamp", "cwd", "prompt", "transformedPrompt"}
    if set(payload) != expected:
        raise ValueError("Copilot hook input fields changed")
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        raise ValueError("Copilot hook timestamp must be epoch milliseconds")
    return CopilotHookInvocationV1(
        session_id=_required_string(payload, "sessionId"),
        timestamp_epoch_ms=timestamp,
        working_directory=_required_string(payload, "cwd"),
        prompt=_required_string(payload, "prompt"),
        transformed_prompt=_required_string(payload, "transformedPrompt"),
    )


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Copilot hook {key} must be a non-empty string")
    return value


def _delivery_fingerprint(receipt: CopilotDeliveryReceiptV1) -> str:
    return canonical_digest(
        {
            "project_id": receipt.project_id,
            "session_digest": receipt.session_digest,
            "prompt_digest": receipt.prompt_digest,
            "transformed_prompt_digest": receipt.transformed_prompt_digest,
            "projection_lease_digest": receipt.projection_lease_digest,
        }
    )


def _atomic_replace(path: Path, payload: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
