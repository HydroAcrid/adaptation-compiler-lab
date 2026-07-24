from __future__ import annotations

import unittest
from pathlib import Path

from deployment_report import build_deployment_report


class DeploymentReportTests(unittest.TestCase):
    def test_report_uses_frozen_inputs(self) -> None:
        root = Path(__file__).parent

        report = build_deployment_report(
            root / "advisories",
            root / "decision-policy.json",
            root / "trial-ledger.json",
        )

        self.assertEqual(report["advisory_id"], "signed-release-2026-07-20")
        self.assertEqual(report["classification"], "inconclusive")
        self.assertEqual(report["valid_runs"], 2)
        self.assertEqual(report["success_rate"], 0.5)
        self.assertEqual(report["outcome_counts"]["timeout"], 1)
        self.assertEqual(report["outcome_counts"]["provider_failure"], 1)


if __name__ == "__main__":
    unittest.main()
