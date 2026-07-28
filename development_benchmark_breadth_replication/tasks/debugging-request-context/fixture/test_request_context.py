import unittest

from request_context import resolve_options


class RequestContextTests(unittest.TestCase):
    def test_request_value_overrides_the_default(self) -> None:
        self.assertEqual(resolve_options({"timeout": 7})["timeout"], 7)

    def test_default_keys_are_present(self) -> None:
        self.assertEqual(resolve_options({})["retries"], 2)


if __name__ == "__main__":
    unittest.main()
