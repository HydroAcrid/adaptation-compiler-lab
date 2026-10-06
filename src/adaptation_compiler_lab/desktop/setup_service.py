"""Presentation-neutral first-run setup over the governed local runtime."""

from __future__ import annotations

import shutil
import sys
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Literal

from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    open_codex_dogfood,
)
from adaptation_compiler_lab.automatic_runtime.credentials import (
    CredentialStoreError,
    PlatformCredentialStore,
    RuntimeSecrets,
    platform_credential_store,
)
from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
    CodexDogfoodLocalConfig,
    CodexDogfoodProjectConfig,
    _ledger,
    _load_config,
    _next_policy_version,
    _registration_signer,
    _replace_config_with_credential_rebind,
    _verify_current_policy,
)
from adaptation_compiler_lab.automatic_runtime.models import (
    CodexProjectRegistration,
    StandingAutomationPolicy,
)
from adaptation_compiler_lab.automatic_runtime.service import initial_runtime_state
from adaptation_compiler_lab.connectors.pins import (
    load_dogfood_runtime_pins,
    persist_codex_runtime_lock,
    select_product_codex_runtime_lock,
)
from adaptation_compiler_lab.desktop.connections import AgentConnectionInspector
from adaptation_compiler_lab.desktop.models import (
    ConfigurationState,
    ExistingInstallationSummary,
    ProjectCandidatePreviewV1,
    SecureStoreStatus,
    SetupCompletionReceiptV1,
    SetupSnapshotV1,
)
from adaptation_compiler_lab.desktop.platform import (
    PlatformPaths,
    platform_paths,
    product_preferences_store,
)
from adaptation_compiler_lab.desktop.preferences import (
    DesktopPreferences,
    LocalDesktopPreferencesStore,
)
from adaptation_compiler_lab.domain import ArtifactRoute, PermittedUse, Scope
from adaptation_compiler_lab.governance import GovernanceEventType, SignerRole
from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    create_signer_identity,
    sign_governance_event,
)
from adaptation_compiler_lab.serialization import canonical_json

SETUP_PREVIEW_TTL_SECONDS = 15 * 60


@dataclass(frozen=True, slots=True)
class _HeldProject:
    created_at: float
    root: Path
    preview: ProjectCandidatePreviewV1


@dataclass(frozen=True, slots=True)
class _HeldInstallation:
    created_at: float
    config_path: Path
    summary: ExistingInstallationSummary


