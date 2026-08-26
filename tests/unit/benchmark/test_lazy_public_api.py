"""The desktop import path must not eagerly load research runners."""

from __future__ import annotations

import subprocess
import sys


def test_benchmark_model_import_does_not_load_agent_development_runners() -> None:
    script = """
import sys
from adaptation_compiler_lab.benchmark.models import BenchmarkConfig
assert BenchmarkConfig is not None
assert 'adaptation_compiler_lab.benchmark.claude_development' not in sys.modules
assert 'adaptation_compiler_lab.benchmark.codex_development' not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_lazy_public_benchmark_exports_remain_compatible() -> None:
    from adaptation_compiler_lab import benchmark

    assert benchmark.BenchmarkConfig.__name__ == "BenchmarkConfig"
    assert benchmark.CodexDevelopmentTask.__name__ == "CodexDevelopmentTask"
