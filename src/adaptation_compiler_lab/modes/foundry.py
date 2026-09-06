"""Quarantined intake and signature verification for the Temper Mode Foundry."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from adaptation_compiler_lab.governance.signing import (
    GovernanceSigner,
    verify_detached_envelope,
)
from adaptation_compiler_lab.modes.foundry_models import (
    CapabilityResourceKind,
    CapabilityResourceV1,
    CuratedCatalogManifestV1,
    CuratedSourceManifestV1,
    SignedCuratedCatalogV1,
    SourceCapabilityRequirementV1,
)

MAX_SOURCE_BYTES = 256 * 1024
MAX_ENVIRONMENT_BYTES = 2 * 1024 * 1024
_EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".exe",
    ".js",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
}
_IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}
_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("encoded-content", re.compile(r"base64\s+(-d|--decode)|frombase64string", re.I)),
    (
        "credential-access",
        re.compile(r"\.ssh|keychain|credential|api[_ -]?key|browser profile", re.I),
    ),
    ("external-egress", re.compile(r"\bcurl\b|\bwget\b|upload|webhook|telemetry", re.I)),
    ("persistence", re.compile(r"launchd|scheduled task|crontab|startup folder", re.I)),
    ("privilege", re.compile(r"\bsudo\b|runas|administrator privileges", re.I)),
)


class FoundryIntakeError(ValueError):
    """Raised when a source cannot enter the review pipeline safely."""


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def canonical_github_repository(value: str) -> str:
    normalized = value.removesuffix(".git")
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", normalized):
        raise FoundryIntakeError("Foundry sources must use a canonical HTTPS GitHub URL")
    return normalized


@contextmanager
def clone_pinned_source(repository_url: str, commit_sha: str) -> Iterator[Path]:
    """Clone one immutable commit without hooks, submodules, or repository execution."""

    repository = canonical_github_repository(repository_url)
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise FoundryIntakeError("Foundry requires a full lowercase Git commit SHA")
    git = shutil.which("git")
    if git is None:
        raise FoundryIntakeError("git is unavailable for quarantined source retrieval")
    with tempfile.TemporaryDirectory(prefix="temper-foundry-") as temporary:
        root = Path(temporary).resolve()
        environment = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "NUL" if os.name == "nt" else "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": os.environ.get("PATH", ""),
        }
        for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE"):
            if value := os.environ.get(name):
                environment[name] = value
        commands = (
            (
                git,
                "-c",
                "core.hooksPath=NUL" if os.name == "nt" else "core.hooksPath=/dev/null",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--no-recurse-submodules",
                repository,
                str(root / "source"),
            ),
            (git, "-C", str(root / "source"), "checkout", "--detach", commit_sha),
        )
        for command in commands:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                env=environment,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise FoundryIntakeError("the pinned source could not be retrieved safely")
        resolved = subprocess.run(
            (git, "-C", str(root / "source"), "rev-parse", "HEAD"),
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=10,
        )
        if resolved.returncode != 0 or resolved.stdout.strip() != commit_sha:
            raise FoundryIntakeError("the retrieved checkout does not match the pinned commit")
        yield root / "source"


def inspect_pinned_skill(
    checkout: Path,
    *,
    source_id: str,
    publisher: str,
    repository_url: str,
    commit_sha: str,
    source_path: str,
    source_format: Literal["agent-skill", "codex-plugin-skill", "claude-skill"],
    license_spdx: str,
    license_locator: str,
    license_bytes: bytes,
    redistribution_permitted: bool,
    retrieved_at: datetime,
) -> tuple[CuratedSourceManifestV1, tuple[str, ...]]:
    """Inventory one exact skill without executing or returning its content."""

    root = checkout.resolve()
    if not root.is_dir():
        raise FoundryIntakeError("the source checkout is unavailable")
    normalized_source = source_path.replace("\\", "/").strip("/")
    skill_file = (root / normalized_source).resolve()
    if not skill_file.is_relative_to(root) or skill_file.name != "SKILL.md":
        raise FoundryIntakeError("the selected skill must remain inside its checkout")
    skill_root = skill_file.parent
    if skill_file.is_symlink() or not skill_file.is_file():
        raise FoundryIntakeError("the selected SKILL.md must be a regular file")

    resources: list[CapabilityResourceV1] = []
    findings: set[str] = set()
    total_bytes = 0
    for path in sorted(skill_root.rglob("*")):
        if any(part in _IGNORED_DIRECTORY_NAMES for part in path.relative_to(skill_root).parts):
            continue
        if path.is_symlink():
            findings.add("symlink-excluded")
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(skill_root).as_posix()
        payload = path.read_bytes()
        total_bytes += len(payload)
        if len(payload) > MAX_SOURCE_BYTES:
            raise FoundryIntakeError("one skill resource exceeds the 256 KiB source limit")
        if total_bytes > MAX_ENVIRONMENT_BYTES:
            raise FoundryIntakeError("the skill exceeds the 2 MiB environment limit")
        kind = _resource_kind(relative, path.suffix.casefold())
        admitted = kind in {
            CapabilityResourceKind.INSTRUCTION,
            CapabilityResourceKind.REFERENCE,
            CapabilityResourceKind.EXAMPLE,
            CapabilityResourceKind.STATIC_ASSET,
        }
        if not admitted:
            findings.add(f"excluded-{kind.value}")
        if kind is not CapabilityResourceKind.STATIC_ASSET:
            try:
                decoded = payload.decode("utf-8")
            except UnicodeDecodeError as error:
                raise FoundryIntakeError(
                    "declarative skill resources must be valid UTF-8"
                ) from error
            if admitted:
                findings.update(
                    label for label, pattern in _RISK_PATTERNS if pattern.search(decoded)
                )
        resources.append(
            CapabilityResourceV1(
                resource_id=_resource_id(source_id, relative),
                source_id=source_id,
                relative_path=relative,
                kind=kind,
                digest=sha256_bytes(payload),
                utf8_bytes=len(payload),
                admitted=admitted,
                admission_reason=(
                    "Declarative material is eligible for review."
                    if admitted
                    else "Executable and capability-changing material is quarantined."
                ),
            )
        )
    if not any(item.relative_path == "SKILL.md" for item in resources):
        raise FoundryIntakeError("the skill inventory does not contain its required SKILL.md")
    skill_bytes = skill_file.read_bytes()
    manifest = CuratedSourceManifestV1(
        source_id=source_id,
        publisher=publisher,
        repository_url=canonical_github_repository(repository_url),
        commit_sha=commit_sha,
        source_path=normalized_source,
        source_format=source_format,
        source_digest=sha256_bytes(skill_bytes),
        license_spdx=license_spdx,
        license_locator=license_locator,
        license_digest=sha256_bytes(license_bytes),
        redistribution_permitted=redistribution_permitted,
        retrieved_at=retrieved_at,
        resources=tuple(sorted(resources, key=lambda item: item.resource_id)),
        requirements=_infer_requirements(resources, findings),
    )
    return manifest, tuple(sorted(findings))


def sign_catalog(
    catalog: CuratedCatalogManifestV1, *, signer: GovernanceSigner
) -> SignedCuratedCatalogV1:
    envelope = signer.envelope(
        catalog.model_dump(mode="json"),
        purpose="curated_mode_catalog",
        signed_at=catalog.generated_at,
    )
    public_key = signer.private_key.public_key().public_bytes_raw()
    return SignedCuratedCatalogV1(
        catalog=catalog,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
        signature=envelope,
    )


def verify_catalog(value: SignedCuratedCatalogV1) -> None:
    try:
        public_key = base64.b64decode(value.public_key_base64, validate=True)
    except (ValueError, TypeError) as error:
        raise FoundryIntakeError("the catalog verification key is invalid") from error
    if len(public_key) != 32:
        raise FoundryIntakeError("the catalog verification key has an invalid length")
    verify_detached_envelope(
        value.catalog.model_dump(mode="json"),
        value.signature,
        public_key_base64=value.public_key_base64,
        expected_purpose="curated_mode_catalog",
    )


def _resource_kind(relative: str, suffix: str) -> CapabilityResourceKind:
    parts = relative.split("/")
    if relative == "SKILL.md":
        return CapabilityResourceKind.INSTRUCTION
    if parts[0] == "scripts" or suffix in _EXECUTABLE_SUFFIXES:
        return CapabilityResourceKind.SCRIPT
    if parts[0] == "references":
        return CapabilityResourceKind.REFERENCE
    if parts[0] == "assets":
        return CapabilityResourceKind.STATIC_ASSET
    if "example" in relative.casefold() or "test" in relative.casefold():
        return CapabilityResourceKind.EXAMPLE
    return CapabilityResourceKind.REFERENCE


def _resource_id(source_id: str, relative: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", relative.casefold()).strip("-")
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:10]
    return f"{source_id}-{slug[:32]}-{digest}"


def _infer_requirements(
    resources: list[CapabilityResourceV1], findings: set[str]
) -> tuple[SourceCapabilityRequirementV1, ...]:
    requirements: list[SourceCapabilityRequirementV1] = []
    if any(not item.admitted for item in resources):
        requirements.append(
            SourceCapabilityRequirementV1(
                requirement_id="upstream-executable-resources",
                kind="system_tool",
                name="Upstream executable resources",
                required=False,
                portable=False,
                rationale="Temper quarantines these resources and grants no execution authority.",
            )
        )
    if "external-egress" in findings:
        requirements.append(
            SourceCapabilityRequirementV1(
                requirement_id="upstream-network-reference",
                kind="network",
                name="Upstream network references",
                required=False,
                portable=False,
                rationale="Network references are inventoried but omitted from the offline Mode.",
            )
        )
    return tuple(sorted(requirements, key=lambda item: item.requirement_id))
