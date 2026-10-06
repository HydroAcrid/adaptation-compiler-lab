"""Deterministic, non-executing adapters for native agent instruction sources."""

from __future__ import annotations

import os
import platform
import re
import tomllib
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final, Literal

from adaptation_compiler_lab.instruction_environment.models import (
    InstructionSourceManifestV1,
    NativeActivationStatus,
    NativeAuthorityClass,
    NativeInstructionClauseV1,
    NativeInstructionKind,
    NativeNormStrength,
    NativeReadStatus,
    NativeSourceKind,
    NativeTarget,
)
from adaptation_compiler_lab.serialization import canonical_digest

MAX_SOURCE_BYTES: Final = 256 * 1024
MAX_ENVIRONMENT_BYTES: Final = 2 * 1024 * 1024
DEFAULT_CODEX_INSTRUCTION_BYTES: Final = 32 * 1024
_EXCLUDED_COMPONENTS: Final = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "tmp",
    }
)
_MARKDOWN_PREFIX = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+|>\s*)")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True, slots=True)
class _SourceCandidate:
    path: Path
    boundary: Path
    display_path: str
    kind: NativeSourceKind
    authority: NativeAuthorityClass
    opt_in_basis: str
    precedence: int
    project_id: str | None
    skill: bool = False


@dataclass(frozen=True, slots=True)
class DiscoveredInstructionSource:
    """Internal source bytes paired with its raw-free public manifest."""

    manifest: InstructionSourceManifestV1
    path: Path
    content: str | None
    raw_bytes: bytes | None
    clauses: tuple[NativeInstructionClauseV1, ...]