class DesktopSetupApplicationService:
    """Create or adopt one exact local Temper runtime without renderer path access."""

    def __init__(
        self,
        *,
        paths: PlatformPaths | None = None,
        inspector: AgentConnectionInspector | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._paths = paths or platform_paths()
        self._preferences = product_preferences_store(self._paths)
        self._inspector = inspector or AgentConnectionInspector(
            platform_name="win32" if self._paths.platform == "windows" else sys.platform
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._projects: dict[str, _HeldProject] = {}
        self._installations: dict[str, _HeldInstallation] = {}

    @property
    def preferences_store(self) -> LocalDesktopPreferencesStore:
        return self._preferences

    def snapshot(self) -> SetupSnapshotV1:
        preferences = self._preferences.load()
        existing = self._existing(preferences)
        configuration_state: ConfigurationState = (
            "configured" if existing is not None else "unconfigured"
        )
        return SetupSnapshotV1(
            configuration_state=configuration_state,
            secure_store=self._secure_store(preferences),
            connections=self._inspector.inspect(),
            existing_installation=existing,
        )

    def preview_project(self, root: Path) -> ProjectCandidatePreviewV1:
        resolved = root.expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("project selection must be an existing directory")
        display_name = resolved.name.strip()
        if not display_name:
            raise ValueError("project selection has no usable name")
        existing_ids: set[str] = set()
        preferences = self._preferences.load()
        if preferences.runtime_config_path is not None:
            try:
                config = _load_config(preferences.runtime_config_path)
                existing_ids = {item.project_id for item in config.projects}
            except (OSError, ValueError):
                existing_ids = set()
        project_id = _project_id(display_name, existing_ids=existing_ids)
        now = self._clock()
        token = uuid.uuid4().hex
        preview = ProjectCandidatePreviewV1(
            preview_token=token,
            project_id=project_id,
            display_name=display_name,
            capture_after_epoch_seconds=int(now.timestamp()),
            expires_at=now + timedelta(seconds=SETUP_PREVIEW_TTL_SECONDS),
        )
        self._purge_projects()
        self._projects[token] = _HeldProject(monotonic(), resolved, preview)
        return preview

    def preview_existing(self, config_path: Path) -> tuple[str, ExistingInstallationSummary]:
        """Hold one exact governed config without returning its path to React."""

        snapshot = self.snapshot()
        if snapshot.existing_installation is not None:
            raise ValueError("this Temper installation is already configured")
        resolved = config_path.expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("existing installation selection must be a config file")
        summary = self._summarize_config(resolved)
        if not summary.secure_store_ready:
            raise ValueError("the selected installation has no usable secure-store enrollment")
        token = uuid.uuid4().hex
        self._purge_installations()
        self._installations[token] = _HeldInstallation(
            created_at=monotonic(),
            config_path=resolved,
            summary=summary,
        )
        return token, summary

    def adopt_existing(
        self,
        *,
        preview_token: str,
        expected_setup_digest: str,
    ) -> ExistingInstallationSummary:
        """Adopt an exact existing identity without rewriting governed records."""

        snapshot = self.snapshot()
        if str(snapshot.content_digest) != expected_setup_digest:
            raise ValueError("setup state changed; review the current setup before continuing")
        if snapshot.existing_installation is not None:
            raise ValueError("this Temper installation is already configured")
        self._purge_installations()
        held = self._installations.get(preview_token)
        if held is None:
            raise ValueError("existing installation preview expired; choose it again")
        current = self._summarize_config(held.config_path)
        if current != held.summary:
            raise ValueError("the existing Temper installation changed after preview")
        preferences = self._preferences.load()
        self._preferences.save(
            DesktopPreferences(
                runtime_config_path=held.config_path,
                predecessor_config_path=preferences.predecessor_config_path,
                background_enabled=False,
                aggregate_reporting_enabled=False,
            )
        )
        del self._installations[preview_token]
        return current

    def initialize(
        self,
        *,
        preview_token: str,
        expected_setup_digest: str,
        consent_confirmed: bool,
    ) -> SetupCompletionReceiptV1:
        if not consent_confirmed:
            raise ValueError("setup requires explicit local consent confirmation")
        snapshot = self.snapshot()
        if str(snapshot.content_digest) != expected_setup_digest:
            raise ValueError("setup state changed; review the current setup before continuing")
        if snapshot.existing_installation is not None:
            raise ValueError("an existing Temper installation must be adopted, not replaced")
        self._purge_projects()
        held = self._projects.get(preview_token)
        if held is None:
            raise ValueError("project preview expired; choose the project again")
        codex = snapshot.connections[0]
        if (
            codex.agent_id != "codex"
            or codex.authentication_state != "signed_in"
            or codex.conformance_state != "compatible"
        ):
            raise ValueError("a compatible ChatGPT-authenticated Codex installation is required")
        executable = self._inspector.codex_executable()
        if executable is None:
            raise ValueError("the inspected Codex executable is unavailable")
        config_path, receipt = self._create_runtime(held, executable=executable)
        self._preferences.save(
            DesktopPreferences(
                runtime_config_path=config_path,
                background_enabled=False,
                aggregate_reporting_enabled=False,
            )
        )
        del self._projects[preview_token]
        return receipt

    def register_project(self, *, preview_token: str) -> ProjectCandidatePreviewV1:
        """Append one exact signed prospective project registration."""

        self._purge_projects()
        held = self._projects.get(preview_token)
        if held is None:
            raise ValueError("project preview expired; choose the project again")
        preferences = self._preferences.load()
        if preferences.runtime_config_path is None:
            raise ValueError("project registration requires a configured Temper runtime")
        config_path = preferences.runtime_config_path
        config = _load_config(config_path)
        if held.preview.project_id in {item.project_id for item in config.projects}:
            raise ValueError("project ID is already registered")
        now = self._clock()
        _verify_current_policy(config, effective_at=now)
        expanded_scope = config.policy.scope.model_copy(
            update={
                "project_ids": tuple(
                    sorted((*config.policy.scope.project_ids, held.preview.project_id))
                )
            }
        )
        amended_policy = StandingAutomationPolicy.model_validate(
            config.policy.model_copy(
                update={
                    "policy_version": _next_policy_version(config.policy.policy_version),
                    "scope": expanded_scope,
                    "effective_at": now,
                    "previous_policy": config.policy,
                }
            ).model_dump(mode="python"),
            strict=True,
        )
        signer = _registration_signer(config)
        policy_authorization = sign_governance_event(
            {
                "event_id": f"enable-{held.preview.project_id}-{int(now.timestamp())}",
                "subject_id": config.subject_id,
                "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
                "target_ref": amended_policy.authorization_target_ref,
                "target_digest": amended_policy.content_digest,
                "decision": "enabled",
                "reason": "Add one prospective read-only Codex evidence project.",
                "policy_version": amended_policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        cutoff = held.preview.capture_after_epoch_seconds
        registration_id = f"project-registration-{held.preview.project_id}-{cutoff}"
        registration = CodexProjectRegistration(
            registration_id=registration_id,
            subject_id=config.subject_id,
            project_id=held.preview.project_id,
            project_root=str(held.root),
            source_roots=(str(held.root),),
            capture_after_epoch_seconds=cutoff,
            standing_policy_digest=amended_policy.content_digest,
            registered_at=now,
        )
        registration_authorization = sign_governance_event(
            {
                "event_id": f"authorize-{registration_id}",
                "subject_id": config.subject_id,
                "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
                "target_ref": f"codex-project-registration:{registration_id}",
                "target_digest": registration.content_digest,
                "decision": "registered_read_only",
                "reason": "Authorize prospective read-only capture without modifying source tasks.",
                "policy_version": amended_policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        project_scope = Scope(
            subject_ids=(config.subject_id,),
            project_ids=(held.preview.project_id,),
            target_families=("codex",),
        )
        project = CodexDogfoodProjectConfig(
            project_id=held.preview.project_id,
            root=held.root,
            scope=project_scope,
            source_roots=(held.root,),
            capture_after_epoch_seconds=cutoff,
            registration=registration,
            registration_authorization=registration_authorization,
        )
        updated = CodexDogfoodLocalConfig.model_validate(
            config.model_copy(
                update={
                    "config_version": "1.4.0",
                    "policy": amended_policy,
                    "policy_authorization": policy_authorization,
                    "projects": tuple(
                        sorted((*config.projects, project), key=lambda item: item.project_id)
                    ),
                }
            ).model_dump(mode="python"),
            strict=True,
        )
        _replace_config_with_credential_rebind(config_path, config, updated)
        del self._projects[preview_token]
        return held.preview

    def _create_runtime(
        self,
        held: _HeldProject,
        *,
        executable: Path,
    ) -> tuple[Path, SetupCompletionReceiptV1]:
        state = (self._paths.state_root / "runtime").resolve()
        if state.exists() and any(state.iterdir()):
            raise ValueError("Temper runtime storage already contains data")
        state.mkdir(parents=True, exist_ok=True)
        state.chmod(0o700)
        now = self._clock()
        subject_id = f"temper-{uuid.uuid4().hex}"
        secrets = RuntimeSecrets.generate_managed()
        signer = GovernanceSigner(
            secrets.private_key(workspace_root=held.root),
            identity_id=f"temper-owner-{uuid.uuid4().hex[:16]}",
            subject_id=subject_id,
        )
        identity = create_signer_identity(
            signer,
            roles=(
                SignerRole.ACTIVATION,
                SignerRole.CONSENT,
                SignerRole.CUSTODY,
                SignerRole.RELEASE,
                SignerRole.REVIEW,
            ),
            created_at=now,
            expires_at=now + timedelta(days=31),
        )
        scope = Scope(
            subject_ids=(subject_id,),
            project_ids=(held.preview.project_id,),
            target_families=("codex",),
        )
        policy = StandingAutomationPolicy(
            policy_id=f"{subject_id}-temper-runtime",
            subject_id=subject_id,
            scope=scope,
            permitted_uses=(
                PermittedUse.AUDIT,
                PermittedUse.CONSTRUCTION,
                PermittedUse.PROMOTION,
                PermittedUse.TARGET_DELIVERY,
            ),
            allowed_routes=(
                ArtifactRoute.EXAMPLE,
                ArtifactRoute.MEMORY,
                ArtifactRoute.PREFERENCE,
                ArtifactRoute.PROCEDURE,
                ArtifactRoute.PROMPT_RULE,
            ),
            allowed_target_families=("codex",),
            effective_at=now,
            expires_at=now + timedelta(days=30),
        )
        authorization = sign_governance_event(
            {
                "event_id": f"enable-{subject_id}-temper-runtime",
                "subject_id": subject_id,
                "event_type": GovernanceEventType.ACTIVATION_DECISION.value,
                "target_ref": policy.authorization_target_ref,
                "target_digest": policy.content_digest,
                "decision": "enabled",
                "reason": "Enable bounded local Temper learning with review and undo.",
                "policy_version": policy.policy_version,
                "occurred_at": now.isoformat(),
            },
            signer,
        )
        codex_home = Path.home() / ".codex"
        if not (codex_home / "auth.json").is_file():
            raise ValueError("saved ChatGPT authentication is unavailable")
        pin_path = select_product_codex_runtime_lock(
            executable, "win32" if self._paths.platform == "windows" else sys.platform
        )
        pins = load_dogfood_runtime_pins(pin_path)
        with open_codex_dogfood(
            executable=executable,
            codex_home=codex_home,
            pin=pins.codex,
            windows_interop=False,
        ):
            pass
        pin_path = persist_codex_runtime_lock(pin_path, state)
        config = CodexDogfoodLocalConfig(
            subject_id=subject_id,
            repository_root=held.root,
            state_root=state,
            database_path=state / "runtime.sqlite3",
            raw_store_path=state / "raw",
            source_codex_home=codex_home,
            codex_executable=executable,
            runtime_pin_path=pin_path,
            capture_after_epoch_seconds=held.preview.capture_after_epoch_seconds,
            policy=policy,
            policy_authorization=authorization,
            signer_identity=identity,
            projects=(
                CodexDogfoodProjectConfig(
                    project_id=held.preview.project_id,
                    root=held.root,
                    scope=scope,
                    source_roots=(held.root,),
                ),
            ),
        )
        config_path = state / "config.json"
        config_path.write_text(canonical_json(config) + "\n", encoding="utf-8")
        config_path.chmod(0o600)
        credential_store = self._credential_store(state)
        try:
            credential_store.enroll(
                secrets,
                subject_id=subject_id,
                config_digest=config.credential_binding_digest,
                signer_fingerprint=identity.key_fingerprint,
            )
            _ledger(config).initialize(initial_runtime_state(policy))
        except BaseException:
            with suppress(CredentialStoreError):
                credential_store.revoke()
            self._cleanup_failed_runtime(state)
            raise
        return config_path, SetupCompletionReceiptV1(
            subject_id=subject_id,
            signer_fingerprint=identity.key_fingerprint,
            project_id=held.preview.project_id,
            capture_after_epoch_seconds=held.preview.capture_after_epoch_seconds,
            consent_expires_at=policy.expires_at,
        )

    def _existing(self, preferences: DesktopPreferences) -> ExistingInstallationSummary | None:
        path = preferences.runtime_config_path
        if path is None or not path.is_file():
            return None
        try:
            return self._summarize_config(path)
        except (OSError, ValueError):
            return None

    def _summarize_config(self, path: Path) -> ExistingInstallationSummary:
        config = _load_config(path)
        _verify_current_policy(config, effective_at=self._clock())
        enrolled = self._credential_store(config.state_root).status() is not None
        return ExistingInstallationSummary(
            signer_fingerprint=config.signer_identity.key_fingerprint,
            project_count=len(config.projects),
            consent_expires_at=config.policy.expires_at,
            secure_store_ready=enrolled,
        )

    def _secure_store(self, preferences: DesktopPreferences) -> SecureStoreStatus:
        platform = self._paths.platform
        protector: Literal[
            "windows-dpapi-current-user",
            "macos-keychain-security-framework",
            "unavailable",
        ]
        if platform == "macos":
            protector = "macos-keychain-security-framework"
        elif platform == "windows":
            protector = "windows-dpapi-current-user"
        else:
            protector = "unavailable"
        if platform not in {"macos", "windows"}:
            return SecureStoreStatus(
                platform=platform,
                protector=protector,
                status="unavailable",
            )
        path = preferences.runtime_config_path
        if path is None or not path.is_file():
            return SecureStoreStatus(
                platform=platform,
                protector=protector,
                status="not_created",
            )
        try:
            config = _load_config(path)
            ready = self._credential_store(config.state_root).status() is not None
        except CredentialStoreError as error:
            status: Literal["locked", "unavailable"] = (
                "locked" if "locked" in str(error).casefold() else "unavailable"
            )
            return SecureStoreStatus(
                platform=platform,
                protector=protector,
                status=status,
            )
        except (OSError, ValueError):
            return SecureStoreStatus(
                platform=platform,
                protector=protector,
                status="unavailable",
            )
        return SecureStoreStatus(
            platform=platform,
            protector=protector,
            status="ready" if ready else "not_created",
        )

    def _credential_store(self, state_root: Path) -> PlatformCredentialStore:
        selected = {"windows": "win32", "macos": "darwin"}.get(self._paths.platform, sys.platform)
        return platform_credential_store(state_root, platform_name=selected)

    def _purge_projects(self) -> None:
        cutoff = monotonic() - SETUP_PREVIEW_TTL_SECONDS
        self._projects = {
            key: value for key, value in self._projects.items() if value.created_at >= cutoff
        }

    def _purge_installations(self) -> None:
        cutoff = monotonic() - SETUP_PREVIEW_TTL_SECONDS
        self._installations = {
            key: value for key, value in self._installations.items() if value.created_at >= cutoff
        }

    def _cleanup_failed_runtime(self, state: Path) -> None:
        resolved = state.resolve()
        expected_parent = self._paths.state_root.resolve()
        if resolved.parent != expected_parent or resolved.name != "runtime":
            return
        shutil.rmtree(resolved, ignore_errors=True)


def _project_id(display_name: str, *, existing_ids: set[str]) -> str:
    words = "".join(char.casefold() if char.isalnum() else " " for char in display_name).split()
    normalized = "-".join(part for part in words)
    if not normalized:
        normalized = "project"
    if not normalized[0].isalpha():
        normalized = f"project-{normalized}"
    candidate = normalized[:64]
    if candidate not in existing_ids:
        return candidate
    for number in range(2, 10_000):
        suffix = f"-{number}"
        candidate = f"{normalized[: 64 - len(suffix)]}{suffix}"
        if candidate not in existing_ids:
            return candidate
    raise ValueError("project name has too many existing registrations")
