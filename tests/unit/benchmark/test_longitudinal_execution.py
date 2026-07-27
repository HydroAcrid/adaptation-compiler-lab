from __future__ import annotations

from pathlib import Path

import pytest

from adaptation_compiler_lab.benchmark.codex_development import development_tree_digest
from adaptation_compiler_lab.benchmark.longitudinal import load_longitudinal_comparison
from adaptation_compiler_lab.benchmark.longitudinal_execution import (
    load_compiled_materials,
    load_evidence_packets,
    load_execution_protocol,
    validate_static_profile,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file


def _root() -> Path:
    return Path(__file__).parents[3] / "development_benchmark_longitudinal"


def test_execution_protocol_binds_design_evidence_and_compiled_materials() -> None:
    root = _root()
    design = load_longitudinal_comparison(root)
    packets = load_evidence_packets(root)
    compiled = load_compiled_materials(root)
    protocol = load_execution_protocol(root)

    assert protocol.design_digest == design.content_digest
    assert protocol.preregistration_sha256 == sha256_file(root / "PREREGISTRATION-v1.0.json")
    assert protocol.evidence_packet_digests == tuple(item.content_digest for item in packets)
    assert protocol.compiled_material_digests == tuple(
        sha256_bytes(item.encode("utf-8")) for item in compiled
    )
    assert protocol.task_fixture_digests == tuple(
        development_tree_digest(root / task.fixture_directory) for task in design.tasks
    )
    assert protocol.independent_scorer_digest == sha256_file(
        Path(__file__).parents[3]
        / "src"
        / "adaptation_compiler_lab"
        / "benchmark"
        / "longitudinal_scoring.py"
    )
    assert protocol.dogfood_metrics_digest == sha256_file(root / "DOGFOOD_METRICS-v1.0.json")
    assert protocol.maximum_total_sessions == 19
    assert protocol.compiled_stage_maintenance_actions == (3, 4, 5)
    assert protocol.compiled_stage_maintenance_seconds == (30.0, 30.0, 30.0)
    assert protocol.compiled_stage_update_latency_seconds == (40.0, 40.0, 40.0)
    assert not protocol.api_keys_allowed
    assert not protocol.external_validation_access_allowed


def test_evidence_packets_are_cumulative_and_stage_three_supersedes() -> None:
    packets = load_evidence_packets(_root())

    assert [packet.evidence_ids for packet in packets] == [
        ("dogfood-evidence-1",),
        ("dogfood-evidence-1", "dogfood-evidence-2"),
        ("dogfood-evidence-1", "dogfood-evidence-2", "dogfood-evidence-3"),
    ]
    assert packets[2].items[0].status == "superseded"
    assert packets[2].items[2].supersedes == "dogfood-evidence-1"


def test_static_profile_validator_enforces_scope_semantics_and_no_study_leakage() -> None:
    packet = load_evidence_packets(_root())[2]
    valid = (
        "# Publish safety\n\n"
        "- For persistent destinations that already exist, refuse overwrite unless a "
        "recoverable backup was explicitly requested; then back up before replacement.\n"
        "- For disposable generated-cache destinations, atomically replace without backup."
    )

    validate_static_profile(
        stage=3,
        evidence_ids=packet.evidence_ids,
        profile_text=valid,
        packet=packet,
    )

    with pytest.raises(ValueError, match="forbidden"):
        validate_static_profile(
            stage=3,
            evidence_ids=packet.evidence_ids,
            profile_text=valid + "\nThis compiled adaptation is from Milestone 6.",
            packet=packet,
        )
