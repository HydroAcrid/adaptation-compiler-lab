import unittest

from src.solution import (
    onboarding_state,
    parse_endpoint,
    review_queue_view,
    settings_layout,
    summarize_api_note,
)


class FrontendFixtureTests(unittest.TestCase):
    def test_settings_ready_state_is_available(self) -> None:
        self.assertEqual(settings_layout(1000, "ready", False)[1], "ready")

    def test_queue_rejects_negative_counts(self) -> None:
        with self.assertRaises(ValueError):
            review_queue_view(-1, 800, False)

    def test_onboarding_rejects_unknown_status(self) -> None:
        with self.assertRaises(ValueError):
            onboarding_state("unknown", "none")

    def test_endpoint_has_a_numeric_port(self) -> None:
        self.assertEqual(parse_endpoint("api=8080"), ("api", 8080))

    def test_api_note_preserves_supplied_fields(self) -> None:
        self.assertEqual(
            summarize_api_note("2.1", "streaming", "no retries"),
            ("2.1", "streaming", "no retries"),
        )


if __name__ == "__main__":
    unittest.main()
