import unittest

from migration_guide import build_copy_guide


class MigrationGuideTests(unittest.TestCase):
    def test_returns_a_nonempty_guide(self) -> None:
        self.assertTrue(build_copy_guide("/tmp/source", "/tmp/destination", "zsh"))

    def test_paths_are_included(self) -> None:
        result = build_copy_guide("/tmp/source", "/tmp/destination", "zsh")
        self.assertIn("/tmp/source", result)
        self.assertIn("/tmp/destination", result)


if __name__ == "__main__":
    unittest.main()