class InstructionSourceAdapter(ABC):
    """Port for one target's documented native instruction behavior."""

    target: NativeTarget
    surface: str
    surface_contract_version: str

    def discover(
        self,
        *,
        project_id: str,
        project_root: Path,
        working_directory: Path | None = None,
        global_roots: tuple[Path, ...] = (),
    ) -> tuple[DiscoveredInstructionSource, ...]:
        root = project_root.expanduser().resolve(strict=True)
        cwd = (
            root
            if working_directory is None
            else working_directory.expanduser().resolve(strict=True)
        )
        if cwd != root and not cwd.is_relative_to(root):
            raise ValueError("instruction working directory escaped its registered project")
        candidates = self._project_candidates(
            project_id=project_id,
            root=root,
            cwd=cwd,
            global_roots=global_roots,
        )
        candidates.extend(self._managed_candidates())
        for global_root in global_roots:
            boundary = global_root.expanduser().resolve(strict=True)
            candidates.extend(self._global_candidates(boundary))
        ordered = sorted(
            _deduplicate_candidates(candidates),
            key=lambda item: (item.precedence, item.display_path.casefold()),
        )
        results: list[DiscoveredInstructionSource] = []
        total = 0
        native_total = 0
        native_limit = self._native_instruction_limit(global_roots)
        for candidate in ordered:
            discovered = self._read_candidate(
                candidate,
                total_bytes=total,
                native_instruction_bytes=native_total,
                native_instruction_limit=native_limit,
                activation_status=self._activation_status(candidate, global_roots),
            )
            if discovered.raw_bytes == b"" and candidate.kind in {
                NativeSourceKind.PERSONAL_INSTRUCTIONS,
                NativeSourceKind.PROJECT_INSTRUCTIONS,
            }:
                continue
            results.append(discovered)
            total += discovered.manifest.byte_length
            if candidate.kind in {
                NativeSourceKind.PERSONAL_INSTRUCTIONS,
                NativeSourceKind.PROJECT_INSTRUCTIONS,
            }:
                if discovered.manifest.read_status is NativeReadStatus.READY:
                    native_total += discovered.manifest.byte_length
                elif discovered.manifest.read_status is NativeReadStatus.TOO_LARGE:
                    native_total = native_limit or native_total
        return tuple(results)

    def _native_instruction_limit(self, global_roots: tuple[Path, ...]) -> int | None:
        return None

    def _managed_candidates(self) -> list[_SourceCandidate]:
        return []

    def _activation_status(
        self, candidate: _SourceCandidate, global_roots: tuple[Path, ...]
    ) -> NativeActivationStatus:
        if not candidate.skill:
            return NativeActivationStatus.ACTIVE
        return NativeActivationStatus.AVAILABLE

    @abstractmethod
    def _project_candidates(
        self,
        *,
        project_id: str,
        root: Path,
        cwd: Path,
        global_roots: tuple[Path, ...],
    ) -> list[_SourceCandidate]: ...

    @abstractmethod
    def _global_candidates(self, root: Path) -> list[_SourceCandidate]: ...

    def _read_candidate(
        self,
        candidate: _SourceCandidate,
        *,
        total_bytes: int,
        native_instruction_bytes: int,
        native_instruction_limit: int | None,
        activation_status: NativeActivationStatus,
    ) -> DiscoveredInstructionSource:
        source_id = _source_id(
            target=self.target,
            project_id=candidate.project_id,
            kind=candidate.kind,
            display_path=candidate.display_path,
        )
        base: dict[str, object] = {
            "source_id": source_id,
            "target": self.target,
            "surface": self.surface,
            "surface_contract_version": self.surface_contract_version,
            "source_kind": candidate.kind,
            "display_path": candidate.display_path,
            "project_id": candidate.project_id,
            "native_precedence": candidate.precedence,
            "authority_class": candidate.authority,
            "opt_in_basis": candidate.opt_in_basis,
            "symlink": candidate.path.is_symlink(),
            "contains_executable_resources": _skill_has_resources(candidate.path)
            if candidate.skill
            else False,
            "activation_status": activation_status,
        }
        try:
            resolved = candidate.path.resolve(strict=True)
        except OSError:
            return _unreadable_source(
                base, candidate.path, NativeReadStatus.UNREADABLE, resolved_within=False
            )
        boundary = candidate.boundary.resolve(strict=True)
        within = resolved == boundary or resolved.is_relative_to(boundary)
        if not within:
            return _unreadable_source(
                base, candidate.path, NativeReadStatus.OUTSIDE_BOUNDARY, resolved_within=False
            )
        try:
            with resolved.open("rb") as stream:
                before = os.fstat(stream.fileno())
                if (
                    before.st_size > MAX_SOURCE_BYTES
                    or total_bytes + before.st_size > MAX_ENVIRONMENT_BYTES
                    or (
                        native_instruction_limit is not None
                        and candidate.kind
                        in {
                            NativeSourceKind.PERSONAL_INSTRUCTIONS,
                            NativeSourceKind.PROJECT_INSTRUCTIONS,
                        }
                        and native_instruction_bytes + before.st_size > native_instruction_limit
                    )
                ):
                    return _unreadable_source(
                        base,
                        candidate.path,
                        NativeReadStatus.TOO_LARGE,
                        byte_length=max(0, before.st_size),
                        resolved_within=True,
                    )
                payload = stream.read(MAX_SOURCE_BYTES + 1)
                after = os.fstat(stream.fileno())
        except OSError:
            return _unreadable_source(
                base, candidate.path, NativeReadStatus.UNREADABLE, resolved_within=True
            )
        if (
            len(payload) > MAX_SOURCE_BYTES
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or candidate.path.resolve(strict=True) != resolved
        ):
            return _unreadable_source(
                base,
                candidate.path,
                NativeReadStatus.UNREADABLE,
                byte_length=len(payload),
                resolved_within=True,
            )
        encoding: Literal["utf-8", "utf-8-sig"] = (
            "utf-8-sig" if payload.startswith(b"\xef\xbb\xbf") else "utf-8"
        )
        try:
            content = payload.decode(encoding)
        except UnicodeDecodeError:
            return _unreadable_source(
                base,
                candidate.path,
                NativeReadStatus.INVALID_ENCODING,
                byte_length=len(payload),
                resolved_within=True,
            )
        digest = f"sha256:{sha256(payload).hexdigest()}"
        manifest = InstructionSourceManifestV1.model_validate(
            {
                **base,
                "content_digest": digest,
                "byte_length": len(payload),
                "encoding": encoding,
                "newline_style": _newline_style(content),
                "read_status": NativeReadStatus.READY,
                "resolved_within_boundary": True,
            },
            strict=True,
        )
        clauses = _parse_markdown_clauses(
            content,
            manifest=manifest,
            project_id=candidate.project_id,
        )
        return DiscoveredInstructionSource(
            manifest=manifest,
            path=resolved,
            content=content,
            raw_bytes=payload,
            clauses=clauses,
        )


