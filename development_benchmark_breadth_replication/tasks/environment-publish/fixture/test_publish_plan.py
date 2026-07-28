import unittest

from publish_plan import plan_publish


class PublishPlanTests(unittest.TestCase):
    def test_missing_destination_is_created(self) -> None:
        self.assertEqual(plan_publish(False, True), ("create",))

    def test_identical_destination_is_a_noop(self) -> None:
        self.assertEqual(plan_publish(True, False), ("no_change",))


if __name__ == "__main__":
    unittest.main()
