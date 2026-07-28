import unittest

from ledger_status import derive_status


class LedgerStatusTests(unittest.TestCase):
    def test_note_is_used_without_events(self) -> None:
        self.assertEqual(
            derive_status((), "ready"),
            {"classification": "ready", "source": "status_note"},
        )

    def test_result_is_structured(self) -> None:
        events = ({"at": "2026-07-01T12:00:00Z", "status": "completed"},)
        self.assertIsInstance(derive_status(events, "blocked"), dict)


if __name__ == "__main__":
    unittest.main()
