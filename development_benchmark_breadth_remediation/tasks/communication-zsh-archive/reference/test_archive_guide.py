import unittest

from archive_guide import build_archive_guide


class ArchiveGuideTests(unittest.TestCase):
    def test_supplied_paths_appear_in_the_handoff(self) -> None:
        result = build_archive_guide("/tmp/source tree", "/tmp/release tree")
        self.assertIn("source tree", result)
        self.assertIn("release tree", result)

    def test_rendering_is_deterministic(self) -> None:
        arguments = ("/tmp/source", "/tmp/release", "zsh")
        self.assertEqual(build_archive_guide(*arguments), build_archive_guide(*arguments))


if __name__ == "__main__":
    unittest.main()
