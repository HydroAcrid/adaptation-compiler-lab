import unittest

from src.transfer_policy import plan_transfer


class TransferPolicyTests(unittest.TestCase):
    def test_new_targets_are_created(self) -> None:
        self.assertEqual(
            plan_transfer(False, "retained_user_tree"),
            ("open_target",),
        )
        self.assertEqual(
            plan_transfer(False, "rebuildable_cache"),
            ("open_target",),
        )

    def test_unknown_retention_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported retention class"):
            plan_transfer(True, "unknown")


if __name__ == "__main__":
    unittest.main()
