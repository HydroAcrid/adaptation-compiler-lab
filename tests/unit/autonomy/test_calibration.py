from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION
from adaptation_compiler_lab.autonomy.calibration import (
    NATIVE_CHECKS,
    NativeCalibrationVerifier,
    assess_detection,
    native_binding,
)
from adaptation_compiler_lab.autonomy.models import CalibrationReleaseV1
from adaptation_compiler_lab.autonomy.publisher import END, START
from adaptation_compiler_lab.autonomy.store import AutonomyIntegrityError, AutonomyStore
from adaptation_compiler_lab.autonomy.styles import StyleKey, style_contract
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from scripts.run_owner_habit_evaluation import OwnerRequestedEvaluationRunner
from tests.unit.autonomy.test_autonomy import app as app
from tests.unit.autonomy.test_evaluation_run import BINDING, Sensor

ROOT = Path(__file__).parents[2] / "fixtures/autonomy"
PREFIX = EVALUATION_VERSION.replace("-", "_")
DATA = ROOT / (PREFIX + "_prospective.json")
MANIFEST = ROOT / (PREFIX + "_prospective.manifest.json")


def source(app: Any, store: AutonomyStore | None = None) -> OwnerRequestedEvaluationRunner:
    service, clock = app
    return OwnerRequestedEvaluationRunner(
        dataset=DATA,
        manifest=MANIFEST,
        store=store or service.store,
        sensor=Sensor(),
        remaining_capacity=lambda: 50,
        runtime_binding=BINDING,
        clock=clock,
    )


def inspect(app: Any, runtime: dict[str, str] = BINDING) -> dict[str, Any]:
    return assess_detection(app[0].store, dataset=DATA, manifest=MANIFEST, runtime=runtime)


def test_partial_calibration_is_read_only_and_never_authorizes_serving(app: Any) -> None:
    value = source(app)
    before = value.store.head_digest
    report = inspect(app)
    assert not report["complete"] and not report["detector_gate_passed"]
    assert not report["automatic_serving_gate_passed"]
    assert value.store.head_digest == before


@pytest.mark.parametrize("field", ["model", "effort", "runtime_pin_digest"])
def test_calibration_rejects_runtime_drift(app: Any, field: str) -> None:
    source(app)
    with pytest.raises(AutonomyIntegrityError, match="binding changed"):
        inspect(app, {**BINDING, field: "different"})


def test_development_materials_are_not_release_calibration(app: Any) -> None:
    source(app)
    with pytest.raises(AutonomyIntegrityError, match="development/replay"):
        assess_detection(
            app[0].store,
            dataset=ROOT / (PREFIX + "_trusted.json"),
            manifest=ROOT / (PREFIX + "_trusted.manifest.json"),
            runtime=BINDING,
        )


