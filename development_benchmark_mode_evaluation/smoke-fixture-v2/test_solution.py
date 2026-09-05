import unittest

from src.solution import clamp_attempts


class ModeRepairSmokeTests(unittest.TestCase):
    def test_requested_value_is_preserved_below_ceiling(self) -> None:
        self.assertEqual(clamp_attempts(2, 5), 2)

    def test_requested_value_is_clamped_at_ceiling(self) -> None:
        self.assertEqual(clamp_attempts(8, 5), 5)

    def test_zero_is_allowed(self) -> None:
        self.assertEqual(clamp_attempts(0, 3), 0)

    def test_negative_requested_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            clamp_attempts(-1, 3)

    def test_nonpositive_ceiling_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            clamp_attempts(1, 0)


if __name__ == "__main__":
    unittest.main()
