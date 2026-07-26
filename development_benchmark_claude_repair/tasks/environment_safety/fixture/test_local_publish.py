from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_publish import (
    PublishConflictError,
    UnsafeLayoutError,
    preflight_publish,
    publish_local,
    restore_publish,
)


def _write(root: Path, relative: str, value: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class LocalPublishTests(unittest.TestCase):
    def test_new_destination_is_created_recursively_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            _write(source, "nested/value.txt", "source")
            source_before = _snapshot(source)

            result = publish_local(source, destination)

            self.assertEqual(_snapshot(destination), source_before)
            self.assertEqual(_snapshot(source), source_before)
            self.assertIsNone(result.backup_path)

    def test_recursive_difference_is_safe_by_default_and_visible_in_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            _write(source, "nested/value.txt", "source")
            _write(destination, "nested/value.txt", "hand-edited")
            destination_before = _snapshot(destination)

            plan = preflight_publish(source, destination)
            with self.assertRaises(PublishConflictError):
                publish_local(source, destination)

            self.assertTrue(plan.destination_exists)
            self.assertTrue(plan.content_differs)
            self.assertTrue(plan.overwrite_risk)
            self.assertIsNotNone(plan.backup_path)
            self.assertEqual(_snapshot(destination), destination_before)

    def test_identical_destination_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            _write(source, "nested/value.txt", "same")
            _write(destination, "nested/value.txt", "same")
            before = (destination / "nested" / "value.txt").stat().st_mtime_ns

            result = publish_local(source, destination)

            self.assertEqual((destination / "nested" / "value.txt").stat().st_mtime_ns, before)
            self.assertIsNone(result.backup_path)

    def test_replace_uses_unused_exact_backup_and_restore_removes_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            _write(source, "nested/value.txt", "source")
            _write(destination, "nested/value.txt", "hand-edited")
            _write(destination, "custom/local.txt", "keep")
            destination_before = _snapshot(destination)
            occupied_backup = destination.with_name(destination.name + ".backup")
            _write(occupied_backup, "marker.txt", "existing backup")

            result = publish_local(source, destination, replace=True)

            self.assertIsNotNone(result.backup_path)
            assert result.backup_path is not None
            self.assertNotEqual(result.backup_path, occupied_backup)
            self.assertEqual(_snapshot(result.backup_path), destination_before)
            self.assertEqual(_snapshot(destination), _snapshot(source))
            _write(destination, "post-publish.txt", "remove during restore")

            restore_publish(result.backup_path, destination)

            self.assertEqual(_snapshot(destination), destination_before)

    def test_identical_and_nested_layouts_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            _write(source, "nested/value.txt", "source")

            for unsafe_source, unsafe_destination in (
                (source, source),
                (source, source / "output"),
                (source / "input", source),
            ):
                with (
                    self.subTest(source=unsafe_source, destination=unsafe_destination),
                    self.assertRaises(UnsafeLayoutError),
                ):
                    preflight_publish(unsafe_source, unsafe_destination)


if __name__ == "__main__":
    unittest.main()