def test_full_detection_pass_still_needs_native_proof_and_rejects_a_checklist(app: Any) -> None:
    service, clock = app
    source_root = service.store.path.parent / "separate-evaluation"
    source_store = AutonomyStore(
        source_root / "events.sqlite3",
        signer=service.store.signer,
        raw_store=LocalRawPayloadStore(
            source_root / "raw", encryption_key=RawEncryptionKey(b"s" * 32)
        ),
    )
    runner = source(app, source_store)
    for phase in runner.phases:
        case = runner.cases[phase.case_id]
        selected = (
            case["episodes"][-1:]
            if phase.stage == "contradiction"
            else (case["episodes"][:-1] if case["group"] == "changing" else case["episodes"])
        )
        used = any(value["origin"] in {"human", "owner_authorized_chat"} for value in selected)
        hypotheses = [
            {
                "style_key": key,
                "project_id": case["expected"]["project_id"],
                "task_class": style_contract(StyleKey(key))[1],
                "state": "paused" if phase.stage == "contradiction" else "provisional",
                "shadow_trial_eligible": case["group"] != "sparse",
            }
            for key in case["expected"]["style_keys"]
        ]
        if used:
            ref = runner.store.save_raw(b'{"fictional_unit_wire":true}')
            runner.store.append(
                "wire-" + phase.key,
                "evaluation_wire",
                {"phase": phase.key, "stage": "proposal", "raw_ref": asdict(ref)},
                at=clock(),
            )
        runner.store.append(
            "phase-" + phase.key,
            "evaluation_phase",
            {
                "phase": phase.key,
                "case_id": phase.case_id,
                "stage": phase.stage,
                "status": "complete",
                "hypotheses": hypotheses,
                "model_session_used": used,
            },
            at=clock(),
        )
    report = assess_detection(runner.store, dataset=DATA, manifest=MANIFEST, runtime=BINDING)
    assert report["detector_gate_passed"]
    assert report["hypothesis_detection"]["precision"] == 1
    assert report["contradiction_pauses"] == 20
    assert not report["automatic_serving_gate_passed"]
    release = CalibrationReleaseV1(
        evaluation_version=report["evaluation_version"],
        dataset_digest=report["dataset_digest"],
        analyzer_digest=report["analyzer_digest"],
        precision=1,
        recall=1,
        disallowed_promotions=0,
        wrong_scope_activations=0,
        lifecycle_checks_passed=True,
        synthetic=True,
        recorded_at=clock(),
    )
    verifier = NativeCalibrationVerifier(
        store=service.store,
        fixtures=ROOT,
        open_run=lambda _: runner.store,
        runtime=lambda: BINDING,
    )
    assert not verifier(release)
    # Even a signed all-green checklist must not substitute for native observations.
    service.store.append(
        "native-checklist",
        "calibration_native_validation",
        {
            "native_binding": native_binding(),
            "runtime": BINDING,
            "checks": dict.fromkeys(NATIVE_CHECKS, True),
        },
        at=clock(),
    )
    native_digest = service.store.events()[-1]["digest"]
    service.store.append(
        "qualification",
        "calibration_qualification",
        {
            "protocol": "native-calibration-v1",
            "release": release.model_dump(mode="json"),
            "run_name": "owner-eval-fixture",
            "source_head_digest": runner.store.head_digest,
            "native_receipt_digest": native_digest,
        },
        at=clock(),
    )
    assert not verifier(release)
    with pytest.raises(AutonomyIntegrityError, match="unverified calibration"):
        service.calibration_verifier = verifier
        service.install_calibration(release)
    assert not service.switch("personalization")
    owner = asdict(service.store.save_raw(b"Owner content.\n", media_type="text/markdown"))
    changed = asdict(
        service.store.save_raw(
            (START + "\nOwner-edited style.\n" + END).encode(), media_type="text/markdown"
        )
    )
    turns = {
        name: {
            "native_turn_completed": True,
            "runtime": BINDING,
            "thread_id": "fixture-" + name,
            "workspace": "C:/fictional/work-a",
        }
        for name in (
            "instruction_loading",
            "applicable_behavior",
            "unrelated_project",
            "current_request_override",
        )
    }
    turns["instruction_loading"].update(
        expected_token="fixture-native-token-000001", response="fixture-native-token-000001"
    )
    turns["applicable_behavior"].update(
        style_key="numbered_steps", response="1. First.\n2. Second."
    )
    turns["unrelated_project"].update(
        workspace="C:/fictional/work-b", response="No Temper profile applies."
    )
    turns["current_request_override"].update(
        expected_token="fixture-request-token-00002", response="fixture-request-token-00002"
    )
    observations = {
        "protocol": "native-calibration-observations-v1",
        "native_binding": native_binding(),
        "runtime": BINDING,
        "checks": {
            **turns,
            "native_policy_conflict": {"state": "conflict", "blocked": True},
            "publication_rollback": {
                "interrupted": True,
                "before_ref": owner,
                "interrupted_ref": changed,
                "after_ref": owner,
            },
            "revocation": {
                "grant_enabled": False,
                "profile": "",
                "before_ref": changed,
                "after_ref": owner,
            },
            "owner_edit_pause": {"blocked": True, "before_ref": changed, "after_ref": changed},
        },
    }
    ref = service.store.save_raw(json.dumps(observations).encode())
    service.store.append(
        "fictional-native-proof",
        "calibration_native_validation",
        {
            "native_binding": native_binding(),
            "runtime": BINDING,
            "checks": dict.fromkeys(NATIVE_CHECKS, True),
            "native_evidence_ref": asdict(ref),
        },
        at=clock(),
    )
    native_digest = service.store.events()[-1]["digest"]
    service.store.append(
        "fictional-qualified-candidate",
        "calibration_qualification",
        {
            "protocol": "native-calibration-v1",
            "release": release.model_dump(mode="json"),
            "run_name": "owner-eval-fixture",
            "source_head_digest": runner.store.head_digest,
            "native_receipt_digest": native_digest,
        },
        at=clock(),
    )
    assert verifier(release), "A complete fixture proof must reach the accepting path"
    assert not verifier(release.model_copy(update={"precision": 0.99}))
    service.store.raw_store.discard(ref)
    assert not verifier(release), "Missing encrypted native observations must fail closed"

    # Correct signatures do not make malformed containers valid schemas (CAL-FB-01).
    restored_ref = service.store.save_raw(json.dumps(observations).encode())
    for index, malformed in enumerate((list(NATIVE_CHECKS), None, True, 0, "checks", [])):
        service.store.append(
            f"malformed-native-{index}",
            "calibration_native_validation",
            {
                "native_binding": native_binding(),
                "runtime": BINDING,
                "native_evidence_ref": asdict(restored_ref),
                "checks": malformed,
            },
            at=clock(),
        )
        service.store.append(
            f"malformed-qualification-{index}",
            "calibration_qualification",
            {
                "protocol": "native-calibration-v1",
                "release": release.model_dump(mode="json"),
                "run_name": "owner-eval-fixture",
                "source_head_digest": runner.store.head_digest,
                "native_receipt_digest": service.store.events()[-1]["digest"],
            },
            at=clock(),
        )
        assert not verifier(release), "Malformed signed checks must reject without crashing"


def test_independently_disqualified_freeze_cannot_qualify(app: Any) -> None:
    with pytest.raises(AutonomyIntegrityError, match="adjudicated ambiguous"):
        assess_detection(
            app[0].store,
            dataset=ROOT / "habit_eval_v14_prospective.json",
            manifest=ROOT / "habit_eval_v14_prospective.manifest.json",
            runtime=BINDING,
        )


def test_forged_scope_or_disallowed_eligibility_cannot_hide_behind_precision(app: Any) -> None:
    runner = source(app)
    service, clock = app
    case = next(case for case in runner.cases.values() if case["group"] == "untrusted")
    service.store.append(
        "bad-scope",
        "evaluation_phase",
        {
            "phase": case["id"] + ":initial",
            "case_id": case["id"],
            "stage": "initial",
            "status": "complete",
            "model_session_used": False,
            "hypotheses": [
                {
                    "project_id": "unrelated-project",
                    "task_class": "summary",
                    "style_key": "concise_summary",
                    "state": "trial",
                    "shadow_trial_eligible": True,
                }
            ],
        },
        at=clock(),
    )
    report = inspect(app)
    assert report["disallowed_trial_eligibility"] == report["wrong_scope_hypotheses"] == 1
    assert not report["detector_gate_passed"]
