"""Classify every public 6A and proposed 6A.1 target-visible line."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

_ACTION = "Actionable behavior"
_SCOPE = "Necessary scope"
_PRECEDENCE = "Necessary precedence or exception"
_VERIFICATION = "Necessary verification"
_BOUNDARY = "Universal execution/security boundary"
_AUDIT = "Audit-only provenance"
_BOILERPLATE = "Redundant metadata or boilerplate"
_HARMFUL = "Potentially distracting or harmful instruction"


def _exclusive_write(path: Path, value: dict[str, object]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    encoded = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _old_classification(line: str) -> tuple[str, tuple[str, ...]]:
    stripped = line.strip()
    if not stripped:
        return _BOILERPLATE, ()
    if stripped == "# Compiled adaptation" or stripped.startswith("## Apply "):
        return _HARMFUL, ()
    if stripped.startswith("These scoped, reviewed artifacts"):
        return _BOUNDARY, ()
    if stripped.startswith("- For "):
        return _ACTION, (_SCOPE,)
    if stripped.startswith("- Verify "):
        return _VERIFICATION, ()
    if stripped.startswith("- Projects:"):
        return _SCOPE, ()
    if (
        stripped.startswith("- Supporting evidence IDs:")
        or stripped.startswith("- Evaluation case IDs:")
        or stripped.startswith("- Claim-specific authority:")
        or stripped.startswith("- user_correction:")
        or stripped.startswith("Type:")
        or stripped.startswith("Artifact:")
        or stripped.startswith("- Subjects:")
        or stripped.startswith("- Target families:")
        or stripped.startswith("- Compatible target profiles:")
        or stripped.startswith("- Precedence:")
    ):
        return _AUDIT, ()
    if stripped.startswith("#"):
        return _BOILERPLATE, ()
    raise ValueError(f"unclassified compiled line: {line!r}")


def _profile_classification(line: str) -> tuple[str, tuple[str, ...]]:
    stripped = line.strip()
    if not stripped:
        return _BOILERPLATE, ()
    if stripped.startswith("Scoped exception:"):
        return _PRECEDENCE, (_ACTION, _SCOPE)
    roles = [_SCOPE]
    if "Verify " in stripped:
        roles.append(_VERIFICATION)
    return _ACTION, tuple(roles)


def _runtime_classification(
    line: str,
    clauses: list[dict[str, object]],
) -> tuple[str, tuple[str, ...]]:
    text = line.removeprefix("- ").rstrip("\n")
    clause = next((item for item in clauses if item.get("text") == text), None)
    if clause is None:
        raise ValueError(f"runtime line has no canonical clause: {text!r}")
    raw_roles = clause.get("roles")
    if not isinstance(raw_roles, list) or not all(isinstance(item, str) for item in raw_roles):
        raise ValueError("runtime clause roles are malformed")
    role_map = {
        "actionable_behavior": _ACTION,
        "necessary_scope": _SCOPE,
        "necessary_precedence": _PRECEDENCE,
        "necessary_verification": _VERIFICATION,
    }
    roles = tuple(role_map[item] for item in raw_roles)
    primary = (
        _ACTION if _ACTION in roles else _PRECEDENCE if _PRECEDENCE in roles else _VERIFICATION
    )
    return primary, tuple(item for item in roles if item != primary)


def _records(
    path: Path,
    *,
    stage: int,
    material: str,
    clauses: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    records: list[dict[str, object]] = []
    totals: defaultdict[str, int] = defaultdict(int)
    with path.open("r", encoding="utf-8", newline="") as stream:
        lines = stream.readlines()
    for line_number, line in enumerate(lines, start=1):
        encoded_bytes = len(line.encode("utf-8"))
        if material == "compiled_6a":
            category, secondary = _old_classification(line)
        elif material == "strong_profile_6a":
            category, secondary = _profile_classification(line)
        else:
            assert clauses is not None
            category, secondary = _runtime_classification(line, clauses)
        records.append(
            {
                "classification": category,
                "line": line.rstrip("\r\n"),
                "line_number": line_number,
                "secondary_semantic_roles": list(secondary),
                "utf8_bytes_including_newline": encoded_bytes,
            }
        )
        totals[category] += encoded_bytes
    if sum(totals.values()) != path.stat().st_size:
        raise RuntimeError(f"line classification does not sum to exact file size: {path}")
    return records, dict(sorted(totals.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    old = repo / "development_benchmark_longitudinal" / "condition-materials"
    runtime = repo / "development_benchmark_compact_projection" / "runtime-fixture"
    stages: list[dict[str, object]] = []
    for stage in (1, 2, 3):
        projection = json.loads(
            (runtime / f"canonical-runtime-projection-stage-{stage}.json").read_text(
                encoding="utf-8"
            )
        )
        clauses = projection.get("clauses")
        if not isinstance(clauses, list) or not all(isinstance(item, dict) for item in clauses):
            raise RuntimeError("canonical runtime fixture clauses are malformed")
        values: dict[str, object] = {"stage": stage}
        for material, path, material_clauses in (
            ("compiled_6a", old / f"compiled-stage-{stage}.md", None),
            (
                "strong_profile_6a",
                old / f"strong-profile-stage-{stage}.md",
                None,
            ),
            (
                "compact_runtime_6a1",
                runtime / f"codex-runtime-stage-{stage}.md",
                clauses,
            ),
        ):
            records, totals = _records(
                path,
                stage=stage,
                material=material,
                clauses=material_clauses,
            )
            values[material] = {
                "classification_bytes": totals,
                "clauses": records,
                "total_utf8_bytes": path.stat().st_size,
            }
        stages.append(values)
    _exclusive_write(
        arguments.output.resolve(),
        {
            "analysis_version": "1.0.0",
            "classification_is_line_based": True,
            "stages": stages,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
