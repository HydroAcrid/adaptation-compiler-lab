import unittest

from deployment_state import derive_deployment_state


class DeploymentStateTests(unittest.TestCase):
    def test_note_is_fallback_without_events(self) -> None:
        self.assertEqual(
            derive_deployment_state((), "ready"),
            {"state": "ready", "source": "status_note"},
        )

    def test_returns_a_state_mapping(self) -> None:
        result = derive_deployment_state(
            ({"observed_at": "2026-07-01T10:00:00Z", "status": "completed"},),
            "unknown",
        )
        self.assertEqual(set(result), {"state", "source"})


if __name__ == "__main__":
    unittest.main()
