from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_publish import PublishConflictError, publish_local


class LocalPublishTests(unittest.TestCase):
    def test_new_destination_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            (source / "value.txt").write_text("source", encoding="utf-8")

            result = publish_local(source, destination)

            self.assertEqual((destination / "value.txt").read_text(), "source")
            self.assertIsNone(result.backup_path)

    def test_different_destination_is_safe_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "value.txt").write_text("source", encoding="utf-8")
            (destination / "value.txt").write_text("custom", encoding="utf-8")

            with self.assertRaises(PublishConflictError):
                publish_local(source, destination)
            self.assertEqual((destination / "value.txt").read_text(), "custom")


if __name__ == "__main__":
    unittest.main()
