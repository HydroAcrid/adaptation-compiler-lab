"""Accelerated longitudinal simulation conformance tests."""

from __future__ import annotations

from pathlib import Path

from adaptation_compiler_lab.automatic_runtime import run_longitudinal_simulation
from adaptation_compiler_lab.serialization import canonical_json


def test_longitudinal_simulation_passes_frozen_mechanics_without_claiming_evidence(
    tmp_path: Path,
) -> None:
    report = run_longitudinal_simulation(tmp_path)

    assert report.simulated_product_gate_passed is True
    assert report.counts_toward_ordinary_use_gate is False
    assert report.evidence_class == "synthetic_instrument_conformance"
    assert report.interaction_count == 20
    assert len(report.simulated_dates) == 3
    assert report.activation_count == 6
    assert report.simulated_gate.evidence_ready is True
    assert report.simulated_gate.correct_learning_count == 18
    assert report.simulated_gate.false_learning_count == 1
    assert report.simulated_gate.missed_learning_count == 1
    assert report.simulated_gate.promoted_count == 5
    assert report.simulated_gate.revoked_count == 2
    assert report.simulated_gate.correct_activation_count == 6
    assert report.simulated_gate.false_activation_count == 0
    assert report.simulated_gate.missed_activation_count == 0
    assert report.simulated_gate.helped_count == 3
    assert report.simulated_gate.hurt_count == 1
    assert report.simulated_gate.irrelevant_count == 2
    assert report.simulated_gate.repeated_correction_count == 0
    assert report.pack_bytes_by_activation == (0, 190, 209, 302, 227, 0)
    assert report.maximum_pack_utf8_bytes == 302
    assert report.latest_pack_utf8_bytes == 0
    assert report.final_active_aliases == ("alpha_safety", "incident_exception")
    assert all(item.exact_scope_match for item in report.activations)
    assert all(item.forbidden_learning_absent for item in report.activations)
    assert not tuple(tmp_path.iterdir())


def test_longitudinal_simulation_is_deterministic_and_raw_free(tmp_path: Path) -> None:
    first = run_longitudinal_simulation(tmp_path / "first")
    second = run_longitudinal_simulation(tmp_path / "second")

    assert first == second
    assert first.content_digest == second.content_digest
    payload = canonical_json(first)
    assert "supporting_quote" not in payload
    assert "payload_digest" not in payload
    assert "locator" not in payload
    assert "password=" not in payload
    assert "Explain purpose plainly" not in payload
    assert "synthetic-task-" not in payload
