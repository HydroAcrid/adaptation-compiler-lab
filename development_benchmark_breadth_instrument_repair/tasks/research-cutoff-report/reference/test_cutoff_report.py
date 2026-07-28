import copy
import unittest

from cutoff_report import build_cutoff_report


class CutoffReportTests(unittest.TestCase):
    def test_uses_registered_trials_and_frozen_thresholds(self) -> None:
        protocol = {
            "construction_cutoff": "2026-07-01T00:00:00Z",
            "planned_runs": 4,
            "minimum_record_rate": 0.5,
            "success_threshold": 0.8,
        }
        trials = (
            {"started_at": "2026-06-28T00:00:00Z", "status": "completed", "score": 0.9},
            {"started_at": "2026-06-29T00:00:00Z", "status": "failed"},
            {"started_at": "2026-07-02T00:00:00Z", "status": "completed", "score": 0.1},
        )

        self.assertEqual(
            build_cutoff_report(protocol, trials),
            {
                "classification": "positive",
                "outcome_counts": {"completed": 1, "failed": 1, "timed_out": 0},
                "record_rate": 0.5,
            },
        )

    def test_preserves_inputs_and_reports_inconclusive(self) -> None:
        protocol = {
            "construction_cutoff": "2026-07-01T00:00:00Z",
            "planned_runs": 5,
            "minimum_record_rate": 0.8,
            "success_threshold": 0.7,
        }
        trials = (
            {"started_at": "2026-06-28T00:00:00Z", "status": "failed"},
            {"started_at": "2026-06-29T00:00:00Z", "status": "timed_out"},
        )
        snapshot = copy.deepcopy((protocol, trials))

        report = build_cutoff_report(protocol, trials)

        self.assertEqual(report["classification"], "inconclusive")
        self.assertEqual((protocol, trials), snapshot)


if __name__ == "__main__":
    unittest.main()
