"""Public calibration inputs bundled with the engine; never owner evidence or credentials."""

from __future__ import annotations

import shutil
from pathlib import Path

from adaptation_compiler_lab.autonomy.analyzer import EVALUATION_VERSION
from adaptation_compiler_lab.connectors.pins import sha256_file
from adaptation_compiler_lab.serialization import canonical_digest

PROTOCOL_FILES = {
    "runner": "evaluation_run.py",
    "host": "service.py",
    "scorer": "evaluation.py",
    "lifecycle_scorer": "lifecycle_evaluation.py",
    "budget": "budget.py",
    "retention": "retention.py",
    "store": "store.py",
    "analyzer_host": "analyzer.py",
    "episode_models": "models.py",
    "transport": "codex_transport.py",
}
NATIVE_FILES = (
    "calibration.py",
    "native.py",
    "publisher.py",
    "native_policy.py",
    "agent_bridge.py",
    "calibration_assets.py",
    "qualification.py",
    "worker.py",
    "validation_retention.py",
)
INSTRUCTION_FILES = ("adapters.py", "resolver.py", "semantic.py", "codex_semantic.py")
PREFIX = EVALUATION_VERSION.replace("-", "_") + "_prospective"
FIXTURE = "tests/fixtures/autonomy/" + PREFIX + ".json"
MANIFEST = "tests/fixtures/autonomy/" + PREFIX + ".manifest.json"
DRIVER = "scripts/run_owner_habit_evaluation.py"
NATIVE_PRODUCER = "scripts/validate_native_habit_delivery.py"
PUBLIC_INPUTS = tuple(
    sorted(
        {
            *("src/adaptation_compiler_lab/autonomy/" + name for name in PROTOCOL_FILES.values()),
            *("src/adaptation_compiler_lab/autonomy/" + name for name in NATIVE_FILES),
            *(
                "src/adaptation_compiler_lab/instruction_environment/" + name
                for name in INSTRUCTION_FILES
            ),
            "src/adaptation_compiler_lab/desktop/engine_main.py",
            "src/adaptation_compiler_lab/autonomy/codex_capacity.py",
            "src/adaptation_compiler_lab/connectors/pins.py",
            FIXTURE,
            MANIFEST,
            DRIVER,
            NATIVE_PRODUCER,
        }
    )
)


def _asset_name(relative: str) -> str:
    # Short inert filenames avoid Windows MAX_PATH at Nuitka's nested staging root.
    # The sorted allowlist and its own source are bound into inputs_digest().
    return f"{PUBLIC_INPUTS.index(relative):03d}.txt"


def asset_path(relative: str) -> Path:
    if relative not in PUBLIC_INPUTS:
        raise ValueError("unknown public calibration input")
    if "__compiled__" in globals():
        # Nuitka deliberately excludes Python code from generic data directories.
        # These are inert source snapshots used only for hashing, with .txt suffixes.
        path = Path(__file__).parent / "qualification_assets" / _asset_name(relative)
    else:
        path = Path(__file__).resolve().parents[3] / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError("public calibration input is unavailable")
    return path


def inputs_digest() -> str:
    return str(canonical_digest({name: sha256_file(asset_path(name)) for name in PUBLIC_INPUTS}))


def export_assets(repository: Path, destination: Path) -> None:
    """Copy a fixed public allowlist; no discovery of runtime/owner state."""
    root = repository.resolve()
    target = destination.resolve()
    if target != root / "build" / "calibration-assets":
        raise ValueError("calibration export must use the bounded build directory")
    # The resolved absolute target was checked against the intended workspace.
    # Never bundle stray files from an earlier build or owner-created scratch data.
    if target.exists():
        shutil.rmtree(target)
    for name in PUBLIC_INPUTS:
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("public calibration build input is unavailable")
        path = target / _asset_name(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
