from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy import calibration_assets as assets
from adaptation_compiler_lab.autonomy.calibration import NativeCalibrationVerifier
from adaptation_compiler_lab.autonomy.models import CalibrationReleaseV1
from adaptation_compiler_lab.autonomy.qualification import (
    PURPOSE,
    _key,
    qualification_info,
    verify_certificate,
)
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_evaluation_run import BINDING


def certificate(
    app: Any,
    *,
    purpose: str = PURPOSE,
    runtime: dict[str, str] | None = None,
) -> tuple[CalibrationReleaseV1, dict[str, Any]]:
    service, clock = app
    info = qualification_info()
    release = CalibrationReleaseV1(
        evaluation_version=info["evaluation_version"],
        dataset_digest=info["dataset_digest"],
        analyzer_digest=info["analyzer_digest"],
        precision=1,
        recall=1,
        disallowed_promotions=0,
        wrong_scope_activations=0,
        lifecycle_checks_passed=True,
        synthetic=True,
        recorded_at=clock(),
    )
    body = {
        "certificate_version": "1.0.0",
        "purpose": "verified-detection-and-native-v1",
        "subject_id": service.store.signer.subject_id,
        "inputs_digest": info["inputs_digest"],
        "runtime": runtime or BINDING,
        "release": release.model_dump(mode="json"),
        "detection_run": "owner-eval-fictional-unit",
        "detection_head": "sha256:" + "a" * 64,
        "detector_report_digest": "sha256:" + "b" * 64,
        "native_run": "native-delivery-fictional-unit",
        "native_head": "sha256:" + "c" * 64,
        "native_observation_digest": "sha256:" + "d" * 64,
    }
    body["qualification_key"] = _key(body)
    return release, {
        "protocol": "native-calibration-v2",
        "certificate": {
            **body,
            "signature": service.store.signer.envelope(
                body,
                purpose=purpose,
                signed_at=clock(),
            ).model_dump(mode="json"),
        },
    }


def test_owner_certificate_survives_raw_expiry_without_enabling_permissions(app: Any) -> None:
    service, clock = app
    release, proof = certificate(app)
    before = service.grant().content_digest
    service.store.append("fixture-certificate", "calibration_qualification", proof, at=clock())
    verifier = NativeCalibrationVerifier(
        store=service.store,
        fixtures=Path("unavailable-checkout"),
        open_run=lambda _: pytest.fail("Certificate admission must not decrypt expired evidence"),
        runtime=lambda: BINDING,
    )
    assert verifier(release), "A properly owner-attested fixture must reach the accepting path"
    service.calibration_verifier = verifier
    service.install_calibration(release)
    assert service.grant().content_digest == before
    assert not service.switch("personalization")
    assert not verifier(release.model_copy(update={"precision": 0.99}))
    assert not verify_certificate(service.store, proof, release, {**BINDING, "model": "other"})
    tampered = json.loads(json.dumps(proof))
    tampered["certificate"]["native_head"] = "sha256:" + "e" * 64
    assert not verify_certificate(service.store, tampered, release, BINDING)


def test_generic_owner_signature_and_green_checklist_cannot_issue_qualification(app: Any) -> None:
    service, _clock = app
    release, proof = certificate(app, purpose="temper_autonomy_event")
    assert not verify_certificate(service.store, proof, release, BINDING)
    assert not verify_certificate(
        service.store,
        {"protocol": "native-calibration-v2", "certificate": {"passed": True}},
        release,
        BINDING,
    )


def test_exported_inputs_work_without_a_checkout_and_missing_data_cannot_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app: Any,
) -> None:
    root = Path(__file__).resolve().parents[3]
    expected = assets.inputs_digest()
    release, proof = certificate(app)
    repository = tmp_path / "source"
    for relative in assets.PUBLIC_INPUTS:
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    export = repository / "build/calibration-assets"
    export.mkdir(parents=True)
    (export / "unwanted-scratch-file").write_text("must not be bundled")
    assets.export_assets(repository, export)
    assert not (export / "unwanted-scratch-file").exists()
    with pytest.raises(ValueError, match="bounded build"):
        assets.export_assets(repository, tmp_path / "unrelated")
    package = tmp_path / "standalone/autonomy"
    shutil.copytree(export, package / "qualification_assets")
    monkeypatch.setattr(assets, "__file__", str(package / "calibration_assets.py"))
    monkeypatch.setitem(assets.__dict__, "__compiled__", object())
    assert assets.inputs_digest() == expected
    assert qualification_info()["inputs_digest"] == expected
    path = assets.asset_path(assets.DRIVER)
    path.write_bytes(path.read_bytes() + b"\n# deliberate source drift\n")
    assert not verify_certificate(app[0].store, proof, release, BINDING)
    path.unlink()
    with pytest.raises(ValueError, match="unavailable"):
        assets.asset_path(assets.DRIVER)


