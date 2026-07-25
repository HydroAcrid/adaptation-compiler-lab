from __future__ import annotations

import unittest

import retry_budget


class RetryBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        retry_budget.reset_job("alpha")
        retry_budget.reset_job("beta")

    def test_failure_budget_isolated_between_jobs(self) -> None:
        self.assertTrue(retry_budget.should_retry("alpha", 1))
        self.assertFalse(retry_budget.should_retry("alpha", 1))
        self.assertTrue(retry_budget.should_retry("beta", 1))

    def test_equivalent_job_ids_share_one_budget(self) -> None:
        self.assertTrue(retry_budget.should_retry(" Build-A ", 1))
        self.assertFalse(retry_budget.should_retry("build-a", 1))

    def test_reset_is_scoped_to_one_job(self) -> None:
        self.assertTrue(retry_budget.should_retry("alpha", 1))
        self.assertTrue(retry_budget.should_retry("beta", 1))
        retry_budget.reset_job("alpha")
        self.assertTrue(retry_budget.should_retry("alpha", 1))
        self.assertFalse(retry_budget.should_retry("beta", 1))

    def test_invalid_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            retry_budget.should_retry(" ", 1)
        with self.assertRaises(ValueError):
            retry_budget.should_retry("alpha", 0)
        with self.assertRaises(ValueError):
            retry_budget.reset_job("")


if __name__ == "__main__":
    unittest.main()
