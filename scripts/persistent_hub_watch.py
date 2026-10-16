"""Optional foreground source watcher. No project writes or model calls.

Start explicitly against an initialized private hub. This does not install a
service, change personal Temper state, or infer a task from private conversations.
The next ordinary agent session consumes validated updates through the hub.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from scripts.discovery_maintenance import save
from scripts.persistent_hub import Hub


def tick(home: Path) -> dict[str, object]:
    began = time.monotonic()
    try:
        with Hub(home).transaction() as hub:
            result = hub.poll()
        value = {
            "status": "sources_checked",
            "result": result,
            "seconds": time.monotonic() - began,
            "native_model_turns": 0,
            "project_files_changed": False,
        }
    except (ValueError, OSError, TimeoutError, sqlite3.Error) as error:
        value = {
            "status": "source_check_failed",
            "error_type": type(error).__name__,
            "seconds": time.monotonic() - began,
            "native_model_turns": 0,
            "project_files_changed": False,
        }
    save(home / "watch-receipts" / (str(time.time_ns()) + ".json"), value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.interval < 300:
        parser.error("Source checks are limited to once per five minutes")
    # Refuse unconfigured roots before any receipt or long-running loop.
    with Hub(args.home).transaction() as hub:
        hub.get("config")
    while True:
        print(json.dumps(tick(args.home)), flush=True)
        if args.once:
            break
        time.sleep(args.interval)
