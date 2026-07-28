import unittest

from release_handoff import render_release_handoff


class ReleaseHandoffTests(unittest.TestCase):
    def test_mentions_both_paths(self) -> None:
        value = render_release_handoff("/tmp/build", "/tmp/release")
        self.assertIn("/tmp/build", value)
        self.assertIn("/tmp/release", value)

    def test_is_deterministic(self) -> None:
        arguments = ("/tmp/build", "/tmp/release", "zsh")
        self.assertEqual(
            render_release_handoff(*arguments),
            render_release_handoff(*arguments),
        )


if __name__ == "__main__":
    unittest.main()
