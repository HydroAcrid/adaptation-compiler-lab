import unittest

from src.solution import (
    audit_trials,
    normalize_label,
    panel_width,
    synthesize_reports,
    version_recommendation,
)


class ResearchFixtureTests(unittest.TestCase):
    def test_official_matching_support_is_usable(self) -> None:
        self.assertEqual(
            version_recommendation("official", "3.2", "3.2", True)[0],
            "use",
        )

    def test_identical_reports_can_agree(self) -> None:
        self.assertEqual(synthesize_reports("lab", "pass", "lab", "pass")[0], "pass")

    def test_completed_count_is_preserved(self) -> None:
        self.assertEqual(audit_trials(4, 0, 0)[0], 4)

    def test_small_content_keeps_its_width(self) -> None:
        self.assertEqual(panel_width(800, 24, 500), 500)

    def test_label_normalization_is_stable(self) -> None:
        self.assertEqual(normalize_label("  Release Notes  "), "release-notes")


if __name__ == "__main__":
    unittest.main()
