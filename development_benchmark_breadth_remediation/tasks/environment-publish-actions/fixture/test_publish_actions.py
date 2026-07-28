import unittest

from publish_actions import CREATE, NO_CHANGE, plan_publish


class PublishActionTests(unittest.TestCase):
    def test_missing_destination_is_created(self) -> None:
        self.assertEqual(plan_publish(False, True), (CREATE,))

    def test_matching_destination_is_unchanged(self) -> None:
        self.assertEqual(plan_publish(True, False), (NO_CHANGE,))


if __name__ == "__main__":
    unittest.main()
