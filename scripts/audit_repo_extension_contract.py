"""Diagnostic API-neutral replay; original frozen tests and scores remain untouched."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config, _runtime_secrets
from adaptation_compiler_lab.benchmark.repo_extension_screen import RepoShell, parse_grade
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore, RawPayloadRef
from scripts.run_repo_extension_screen import (
    BENCH,
    extended,
    extract,
    mapping,
    new_json,
    put,
    remove_tree,
    runtime_for,
)

HELPER = (
    """
// Diagnostic test-fixture adapter: the task adds explicit runtime identity.
// Existing expected values and test bodies are unchanged.
function __lockedIdentity(input: any): any {
  const first = input.embeddings?.[0];
  const runtimeId = input.runtimeId ?? first?.runtimeId;
  const runtimeBackend = input.runtimeBackend ?? first?.runtimeBackend ??
    (typeof runtimeId === "string" && runtimeId.startsWith("onnxruntime-node@") ? "node" :
      """
    'typeof runtimeId === "string" && runtimeId.startsWith("onnxruntime-web@") ? '
    '"wasm" : undefined);\n'
    """  return { ...input, ...(runtimeId === undefined ? {} : { runtimeId }),
    ...(runtimeBackend === undefined ? {} : { runtimeBackend }) };
}
"""
)


def adapt(files: dict[str, str]) -> dict[str, str]:
    result = dict(files)
    targets = {
        "tests/evidenceTraining.test.ts": (
            "buildRepositoryIndexSnapshotCacheKey",
            "buildSemanticLineageCacheKey",
            "buildSemanticSnapshotCacheKey",
        ),
        "tests/semanticCandidates.test.ts": ("scoreSemanticEmbeddingIndex",),
    }
    for path, names in targets.items():
        text = result[path]
        wrappers = []
        for name in names:
            text, count = re.subn(
                r"(?m)^(\s*)" + name + r"(,?)\s*$",
                rf"\g<1>{name} as __locked_{name}\g<2>",
                text,
                count=1,
            )
            if count != 1:
                raise ValueError("pinned fixture import no longer matches its adapter")
            wrappers.append(
                f"function {name}(input: any): ReturnType<typeof __locked_{name}> "
                f"{{ return __locked_{name}(__lockedIdentity(input)); }}"
            )
        result[path] = text + HELPER + "\n".join(wrappers) + "\n"
    return result


def main(config_path: Path, run: Path, fixtures: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    config = _load_config(config_path)
    raw = LocalRawPayloadStore(
        run / "encrypted-raw",
        encryption_key=_runtime_secrets(config).raw_encryption_key(
            workspace_root=config.repository_root
        ),
    )
    cases = json.loads((BENCH / "cases.json").read_text(encoding="utf-8"))
    case = next(c for c in cases if c["kind"] == "node")
    tests = adapt(mapping(case, fixtures, "grading"))
    new_json(
        output / "fixture-binding.json",
        {
            "adapted_tests_sha256": {
                p: hashlib.sha256(v.encode()).hexdigest() for p, v in tests.items()
            },
            "expected_tests": 98,
            "scope": "Supply complete explicit runtime identity to four internal helpers; "
            "do not change assertions, queries, expected outputs, production code "
            "or frozen scores.",
        },
    )
    controls: list[dict[str, Any]] = []
    for label in ("original", "reference"):
        project = output / ("control-" + label)
        extract(case, fixtures, project)
        if label == "reference":
            put(project, mapping(case, fixtures, "oracle"))
        put(project, tests)
        result = RepoShell(project, runtime_for(case)).run(case["grade_check"], limit=2_000_000)
        score = parse_grade("node", result["output"], result["returncode"])
        ref = raw.put(json.dumps(result).encode(), media_type="application/json")
        controls.append({"label": label, "score": score, "raw_ref": asdict(ref)})
        remove_tree(project, output)
    if not (
        controls[0]["score"]["failed"] > 0
        and controls[1]["score"]["passed"] == 98
        and controls[1]["score"]["complete"]
    ):
        new_json(output / "failed-controls.json", controls)
        raise ValueError(
            "API-neutral fixture controls did not detect the bug and accept its repair"
        )
    new_json(output / "controls.json", controls)
    print(json.dumps({"api_neutral_controls": [c["score"] for c in controls]}), flush=True)
    seen: set[str] = set()
    while len(seen) < 6:
        for path in sorted((run / "trials").glob("kairn*/receipt.json")):
            name = path.parent.name
            if name in seen:
                continue
            receipt = json.loads(path.read_text(encoding="utf-8"))
            start = time.monotonic()
            project = output / (name + "-project")
            extract(case, fixtures, project)
            patch = json.loads(raw.read(RawPayloadRef(**receipt["patch_ref"])))
            put(project, patch)
            put(project, tests)
            result = RepoShell(project, runtime_for(case)).run(case["grade_check"], limit=2_000_000)
            score = parse_grade("node", result["output"], result["returncode"])
            ref = raw.put(json.dumps(result).encode(), media_type="application/json")
            remove_tree(project, output)
            new_json(
                output / (name + ".json"),
                {
                    "task_id": receipt["task_id"],
                    "arm": receipt["arm"],
                    "repeat": receipt["repeat"],
                    "score": score,
                    "instrument_valid": result["instrument_valid"] and score["receipt_present"],
                    "audit_seconds": time.monotonic() - start,
                    "raw_ref": asdict(ref),
                    "diagnostic_only": True,
                },
            )
            seen.add(name)
            print(
                json.dumps(
                    {"contract_audited": name, "passed": score["passed"], "failed": score["failed"]}
                ),
                flush=True,
            )
        if len(seen) < 6:
            time.sleep(5)
    new_json(output / "complete.json", {"audited_kairn_trials": 6, "additional_model_turns": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("config", "run", "fixtures", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    main(args.config, extended(args.run), extended(args.fixtures), extended(args.output))
