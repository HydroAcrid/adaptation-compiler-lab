from __future__ import annotations

import unittest

from recovery_handoff import build_recovery_handoff


class RecoveryHandoffTests(unittest.TestCase):
    def test_purpose_precedes_recovery_commands(self) -> None:
        handoff = build_recovery_handoff(
            "Restore the on-call configuration after a failed rollout.",
            r"C:\Recovery\on-call archive",
            r"C:\Service\config",
        )

        self.assertLess(handoff.index("Restore the on-call"), handoff.index("Recovery commands"))

    def test_output_is_deterministic(self) -> None:
        arguments = (
            "Restore a known-good configuration.",
            r"C:\Recovery\known-good",
            r"C:\Service\config",
        )

        self.assertEqual(build_recovery_handoff(*arguments), build_recovery_handoff(*arguments))


if __name__ == "__main__":
    unittest.main()