class CodexInstructionSourceAdapter(InstructionSourceAdapter):
    target = NativeTarget.CODEX
    surface = "codex-cli"
    surface_contract_version = "codex-cli-0.153.1"

    def __init__(self, *, cli_version: str = "0.153.1") -> None:
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?", cli_version):
            raise ValueError("invalid Codex instruction contract version")
        self.surface_contract_version = f"codex-cli-{cli_version}"

    def _native_instruction_limit(self, global_roots: tuple[Path, ...]) -> int | None:
        configured = _codex_config_value(global_roots, "project_doc_max_bytes")
        if isinstance(configured, int) and not isinstance(configured, bool) and configured > 0:
            return min(configured, MAX_ENVIRONMENT_BYTES)
        return DEFAULT_CODEX_INSTRUCTION_BYTES

    def _activation_status(
        self, candidate: _SourceCandidate, global_roots: tuple[Path, ...]
    ) -> NativeActivationStatus:
        if not candidate.skill:
            return NativeActivationStatus.ACTIVE
        if not global_roots:
            return NativeActivationStatus.UNKNOWN
        disabled = _codex_disabled_skill_paths(global_roots)
        try:
            resolved = candidate.path.expanduser().resolve(strict=True)
        except OSError:
            return NativeActivationStatus.UNKNOWN
        return (
            NativeActivationStatus.DISABLED
            if resolved in disabled
            else NativeActivationStatus.AVAILABLE
        )

    def _project_candidates(
        self,
        *,
        project_id: str,
        root: Path,
        cwd: Path,
        global_roots: tuple[Path, ...],
    ) -> list[_SourceCandidate]:
        candidates: list[_SourceCandidate] = []
        fallback_names = _codex_project_fallback_filenames(global_roots)
        for depth, directory in enumerate(_path_chain(root, cwd)):
            chosen = _first_codex_instruction(
                directory / "AGENTS.override.md",
                directory / "AGENTS.md",
                *(directory / name for name in fallback_names),
            )
            if chosen is not None:
                candidates.append(
                    _project_candidate(
                        chosen,
                        root=root,
                        project_id=project_id,
                        kind=NativeSourceKind.PROJECT_INSTRUCTIONS,
                        precedence=100 + depth * 10,
                    )
                )
            candidates.extend(
                _skill_candidates(
                    directory / ".agents" / "skills",
                    boundary=root,
                    project_id=project_id,
                    kind=NativeSourceKind.PROJECT_SKILL,
                    authority=NativeAuthorityClass.PROJECT_POLICY,
                    opt_in_basis="registered_project",
                    precedence=105 + depth * 10,
                    display_prefix=directory.relative_to(root).as_posix(),
                )
            )
        return candidates

    def _global_candidates(self, root: Path) -> list[_SourceCandidate]:
        candidates: list[_SourceCandidate] = []
        codex_home = root if root.name == ".codex" else root / ".codex"
        chosen = _first_codex_instruction(
            codex_home / "AGENTS.override.md", codex_home / "AGENTS.md"
        )
        if chosen is not None:
            candidates.append(
                _global_candidate(
                    chosen,
                    root=root,
                    kind=NativeSourceKind.PERSONAL_INSTRUCTIONS,
                    precedence=10,
                )
            )
        if root.name != ".codex":
            candidates.extend(
                _skill_candidates(
                    root / ".agents" / "skills",
                    boundary=root,
                    project_id=None,
                    kind=NativeSourceKind.PERSONAL_SKILL,
                    authority=NativeAuthorityClass.USER_CONFIGURED,
                    opt_in_basis="explicit_global_opt_in",
                    precedence=20,
                    display_prefix="Personal/.agents/skills",
                )
            )
        return candidates


