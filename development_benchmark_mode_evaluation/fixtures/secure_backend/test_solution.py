import unittest

from src.solution import (
    authorize_record,
    card_columns,
    clarify_onboarding,
    safe_failure,
    webhook_plan,
)


class SecureBackendFixtureTests(unittest.TestCase):
    def test_matching_tenant_can_be_allowed(self) -> None:
        self.assertEqual(authorize_record("a", "a", False)[0], "deny")

    def test_invalid_webhook_is_rejected(self) -> None:
        self.assertEqual(webhook_plan(False, False, False), ("reject",))

    def test_failure_returns_two_messages(self) -> None:
        self.assertEqual(len(safe_failure("token", "/private", "E1")), 2)

    def test_wide_layout_uses_three_columns(self) -> None:
        self.assertEqual(card_columns(1200), 3)

    def test_new_setup_copy_mentions_creation(self) -> None:
        self.assertIn("created", clarify_onboarding(False)[1])


if __name__ == "__main__":
    unittest.main()
