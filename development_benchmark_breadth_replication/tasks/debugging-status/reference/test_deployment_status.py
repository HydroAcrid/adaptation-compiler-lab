import unittest

from deployment_status import derive_deployment_status


class DeploymentStatusTests(unittest.TestCase):
    def test_completed_event_is_ready(self) -> None:
        events = ({"at": "2026-01-01T00:00:00Z", "status": "completed"},)
        self.assertEqual(derive_deployment_status(events, "ready")["classification"], "ready")

    def test_result_is_structured(self) -> None:
        self.assertIn("source", derive_deployment_status((), "pending"))


if __name__ == "__main__":
    unittest.main()
