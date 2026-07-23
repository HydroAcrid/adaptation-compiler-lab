from __future__ import annotations

import unittest

from readiness import build_report


class ReadinessTests(unittest.TestCase):
    def test_report_is_json_compatible_and_does_not_mutate_inputs(self) -> None:
        snapshots = [
            {
                "applicable_scope": "release-readiness",
                "authority": "release-owner",
                "observed_at": "2026-07-01T00:00:00Z",
                "signed": True,
                "snapshot_id": "current",
                "status": "blocked",
            }
        ]
        protocol = {
            "protocol_id": "visible",
            "frozen": True,
            "minimum_pass_rate": 0.75,
            "minimum_valid_rate": 0.8,
            "non_evaluable_statuses": ["timeout"],
        }
        trials = [{"trial_id": "visible-1", "status": "passed"}]
        original_protocol = dict(protocol)
        original_trials = [dict(item) for item in trials]

        report = build_report(snapshots, protocol, trials)

        self.assertIsInstance(report, dict)
        self.assertEqual(protocol, original_protocol)
        self.assertEqual(trials, original_trials)

    def test_empty_trial_ledger_is_inconclusive(self) -> None:
        report = build_report(
            [
                {
                    "applicable_scope": "release-readiness",
                    "authority": "release-owner",
                    "observed_at": "2026-07-01T00:00:00Z",
                    "signed": True,
                    "snapshot_id": "current",
                    "status": "blocked",
                }
            ],
            {
                "protocol_id": "visible",
                "frozen": True,
                "minimum_pass_rate": 0.75,
                "minimum_valid_rate": 0.8,
                "non_evaluable_statuses": ["timeout"],
            },
            [],
        )

        self.assertEqual(report["classification"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
