from __future__ import annotations

import unittest

from src.solution import render_request_pair


class RequestContextTests(unittest.TestCase):
    def test_pair_keeps_user_ids(self) -> None:
        self.assertEqual(
            tuple(item["user_id"] for item in render_request_pair("ada", (), "grace", ())),
            ("ada", "grace"),
        )

    def test_pair_uses_default_locale(self) -> None:
        result = render_request_pair("ada", (), "grace", ())
        self.assertEqual(result[0]["locale"], "en-US")
        self.assertEqual(result[1]["locale"], "en-US")

    def test_rejects_blank_user(self) -> None:
        with self.assertRaises(ValueError):
            render_request_pair("  ", (), "grace", ())


if __name__ == "__main__":
    unittest.main()
