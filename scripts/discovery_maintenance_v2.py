"""Dependency-aware repair of the frozen v1 prototype; v1 evidence stays unchanged."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts import discovery_maintenance as core
except ModuleNotFoundError:
    import discovery_maintenance as core  # type: ignore[no-redef,import-not-found]

_recommend = core.recommend
_reconcile = core.reconcile


def dependencies(row: dict[str, Any], corpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve strong named skill requirements within the authorized source only.

    This deliberately does not pretend to understand every conditional procedure
    or framework runtime dependency. Unknown declarative dependency names fail.
    """
    available = {r["name"]: r for r in corpus if r["source"] == row["source"]}
    fields = core.metadata(Path(row["path"]) / "SKILL.md")
    names = set()
    for field in ("depends", "dependencies", "requires"):
        declared = fields.get(field, "")
        for name in re.findall(r"[a-z][a-z0-9_-]+", declared):
            if name not in available:
                raise ValueError("Unresolved declared skill dependency: " + name)
            names.add(name)
    body = row["body"].split("---", 2)[-1]
    pattern = (
        r"\b(?:apply|load|invoke|use|run)\s+(?:the\s+)?(?:\*\*|`)?"
        r"([a-z][a-z0-9_-]+)(?:\*\*|`)?\s+skill\b"
    )
    for name in re.findall(pattern, body, flags=re.IGNORECASE):
        if name in available and name != row["name"]:
            names.add(name)
    return [available[name] for name in sorted(names)]


def recommend(
    root: Path, catalog: Path, goal: str, *, count: int = 2, node: int = 24
) -> dict[str, Any]:
    result = _recommend(root, catalog, goal, count=count, node=node)
    corpus = core.discover(catalog)
    blocked = {r["id"] for r in result["blocked"]}
    selected: dict[str, dict[str, Any]] = {}
    unresolved = []

    def expand(row: dict[str, Any], stack: set[str], output: dict[str, Any]) -> None:
        if row["id"] in stack:
            raise ValueError("Cyclic skill dependency")
        if row["id"] in blocked:
            raise ValueError("Dependency is incompatible or incomplete")
        if row["id"] in output:
            return
        for child in dependencies(row, corpus):
            expand(child, stack | {row["id"]}, output)
        output[row["id"]] = row

    for row in result["selected"]:
        try:
            closure: dict[str, Any] = {}
            expand(row, set(), closure)
            if len(set(closure) | set(selected)) > count:
                raise ValueError("Complete dependency closure exceeds profile budget")
            selected.update(closure)
        except ValueError as error:
            unresolved.append({"id": row["id"], "reason": str(error)})
    result.update(
        selected=list(selected.values()),
        selection="lexical_metadata_with_dependencies_v2",
        unresolved=unresolved,
    )
    return result


def reconcile(root: Path, selection: dict[str, Any]) -> dict[str, Any]:
    if selection.get("unresolved") and not selection["selected"]:
        return {
            "status": "blocked_dependency",
            "changed": False,
            "unresolved": selection["unresolved"],
        }
    result = _reconcile(root, selection)
    explicit = []
    state_path = root / core.STATE
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    if result["status"] == "deferred_update":
        complete = all(
            (root / p).is_file() and core.sha((root / p).read_bytes()) == digest
            for p, digest in state.get("files", {}).items()
        )
        result["retained_previous_profile_complete"] = complete
        if not complete:
            result.update(
                status="blocked_recovery_requires_compatible_source",
                retained_previous_profile=False,
            )
    for name in state.get("sources", {}):
        path = root / ".agents/skills" / name / "SKILL.md"
        fields = core.metadata(path) if path.is_file() else {}
        if fields.get("disable-model-invocation", "").casefold() in ("true", "yes"):
            explicit.append(name)
    return {
        **result,
        "source_restricts_implicit_invocation": sorted(explicit),
        "instruction_delivery_verified": False,
    }


def main() -> None:
    core.recommend = recommend
    core.reconcile = reconcile
    core.main()


if __name__ == "__main__":
    main()
