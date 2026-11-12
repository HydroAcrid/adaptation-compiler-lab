from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path, PureWindowsPath

import pytest

from adaptation_compiler_lab.tools_hub.paths import check_windows_path, files


def test_windows_file_budget_counts_non_bmp_utf16_units() -> None:
    root = PureWindowsPath("C:/", "a" * 230)
    allowed = root / ("a" * 23 + "\U0001f600")
    check_windows_path(allowed, directory=False, operation="test")
    with pytest.raises(ValueError, match=r"file path uses 260 UTF-16 units \(limit 259\)"):
        check_windows_path(allowed.with_name(allowed.name + "a"), directory=False, operation="test")


def test_windows_directory_budget_applies_to_file_parents() -> None:
    root = PureWindowsPath("C:/", "a" * 244)
    check_windows_path(root, directory=True, operation="test")
    check_windows_path(root / "b", directory=False, operation="test")
    longer = root.with_name(root.name + "a")
    with pytest.raises(ValueError, match=r"directory path uses 248 UTF-16 units \(limit 247\)"):
        check_windows_path(longer, directory=True, operation="test")
    with pytest.raises(ValueError, match=r"directory path uses 248 UTF-16 units \(limit 247\)"):
        check_windows_path(longer / "b", directory=False, operation="test")


def test_windows_component_budget_is_independent_of_absolute_file_budget() -> None:
    root = PureWindowsPath("C:/")
    allowed = "a" * 253 + "\U0001f600"
    check_windows_path(root / allowed, directory=False, operation="test")
    with pytest.raises(ValueError, match=r"path component uses 256 UTF-16 units \(limit 255\)"):
        check_windows_path(root / (allowed + "a"), directory=False, operation="test")


def test_file_walk_propagates_disappearing_listed_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    disappeared = tmp_path / "unavailable"
    original = Path.iterdir

    def listing(path: Path) -> Iterator[Path]:
        if path == tmp_path:
            return iter([disappeared])
        return original(path)

    monkeypatch.setattr(Path, "iterdir", listing)
    with pytest.raises(FileNotFoundError):
        files(tmp_path, maximum_bytes=100)