class ClaudeInstructionSourceAdapter(InstructionSourceAdapter):
    target = NativeTarget.CLAUDE
    surface = "claude-code"
    surface_contract_version = "claude-code-docs-2026-08-28"

    def __init__(self, *, managed_instruction_paths: tuple[Path, ...] | None = None) -> None:
        self._managed_instruction_paths = (
            _default_claude_managed_instruction_paths()
            if managed_instruction_paths is None
            else managed_instruction_paths
        )

    def _managed_candidates(self) -> list[_SourceCandidate]:
        candidates: list[_SourceCandidate] = []
        for offset, path in enumerate(self._managed_instruction_paths):
            if not (path.is_file() or path.is_symlink()):
                continue
            candidates.append(
                _SourceCandidate(
                    path=path,
                    boundary=path.parent,
                    display_path="Managed/CLAUDE.md",
                    kind=NativeSourceKind.MANAGED_INSTRUCTIONS,
                    authority=NativeAuthorityClass.MANAGED_POLICY,
                    opt_in_basis="managed",
                    precedence=offset,
                    project_id=None,
                )
            )
        return candidates

    def _project_candidates(
        self,
        *,
        project_id: str,
        root: Path,
        cwd: Path,
        global_roots: tuple[Path, ...],
    ) -> list[_SourceCandidate]:
        del global_roots
        candidates: list[_SourceCandidate] = []
        for depth, directory in enumerate(_path_chain(root, cwd)):
            for offset, path in enumerate((directory / "CLAUDE.md", directory / "CLAUDE.local.md")):
                if path.is_file() or path.is_symlink():
                    candidates.append(
                        _project_candidate(
                            path,
                            root=root,
                            project_id=project_id,
                            kind=NativeSourceKind.PROJECT_INSTRUCTIONS,
                            precedence=100 + depth * 10 + offset,
                        )
                    )
        project_dot_claude = root / ".claude" / "CLAUDE.md"
        if project_dot_claude.is_file() or project_dot_claude.is_symlink():
            candidates.append(
                _project_candidate(
                    project_dot_claude,
                    root=root,
                    project_id=project_id,
                    kind=NativeSourceKind.PROJECT_INSTRUCTIONS,
                    precedence=102,
                )
            )
        candidates.extend(
            _bounded_pattern_candidates(
                root / ".claude" / "rules",
                "*.md",
                boundary=root,
                project_id=project_id,
                kind=NativeSourceKind.PROJECT_RULE,
                precedence=120,
            )
        )
        candidates.extend(
            _skill_candidates(
                root / ".claude" / "skills",
                boundary=root,
                project_id=project_id,
                kind=NativeSourceKind.PROJECT_SKILL,
                authority=NativeAuthorityClass.PROJECT_POLICY,
                opt_in_basis="registered_project",
                precedence=130,
                display_prefix=".claude/skills",
            )
        )
        return candidates

    def _global_candidates(self, root: Path) -> list[_SourceCandidate]:
        candidates: list[_SourceCandidate] = []
        claude_home = root if root.name == ".claude" else root / ".claude"
        for path, kind, authority, precedence in (
            (
                claude_home / "CLAUDE.md",
                NativeSourceKind.PERSONAL_INSTRUCTIONS,
                NativeAuthorityClass.USER_CONFIGURED,
                10,
            ),
            (
                root / "MEMORY.md",
                NativeSourceKind.PERSONAL_MEMORY,
                NativeAuthorityClass.AGENT_GENERATED,
                5,
            ),
        ):
            if path.is_file() or path.is_symlink():
                candidates.append(
                    _global_candidate(
                        path,
                        root=root,
                        kind=kind,
                        precedence=precedence,
                        authority=authority,
                    )
                )
        candidates.extend(
            _bounded_global_pattern_candidates(
                claude_home / "rules",
                "*.md",
                boundary=root,
                kind=NativeSourceKind.PERSONAL_INSTRUCTIONS,
                precedence=11,
            )
        )
        candidates.extend(
            _skill_candidates(
                claude_home / "skills",
                boundary=root,
                project_id=None,
                kind=NativeSourceKind.PERSONAL_SKILL,
                authority=NativeAuthorityClass.USER_CONFIGURED,
                opt_in_basis="explicit_global_opt_in",
                precedence=20,
                display_prefix="Personal/.claude/skills",
            )
        )
        return candidates


