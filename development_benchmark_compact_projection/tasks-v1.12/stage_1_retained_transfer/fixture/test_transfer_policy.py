import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from transfer_policy import plan_transfer


class TransferPolicyTests(unittest.TestCase):
    def test_new_target_is_created(self) -> None:
        self.assertEqual(
            plan_transfer(False, "retained_user_tree"),
            ("create_target",),
        )

    def test_unknown_retention_class_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_transfer(False, "unknown")


if __name__ == "__main__":
    unittest.main()
