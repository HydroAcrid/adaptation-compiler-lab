"""Content-addressed delivery of task-scoped adaptation material."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from adaptation_compiler_lab.benchmark.codex_development import CodexDevelopmentTask
from adaptation_compiler_lab.domain import FrozenModel, Sha256Digest
from adaptation_compiler_lab.targets.base import sha256_text

_MATERIAL_HEADER = "Current approved task rules (apply exactly):"
_TASK_HEADER = "Task:"


class TaskMaterialDeliveryReceipt(FrozenModel):
    """Exact binding for one nonduplicated user-task material delivery."""

    receipt_version: Literal["1.0.0"] = "1.0.0"
    channel: Literal["user_task"] = "user_task"
    original_prompt_digest: Sha256Digest
    material_digest: Sha256Digest
    delivered_prompt_digest: Sha256Digest
    material_utf8_bytes: int = Field(ge=1)
    material_occurrences: Literal[1] = 1

    @model_validator(mode="after")
    def receipt_is_measured(self) -> Self:
        if self.material_utf8_bytes < 1:
            raise ValueError("delivered task material must not be empty")
        return self


def deliver_task_scoped_material(
    task: CodexDevelopmentTask,
    material: str,
) -> tuple[CodexDevelopmentTask, TaskMaterialDeliveryReceipt]:
    """Embed one exact material instance ahead of the concrete user task."""

    normalized = material.rstrip()
    if not normalized:
        raise ValueError("task-scoped material must not be empty")
    delivered_prompt = (
        f"{_MATERIAL_HEADER}\n\n{normalized}\n\n{_TASK_HEADER}\n\n{task.prompt.rstrip()}"
    )
    if delivered_prompt.count(normalized) != 1:
        raise ValueError("task-scoped material delivery must be nonduplicated")
    delivered = task.model_copy(update={"prompt": delivered_prompt})
    receipt = TaskMaterialDeliveryReceipt(
        original_prompt_digest=sha256_text(task.prompt),
        material_digest=sha256_text(normalized),
        delivered_prompt_digest=sha256_text(delivered_prompt),
        material_utf8_bytes=len(normalized.encode("utf-8")),
    )
    if sha256_text(delivered.prompt) != receipt.delivered_prompt_digest:
        raise ValueError("delivered task prompt digest drifted")
    return delivered, receipt
