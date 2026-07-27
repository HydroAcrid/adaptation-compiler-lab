import unittest

from policy import build_publish_plan


class CachePublishPlanTests(unittest.TestCase):
    def test_new_cache_is_created(self) -> None:
        self.assertEqual(build_publish_plan(False), ("create_destination",))

    def test_plan_is_nonempty(self) -> None:
        self.assertTrue(build_publish_plan(True))


if __name__ == "__main__":
    unittest.main()
