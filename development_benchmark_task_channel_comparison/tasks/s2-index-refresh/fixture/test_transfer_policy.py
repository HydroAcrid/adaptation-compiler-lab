import unittest

from src.transfer_policy import plan_transfer


class TransferPolicyTests(unittest.TestCase):
    def test_new_destinations_use_the_creation_action(self) -> None:
        self.assertEqual(
            plan_transfer(False, "retained_user_tree", False),
            ("create_index",),
        )
        self.assertEqual(
            plan_transfer(False, "rebuildable_cache", True),
            ("create_index",),
        )

    def test_unknown_retention_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported retention class"):
            plan_transfer(True, "unknown", False)


if __name__ == "__main__":
    unittest.main()
