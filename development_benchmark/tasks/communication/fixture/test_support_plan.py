from __future__ import annotations

import unittest

from support_plan import render_support_plan


class SupportPlanTests(unittest.TestCase):
    def test_contains_purpose_and_commands_in_order(self) -> None:
        rendered = render_support_plan("Collect diagnostics", ["tool status", "tool check"])

        self.assertIn("Collect diagnostics", rendered)
        self.assertLess(rendered.index("tool status"), rendered.index("tool check"))

    def test_requires_a_purpose(self) -> None:
        with self.assertRaises(ValueError):
            render_support_plan(" ", ["tool status"])


if __name__ == "__main__":
    unittest.main()
