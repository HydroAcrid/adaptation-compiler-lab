from __future__ import annotations

import unittest

from report import summarize_trials


class ReportTests(unittest.TestCase):
    def test_reports_all_input_rows(self) -> None:
        rows = [{"status": "passed"}, {"status": "failed"}]
        summary = summarize_trials(rows)

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["statuses"], ["passed", "failed"])

    def test_empty_input_is_descriptive(self) -> None:
        summary = summarize_trials([])

        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["valid_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
