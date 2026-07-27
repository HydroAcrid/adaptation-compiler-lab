import unittest

from policy import choose_publish_action


class CachePublishPolicyTests(unittest.TestCase):
    def test_new_cache_is_created(self) -> None:
        self.assertEqual(choose_publish_action(False), "create")

    def test_action_uses_closed_vocabulary(self) -> None:
        self.assertIn(
            choose_publish_action(True),
            {"atomic_replace", "backup_then_replace", "create", "refuse"},
        )


if __name__ == "__main__":
    unittest.main()
