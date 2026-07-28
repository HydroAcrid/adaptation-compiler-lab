"""Render deterministic compact materials for Milestone 6A.4."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from adaptation_compiler_lab.benchmark.breadth_replication import (
    BreadthProfileSet,
    validate_breadth_profile_content,
)

_RULES = (
    "- Nontechnical handoff: state practical purpose before procedure.",
    (
        "- Failed fix: reproduce on the live implementation and rediagnose before choosing "
        "a new cause."
    ),
    (
        "- Time-sensitive decision: use the most authoritative applicable source available "
        "at decision time."
    ),
    (
        "- Named shell or environment: render commands for it; quote supplied values as "
        "literal data."
    ),
    (
        "- Replacing differing user-managed content: disclose overwrite risk and recovery; "
        "replace only with explicit authorization."
    ),
)
_STAGE_3_RULES = (
    _RULES[0],
    _RULES[3],
    (
        "- Fix status: treat notes and remembered fixes as hypotheses; use live repository "
        "state and current execution evidence to decide whether the defect is resolved, "
        "reproducing when needed."
    ),
    (
        "- User-content replacement: disclose overwrite risk and recovery. Explicit "
        "authorization in the current task or function input is sufficient; stay in scope "
        "and do not add another permission gate."
    ),
    _RULES[2],
    (
        "- Frozen evaluation: preserve failures and timeouts; honestly report negative or "
        "inconclusive results when registered criteria require them."
    ),
)


def render_breadth_compiled_materials() -> tuple[str, str, str]:
    """Render the three cumulative snapshots from the minimized evidence rules."""

    stage_rules = (_RULES[:3], _RULES, _STAGE_3_RULES)
    values = cast(
        tuple[str, str, str],
        tuple("Use only when relevant:\n\n" + "\n".join(rules) + "\n" for rules in stage_rules),
    )
    profile = BreadthProfileSet(
        stage_1=values[0],
        stage_2=values[1],
        stage_3=values[2],
    )
    validate_breadth_profile_content(profile)
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    if not arguments.check:
        raise RuntimeError(
            "renderer is check-only; edit the versioned source and snapshots together"
        )
    root = arguments.root.resolve()
    expected = render_breadth_compiled_materials()
    for stage, value in enumerate(expected, start=1):
        path = root / f"condition-materials/compiled-stage-{stage}.md"
        if path.read_text(encoding="utf-8") != value:
            raise RuntimeError(f"compiled Stage {stage} does not match its deterministic renderer")


if __name__ == "__main__":
    main()
