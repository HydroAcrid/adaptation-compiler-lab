import unittest

from deployment_policy import plan_delivery


class DeliveryPolicyTests(unittest.TestCase):
    def test_new_destination_is_created_for_each_storage_class(self) -> None:
        for storage_class in ("durable_release", "ephemeral_build_cache"):
            with self.subTest(storage_class=storage_class):
                self.assertEqual(
                    plan_delivery(False, storage_class),
                    ("create_destination",),
                )

    def test_unknown_storage_class_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_delivery(True, "unknown")


if __name__ == "__main__":
    unittest.main()
