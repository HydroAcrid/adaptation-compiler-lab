from __future__ import annotations

import unittest

from src.solution import build_policy_pair


class DeliveryPolicyTests(unittest.TestCase):
    def test_first_policy_contains_defaults(self) -> None:
        result = build_policy_pair("one", {}, None, "two", {}, None)[0]
        self.assertEqual(result["headers"]["Accept"], "application/json")
        self.assertEqual(result["retry_delays"], ())

    def test_first_policy_applies_overrides(self) -> None:
        result = build_policy_pair("one", {"X-Trace": "yes"}, 2, "two", {}, None)[0]
        self.assertEqual(result["headers"]["X-Trace"], "yes")
        self.assertEqual(result["retry_delays"], (2,))

    def test_negative_delay_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_policy_pair("one", {}, -1, "two", {}, None)


if __name__ == "__main__":
    unittest.main()
