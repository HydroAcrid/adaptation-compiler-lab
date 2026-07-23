from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sync_helper import SyncConflictError, restore_backup, sync_local


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SyncHelperTests(unittest.TestCase):
    def test_conflicting_destination_is_safe_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            _write(source, "settings.ini", "source")
            _write(destination, "settings.ini", "customized")

            with self.assertRaises(SyncConflictError):
                sync_local(source, destination)

            self.assertEqual((destination / "settings.ini").read_text(), "customized")

    def test_explicit_replacement_can_be_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            _write(source, "settings.ini", "source")
            _write(destination, "settings.ini", "customized")

            result = sync_local(source, destination, replace=True)

            self.assertIsNotNone(result.backup_path)
            assert result.backup_path is not None
            self.assertTrue(result.backup_path.is_dir())
            self.assertEqual((destination / "settings.ini").read_text(), "source")
            restore_backup(result.backup_path, destination)
            self.assertEqual((destination / "settings.ini").read_text(), "customized")

    def test_new_destination_is_copied_without_a_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            _write(source, "nested/value.txt", "new")

            result = sync_local(source, destination)

            self.assertIsNone(result.backup_path)
            self.assertEqual((destination / "nested/value.txt").read_text(), "new")


if __name__ == "__main__":
    unittest.main()
