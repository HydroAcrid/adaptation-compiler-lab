"""Nuitka entrypoint kept outside package directories that shadow stdlib modules."""

from __future__ import annotations

from adaptation_compiler_lab.desktop.engine_main import main

if __name__ == "__main__":
    raise SystemExit(main())
