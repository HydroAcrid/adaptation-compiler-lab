import unittest

from trial_report import build_trial_report


class TrialReportTests(unittest.TestCase):
    def test_completed_successes_can_be_positive(self) -> None:
        protocol = {"minimum_valid_rate": 1.0, "success_threshold": 0.75}
        ledger = ({"status": "completed", "score": 0.9},)
        self.assertEqual(build_trial_report(protocol, ledger)["classification"], "positive")

    def test_result_contains_outcome_counts(self) -> None:
        protocol = {"minimum_valid_rate": 1.0, "success_threshold": 0.75}
        ledger = ({"status": "completed", "score": 0.9},)
        self.assertIn("outcome_counts", build_trial_report(protocol, ledger))


if __name__ == "__main__":
    unittest.main()
