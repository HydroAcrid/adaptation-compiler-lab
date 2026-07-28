import unittest

from posix_handoff import render_posix_handoff


class PosixHandoffTests(unittest.TestCase):
    def test_mentions_paths(self) -> None:
        result = render_posix_handoff("/tmp/source", "/tmp/destination")
        self.assertIn("/tmp/source", result)
        self.assertIn("/tmp/destination", result)

    def test_is_deterministic(self) -> None:
        arguments = ("/tmp/source", "/tmp/destination", "zsh")
        self.assertEqual(render_posix_handoff(*arguments), render_posix_handoff(*arguments))


if __name__ == "__main__":
    unittest.main()
