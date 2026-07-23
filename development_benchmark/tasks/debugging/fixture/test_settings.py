from __future__ import annotations

import unittest

from settings import effective_timeout


class TimeoutTests(unittest.TestCase):
    def test_uses_each_supplied_environment(self) -> None:
        self.assertEqual(effective_timeout({"APP_TIMEOUT": "10"}), 10)
        self.assertEqual(effective_timeout({"APP_TIMEOUT": "45"}), 45)

    def test_defaults_invalid_values(self) -> None:
        self.assertEqual(effective_timeout({"APP_TIMEOUT": "invalid"}), 30)


if __name__ == "__main__":
    unittest.main()
