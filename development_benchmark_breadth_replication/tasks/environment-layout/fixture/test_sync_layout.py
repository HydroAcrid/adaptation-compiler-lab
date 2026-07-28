import unittest

from sync_layout import plan_sync


class SyncLayoutTests(unittest.TestCase):
    def test_missing_destination_is_copied(self) -> None:
        self.assertEqual(plan_sync("/tmp/a", "/tmp/b", False, True), ("copy",))

    def test_matching_destination_is_unchanged(self) -> None:
        self.assertEqual(plan_sync("/tmp/a", "/tmp/b", True, False), ("no_change",))


if __name__ == "__main__":
    unittest.main()
