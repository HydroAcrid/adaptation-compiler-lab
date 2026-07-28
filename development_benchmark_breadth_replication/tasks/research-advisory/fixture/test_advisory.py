import unittest

from advisory import select_advisory


class AdvisoryTests(unittest.TestCase):
    def test_one_signed_record_is_selected(self) -> None:
        records = (
            {
                "source": "signed_registry",
                "signed": True,
                "applicable": True,
                "effective_at": "2026-01-01T00:00:00Z",
                "recommendation": "allow",
            },
        )
        self.assertEqual(
            select_advisory(records, "2026-02-01T00:00:00Z")["recommendation"],
            "allow",
        )

    def test_result_is_a_new_mapping(self) -> None:
        record = {
            "source": "signed_registry",
            "signed": True,
            "applicable": True,
            "effective_at": "2026-01-01T00:00:00Z",
        }
        self.assertIsNot(select_advisory((record,), "2026-02-01T00:00:00Z"), record)


if __name__ == "__main__":
    unittest.main()
