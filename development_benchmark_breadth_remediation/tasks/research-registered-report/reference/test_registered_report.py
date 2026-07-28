import unittest

from registered_report import REPORT_FIELDS, build_registered_report


class RegisteredReportTests(unittest.TestCase):
    def test_completed_success_can_be_positive(self) -> None:
        protocol = {"minimum_valid_rate": 1.0, "success_threshold": 0.75}
        ledger = ({"status": "completed", "score": 0.9},)
        self.assertEqual(
            build_registered_report(protocol, ledger)["classification"],
            "positive",
        )

    def test_report_uses_registered_fields(self) -> None:
        protocol = {"minimum_valid_rate": 1.0, "success_threshold": 0.75}
        ledger = ({"status": "completed", "score": 0.9},)
        self.assertLessEqual(
            REPORT_FIELDS,
            set(build_registered_report(protocol, ledger)),
        )


if __name__ == "__main__":
    unittest.main()
