"""Target-native packaging command tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[3]


def _build_module() -> ModuleType:
    path = ROOT / "packaging" / "build_native.py"
    spec = importlib.util.spec_from_file_location("adaptation_compiler_native_build", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_builder_is_standalone_and_includes_only_product_qml() -> None:
    command = _build_module().build_command(ROOT, platform_name="win32")
    rendered = "\n".join(command)

    assert "--standalone" in command
    assert "--enable-plugin=pyside6" in command
    assert "adaptation_compiler_lab/desktop/qml" in rendered
    assert "--windows-console-mode=disable" in command
    assert "--onefile" not in command
    assert ".env" not in rendered


def test_native_builder_refuses_unsupported_cross_platform_output() -> None:
    with pytest.raises(ValueError, match="only native Windows and macOS"):
        _build_module().build_command(ROOT, platform_name="linux")
