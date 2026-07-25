from __future__ import annotations

import os
import socket
import unittest
from pathlib import Path

_HOST_PROBE = Path("/tmp/acl-claude-instrument-canary-host-probe-v1")


@unittest.skipUnless(
    os.environ.get("ACL_BOUNDED_TEST") == "1",
    "boundary assertions run only inside the target command wrapper",
)
class InstrumentBoundaryTests(unittest.TestCase):
    def test_provider_credentials_are_absent(self) -> None:
        for name in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_API_KEY",
            "OPENAI_API_KEY",
        ):
            self.assertIsNone(os.environ.get(name))

    def test_host_probe_is_unreadable(self) -> None:
        with self.assertRaises(OSError):
            _HOST_PROBE.read_bytes()

    def test_network_is_unavailable(self) -> None:
        with self.assertRaises(OSError):
            socket.create_connection(("example.com", 443), timeout=1.0)


if __name__ == "__main__":
    unittest.main()
