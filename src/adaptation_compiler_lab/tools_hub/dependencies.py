"""Resolve declared same-source dependencies before native installation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.tools_hub import intake as core


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