class CopilotInstructionSourceAdapter(InstructionSourceAdapter):
    target = NativeTarget.COPILOT
    surface = "github-copilot-coding-agent"
    surface_contract_version = "github-copilot-docs-2026-08-28"

    def _project_candidates(
        self,
        *,
        project_id: str,
        root: Path,
        cwd: Path,
        global_roots: tuple[Path, ...],
    ) -> list[_SourceCandidate]:
        del cwd, global_roots
        candidates: list[_SourceCandidate] = []
        direct = (
            (root / ".github" / "copilot-instructions.md", 100),
            (root / "AGENTS.md", 110),
            (root / "CLAUDE.md", 111),
            (root / "GEMINI.md", 112),
        )
        for path, precedence in direct:
            if path.is_file() or path.is_symlink():
                candidates.append(
                    _project_candidate(
                        path,
                        root=root,
                        project_id=project_id,
                        kind=NativeSourceKind.PROJECT_INSTRUCTIONS,
                        precedence=precedence,
                    )
                )
        candidates.extend(
            _bounded_pattern_candidates(
                root / ".github" / "instructions",
                "*.instructions.md",
                boundary=root,
                project_id=project_id,
                kind=NativeSourceKind.PROJECT_RULE,
                precedence=120,
            )
        )
        for skills_root, precedence in (
            (root / ".github" / "skills", 130),
            (root / ".agents" / "skills", 131),
            (root / ".claude" / "skills", 132),
        ):
            candidates.extend(
                _skill_candidates(
                    skills_root,
                    boundary=root,
                    project_id=project_id,
                    kind=NativeSourceKind.PROJECT_SKILL,
                    authority=NativeAuthorityClass.PROJECT_POLICY,
                    opt_in_basis="registered_project",
                    precedence=precedence,
                    display_prefix=skills_root.relative_to(root).as_posix(),
                )
            )
        return candidates

    def _global_candidates(self, root: Path) -> list[_SourceCandidate]:
        candidates: list[_SourceCandidate] = []
        copilot_home = root if root.name == ".copilot" else root / ".copilot"
        path = copilot_home / "copilot-instructions.md"
        if path.is_file() or path.is_symlink():
            candidates.append(
                _global_candidate(
                    path,
                    root=root,
                    kind=NativeSourceKind.PERSONAL_INSTRUCTIONS,
                    precedence=10,
                )
            )
        candidates.extend(
            _bounded_global_pattern_candidates(
                copilot_home / "instructions",
                "*.instructions.md",
                boundary=root,
                kind=NativeSourceKind.PERSONAL_INSTRUCTIONS,
                precedence=11,
            )
        )
        for relative, precedence in (
            (Path(".copilot/skills"), 20),
            (Path(".agents/skills"), 21),
        ):
            candidates.extend(
                _skill_candidates(
                    root / relative,
                    boundary=root,
                    project_id=None,
                    kind=NativeSourceKind.PERSONAL_SKILL,
                    authority=NativeAuthorityClass.USER_CONFIGURED,
                    opt_in_basis="explicit_global_opt_in",
                    precedence=precedence,
                    display_prefix=f"Personal/{relative.as_posix()}",
                )
            )
        return candidates


def _path_chain(root: Path, cwd: Path) -> tuple[Path, ...]:
    relative = cwd.relative_to(root)
    chain = [root]
    current = root
    for part in relative.parts:
        if part in _EXCLUDED_COMPONENTS:
            break
        current = current / part
        chain.append(current)
    return tuple(chain)


def _first_existing(*paths: Path) -> Path | None:
    return next((path for path in paths if path.is_file() or path.is_symlink()), None)


