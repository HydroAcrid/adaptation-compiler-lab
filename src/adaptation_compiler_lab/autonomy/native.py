"""Native runtime factory reuses protected credentials; unsupported provenance stays closed."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.autonomy.service import AutonomyApplicationService
from adaptation_compiler_lab.autonomy.store import AutonomyStore


def native_autonomy_service(config_path: Path) -> AutonomyApplicationService:
    from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
        _load_config,
        _registration_signer,
        _runtime_secrets,
    )
    from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore

    config = _load_config(config_path)
    signer = _registration_signer(config)

    def secure_store_available() -> bool:
        try:
            return _registration_signer(_load_config(config_path)).fingerprint == signer.fingerprint
        except (OSError, ValueError):
            return False

    store = AutonomyStore(
        config.state_root / "autonomy" / "events.sqlite3",
        signer=signer,
        raw_store=LocalRawPayloadStore(
            config.state_root / "autonomy" / "raw",
            encryption_key=_runtime_secrets(config).raw_encryption_key(
                workspace_root=config.repository_root
            ),
        ),
    )
    from datetime import UTC, datetime

    from adaptation_compiler_lab.autonomy.project_registry import (
        LearningProjectRegistry,
        LearningProjectV1,
    )

    registry = LearningProjectRegistry(
        store,
        tuple(
            LearningProjectV1(
                project_id=p.project_id,
                root=str(p.root.resolve()),
                source_roots=tuple(
                    sorted(str(root.resolve()) for root in p.effective_source_roots)
                ),
                capture_after_epoch_seconds=p.capture_after_epoch_seconds
                or config.capture_after_epoch_seconds,
            )
            for p in config.projects
        ),
        clock=lambda: datetime.now(UTC),
    )
    service = AutonomyApplicationService(
        store=store,
        projects={key: Path(project.root) for key, project in registry.projects().items()},
        codex_home=config.source_codex_home,
        secure_store_available=secure_store_available,
    )
    from adaptation_compiler_lab.autonomy.calibration import NativeCalibrationVerifier
    from adaptation_compiler_lab.autonomy.calibration_assets import FIXTURE, asset_path
    from adaptation_compiler_lab.autonomy.codex_source import ConfiguredCodexHabitSource
    from adaptation_compiler_lab.autonomy.codex_transport import (
        ConfiguredCodexHabitSensor,
        ConfiguredNativeRelationSensor,
    )
    from adaptation_compiler_lab.autonomy.native_policy import NativeStylePolicy
    from adaptation_compiler_lab.autonomy.validation_retention import (
        checked_validation_run,
        sweep_validation_raw,
    )
    from adaptation_compiler_lab.autonomy.worker import BackgroundHabitWorker
    from adaptation_compiler_lab.connectors.pins import load_dogfood_runtime_pins
    from adaptation_compiler_lab.instruction_environment.codex_semantic import (
        instruction_relation_analyzer_digest,
    )

    policy = NativeStylePolicy(
        projects=service.projects,
        codex_home=config.source_codex_home,
        cli_version=load_dogfood_runtime_pins(
            config.runtime_pin_path
        ).codex.executable.package_version,
        store=store,
        analyzer_digest=instruction_relation_analyzer_digest(
            model=config.semantic_model, reasoning_effort=config.semantic_reasoning_effort
        ),
    )
    service.native_conflict_checker = policy.blocked

    def calibration_runtime() -> dict[str, str]:
        from adaptation_compiler_lab.connectors.pins import sha256_file

        current = _load_config(config_path)
        return {
            "model": current.semantic_model,
            "effort": current.semantic_reasoning_effort,
            "runtime_pin_digest": sha256_file(current.runtime_pin_path),
        }

    def open_calibration_run(name: str) -> AutonomyStore:
        base = config.state_root / "autonomy" / "validation"
        root = checked_validation_run(base, name)
        database = root / "events.sqlite3"
        return AutonomyStore(
            database,
            signer=signer,
            raw_store=LocalRawPayloadStore(
                root / "raw",
                encryption_key=_runtime_secrets(config).raw_encryption_key(
                    workspace_root=config.repository_root
                ),
            ),
        )

    service.calibration_verifier = NativeCalibrationVerifier(
        store=store,
        fixtures=asset_path(FIXTURE).parent,
        open_run=open_calibration_run,
        runtime=calibration_runtime,
    )

    sensor = ConfiguredCodexHabitSensor(config_path)
    source = ConfiguredCodexHabitSource(config_path, service)
    service.provenance_verifier = source.verify_episode
    service.provenance_admission = source.admitted
    service.background_worker = BackgroundHabitWorker(
        service,
        read_completed=source.read_completed,
        sensor=sensor,
        remaining_capacity=sensor.remaining_capacity,
        context=policy.context,
        native_policy=policy,
        relation_analyzer=ConfiguredNativeRelationSensor(config_path),
        maintenance=lambda now: sweep_validation_raw(
            config.state_root / "autonomy" / "validation", open_calibration_run, now=now
        ),
        project_registry=registry,
    )
    return service
