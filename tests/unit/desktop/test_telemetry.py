"""Strict aggregate-report construction, signing, and tamper tests."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from adaptation_compiler_lab.desktop.service import DesktopApplicationService
from adaptation_compiler_lab.desktop.telemetry import (
    AggregateReport,
    ProjectionSizeSummary,
    SignedAggregateReport,
    build_aggregate_report,
    sign_aggregate_report,
    verify_aggregate_report,
)
from adaptation_compiler_lab.serialization import canonical_json
from tests.unit.automatic_runtime.test_runtime import NOW
from tests.unit.automatic_runtime.test_terminal_alpha import _empty_snapshot
from tests.unit.desktop.test_service import FakeDesktopBackend


def _report(tmp_path: Path) -> AggregateReport:
    terminal, _state = _empty_snapshot(tmp_path)
    snapshot = DesktopApplicationService(
        FakeDesktopBackend(terminal),
        background_enabled=True,
        aggregate_reporting_enabled=True,
        clock=lambda: NOW,
    ).load()
    return build_aggregate_report(
        snapshot,
        report_id="report-" + "a" * 32,
        installation_id="installation-" + "b" * 32,
        app_version="0.3.0a1",
        platform="windows",
        architecture="x86_64",
        period_started_at=NOW - timedelta(days=7),
        active_days=4,
    )


def test_report_has_no_free_form_or_private_content_fields(tmp_path: Path) -> None:
    report = _report(tmp_path)

    payload = canonical_json(report)

    for forbidden in (
        "prompt",
        "output",
        "path",
        "repository",
        "project_id",
        "evidence",
        "behavior",
        "instruction",
    ):
        assert forbidden not in payload.lower()
    assert len(payload.encode("utf-8")) < 32_000


def test_reporting_key_signs_and_tampering_fails(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    envelope = sign_aggregate_report(_report(tmp_path), key)
    verify_aggregate_report(envelope, key.public_key())
    changed = envelope.report.model_copy(update={"active_days": 5})
    tampered = envelope.model_copy(update={"report": changed})

    with pytest.raises(ValueError, match="signature"):
        verify_aggregate_report(tampered, key.public_key())


def test_unknown_or_free_form_report_fields_are_rejected(tmp_path: Path) -> None:
    payload = _report(tmp_path).model_dump(mode="json")
    payload["prompt"] = "private source text"

    with pytest.raises(ValidationError):
        AggregateReport.model_validate(payload)


def test_malformed_signature_is_rejected(tmp_path: Path) -> None:
    envelope = sign_aggregate_report(_report(tmp_path), Ed25519PrivateKey.generate())
    payload = envelope.model_dump(mode="json")
    payload["signature_base64"] = "not-a-signature"

    with pytest.raises(ValidationError):
        SignedAggregateReport.model_validate(payload)


def test_typescript_fixture_is_the_exact_python_signature_vector(tmp_path: Path) -> None:
    del tmp_path
    report = AggregateReport(
        report_id="report-" + "a" * 32,
        installation_id="installation-" + "b" * 32,
        app_version="0.3.0a1",
        platform="windows",
        architecture="x86_64",
        period_started_at=datetime(2026, 8, 1, tzinfo=UTC),
        period_ended_at=datetime(2026, 8, 8, tzinfo=UTC),
        active_days=4,
        eligible_interactions=8,
        correct_learning=7,
        false_learning=1,
        missed_learning=0,
        pending_reviews=0,
        resolved_reviews=2,
        activations=4,
        correct_activations=4,
        false_activations=0,
        helped=3,
        hurt=0,
        irrelevant=1,
        repeated_corrections=0,
        maintenance_actions=2,
        projection_size=ProjectionSizeSummary(
            latest_utf8_bytes=200,
            maximum_utf8_bytes=240,
        ),
    )
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    envelope = sign_aggregate_report(report, private_key)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fixture_path = (
        Path(__file__).parents[3]
        / "preview_portal"
        / "src"
        / "lib"
        / "fixtures"
        / "python-envelope.json"
    )

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture == {
        "envelope": envelope.model_dump(mode="json"),
        "public_key_base64": base64.b64encode(public_key).decode("ascii"),
    }