def importer_fixture(app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    import adaptation_compiler_lab.automatic_runtime.dogfood_cli as dogfood
    import adaptation_compiler_lab.autonomy.native as native

    pin = tmp_path / "pin.json"
    pin.write_text("{}")
    config = SimpleNamespace(
        state_root=tmp_path / "runtime",
        repository_root=tmp_path,
        runtime_pin_path=pin,
        semantic_model=BINDING["model"],
        semantic_reasoning_effort=BINDING["effort"],
    )
    monkeypatch.setattr(dogfood, "_load_config", lambda _: config)
    monkeypatch.setattr(native, "native_autonomy_service", lambda _: app[0])
    monkeypatch.setattr(dogfood, "_registration_signer", lambda _: app[0].store.signer)
    monkeypatch.setattr(
        dogfood,
        "_runtime_secrets",
        lambda _: SimpleNamespace(
            raw_encryption_key=lambda **kwargs: RawEncryptionKey(b"k" * 32),
        ),
    )
    return config


def test_import_recovers_interrupted_install_after_raw_expiry_without_new_permission(
    app: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adaptation_compiler_lab.autonomy.qualification import qualify

    config = importer_fixture(app, tmp_path, monkeypatch)
    runtime = {**BINDING, "runtime_pin_digest": sha256_file(config.runtime_pin_path)}
    _release, proof = certificate(app, runtime=runtime)
    service, clock = app
    service.store.append(
        "interrupted-qualification", "calibration_qualification", proof, at=clock()
    )
    service.calibration_verifier = NativeCalibrationVerifier(
        store=service.store,
        fixtures=Path("no-checkout"),
        runtime=lambda: runtime,
        open_run=lambda _: pytest.fail(
            "Expired source must not be reopened for certificate recovery"
        ),
    )
    before = service.grant().content_digest
    result = qualify(
        Path("fixture"),
        detection_run="owner-eval-fictional-unit",
        native_run="native-delivery-fictional-unit",
    )
    head = service.store.head_digest
    assert result["qualification_installed"] and not result["personalization_enabled"]
    assert service.grant().content_digest == before
    assert (
        qualify(
            Path("fixture"),
            detection_run="owner-eval-fictional-unit",
            native_run="native-delivery-fictional-unit",
        )
        == result
    )
    assert service.store.head_digest == head


@pytest.mark.parametrize("failure", ["detection", "native_binding", "green_checklist"])
def test_import_never_signs_failed_or_unsubstantiated_evidence(
    app: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    import adaptation_compiler_lab.autonomy.calibration as calibration
    from adaptation_compiler_lab.autonomy.qualification import qualify

    config = importer_fixture(app, tmp_path, monkeypatch)
    info = qualification_info()
    stores = []
    for name in ("owner-eval-unit", "native-delivery-unit"):
        root = config.state_root / "autonomy/validation" / name
        stores.append(
            AutonomyStore(
                root / "events.sqlite3",
                signer=app[0].store.signer,
                raw_store=LocalRawPayloadStore(
                    root / "raw", encryption_key=RawEncryptionKey(b"k" * 32)
                ),
            )
        )
    monkeypatch.setattr(
        calibration,
        "assess_detection",
        lambda *args, **kwargs: {
            "detector_gate_passed": failure != "detection",
        },
    )
    if failure == "green_checklist":
        native = stores[1]
        binding = {
            "runtime": {
                "model": config.semantic_model,
                "effort": config.semantic_reasoning_effort,
                "runtime_pin_digest": sha256_file(config.runtime_pin_path),
            },
            "native_binding": info["native_binding"],
            "producer_digest": info["native_producer_digest"],
            "fixture_only": True,
        }
        from dataclasses import asdict

        ref = native.save_raw(b'{"checks":true,"passed":true}')
        native.append("binding", "native_delivery_binding", binding, at=app[1]())
        native.append(
            "result",
            "native_delivery_validation",
            {
                **binding,
                "native_evidence_ref": asdict(ref),
            },
            at=app[1](),
        )
    before = app[0].store.head_digest
    with pytest.raises(AutonomyIntegrityError):
        qualify(Path("fixture"), detection_run="owner-eval-unit", native_run="native-delivery-unit")
    assert app[0].store.head_digest == before
    assert not app[0].switch("personalization")
