from __future__ import annotations

import unittest

from timeouts import DEFAULT_TIMEOUT_SECONDS, timeout_for_request


class TimeoutTests(unittest.TestCase):
    def test_header_name_and_value_are_normalized(self) -> None:
        self.assertEqual(timeout_for_request({" X-Request-Timeout ": " 17 "}), 17)

    def test_request_override_does_not_leak_to_the_next_request(self) -> None:
        self.assertEqual(timeout_for_request({"X-Request-Timeout": "23"}), 23)
        self.assertEqual(timeout_for_request({}), DEFAULT_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
