"""Freeze a condition-blind long-horizon output packet for an isolated judge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonDesign,
    LongHorizonPublicPlan,
    LongHorizonTurnKind,
)
from adaptation_compiler_lab.connectors.pins import sha256_bytes, sha256_file
from adaptation_compiler_lab.serialization import canonical_json


def _exclusive_write(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-version", choices=("v1", "v1.1"), default="v1")
    arguments = parser.parse_args()
    version = arguments.results_version
    repo = Path(__file__).parents[1].resolve()
    root = repo / "development_benchmark_long_horizon"
    results = root / f"results-{version}"
    report_path = results / f"BLIND_REPORT-{version}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    design = LongHorizonDesign.model_validate_json((root / "PREREGISTRATION-v1.json").read_bytes())
    public = LongHorizonPublicPlan.model_validate_json(
        (root / f"PUBLIC_PLAN-{version}.json").read_bytes()
    )
    if (
        report.get("instrument_valid") is not True
        or report.get("condition_mapping_withheld") is not True
        or report.get("design_digest") != design.content_digest
        or report.get("public_plan_digest") != public.content_digest
    ):
        raise RuntimeError("judge packet requires a valid frozen blind report")
    output_ids = tuple(item.blind_output_id for item in public.episodes)
    sections: list[str] = []
    bindings: list[dict[str, object]] = []
    for turn in design.scenario.turns:
        if turn.task.kind is LongHorizonTurnKind.EXPLICIT_FEEDBACK:
            continue
        ordered = (
            output_ids
            if hashlib.sha256(f"{public.seed_commitment}:{turn.task.task_id}".encode()).digest()[0]
            % 2
            == 0
            else tuple(reversed(output_ids))
        )
        file_name = f"turn-{turn.turn:02d}-{turn.task.allowed_change_paths[0].split('/')[-1]}"
        sources = tuple(
            (results / "anonymous-outputs" / output_id / file_name).read_text(encoding="utf-8")
            for output_id in ordered
        )
        bindings.append(
            {
                "turn": turn.turn,
                "task_id": turn.task.task_id,
                "ordered_output_ids": list(ordered),
            }
        )
        sections.append(
            f"## Turn {turn.turn}: {turn.task.task_id}\n\n"
            f"Task:\n\n{turn.task.prompt}\n\n"
            f"### First — {ordered[0]}\n\n```python\n{sources[0].rstrip()}\n```\n\n"
            f"### Second — {ordered[1]}\n\n```python\n{sources[1].rstrip()}\n```\n"
        )
    binding_value = {
        "bindings_version": "1.1.0" if version == "v1.1" else "1.0.0",
        "blind_report_digest": sha256_file(report_path),
        "condition_mapping_withheld": True,
        "automated_scores_included": False,
        "task_ratings": bindings,
        "external_validation_accessed": False,
    }
    packet = (
        f"# Milestone 6A.5 condition-blind judge packet {version}\n\n"
        "Compare each First/Second implementation against the supplied task. Judge instruction "
        "adherence, implementation quality, maintainability, safety, and unsupported assumptions. "
        "Use a tie when there is no meaningful quality difference. Do not infer condition "
        "identity. Automated scores, traces, condition materials, and mappings are intentionally "
        "absent.\n\n" + "\n".join(sections)
    )
    _exclusive_write(
        results / f"JUDGE_BINDINGS-{version}.json",
        (canonical_json(binding_value) + "\n").encode("utf-8"),
    )
    _exclusive_write(
        results / f"JUDGE_PACKET-{version}.md",
        packet.encode("utf-8"),
    )
    completion = {
        "completion_version": "1.1.0" if version == "v1.1" else "1.0.0",
        "blind_report_digest": sha256_file(report_path),
        "judge_bindings_digest": sha256_file(results / f"JUDGE_BINDINGS-{version}.json"),
        "judge_packet_digest": sha256_file(results / f"JUDGE_PACKET-{version}.md"),
        "condition_mapping_withheld": True,
        "instrument_valid": True,
        "provider_billed_calls": 0,
        "target_turns": 30,
        "external_validation_accessed": False,
    }
    _exclusive_write(
        results / f"BLIND_COMPLETION-{version}.json",
        (canonical_json(completion) + "\n").encode("utf-8"),
    )
    print(
        canonical_json(
            {
                "bindings": len(bindings),
                "condition_mapping_withheld": True,
                "packet_digest": sha256_bytes(packet.encode("utf-8")),
            }
        )
    )


if __name__ == "__main__":
    main()
