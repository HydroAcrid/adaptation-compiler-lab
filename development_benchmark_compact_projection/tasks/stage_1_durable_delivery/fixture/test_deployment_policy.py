import unittest

from deployment_policy import plan_delivery


class DeliveryPolicyTests(unittest.TestCase):
    def test_new_destination_is_created(self) -> None:
        self.assertEqual(
            plan_delivery(False, "durable_release"),
            ("create_destination",),
        )

    def test_unknown_storage_class_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_delivery(False, "unknown")


if __name__ == "__main__":
    unittest.main()
