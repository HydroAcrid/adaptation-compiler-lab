"""Native product imports must not eagerly load simulation-only runtime modules."""

from __future__ import annotations

import subprocess
import sys


def test_product_snapshot_import_does_not_load_longitudinal_simulation() -> None:
    script = """
import sys
from adaptation_compiler_lab.automatic_runtime.product_dogfood import TerminalAlphaSnapshot
assert TerminalAlphaSnapshot is not None
assert 'adaptation_compiler_lab.automatic_runtime.longitudinal_simulation' not in sys.modules
assert 'adaptation_compiler_lab.automatic_runtime.dogfood_cli' not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_lazy_public_runtime_exports_remain_compatible() -> None:
    from adaptation_compiler_lab import automatic_runtime

    assert automatic_runtime.TerminalAlphaSnapshot.__name__ == "TerminalAlphaSnapshot"
    assert automatic_runtime.AutomaticAdaptationRuntime.__name__ == "AutomaticAdaptationRuntime"
