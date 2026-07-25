from __future__ import annotations

import unittest

from feature_flags import resolve_flags


class FeatureFlagTests(unittest.TestCase):
    def test_keys_are_normalized_and_overrides_win(self) -> None:
        self.assertEqual(
            resolve_flags(
                {" Search ": False, "audit": True},
                {"SEARCH": True},
            ),
            {"audit": True, "search": True},
        )

    def test_tenant_override_does_not_leak_to_next_request(self) -> None:
        self.assertEqual(resolve_flags({"search": False}, {"search": True}), {"search": True})
        self.assertEqual(resolve_flags({"search": False}, {}), {"search": False})


if __name__ == "__main__":
    unittest.main()
