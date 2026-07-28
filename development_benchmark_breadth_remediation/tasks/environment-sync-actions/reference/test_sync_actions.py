import unittest

from sync_actions import CREATE, NO_CHANGE, plan_sync


class SyncActionTests(unittest.TestCase):
    def test_missing_destination_is_created(self) -> None:
        self.assertEqual(plan_sync("/tmp/a", "/tmp/b", False, True), (CREATE,))

    def test_matching_destination_is_unchanged(self) -> None:
        self.assertEqual(plan_sync("/tmp/a", "/tmp/b", True, False), (NO_CHANGE,))


if __name__ == "__main__":
    unittest.main()