def _first_codex_instruction(*paths: Path) -> Path | None:
    """Return Codex's first present, non-empty instruction file.

    A present source that cannot be safely inspected is retained so the normal
    discovery path reports it as unreadable and fails closed. Empty UTF-8 files
    are skipped exactly as Codex skips them.
    """

    for path in paths:
        if not (path.is_file() or path.is_symlink()):
            continue
        try:
            payload = path.read_bytes()
            text = payload.decode("utf-8-sig")
        except (OSError, UnicodeError):
            return path
        if text.strip():
            return path
    return None


def _project_candidate(
    path: Path,
    *,
    root: Path,
    project_id: str,
    kind: NativeSourceKind,
    precedence: int,
) -> _SourceCandidate:
    return _SourceCandidate(
        path=path,
        boundary=root,
        display_path=path.relative_to(root).as_posix(),
        kind=kind,
        authority=NativeAuthorityClass.PROJECT_POLICY,
        opt_in_basis="registered_project",
        precedence=precedence,
        project_id=project_id,
        skill=kind is NativeSourceKind.PROJECT_SKILL,
    )


def _global_candidate(
    path: Path,
    *,
    root: Path,
    kind: NativeSourceKind,
    precedence: int,
    authority: NativeAuthorityClass = NativeAuthorityClass.USER_CONFIGURED,
) -> _SourceCandidate:
    return _SourceCandidate(
        path=path,
        boundary=root,
        display_path=f"Personal/{path.relative_to(root).as_posix()}",
        kind=kind,
        authority=authority,
        opt_in_basis="explicit_global_opt_in",
        precedence=precedence,
        project_id=None,
        skill=kind is NativeSourceKind.PERSONAL_SKILL,
    )


def _bounded_pattern_candidates(
    root: Path,
    pattern: str,
    *,
    boundary: Path,
    project_id: str,
    kind: NativeSourceKind,
    precedence: int,
) -> list[_SourceCandidate]:
    if not root.is_dir():
        return []
    candidates: list[_SourceCandidate] = []
    for path in sorted(root.rglob(pattern), key=lambda item: item.as_posix().casefold()):
        try:
            relative = path.relative_to(boundary)
        except ValueError:
            continue
        if any(part in _EXCLUDED_COMPONENTS for part in relative.parts):
            continue
        candidates.append(
            _project_candidate(
                path,
                root=boundary,
                project_id=project_id,
                kind=kind,
                precedence=precedence + len(candidates),
            )
        )
    return candidates


def _bounded_global_pattern_candidates(
    root: Path,
    pattern: str,
    *,
    boundary: Path,
    kind: NativeSourceKind,
    precedence: int,
) -> list[_SourceCandidate]:
    if not root.is_dir():
        return []
    candidates: list[_SourceCandidate] = []
    for path in sorted(root.rglob(pattern), key=lambda item: item.as_posix().casefold()):
        try:
            relative = path.relative_to(boundary)
        except ValueError:
            continue
        if any(part in _EXCLUDED_COMPONENTS for part in relative.parts):
            continue
        candidates.append(
            _global_candidate(
                path,
                root=boundary,
                kind=kind,
                precedence=precedence + len(candidates),
            )
        )
    return candidates


def _skill_candidates(
    root: Path,
    *,
    boundary: Path,
    project_id: str | None,
    kind: NativeSourceKind,
    authority: NativeAuthorityClass,
    opt_in_basis: str,
    precedence: int,
    display_prefix: str,
) -> list[_SourceCandidate]:
    if not root.is_dir():
        return []
    candidates: list[_SourceCandidate] = []
    try:
        directories = sorted(
            (item for item in root.iterdir() if item.is_dir()),
            key=lambda item: item.name.casefold(),
        )
    except OSError:
        return []
    for directory in directories:
        if directory.name in _EXCLUDED_COMPONENTS:
            continue
        skill = directory / "SKILL.md"
        if not (skill.is_file() or skill.is_symlink()):
            continue
        prefix = display_prefix.strip("/")
        display = f"{prefix}/{directory.name}/SKILL.md" if prefix else f"{directory.name}/SKILL.md"
        candidates.append(
            _SourceCandidate(
                path=skill,
                boundary=boundary,
                display_path=display,
                kind=kind,
                authority=authority,
                opt_in_basis=opt_in_basis,
                precedence=precedence + len(candidates),
                project_id=project_id,
                skill=True,
            )
        )
    return candidates


