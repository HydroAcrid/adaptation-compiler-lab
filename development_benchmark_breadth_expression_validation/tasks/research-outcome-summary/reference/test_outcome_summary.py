import unittest

from outcome_summary import summarize_outcomes


class OutcomeSummaryTests(unittest.TestCase):
    def test_completed_runs_can_meet_the_threshold(self) -> None:
        result = summarize_outcomes(1, ("completed",))
        self.assertEqual(result["classification"], "positive")

    def test_returns_counts(self) -> None:
        self.assertIn("counts", summarize_outcomes(1, ("failed",)))


if __name__ == "__main__":
    unittest.main()
