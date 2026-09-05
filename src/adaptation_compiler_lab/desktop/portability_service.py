"""Presentation-neutral desktop bridge for offline profile portability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    _ledger,
    _load_config,
    _registration_signer,
    _runtime,
)
from adaptation_compiler_lab.automatic_runtime.models import (
    AutomaticRuntimeState,
    ExternalProposalOriginV1,
    RuntimeExternalAdoptionResolution,
)
from adaptation_compiler_lab.domain import (
    ApprovalDecision,
    ArtifactKind,
    ArtifactRoute,
    Scope,
)
from adaptation_compiler_lab.modes import MODE_CATALOG, CapabilityMode, mode_by_id
from adaptation_compiler_lab.portability import (
    CapabilityModePackageV1,
    EncryptedProfileEnvelope,
    PackageImportPreviewV1,
    PackageImportReceiptV1,
    PackageReviewDecisionReceiptV1,
    PackageReviewItemV1,
    PortableProfilePackage,
    PortableProfilePreview,
    ProfileImportReceipt,
    ProfileImportStore,
    ShareableBehaviorClauseV1,
    ShareableBehaviorPackV1,
    ShareablePackage,
    ShareablePackageImportStore,
    build_capability_mode_package,
    build_portable_profile,
    build_shareable_behavior_pack,
    encrypt_portable_profile,
    preview_portable_profile,
    preview_profile_export,
    preview_shareable_package,
    read_portable_profile,
    read_shareable_package,
    write_portable_profile,
    write_shareable_package,
)
from adaptation_compiler_lab.portability.profile import PortableProfileScope

_ARTIFACT_ROUTE = {
    ArtifactKind.MEMORY: ArtifactRoute.MEMORY,
    ArtifactKind.PREFERENCE: ArtifactRoute.PREFERENCE,
    ArtifactKind.EXAMPLE: ArtifactRoute.EXAMPLE,
    ArtifactKind.PROCEDURE: ArtifactRoute.PROCEDURE,
    ArtifactKind.PROMPT_RULE: ArtifactRoute.PROMPT_RULE,
}


def _require_matching_external_adoption(
    resolution: RuntimeExternalAdoptionResolution,
    state: AutomaticRuntimeState,
    *,
    claim_key: str,
    scope: Scope,
) -> None:
    """Fail closed when a crash retry attempts to change an adopted clause's scope."""

    if resolution.transition_digest is None:
        raise ValueError("approved package clause lost its governed transition")
    matches = tuple(
        transition
        for transition in state.transitions
        if transition.content_digest == resolution.transition_digest
    )
    if len(matches) != 1:
        raise ValueError("approved package clause is missing its exact governed transition")
    transition = matches[0]
    if (
        transition.claim_key != claim_key
        or transition.instruction is None
        or transition.instruction.scope != scope
    ):
        raise ValueError("package clause was already adopted for another local scope")