def _deduplicate_candidates(candidates: list[_SourceCandidate]) -> list[_SourceCandidate]:
    selected: dict[tuple[str, NativeSourceKind], _SourceCandidate] = {}
    for candidate in candidates:
        key = (str(candidate.path.absolute()).casefold(), candidate.kind)
        current = selected.get(key)
        if current is None or candidate.precedence > current.precedence:
            selected[key] = candidate
    return list(selected.values())


def _unreadable_source(
    base: Mapping[str, object],
    path: Path,
    status: NativeReadStatus,
    *,
    byte_length: int = 0,
    resolved_within: bool,
) -> DiscoveredInstructionSource:
    manifest = InstructionSourceManifestV1.model_validate(
        {
            **base,
            "content_digest": None,
            "byte_length": byte_length,
            "encoding": "unknown",
            "newline_style": "unknown",
            "read_status": status,
            "resolved_within_boundary": resolved_within,
        },
        strict=True,
    )
    return DiscoveredInstructionSource(
        manifest=manifest,
        path=path,
        content=None,
        raw_bytes=None,
        clauses=(),
    )


def _source_id(
    *,
    target: NativeTarget,
    project_id: str | None,
    kind: NativeSourceKind,
    display_path: str,
) -> str:
    raw = f"{target.value}\0{project_id or 'global'}\0{kind.value}\0{display_path}".encode()
    return f"native-{target.value}-{sha256(raw).hexdigest()[:24]}"


def _newline_style(text: str) -> Literal["lf", "crlf", "mixed", "none"]:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    if crlf and lf:
        return "mixed"
    if crlf:
        return "crlf"
    if lf:
        return "lf"
    return "none"


def _skill_has_resources(skill_path: Path) -> bool:
    try:
        return any(item.name != "SKILL.md" for item in skill_path.parent.iterdir())
    except OSError:
        return False


def _parse_markdown_clauses(
    content: str,
    *,
    manifest: InstructionSourceManifestV1,
    project_id: str | None,
) -> tuple[NativeInstructionClauseV1, ...]:
    """Extract prose blocks without interpreting or executing Markdown."""

    body = _strip_frontmatter(content)
    blocks: list[str] = []
    current: list[str] = []
    fenced = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if _FENCE.match(line):
            fenced = not fenced
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        if fenced:
            continue
        if not line:
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        normalized = _MARKDOWN_PREFIX.sub("", line).strip()
        if not normalized or normalized.startswith("<!--"):
            continue
        if _MARKDOWN_PREFIX.match(line) and current:
            blocks.append(" ".join(current))
            current = []
        current.append(normalized)
    if current:
        blocks.append(" ".join(current))
    clauses: list[NativeInstructionClauseV1] = []
    seen: set[str] = set()
    scope_labels = tuple(
        sorted(
            {
                *(() if project_id is None else (f"project:{project_id}",)),
                *_frontmatter_scope_labels(content),
            }
        )
    )
    assert manifest.content_digest is not None
    for index, block in enumerate(blocks):
        text = " ".join(block.split())
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        text_digest = canonical_digest({"text": text})
        clauses.append(
            NativeInstructionClauseV1(
                clause_id=f"{manifest.source_id}-clause-{index + 1}",
                text=text,
                text_digest=text_digest,
                source_id=manifest.source_id,
                source_digest=manifest.content_digest,
                target=manifest.target,
                kind=NativeInstructionKind.UNKNOWN,
                norm_strength=NativeNormStrength.NONE,
                scope_labels=scope_labels,
            )
        )
    return tuple(clauses)


def _strip_frontmatter(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[index + 1 :])
    return text


