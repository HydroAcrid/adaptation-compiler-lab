"""Fingerprint the applicable native instruction inventory without copying private prose."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.instruction_environment.adapters import CodexInstructionSourceAdapter

from .controller import fingerprint
from .intake import sha
from .paths import files, safe


def native_policy_digest(
    root: Path,
    codex_home: Path,
    owned: dict[str, str] | None = None,
    working_directory: Path | None = None,
) -> str:
    inventory = CodexInstructionSourceAdapter(exact_codex_homes=True).discover(
        project_id="hub-policy",
        project_root=root,
        working_directory=working_directory,
        global_roots=(codex_home,) if codex_home.is_dir() else (),
    )
    result: dict[str, Any] = {"working_directory": str(working_directory or root)}
    config_path = safe(codex_home, "config.toml")
    if config_path.is_file() and config_path.stat().st_size > 1_000_000:
        raise ValueError("Codex configuration exceeds the supported policy bound")
    config = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
    fallback = config.get("project_doc_fallback_filenames", [])
    if (
        not isinstance(fallback, list)
        or len(fallback) > 16
        or not all(isinstance(name, str) and "/" not in name for name in fallback)
    ):
        raise ValueError("Unsupported native instruction fallback configuration")
    for item in inventory:
        # Temper's own current profile must not invalidate its next cached choice.
        if item.path.is_relative_to(root) and (owned or {}).get(
            item.path.relative_to(root).as_posix()
        ) == sha(item.path.read_bytes()):
            continue
        result[str(item.path)] = item.manifest.model_dump(mode="json")
    # Codex also reads ancestor policy and config-controlled fallback names/disabled skills.
    for directory in (root, *root.parents):
        for name in ("AGENTS.md", "AGENTS.override.md", *fallback):
            path = safe(directory, name)
            if path.is_file() and path.stat().st_size > 256_000:
                raise ValueError("Native instruction source exceeds the supported policy bound")
            result[str(path)] = sha(path.read_bytes()) if path.is_file() else None
    path = safe(codex_home, "config.toml")
    if path.is_file() and path.stat().st_size > 1_000_000:
        raise ValueError("Codex configuration exceeds the supported policy bound")
    result[str(path)] = sha(path.read_bytes()) if path.is_file() else None
    for skill_root in (safe(codex_home, "skills"), safe(codex_home.parent, ".agents/skills")):
        if skill_root.is_dir():
            for skill in files(skill_root, maximum_bytes=64_000_000, maximum_entries=20_000):
                if skill.name == "SKILL.md":
                    if skill.stat().st_size > 256_000:
                        raise ValueError("Native personal skill exceeds its instruction bound")
                    result[str(skill)] = sha(skill.read_bytes())
    return fingerprint(result)
