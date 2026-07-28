import unittest

from migration_plan import CREATE, NO_CHANGE, plan_migration


class MigrationPlanTests(unittest.TestCase):
    def test_missing_destination_is_created(self) -> None:
        self.assertEqual(plan_migration(False, True), (CREATE,))

    def test_matching_destination_is_unchanged(self) -> None:
        self.assertEqual(plan_migration(True, False), (NO_CHANGE,))


if __name__ == "__main__":
    unittest.main()
