import unittest

from handoff import render_recovery_handoff


class HandoffTests(unittest.TestCase):
    def test_returns_text_containing_the_supplied_values(self) -> None:
        result = render_recovery_handoff("Recover checkout.", ("check", "restore"))
        self.assertIsInstance(result, str)
        self.assertIn("Recover checkout.", result)
        self.assertIn("check", result)
        self.assertIn("restore", result)

    def test_rendering_is_deterministic(self) -> None:
        arguments = ("Recover checkout.", ("check", "restore"))
        self.assertEqual(
            render_recovery_handoff(*arguments),
            render_recovery_handoff(*arguments),
        )


if __name__ == "__main__":
    unittest.main()
