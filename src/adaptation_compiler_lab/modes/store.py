"""Append-only raw-free receipt storage for temporary Mode use."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from adaptation_compiler_lab.modes.models import (
    ModeActivationReceipt,
    ModeDeactivationReceipt,
    ModeDeliveryReceipt,
)
from adaptation_compiler_lab.serialization import canonical_json


class ModeReceiptStore:
    """Persist exact signed Mode lifecycle receipts without task or evidence text."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def append_activation(
        self, activation: ModeActivationReceipt, delivery: ModeDeliveryReceipt
    ) -> None:
        if delivery.activation_digest != activation.content_digest:
            raise ValueError("mode delivery does not bind its activation")
        self._write_once(
            f"activation-{activation.activation_id}.json",
            {
                "activation": activation.model_dump(mode="json"),
                "delivery": delivery.model_dump(mode="json"),
            },
        )

    def append_deactivation(self, receipt: ModeDeactivationReceipt) -> None:
        self._write_once(
            f"deactivation-{receipt.receipt_id}.json",
            {"deactivation": receipt.model_dump(mode="json")},
        )

    def lifecycle_count(self) -> tuple[int, int]:
        if not self._root.exists():
            return (0, 0)
        return (
            len(tuple(self._root.glob("activation-*.json"))),
            len(tuple(self._root.glob("deactivation-*.json"))),
        )

    def _write_once(self, filename: str, value: Mapping[str, object]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._root.chmod(0o700)
        path = self._root / filename
        content = canonical_json(value) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise ValueError("mode receipt identifier was reused for different content")
            return
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
