"""Task ownership tied to one native Hub connection and process lifetime."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Literal

from .lifetime import process_identity

TaskOutcome = Literal["completed", "failed", "cancelled", "switched"]
MAX_LEASE_SECONDS = 3600


@dataclass(frozen=True)
class TaskOwner:
    connection_id: str
    pid: int
    process_start: str

    @classmethod
    def current(cls) -> TaskOwner:
        pid = os.getpid()
        started = process_identity(pid)
        if started is None:
            raise ValueError("Could not bind the Hub connection to a native process")
        return cls(secrets.token_hex(16), pid, started)

    def alive(self) -> bool:
        return process_identity(self.pid) == self.process_start
