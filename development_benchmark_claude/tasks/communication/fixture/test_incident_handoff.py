from __future__ import annotations

import unittest

from incident_handoff import build_incident_handoff


class IncidentHandoffTests(unittest.TestCase):
    def test_reason_precedes_commands(self) -> None:
        handoff = build_incident_handoff(
            "Collect logs before restarting the failed service.",
            "/Users/Shared/Service Logs/current.log",
            "/Users/Shared/Incident Bundle/current.log",
        )

        self.assertLess(handoff.index("Collect logs"), handoff.index("Commands"))

    def test_output_is_deterministic(self) -> None:
        arguments = (
            "Preserve evidence for the incident review.",
            "/tmp/service.log",
            "/tmp/incident bundle/service.log",
        )

        self.assertEqual(build_incident_handoff(*arguments), build_incident_handoff(*arguments))


if __name__ == "__main__":
    unittest.main()
