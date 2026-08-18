import unittest

from src.transfer_policy import plan_transfer


class TransferPolicyTests(unittest.TestCase):
    def test_result_is_an_action_tuple(self) -> None:
        result = plan_transfer(False, "retained_user_tree", False)
        self.assertIsInstance(result, tuple)
        self.assertTrue(all(isinstance(item, str) for item in result))

    def test_unknown_retention_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported retention class"):
            plan_transfer(True, "unknown", False)


if __name__ == "__main__":
    unittest.main()
