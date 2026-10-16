"""Materialize public historical repair replays without exposing their solutions to targets."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "development_benchmark_extensions/real-repo-v1"
TEMPER_FIX = "eb0c396837b84101de8156f41f4f6cb2fce45b9d"
KAIRN_FIX = "d2469ac57bd98f0c5babcdbbddef86433b8fcca5"


def git(repo: str, *args: str) -> bytes:
    command = (
        ["wsl", "-d", "Ubuntu", "--", "git", "-C", repo]
        if repo.startswith("/")
        else ["git", "-C", repo]
    )
    return subprocess.check_output([*command, *args])


def new_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def measure_source_setup(destination: Path) -> None:
    """Five fresh local profiles, with real pinned HTTPS reads and file publication."""
    destination = destination.resolve()
    if any((parent / ".git").exists() for parent in (destination, *destination.parents)):
        raise ValueError("setup samples must stay outside Git")
    destination.mkdir(parents=True, exist_ok=False)
    sources = json.loads((BENCH / "sources.json").read_text(encoding="utf-8"))
    samples = []
    for index in range(5):
        start = time.monotonic()
        network, count = 0.0, 0
        for source in sources:
            repository = source["repository"].removeprefix("https://github.com/")
            name = "ponytail" if source["id"] == "ponytail" else "tdd"
            for remote, local, expected in (
                (source["path"], "SKILL.md", source["source_sha256"]),
                ("LICENSE", "LICENSE", source["license_sha256"]),
            ):
                before = time.monotonic()
                url = f"https://raw.githubusercontent.com/{repository}/{source['commit']}/{remote}"
                data = urlopen(url, timeout=30).read()
                network += time.monotonic() - before
                count += len(data)
                if sha(data) != expected:
                    raise ValueError("pinned source setup digest mismatch")
                path = destination / str(index) / ".agents/skills" / name / local
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        samples.append(
            {
                "seconds": time.monotonic() - start,
                "network_seconds": network,
                "bytes": count,
                "https_requests": 4,
                "published_files": 4,
            }
        )
    new_json(
        destination / "measurement.json",
        {
            "samples": samples,
            "scope": "Pinned file-source skill installation into five fresh "
            "local profiles; real HTTPS fetches, hash verification, "
            "license preservation and file writes. Remote caches "
            "uncontrolled; human discovery, native registration and "
            "framework/product installation not measured.",
        },
    )
    print(json.dumps({"fresh_profile_samples": 5, "seconds": [s["seconds"] for s in samples]}))


def main(fixtures: Path) -> None:
    started = time.monotonic()
    fixtures.mkdir(parents=True, exist_ok=False)
    cases: list[dict[str, Any]] = [
        {
            "id": "temper-live-policy",
            "repository": "https://github.com/HydroAcrid/adaptation-compiler-lab",
            "local_repo": str(ROOT),
            "fix": TEMPER_FIX,
            "kind": "python",
            "task": (
                "Repair the live desktop registration and native-policy workflow. "
                "After the desktop "
                "has read learning status, registering another project must make that project "
                "available to learning grant previews without restarting the app. Registration and "
                "preview must not silently expand any existing signed learning grant. Also fix "
                "native instruction discovery when source_codex_home is an exact custom CODEX_HOME "
                "whose directory is not named .codex: manual global instructions, "
                "override precedence, "
                "config limits, fallback names and disabled skill settings must be read from that "
                "exact directory. Preserve the existing adapter's legacy home-root callers and "
                "default behavior. Temper-managed instructions must remain excluded as native "
                "authority. Add practical regression coverage and verify the affected behavior. "
                "Do not change consent/grant scope, product release gates, dependencies or CI."
            ),
            "visible_check": "python -m pytest -q -p no:cacheprovider "
            "tests/unit/autonomy/test_native_policy.py "
            "tests/unit/instruction_environment/test_adapters.py "
            "tests/unit/desktop/test_engine_protocol.py",
            "grade_check": "python -m pytest -q -p no:cacheprovider "
            "tests/unit/autonomy/test_native_policy.py "
            "tests/unit/autonomy/test_registration_refresh.py "
            "tests/unit/instruction_environment/test_adapters.py "
            "tests/unit/desktop/test_engine_protocol.py",
            "oracle_paths": [
                "src/adaptation_compiler_lab/autonomy/native_policy.py",
                "src/adaptation_compiler_lab/instruction_environment/adapters.py",
                "src/adaptation_compiler_lab/desktop/engine_protocol.py",
            ],
            "grade_paths": [
                "tests/unit/autonomy/test_native_policy.py",
                "tests/unit/autonomy/test_registration_refresh.py",
            ],
            "allowed_prefixes": ["src/", "tests/"],
        },
        {
            "id": "kairn-runtime-cache",
            "repository": "https://github.com/HydroAcrid/kairn",
            "local_repo": "/home/kevin_dotel/projects/kairn",
            "fix": KAIRN_FIX,
            "kind": "node",
            "task": (
                "Fix semantic embedding cache contamination when switching inference runtimes. "
                "The same document and model can produce different vectors under native Node and "
                "WASM packages or package versions. Carry runtimeBackend ('node' or 'wasm') and "
                "the exact runtimeId ('package-name@installed-version') through quantization, "
                "indexing, persistence, incremental reuse, retrieval and reusable "
                "corpus snapshots. "
                "Embeddings for the same document/model under different runtime identities must "
                "coexist; no retrieval or snapshot/lineage cache may reuse a different runtime's "
                "vectors. Determine actual installed package versions rather than hardcoding the "
                "current version. Preserve legacy SQLite data with explicit provenance: entries "
                "without runtime fields were produced by wasm onnxruntime-web@1.27.0 and must not "
                "be relabeled as the current runtime. Make reopening/migration "
                "safe and idempotent. "
                "Keep no-network tests executable and update affected typed callers and fixtures. "
                "Do not download models, add dependencies, retune the ranker, change frozen "
                "evaluation inputs or run CI. Add useful regression coverage and verify the fix."
            ),
            "visible_check": "node node_modules/vitest/vitest.mjs run tests/store.test.ts "
            "tests/semanticCandidates.test.ts tests/evidenceTraining.test.ts "
            "--maxWorkers=1 --no-file-parallelism --reporter=json",
            "grade_check": "node node_modules/vitest/vitest.mjs run tests/store.test.ts "
            "tests/semanticCandidates.test.ts tests/evidenceTraining.test.ts "
            "--maxWorkers=1 --no-file-parallelism --reporter=json",
            "typecheck": "node node_modules/typescript/bin/tsc --noEmit",
            "oracle_paths": [
                "scripts/evaluate-semantic-model.ts",
                "scripts/materialize-evidence-corpus.ts",
                "src/indexer/indexRepo.ts",
                "src/retrieval/semanticCandidates.ts",
                "src/semantic/modelRuntime.ts",
                "src/store/sqliteStore.ts",
                "src/types/graph.ts",
            ],
            "grade_paths": [
                "tests/store.test.ts",
                "tests/semanticCandidates.test.ts",
                "tests/evidenceTraining.test.ts",
            ],
            "allowed_prefixes": ["src/", "scripts/", "tests/"],
        },
    ]
    metrics = []
    for case in cases:
        stage = time.monotonic()
        repo = str(case.pop("local_repo"))
        case["base_commit"] = git(repo, "rev-parse", str(case["fix"]) + "^").decode().strip()
        archive = git(repo, "archive", "--format=tar", str(case["base_commit"]))
        case["archive_sha256"] = sha(archive)
        folder = fixtures / str(case["id"])
        folder.mkdir()
        (folder / "base.tar").write_bytes(archive)
        # Validate before any agent is started. No future commit history enters the archive.
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            if any(m.issym() or m.islnk() for m in tar.getmembers()):
                raise ValueError("historical repository has unsupported symlinks")
        for category, paths in (("oracle", case["oracle_paths"]), ("grading", case["grade_paths"])):
            mapping = {str(p): git(repo, "show", f"{case['fix']}:{p}").decode() for p in paths}
            new_json(folder / (category + ".json"), mapping)
            case[category + "_file_sha256"] = {p: sha(c.encode()) for p, c in mapping.items()}
        metrics.append(
            {
                "task_id": case["id"],
                "archive_and_reference_seconds": time.monotonic() - stage,
                "archive_bytes": len(archive),
            }
        )
    source_start = time.monotonic()
    previous = json.loads(
        (ROOT / "development_benchmark_extensions/rapid-v1/sources.json").read_text(
            encoding="utf-8"
        )
    )
    ponytail = previous[0]
    pstack = previous[1]
    url = f"https://raw.githubusercontent.com/backnotprop/pstack/{pstack['commit']}/skills/tdd/SKILL.md"
    text = urlopen(url, timeout=30).read().decode()
    tdd = {
        **pstack,
        "id": "pstack-tdd",
        "path": "skills/tdd/SKILL.md",
        "text": text,
        "source_sha256": sha(text.encode()),
    }
    new_json(BENCH / "sources.json", [ponytail, tdd])
    new_json(BENCH / "cases.json", cases)
    new_json(
        fixtures / "preparation.json",
        {
            "repository_acquisition": metrics,
            "extension_acquisition_seconds": time.monotonic() - source_start,
            "extension_acquisition": "Ponytail reused from the previous pinned local snapshot; "
            "pstack-tdd fetched at that same pinned pstack commit. This is "
            "not a fully cold source installation.",
            "total_automated_preparation_seconds": time.monotonic() - started,
            "human_research_and_harness_development_minutes": None,
        },
    )
    print(
        json.dumps(
            {
                "prepared": [c["id"] for c in cases],
                "fixtures": str(fixtures),
                "source_ids": ["ponytail", "pstack-tdd"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--measure-source-setup", type=Path)
    args = parser.parse_args()
    if args.measure_source_setup is not None:
        measure_source_setup(args.measure_source_setup)
    elif args.fixtures is not None:
        main(args.fixtures)
    else:
        parser.error("choose --fixtures or --measure-source-setup")
