"""Local participant-operated attention timer; never equates agent time with effort.

No keyboard/screen monitoring. Records only explicit participant transitions and
self-report. Unfinished intervals remain unknown. No automated participant events.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ARMS = ("native_managers", "skillkit", "persistent_hub", "shared_overhead")
CATEGORIES = (
    "research",
    "setup",
    "project_switch",
    "update",
    "recovery",
    "review",
    "measurement",
    "waiting",
)


class Effort:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "participant-effort.sqlite3"
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, utc REAL, kind TEXT, "
                "session TEXT, arm TEXT, category TEXT, note TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS intervals(id INTEGER PRIMARY KEY, session TEXT, "
                "arm TEXT, category TEXT, began REAL, ended REAL, seconds REAL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS current(id INTEGER PRIMARY KEY CHECK(id=1), "
                "session TEXT, arm TEXT, category TEXT, began REAL)"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            yield db

    def transition(
        self, session: str, arm: str, category: str | None, *, clock: float | None = None
    ) -> dict[str, Any]:
        if arm not in ARMS or (category is not None and category not in CATEGORIES):
            raise ValueError("Unknown condition or effort category")
        if not session or len(session) > 80:
            raise ValueError("Use a short session identifier")
        now = time.monotonic() if clock is None else clock
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT session,arm,category,began FROM current WHERE id=1").fetchone()
            if old:
                if now < old[3]:
                    raise ValueError("Timer origin changed; mark the interrupted interval unknown")
                db.execute(
                    "INSERT INTO intervals(session,arm,category,began,ended,seconds) "
                    "VALUES(?,?,?,?,?,?)",
                    (*old, now, now - old[3]),
                )
                db.execute("DELETE FROM current")
            if category is not None:
                db.execute("INSERT INTO current VALUES(1,?,?,?,?)", (session, arm, category, now))
            db.execute(
                "INSERT INTO events(utc,kind,session,arm,category,note) VALUES(?,?,?,?,?,?)",
                (
                    time.time(),
                    "participant_transition",
                    session,
                    arm,
                    category,
                    "self_recorded; no automation",
                ),
            )
        return self.summary()

    def abandon(self) -> dict[str, Any]:
        with self.connect() as db:
            current = db.execute("SELECT session,arm,category FROM current").fetchone()
            if current:
                db.execute(
                    "INSERT INTO events(utc,kind,session,arm,category,note) VALUES(?,?,?,?,?,?)",
                    (time.time(), "unknown_interrupted_interval", *current, "duration excluded"),
                )
                db.execute("DELETE FROM current")
        return self.summary()

    def summary(self) -> dict[str, Any]:
        with self.connect() as db:
            data = db.execute(
                "SELECT session,arm,category,SUM(seconds),COUNT(*) FROM intervals "
                "GROUP BY session,arm,category"
            ).fetchall()
            current = db.execute("SELECT session,arm,category FROM current").fetchone()
            events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        rows = [
            {"session": s, "arm": a, "category": c, "seconds": seconds, "intervals": n}
            for s, a, c, seconds, n in data
        ]
        by_arm = {}
        for arm in ARMS:
            observed = [r for r in rows if r["arm"] == arm and r["category"] != "waiting"]
            by_arm[arm] = {
                "active_seconds": sum(r["seconds"] for r in observed) if observed else None,
                "recorded_categories": sorted({r["category"] for r in observed}),
            }
        active = [r for r in rows if r["category"] != "waiting"]
        return {
            "measurement": "participant_self_recorded_attention",
            "rows": rows,
            "active_seconds": sum(r["seconds"] for r in active) if active else None,
            "waiting_seconds": sum(r["seconds"] for r in rows if r["category"] == "waiting")
            if rows
            else None,
            "by_arm": by_arm,
            "open_interval": None
            if current is None
            else dict(zip(("session", "arm", "category"), current, strict=True)),
            "participant_events": events,
            "unfinished_interval_counted": False,
            "participant_attention_recorded": bool(active),
            "limits": "Explicit self-recording, not proof of continuous physical attention. "
            "Agent/observer time is separate.",
        }


PAGE = (
    Path(__file__).resolve().parents[1]
    / "development_benchmark_extensions"
    / "persistent-hub-v1"
    / "participant.html"
).read_text(encoding="utf-8")


def serve(root: Path, port: int) -> None:
    recorder = Effort(root)
    # Monotonic origin changes after a reboot; never resume an old interval.
    recorder.abandon()
    key = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def allowed(self) -> bool:
            from urllib.parse import parse_qs

            return secrets.compare_digest(
                parse_qs(urlparse(self.path).query).get("key", [""])[0], key
            )

        def respond(self, status: int, data: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'",
            )
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if not self.allowed():
                self.respond(403, b"Forbidden", "text/plain")
            elif urlparse(self.path).path == "/api/status":
                self.respond(200, json.dumps(recorder.summary()).encode(), "application/json")
            elif urlparse(self.path).path == "/":
                self.respond(200, PAGE.encode(), "text/html; charset=utf-8")
            else:
                self.respond(404, b"Not found", "text/plain")

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            if (
                not self.allowed()
                or urlparse(self.path).path != "/api/participant"
                or origin not in (None, f"http://127.0.0.1:{port}")
            ):
                self.respond(403, b"Forbidden", "text/plain")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2048:
                    raise ValueError("Invalid body size")
                data = json.loads(self.rfile.read(size))
                value = (
                    recorder.abandon()
                    if data.get("discard")
                    else recorder.transition(data["session"], data["arm"], data["category"])
                )
                self.respond(200, json.dumps(value).encode(), "application/json")
            except (ValueError, KeyError):
                self.respond(400, b"Invalid participant event", "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(
        json.dumps(
            {
                "participant_url": f"http://127.0.0.1:{port}/?key={key}",
                "measurement": "self_recorded_only",
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    serve(args.private_root, args.port)
