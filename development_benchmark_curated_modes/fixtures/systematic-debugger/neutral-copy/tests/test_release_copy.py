from __future__ import annotations

import unittest

from src.solution import release_status


class ReleaseCopyTests(unittest.TestCase):
    def test_ready_status(self) -> None:
        self.assertEqual(release_status("Desktop", "1.2", True), "Desktop 1.2 is ready.")

    def test_not_ready_status(self) -> None:
        self.assertEqual(
            release_status("Desktop", "1.2", False),
            "Desktop 1.2 is not ready.",
        )

    def test_rejects_blank_fields(self) -> None:
        with self.assertRaises(ValueError):
            release_status("", "1.2", True)


if __name__ == "__main__":
    unittest.main()
