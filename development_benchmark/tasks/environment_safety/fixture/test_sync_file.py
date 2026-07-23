from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sync_file import sync_file


class SyncFileTests(unittest.TestCase):
    def test_copies_to_a_new_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            destination = root / "nested" / "destination.txt"
            source.write_text("new", encoding="utf-8")

            self.assertEqual(sync_file(source, destination), "copied")
            self.assertEqual(destination.read_text(encoding="utf-8"), "new")

    def test_missing_source_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                sync_file(root / "missing", root / "destination")


if __name__ == "__main__":
    unittest.main()