@dataclass(frozen=True, slots=True)
class LocalProfilePortabilityService:
    """Use the current governed release and local signing identity without exposing either."""

    config_path: Path

    def build_export(self, *, created_at: datetime | None = None) -> PortableProfilePackage:
        config = _load_config(self.config_path)
        state = _ledger(config).current()
        if state is None or state.release is None:
            raise ValueError("Temper has no active Core to export")
        release = state.release.governed_release
        now = created_at or datetime.now(UTC)
        package_id = f"temper-core-{now.strftime('%Y%m%dT%H%M%SZ')}"
        return build_portable_profile(
            release.active_artifacts,
            release.active_bindings,
            signer=_registration_signer(config),
            source_release_digest=release.content_digest,
            package_id=package_id,
            display_name="Temper Core",
            created_at=now,
        )

    @staticmethod
    def preview_export(package: PortableProfilePackage) -> PortableProfilePreview:
        return preview_profile_export(package)

    @staticmethod
    def write_export(
        package: PortableProfilePackage, *, passphrase: str, destination: Path
    ) -> PortableProfilePreview:
        envelope = encrypt_portable_profile(package, passphrase=passphrase)
        write_portable_profile(envelope, destination)
        return preview_profile_export(package)

    @staticmethod
    def read_import(source: Path) -> EncryptedProfileEnvelope:
        return read_portable_profile(source)

    @staticmethod
    def preview_import(
        envelope: EncryptedProfileEnvelope, *, passphrase: str
    ) -> PortableProfilePreview:
        return preview_portable_profile(envelope, passphrase=passphrase)

    def stage_import(
        self,
        envelope: EncryptedProfileEnvelope,
        *,
        passphrase: str,
        expected_package_digest: str,
        idempotency_key: str,
        imported_at: datetime | None = None,
    ) -> ProfileImportReceipt:
        config = _load_config(self.config_path)
        return ProfileImportStore(config.state_root / "portable-imports").stage(
            envelope,
            passphrase=passphrase,
            expected_package_digest=expected_package_digest,
            signer=_registration_signer(config),
            imported_at=imported_at or datetime.now(UTC),
            idempotency_key=idempotency_key,
        )

    def build_shareable_behavior_export(
        self, *, created_at: datetime | None = None
    ) -> ShareableBehaviorPackV1:
        """Build a raw-free behavior pack without source evidence or local scope IDs."""

        config = _load_config(self.config_path)
        state = _ledger(config).current()
        if state is None or state.release is None:
            raise ValueError("Temper has no active Core to share")
        release = state.release.governed_release
        clauses = tuple(
            ShareableBehaviorClauseV1(
                clause_id=f"shared-clause-{index:04d}",
                claim_key=f"shared.behavior.{index:04d}",
                artifact_kind=artifact.artifact_type,
                behavioral_contract=artifact.behavioral_contract,
                requested_scope=PortableProfileScope.from_governed_scope(artifact.scope),
            )
            for index, artifact in enumerate(release.active_artifacts, start=1)
        )
        now = created_at or datetime.now(UTC)
        return build_shareable_behavior_pack(
            clauses,
            signer=_registration_signer(config),
            package_id=f"temper-behaviors-{now.strftime('%Y%m%dT%H%M%SZ')}",
            release_version=release.release_ref.record_version,
            display_name="Temper behavior pack",
            publisher_name="Local Temper owner",
            source_license="Private sharing; recipient review required",
            created_at=now,
        )

    def build_shareable_mode_export(
        self, mode_id: str, *, created_at: datetime | None = None
    ) -> CapabilityModePackageV1:
        config = _load_config(self.config_path)
        mode = mode_by_id(mode_id)
        if mode is None:
            raise ValueError("unknown capability Mode")
        now = created_at or datetime.now(UTC)
        return build_capability_mode_package(
            mode,
            signer=_registration_signer(config),
            package_id=f"{mode.mode_id}-package",
            display_name=mode.name,
            publisher_name=mode.publisher,
            source_license=mode.source_license,
            created_at=now,
        )

    @staticmethod
    def preview_shareable_export(package: ShareablePackage) -> PackageImportPreviewV1:
        return preview_shareable_package(package)

    @staticmethod
    def write_shareable_export(package: ShareablePackage, destination: Path) -> Path:
        return write_shareable_package(package, destination)

    @staticmethod
    def read_shareable_import(source: Path) -> ShareablePackage:
        return read_shareable_package(source)

    def preview_shareable_import(self, package: ShareablePackage) -> PackageImportPreviewV1:
        config = _load_config(self.config_path)
        state = _ledger(config).current()
        known_behaviors: set[str] = set()
        if state is not None and state.release is not None:
            known_behaviors = {
                behavior.strip()
                for artifact in state.release.governed_release.active_artifacts
                for behavior in artifact.behavioral_contract.required_behaviors
            }
        known_claims = {
            clause.claim_key: next(
                (
                    behavior
                    for behavior in clause.behavioral_contract.required_behaviors
                    if behavior.strip() in known_behaviors
                ),
                "",
            )
            for clause in (package.clauses if isinstance(package, ShareableBehaviorPackV1) else ())
            if any(
                behavior.strip() in known_behaviors
                for behavior in clause.behavioral_contract.required_behaviors
            )
        }
        return preview_shareable_package(
            package,
            known_claims=known_claims,
            known_mode_digests={mode.mode_id: mode.content_digest for mode in MODE_CATALOG},
            local_subject_id=config.subject_id,
        )

    def stage_shareable_import(
        self,
        package: ShareablePackage,
        preview: PackageImportPreviewV1,
        *,
        idempotency_key: str,
        imported_at: datetime | None = None,
    ) -> PackageImportReceiptV1:
        config = _load_config(self.config_path)
        return ShareablePackageImportStore(config.state_root / "shareable-imports").stage(
            package,
            preview,
            signer=_registration_signer(config),
            local_subject_id=config.subject_id,
            imported_at=imported_at or datetime.now(UTC),
            idempotency_key=idempotency_key,
        )

    def package_review_items(self) -> tuple[PackageReviewItemV1, ...]:
        config = _load_config(self.config_path)
        return ShareablePackageImportStore(config.state_root / "shareable-imports").review_items()

    def accepted_imported_modes(self) -> tuple[CapabilityMode, ...]:
        config = _load_config(self.config_path)
        return ShareablePackageImportStore(config.state_root / "shareable-imports").accepted_modes()

    def decide_package_review(
        self,
        *,
        review_id: str,
        review_digest: str,
        decision: ApprovalDecision,
        mapped_project_ids: tuple[str, ...],
        idempotency_key: str,
        decided_at: datetime | None = None,
    ) -> PackageReviewDecisionReceiptV1:
        """Apply one local package decision without inheriting publisher authority."""

        config = _load_config(self.config_path)
        decision_time = decided_at or datetime.now(UTC)
        store = ShareablePackageImportStore(config.state_root / "shareable-imports")
        item = store.review_item(review_id)
        if item is None or str(item.content_digest) != review_digest:
            raise ValueError("package review item changed; review it again")
        known_projects = {project.project_id for project in config.projects}
        if not set(mapped_project_ids) <= known_projects:
            raise ValueError("package review names an unregistered project")
        runtime_adoption_digest = None
        receipt_project_ids: tuple[str, ...] = ()
        if item.package_type.value == "behavior_pack" and decision is ApprovalDecision.APPROVED:
            if item.behavioral_contract is None or item.requested_scope is None:
                raise ValueError("behavior package review lost its exact contract")
            if item.claim_key is None:
                raise ValueError("behavior package review lost its stable claim key")
            try:
                artifact_kind = ArtifactKind(item.kind)
                route = _ARTIFACT_ROUTE[artifact_kind]
            except (KeyError, ValueError) as error:
                raise ValueError(
                    "this imported artifact kind is not yet safely routable"
                ) from error
            requested = item.requested_scope
            projects = tuple(
                sorted(
                    mapped_project_ids
                    or requested.project_ids
                    or tuple(project.project_id for project in config.projects)
                )
            )
            if not projects or not set(projects) <= known_projects:
                raise ValueError("package behavior does not map to a registered project")
            receipt_project_ids = projects
            scope = Scope(
                subject_ids=(config.subject_id,),
                project_ids=projects,
                task_classes=requested.task_classes,
                target_families=(
                    requested.target_families or config.policy.allowed_target_families
                ),
                environment_ids=requested.environment_ids,
                activation_conditions=tuple(
                    sorted(
                        {
                            *config.policy.scope.activation_conditions,
                            *requested.activation_conditions,
                        }
                    )
                ),
                exclusions=tuple(sorted({*config.policy.scope.exclusions, *requested.exclusions})),
            )
            origin = ExternalProposalOriginV1(
                package_id=item.package_id,
                package_digest=item.package_digest,
                import_receipt_id=item.import_receipt_id,
                import_receipt_digest=item.import_receipt_digest,
                item_id=item.item_id,
                item_digest=item.item_digest,
                claim_key=item.claim_key,
                publisher_key_fingerprint=item.publisher_key_fingerprint,
            )
            ledger = _ledger(config)
            existing = ledger.external_adoption(str(item.package_digest), item.item_id)
            if existing is None:
                state = ledger.current()
                if state is None:
                    raise ValueError("Temper Core is not initialized")
                result = _runtime(config).resolve_external_behavior(
                    origin=origin,
                    behavioral_contract=item.behavioral_contract,
                    route=route,
                    scope=scope,
                    state=state,
                    decision=decision,
                    resolved_at=decision_time,
                )
                ledger.append_external_adoption(
                    result.resolution,
                    result.state,
                    release_event=result.release_event,
                )
                existing = result.resolution
            elif existing.decision is not decision:
                raise ValueError("package clause already has another immutable decision")
            else:
                state = ledger.current()
                if state is None:
                    raise ValueError("Temper Core is not initialized")
                _require_matching_external_adoption(
                    existing,
                    state,
                    claim_key=item.claim_key,
                    scope=scope,
                )
            runtime_adoption_digest = existing.content_digest
        return store.decide(
            item,
            signer=_registration_signer(config),
            decision=("approved" if decision is ApprovalDecision.APPROVED else "rejected"),
            mapped_project_ids=receipt_project_ids,
            runtime_adoption_digest=runtime_adoption_digest,
            decided_at=decision_time,
            idempotency_key=idempotency_key,
        )
