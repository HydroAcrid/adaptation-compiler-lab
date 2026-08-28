from __future__ import annotations

import os
from pathlib import Path

import pytest

from adaptation_compiler_lab.instruction_environment import (
    ClaudeInstructionSourceAdapter,
    CodexInstructionSourceAdapter,
    CopilotInstructionSourceAdapter,
)
from adaptation_compiler_lab.instruction_environment.adapters import MAX_SOURCE_BYTES
from adaptation_compiler_lab.instruction_environment.models import (
    NativeActivationStatus,
    NativeAuthorityClass,
    NativeReadStatus,
    NativeSourceKind,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_codex_reproduces_override_chain_and_never_reads_skill_resources(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    nested = root / "packages" / "api"
    nested.mkdir(parents=True)
    _write(root / "AGENTS.md", "Old root instruction.\n")
    _write(root / "AGENTS.override.md", "Use the verified root instruction.\n")
    _write(nested / "AGENTS.md", "Keep API errors structured.\n")
    _write(root / ".agents" / "skills" / "review" / "SKILL.md", "Review exact diffs.\n")
    _write(root / ".agents" / "skills" / "review" / "scripts" / "unsafe.py", "raise SystemExit\n")
    _write(root / "node_modules" / "AGENTS.md", "Do not discover me.\n")

    sources = CodexInstructionSourceAdapter().discover(
        project_id="temper",
        project_root=root,
        working_directory=nested,
    )

    paths = tuple(item.manifest.display_path for item in sources)
    assert "AGENTS.override.md" in paths
    assert "AGENTS.md" not in paths
    assert "packages/api/AGENTS.md" in paths
    assert not any("node_modules" in item for item in paths)
    skill = next(
        item for item in sources if item.manifest.source_kind is NativeSourceKind.PROJECT_SKILL
    )
    assert skill.manifest.contains_executable_resources
    assert all("SystemExit" not in clause.text for clause in skill.clauses)
    assert tuple(item.manifest.native_precedence for item in sources) == tuple(
        sorted(item.manifest.native_precedence for item in sources)
    )


def test_claude_and_copilot_use_only_documented_source_roots(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    _write(root / "CLAUDE.md", "Explain failures plainly.\n")
    _write(root / ".claude" / "rules" / "python" / "testing.md", "Run focused tests.\n")
    _write(root / ".claude" / "skills" / "debug" / "SKILL.md", "Reproduce first.\n")
    _write(root / ".github" / "copilot-instructions.md", "Prefer small diffs.\n")
    _write(
        root / ".github" / "instructions" / "python.instructions.md",
        "Use Python 3.12.\n",
    )
    _write(root / ".github" / "skills" / "security" / "SKILL.md", "Fail closed.\n")

    claude = ClaudeInstructionSourceAdapter().discover(project_id="temper", project_root=root)
    copilot = CopilotInstructionSourceAdapter().discover(project_id="temper", project_root=root)

    assert {item.manifest.display_path for item in claude} == {
        ".claude/rules/python/testing.md",
        ".claude/skills/debug/SKILL.md",
        "CLAUDE.md",
    }
    assert {
        ".github/copilot-instructions.md",
        ".github/instructions/python.instructions.md",
        ".github/skills/security/SKILL.md",
        "CLAUDE.md",
    } <= {item.manifest.display_path for item in copilot}


def test_invalid_and_oversized_sources_fail_closed(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "AGENTS.md").write_bytes(b"\xff\xfe")
    oversized = tmp_path / "oversized"
    oversized.mkdir()
    (oversized / "AGENTS.md").write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))

    invalid_source = CodexInstructionSourceAdapter().discover(
        project_id="invalid", project_root=invalid
    )[0]
    oversized_source = CodexInstructionSourceAdapter().discover(
        project_id="oversized", project_root=oversized
    )[0]

    assert invalid_source.manifest.read_status is NativeReadStatus.INVALID_ENCODING
    assert not invalid_source.clauses
    assert oversized_source.manifest.read_status is NativeReadStatus.TOO_LARGE
    assert not oversized_source.clauses


def test_symlink_outside_registered_boundary_is_never_read(tmp_path: Path) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside.md"
    root.mkdir()
    outside.write_text("Secret outside instruction.\n", encoding="utf-8")
    link = root / "AGENTS.md"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")

    source = CodexInstructionSourceAdapter().discover(project_id="temper", project_root=root)[0]

    assert source.manifest.read_status is NativeReadStatus.OUTSIDE_BOUNDARY
    assert source.content is None
    assert source.raw_bytes is None


def test_codex_applies_native_chain_limit_and_opted_in_skill_configuration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    nested = root / "nested"
    nested.mkdir(parents=True)
    _write(root / "AGENTS.md", "a" * 20_000)
    _write(nested / "AGENTS.md", "b" * 20_000)
    _write(root / ".agents" / "skills" / "review" / "SKILL.md", "Review exact diffs.\n")
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    skill = (root / ".agents" / "skills" / "review" / "SKILL.md").resolve()
    (home / ".codex" / "config.toml").write_text(
        "project_doc_max_bytes = 65536\n\n"
        "[[skills.config]]\n"
        f'path = "{skill.as_posix()}"\n'
        "enabled = false\n",
        encoding="utf-8",
    )

    default = CodexInstructionSourceAdapter().discover(
        project_id="temper", project_root=root, working_directory=nested
    )
    configured = CodexInstructionSourceAdapter().discover(
        project_id="temper",
        project_root=root,
        working_directory=nested,
        global_roots=(home,),
    )

    assert [
        item.manifest.read_status
        for item in default
        if item.manifest.source_kind is NativeSourceKind.PROJECT_INSTRUCTIONS
    ] == [
        NativeReadStatus.READY,
        NativeReadStatus.TOO_LARGE,
    ]
    assert all(item.manifest.read_status is NativeReadStatus.READY for item in configured)
    configured_skill = next(
        item for item in configured if item.manifest.source_kind is NativeSourceKind.PROJECT_SKILL
    )
    assert configured_skill.manifest.activation_status is NativeActivationStatus.DISABLED


def test_claude_hierarchy_and_rule_scope_are_preserved_without_yaml_execution(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    nested = root / "packages" / "api"
    nested.mkdir(parents=True)
    _write(root / "CLAUDE.md", "Use the project formatter.\n")
    _write(nested / "CLAUDE.local.md", "Use the local test account.\n")
    _write(
        root / ".claude" / "rules" / "api.md",
        '---\npaths:\n  - "packages/api/**/*.py"\n---\nValidate every API input.\n',
    )

    sources = ClaudeInstructionSourceAdapter().discover(
        project_id="temper", project_root=root, working_directory=nested
    )

    assert [
        item.manifest.display_path
        for item in sources
        if item.manifest.source_kind is NativeSourceKind.PROJECT_INSTRUCTIONS
    ] == [
        "CLAUDE.md",
        "packages/api/CLAUDE.local.md",
    ]
    rule = next(
        item for item in sources if item.manifest.source_kind is NativeSourceKind.PROJECT_RULE
    )
    assert "path:packages/api/**/*.py" in rule.clauses[0].scope_labels


def test_claude_managed_instruction_is_detected_as_read_only_managed_policy(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    managed = tmp_path / "managed" / "CLAUDE.md"
    _write(managed, "Follow the organization security policy.\n")

    sources = ClaudeInstructionSourceAdapter(managed_instruction_paths=(managed,)).discover(
        project_id="temper", project_root=project
    )

    source = sources[0]
    assert source.manifest.display_path == "Managed/CLAUDE.md"
    assert source.manifest.source_kind is NativeSourceKind.MANAGED_INSTRUCTIONS
    assert source.manifest.authority_class is NativeAuthorityClass.MANAGED_POLICY
    assert source.manifest.opt_in_basis == "managed"
    assert source.manifest.project_id is None


def test_global_sources_use_each_agents_documented_opt_in_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    _write(home / ".codex" / "AGENTS.md", "Prefer verified commands.\n")
    _write(home / ".claude" / "CLAUDE.md", "Explain failures plainly.\n")
    _write(home / ".copilot" / "copilot-instructions.md", "Keep diffs focused.\n")
    _write(home / ".copilot" / "skills" / "review" / "SKILL.md", "Review the diff.\n")

    codex = CodexInstructionSourceAdapter().discover(
        project_id="temper", project_root=project, global_roots=(home,)
    )
    claude = ClaudeInstructionSourceAdapter().discover(
        project_id="temper", project_root=project, global_roots=(home,)
    )
    copilot = CopilotInstructionSourceAdapter().discover(
        project_id="temper", project_root=project, global_roots=(home,)
    )

    assert {item.manifest.display_path for item in codex} == {"Personal/.codex/AGENTS.md"}
    assert {item.manifest.display_path for item in claude} == {"Personal/.claude/CLAUDE.md"}
    assert {item.manifest.display_path for item in copilot} == {
        "Personal/.copilot/copilot-instructions.md",
        "Personal/.copilot/skills/review/SKILL.md",
    }


def test_empty_codex_instruction_file_is_not_reported_as_loaded(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_bytes(b"")

    assert CodexInstructionSourceAdapter().discover(project_id="temper", project_root=project) == ()


def test_empty_codex_override_falls_back_to_nonempty_agents_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.override.md").write_text("  \n", encoding="utf-8")
    (project / "AGENTS.md").write_text("Keep project instructions active.\n", encoding="utf-8")

    sources = CodexInstructionSourceAdapter().discover(project_id="temper", project_root=project)

    assert [item.manifest.display_path for item in sources] == ["AGENTS.md"]


def test_codex_uses_opted_in_configured_fallback_filename(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text(
        'project_doc_fallback_filenames = ["TEAM_GUIDE.md"]\n',
        encoding="utf-8",
    )
    (project / "TEAM_GUIDE.md").write_text("Use the team formatter.\n", encoding="utf-8")

    sources = CodexInstructionSourceAdapter().discover(
        project_id="temper", project_root=project, global_roots=(home,)
    )

    assert "TEAM_GUIDE.md" in {item.manifest.display_path for item in sources}