def _frontmatter_scope_labels(text: str) -> tuple[str, ...]:
    """Extract only documented path selectors; never interpret arbitrary YAML."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ()
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return ()
    values: set[str] = set()
    reading_paths = False
    for raw in lines[1:end]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("paths:"):
            reading_paths = True
            inline = stripped.removeprefix("paths:").strip()
            values.update(_frontmatter_inline_values(inline))
            continue
        if stripped.startswith("applyTo:"):
            reading_paths = False
            inline = stripped.removeprefix("applyTo:").strip().strip("\"'")
            if inline:
                values.update(item.strip() for item in inline.split(",") if item.strip())
            continue
        if reading_paths and stripped.startswith("-"):
            value = stripped.removeprefix("-").strip().strip("\"'")
            if value:
                values.add(value)
            continue
        if not raw.startswith((" ", "\t")):
            reading_paths = False
    return tuple(sorted(f"path:{value}" for value in values))


def _frontmatter_inline_values(value: str) -> set[str]:
    if not value:
        return set()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return {item.strip().strip("\"'") for item in value.split(",") if item.strip().strip("\"'")}


def _codex_disabled_skill_paths(global_roots: tuple[Path, ...]) -> set[Path]:
    """Read only opted-in Codex config files and return explicit disabled skill paths."""

    disabled: set[Path] = set()
    for opted_root in global_roots:
        root = opted_root.expanduser().resolve(strict=True)
        candidates = _codex_config_candidates(root)
        for config, home in candidates:
            if not config.is_file():
                continue
            try:
                payload = config.read_bytes()
                if len(payload) > MAX_SOURCE_BYTES:
                    continue
                parsed = tomllib.loads(payload.decode("utf-8"))
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                continue
            skills = parsed.get("skills")
            if not isinstance(skills, dict):
                continue
            entries = skills.get("config")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("enabled") is not False:
                    continue
                raw_path = entry.get("path")
                if not isinstance(raw_path, str) or not raw_path.strip():
                    continue
                expanded = raw_path.strip()
                if expanded == "~":
                    path = home
                elif expanded.startswith(("~/", "~\\")):
                    path = home / expanded[2:]
                else:
                    path = Path(expanded)
                    if not path.is_absolute():
                        path = config.parent / path
                try:
                    disabled.add(path.resolve(strict=True))
                except OSError:
                    continue
    return disabled


def _codex_config_value(global_roots: tuple[Path, ...], key: str) -> object | None:
    for opted_root in global_roots:
        root = opted_root.expanduser().resolve(strict=True)
        for config, _home in _codex_config_candidates(root):
            if not config.is_file():
                continue
            try:
                payload = config.read_bytes()
                if len(payload) > MAX_SOURCE_BYTES:
                    continue
                parsed = tomllib.loads(payload.decode("utf-8"))
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                continue
            if key in parsed:
                value: object = parsed[key]
                return value
    return None


def _codex_project_fallback_filenames(global_roots: tuple[Path, ...]) -> tuple[str, ...]:
    configured = _codex_config_value(global_roots, "project_doc_fallback_filenames")
    if not isinstance(configured, list):
        return ()
    names: list[str] = []
    for value in configured[:16]:
        if not isinstance(value, str):
            continue
        name = value.strip()
        if (
            not name
            or name in {".", "..", "AGENTS.md", "AGENTS.override.md"}
            or Path(name).name != name
        ):
            continue
        names.append(name)
    return tuple(dict.fromkeys(names))


def _codex_config_candidates(root: Path) -> tuple[tuple[Path, Path], ...]:
    if root.name == ".codex":
        return ((root / "config.toml", root.parent),)
    return ((root / ".codex" / "config.toml", root),)


def _default_claude_managed_instruction_paths() -> tuple[Path, ...]:
    host = platform.system()
    if host == "Windows":
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        return (Path(program_files) / "ClaudeCode" / "CLAUDE.md",)
    if host == "Darwin":
        return (Path("/Library/Application Support/ClaudeCode/CLAUDE.md"),)
    return (Path("/etc/claude-code/CLAUDE.md"),)
