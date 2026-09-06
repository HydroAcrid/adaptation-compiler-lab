"""Deterministic bounded screening design for exact curated Mode releases."""

from __future__ import annotations

import hashlib
from typing import Literal

from adaptation_compiler_lab.modes.catalog import CURATED_MODE_EVALUATION_DESIGNS
from adaptation_compiler_lab.modes.curated_catalog import CURATED_CATALOG
from adaptation_compiler_lab.modes.foundry_models import (
    FoundryScreeningCellV1,
    FoundryScreeningDesignV1,
    FoundryScreeningTaskV1,
)
from adaptation_compiler_lab.serialization import canonical_digest


def build_foundry_screening_design() -> FoundryScreeningDesignV1:
    """Freeze two diagnostics and one control per Mode before target execution."""

    tasks: list[FoundryScreeningTaskV1] = []
    for design in CURATED_MODE_EVALUATION_DESIGNS:
        diagnostics = tuple(task for task in design.tasks if task.kind == "diagnostic")[:2]
        controls = tuple(task for task in design.tasks if task.kind == "neutral_control")[:1]
        for evaluation_task in (*diagnostics, *controls):
            tasks.append(
                FoundryScreeningTaskV1(
                    task_id=f"foundry-{evaluation_task.task_id}",
                    mode_id=design.mode_id,
                    kind=evaluation_task.kind,
                    prompt_digest=canonical_digest(
                        {
                            "brief": evaluation_task.brief,
                            "success_checks": evaluation_task.success_checks,
                            "title": evaluation_task.title,
                        }
                    ),
                )
            )
    sorted_tasks = tuple(sorted(tasks, key=lambda item: item.task_id))
    cells: list[FoundryScreeningCellV1] = []
    for screening_task in sorted_tasks:
        conditions: tuple[Literal["compiled_mode", "core_only", "upstream_safe"], ...] = (
            ("compiled_mode", "core_only", "upstream_safe")
            if screening_task.kind == "diagnostic"
            else ("compiled_mode", "core_only")
        )
        for condition in conditions:
            label = f"{screening_task.task_id}:{condition}"
            cells.append(
                FoundryScreeningCellV1(
                    sequence=len(cells) + 1,
                    run_id=f"foundry-run-{hashlib.sha256(label.encode()).hexdigest()[:16]}",
                    mode_id=screening_task.mode_id,
                    task_id=screening_task.task_id,
                    condition=condition,
                )
            )
    return FoundryScreeningDesignV1(
        catalog_digest=CURATED_CATALOG.content_digest,
        release_digests=tuple(sorted(item.content_digest for item in CURATED_CATALOG.releases)),
        tasks=sorted_tasks,
        cells=tuple(cells),
    )


FOUNDRY_SCREENING_DESIGN = build_foundry_screening_design()
