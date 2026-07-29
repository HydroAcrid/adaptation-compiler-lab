from __future__ import annotations

import json
import os
from pathlib import Path

from adaptation_compiler_lab.benchmark.long_horizon import (
    LongHorizonEpisodeResult,
    LongHorizonTurnKind,
    LongHorizonTurnScore,
)
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawEncryptionKey
from scripts.run_long_horizon_comparison_v2 import _use_terminal_cumulative_usage

_DIGEST = "sha256:" + "1" * 64


def test_v1_1_usage_uses_terminal_cumulative_snapshot(tmp_path: Path) -> None:
    store = LocalRawPayloadStore(
        tmp_path / "encrypted",
        encryption_key=RawEncryptionKey(os.urandom(32)),
    )
    turns = [
        {
            "usage": {
                "input_tokens": turn * 100,
                "cached_input_tokens": turn * 80,
                "output_tokens": turn * 10,
                "reasoning_output_tokens": turn * 4,
            }
        }
        for turn in range(1, 16)
    ]
    reference = store.put(
        json.dumps({"turns": turns}).encode(),
        media_type="application/vnd.acl.long-horizon-episode+json",
    )
    result = LongHorizonEpisodeResult(
        episode_id="episode",
        blind_condition_id="condition",
        blind_output_id="output",
        scenario_digest=_DIGEST,
        material_digests=(_DIGEST, _DIGEST, _DIGEST),
        turn_scores=tuple(
            LongHorizonTurnScore(
                turn=turn,
                task_id=f"task-{turn}",
                kind=LongHorizonTurnKind.DIAGNOSTIC,
                objective_passed=1,
                objective_total=1,
                adaptation_passed=1,
                adaptation_total=1,
                neutral_passed=0,
                neutral_total=0,
            )
            for turn in range(1, 16)
        ),
        trace_digests=tuple(_DIGEST for _ in range(15)),
        encrypted_raw_ref=f"sha256:{reference.sha256}",
        input_tokens=sum(turn * 100 for turn in range(1, 16)),
        cached_input_tokens=sum(turn * 80 for turn in range(1, 16)),
        output_tokens=sum(turn * 10 for turn in range(1, 16)),
        reasoning_output_tokens=sum(turn * 4 for turn in range(1, 16)),
        duration_seconds=1,
        all_turns_conformant=True,
        config_destroyed=True,
        session_destroyed=True,
    )

    corrected = _use_terminal_cumulative_usage(result, store)

    assert corrected.input_tokens == 1500
    assert corrected.cached_input_tokens == 1200
    assert corrected.output_tokens == 150
    assert corrected.reasoning_output_tokens == 60
