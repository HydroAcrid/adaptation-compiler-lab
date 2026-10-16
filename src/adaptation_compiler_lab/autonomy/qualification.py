"""Owner-signed qualification after full evidence validation, without changing permissions.

The certificate retains validation facts when raw responses expire. Its dedicated
signature is issued only by the bounded importer after both evidence stores pass.
As with other local owner signatures, it cannot attest a privileged key holder's honesty.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION, analyzer_digest
from adaptation_compiler_lab.autonomy.calibration_assets import (
    FIXTURE,
    MANIFEST,
    NATIVE_PRODUCER,
    asset_path,
    inputs_digest,
)
from adaptation_compiler_lab.autonomy.evaluation import load_frozen_scenarios
from adaptation_compiler_lab.autonomy.models import CalibrationReleaseV1
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.domain import FrozenModel, Identifier, Sha256Digest
from adaptation_compiler_lab.governance.models import SignatureEnvelope
from adaptation_compiler_lab.persistence.errors import PersistenceError
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from adaptation_compiler_lab.serialization import canonical_digest

PURPOSE = "temper_native_calibration_certificate"


class QualificationCertificateV1(FrozenModel):
    certificate_version: Literal["1.0.0"] = "1.0.0"
    purpose: Literal["verified-detection-and-native-v1"] = "verified-detection-and-native-v1"
    subject_id: Identifier
    qualification_key: Sha256Digest
    inputs_digest: Sha256Digest
    runtime: dict[str, str]
    release: CalibrationReleaseV1
    detection_run: str
    detection_head: Sha256Digest
    detector_report_digest: Sha256Digest
    native_run: str
    native_head: Sha256Digest
    native_observation_digest: Sha256Digest
    signature: SignatureEnvelope


def qualification_info() -> dict[str, Any]:
    from adaptation_compiler_lab.autonomy.calibration import native_binding, protocol_digest

    data = load_frozen_scenarios(asset_path(FIXTURE), asset_path(MANIFEST))
    return {
        "evaluation_version": EVALUATION_VERSION,
        "inputs_digest": inputs_digest(),
        "dataset_digest": canonical_digest(data),
        "analyzer_digest": analyzer_digest(),
        "protocol_digest": protocol_digest(),
        "native_binding": native_binding(),
        "native_producer_digest": sha256_file(asset_path(NATIVE_PRODUCER)),
        "raw_payloads_exposed": False,
    }


def _key(body: Mapping[str, Any]) -> str:
    return str(
        canonical_digest(
            {
                name: body[name]
                for name in (
                    "inputs_digest",
                    "runtime",
                    "detection_run",
                    "detection_head",
                    "detector_report_digest",
                    "native_run",
                    "native_head",
                    "native_observation_digest",
                )
            }
        )
    )


def verify_certificate(
    store: AutonomyStore,
    proof: Mapping[str, Any],
    release: CalibrationReleaseV1,
    runtime: Mapping[str, str],
) -> bool:
    """Verify retained facts without retaining/decrypting raw model responses forever."""
    try:
        certificate = QualificationCertificateV1.model_validate_json(
            json.dumps(proof["certificate"]),
            strict=True,
        )
        body = certificate.model_dump(mode="json", exclude={"signature"})
        store.verify(body, certificate.signature, PURPOSE)
        info = qualification_info()
        return bool(
            proof.get("protocol") == "native-calibration-v2"
            and certificate.subject_id == store.signer.subject_id
            and certificate.inputs_digest == info["inputs_digest"]
            and certificate.runtime == dict(runtime)
            and certificate.qualification_key == _key(body)
            and re.fullmatch(r"owner-eval-[a-z0-9-]{1,160}", certificate.detection_run)
            and re.fullmatch(r"native-delivery-[a-z0-9-]{1,160}", certificate.native_run)
            and certificate.release == release
            and release.evaluation_version == EVALUATION_VERSION
            and release.dataset_digest == info["dataset_digest"]
            and release.analyzer_digest == info["analyzer_digest"]
            and release.synthetic
            and release.admits_automatic_trials
        )
    except (OSError, ValueError, TypeError, KeyError, PersistenceError):
        return False


def qualify(config_path: Path, *, detection_run: str, native_run: str) -> dict[str, Any]:
    from adaptation_compiler_lab.automatic_runtime.dogfood_cli import (
        _load_config,
        _registration_signer,
        _runtime_secrets,
    )
    from adaptation_compiler_lab.autonomy.calibration import (
        assess_detection,
        verify_native_observations,
    )
    from adaptation_compiler_lab.autonomy.native import native_autonomy_service

    config = _load_config(config_path)
    service = native_autonomy_service(config_path)
    runtime = {
        "model": config.semantic_model,
        "effort": config.semantic_reasoning_effort,
        "runtime_pin_digest": sha256_file(config.runtime_pin_path),
    }
    previous = service.store.latest("calibration_qualification")
    if (
        previous is not None
        and previous.get("protocol") == "native-calibration-v2"
        and isinstance(previous.get("certificate"), dict)
        and previous["certificate"].get("detection_run") == detection_run
        and previous["certificate"].get("native_run") == native_run
    ):
        release = CalibrationReleaseV1.model_validate_json(
            json.dumps(previous["certificate"]["release"]),
            strict=True,
        )
        if verify_certificate(service.store, previous, release, runtime):
            # Recover an interrupted install, including after raw retention expires.
            service.install_calibration(release)
            return {
                "qualification_installed": True,
                "qualification_key": previous["certificate"]["qualification_key"],
                "automatic_serving_ready": service.automatic_ready(),
                "personalization_enabled": service.switch("personalization"),
                "permissions_changed": False,
                "raw_payloads_exposed": False,
            }
    base = config.state_root / "autonomy/validation"

    def open_run(name: str, prefix: str) -> AutonomyStore:
        if not re.fullmatch(re.escape(prefix) + r"[a-z0-9-]{1,160}", name):
            raise AutonomyIntegrityError("invalid qualification run name")
        root = base / name
        database = root / "events.sqlite3"
        if (
            root.is_symlink()
            or database.is_symlink()
            or root.resolve().parent != base.resolve()
            or not database.is_file()
        ):
            raise AutonomyIntegrityError("qualification evidence is unavailable")
        return AutonomyStore(
            database,
            signer=_registration_signer(config),
            raw_store=LocalRawPayloadStore(
                root / "raw",
                encryption_key=_runtime_secrets(config).raw_encryption_key(
                    workspace_root=config.repository_root
                ),
            ),
        )

    detector = open_run(detection_run, "owner-eval-")
    native = open_run(native_run, "native-delivery-")
    report = assess_detection(
        detector,
        dataset=asset_path(FIXTURE),
        manifest=asset_path(MANIFEST),
        runtime=runtime,
    )
    if not report["detector_gate_passed"]:
        raise AutonomyIntegrityError("detector evidence does not qualify")
    info = qualification_info()
    binding = native.latest("native_delivery_binding")
    validation = native.latest("native_delivery_validation")
    if (
        binding is None
        or validation is None
        or binding.get("fixture_only") is not True
        or any(
            value.get("runtime") != runtime
            or value.get("native_binding") != info["native_binding"]
            or value.get("producer_digest") != info["native_producer_digest"]
            for value in (binding, validation)
        )
    ):
        raise AutonomyIntegrityError("native validation binding changed")
    observations = json.loads(native.raw(validation["native_evidence_ref"]))
    if not isinstance(observations, dict) or not verify_native_observations(
        observations,
        native,
        runtime,
    ):
        raise AutonomyIntegrityError("native observations do not qualify")
    facts = {
        "inputs_digest": info["inputs_digest"],
        "runtime": runtime,
        "detection_run": detection_run,
        "detection_head": detector.head_digest,
        "detector_report_digest": canonical_digest(report),
        "native_run": native_run,
        "native_head": native.head_digest,
        "native_observation_digest": canonical_digest(observations),
    }
    key = _key(facts)
    previous = service.store.latest("calibration_qualification")
    if (
        previous is not None
        and previous.get("protocol") == "native-calibration-v2"
        and isinstance(previous.get("certificate"), dict)
        and previous["certificate"].get("qualification_key") == key
    ):
        release = CalibrationReleaseV1.model_validate_json(
            json.dumps(previous["certificate"]["release"]),
            strict=True,
        )
        if not verify_certificate(service.store, previous, release, runtime):
            raise AutonomyIntegrityError("previous qualification certificate is invalid")
    else:
        now = datetime.now(UTC)
        release = CalibrationReleaseV1(
            evaluation_version=EVALUATION_VERSION,
            dataset_digest=report["dataset_digest"],
            analyzer_digest=report["analyzer_digest"],
            precision=report["hypothesis_detection"]["precision"],
            recall=report["hypothesis_detection"]["recall"],
            disallowed_promotions=report["disallowed_trial_eligibility"],
            wrong_scope_activations=report["wrong_scope_hypotheses"],
            lifecycle_checks_passed=report["contradiction_pauses"] == 20,
            synthetic=True,
            recorded_at=now,
        )
        body = {
            "certificate_version": "1.0.0",
            "purpose": "verified-detection-and-native-v1",
            "subject_id": service.store.signer.subject_id,
            "qualification_key": key,
            **facts,
            "release": release.model_dump(mode="json"),
        }
        certificate = QualificationCertificateV1.model_validate_json(
            json.dumps(
                {
                    **body,
                    "signature": service.store.signer.envelope(
                        body,
                        purpose=PURPOSE,
                        signed_at=now,
                    ).model_dump(mode="json"),
                }
            ),
            strict=True,
        )
        service.store.append(
            "qualification-v2-" + key[7:],
            "calibration_qualification",
            {
                "protocol": "native-calibration-v2",
                "certificate": certificate.model_dump(mode="json"),
            },
            at=now,
        )
    service.install_calibration(release)
    return {
        "qualification_installed": True,
        "qualification_key": key,
        "automatic_serving_ready": service.automatic_ready(),
        "personalization_enabled": service.switch("personalization"),
        "permissions_changed": False,
        "raw_payloads_exposed": False,
    }
